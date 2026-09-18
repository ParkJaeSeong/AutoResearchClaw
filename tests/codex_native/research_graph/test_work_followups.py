from copy import deepcopy

import pytest

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.views import build_view
from tests.codex_native.research_graph.test_work_episodes import apply, conclude_payload, init, start_payload


def concluded(root, outcome='finished'):
    init(root)
    apply(root, 'episode.start', start_payload('basis', review_required=True), 'start')
    return apply(root, 'episode.conclude', conclude_payload('basis', execution_status=outcome), 'finish')


@pytest.mark.parametrize('decision,outcome,kind,title,purpose,dependencies,return_to,reason,status', [
    ('continue', 'finished', 'followup', '결과를 사용한다', '공개 보고가 준비됐다', ['basis'], None, None, 'planned'),
    ('continue', 'failed', 'followup', '결과를 사용한다', '공개 보고가 준비됐다', ['basis'], None, None, 'blocked'),
    ('revise', 'finished', 'revision', '재검토: 회차 basis', '다시 <확인>\n해주세요', [], 'basis', '다시 <확인>\n해주세요', 'planned'),
    ('revise', 'failed', 'revision', '재검토: 회차 basis', '다시 <확인>\n해주세요', [], 'basis', '다시 <확인>\n해주세요', 'planned'),
])
def test_review_atomically_plans_without_starting_work(tmp_path, decision, outcome, kind, title, purpose, dependencies, return_to, reason, status):
    before = concluded(tmp_path, outcome)
    payload = dict(id='basis', decision=decision, reviewer='local', feedback='다시 <확인>\n해주세요')
    args = dict(operation='episode.review', payload=payload, expected_head=before['id'], command_id='review')
    receipt = commands.apply_command(tmp_path, **args)
    view = build_view(tmp_path)
    assert len(view['work_followups']) == 1
    plan = view['work_followups'][0]
    assert {key: plan[key] for key in ('kind', 'title', 'purpose', 'depends_on', 'return_to', 'return_reason', 'status')} == dict(
        kind=kind, title=title, purpose=purpose, depends_on=dependencies, return_to=return_to, return_reason=reason, status=status)
    assert set(plan) == {'id', 'source_episode_id', 'source_conclusion_sha256', 'source_review_sha256', 'kind', 'title', 'purpose', 'depends_on', 'return_to', 'return_reason', 'status'}
    assert plan['source_episode_id'] == 'basis'
    assert receipt['state']['work_followups'] == {plan['id']: plan}
    assert view['heads'][-1]['parent_head_id'] == before['id']
    assert len(receipt['events']) == len(before['events']) + 1
    assert view['work_episodes'][0]['conclusion'] == before['state']['work_episodes']['basis']['conclusion']
    assert len(view['work_episodes']) == 1
    assert view['approvals'] == []
    assert commands.apply_command(tmp_path, **args) == receipt
    assert store.read_head(tmp_path)['id'] == receipt['id']
    assert build_view(tmp_path, head_id=before['id'])['work_followups'] == []
    apply(tmp_path, 'episode.start', start_payload('independent'), 'independent')
    assert [row['sequence'] for row in build_view(tmp_path)['work_episodes']] == [1, 2]


def raw_commit(root, state, name):
    return store.commit_record(root, expected_head=store.read_head(root)['id'], command_id=name,
        state=state, event={**store._VERSION, 'type': 'fixture', 'payload': {}}, objects={})


def test_old_reviews_are_not_backfilled(tmp_path):
    before = concluded(tmp_path)
    state = deepcopy(before['state'])
    episode = state['work_episodes']['basis']
    episode.update(review=dict(decision='continue', reviewer='old', feedback='past'), review_status='continued')
    old = raw_commit(tmp_path, state, 'legacy-review')
    assert build_view(tmp_path)['work_followups'] == []
    apply(tmp_path, 'episode.start', start_payload('new', review_required=True), 'new')
    apply(tmp_path, 'episode.conclude', conclude_payload('new'), 'new-finish')
    apply(tmp_path, 'episode.review', dict(id='new', decision='continue', reviewer='local', feedback='next'), 'new-review')
    assert [plan['source_episode_id'] for plan in build_view(tmp_path)['work_followups']] == ['new']
    assert build_view(tmp_path, head_id=old['id'])['work_followups'] == []


@pytest.mark.parametrize('field,value', [
    ('source_episode_id', 'missing'), ('source_conclusion_sha256', '0' * 64),
    ('source_review_sha256', '0' * 64), ('id', 'forged'), ('title', 'forged'),
    ('purpose', 'forged'), ('depends_on', []), ('return_to', 'basis'),
    ('return_reason', 'forged'), ('kind', 'revision'), ('status', 'blocked'), ('extra', 'private'),
])
def test_view_rejects_tampered_binding_or_derived_fields(tmp_path, field, value):
    concluded(tmp_path)
    reviewed = apply(tmp_path, 'episode.review', dict(id='basis', decision='continue', reviewer='local', feedback='next'), 'review')
    state = deepcopy(reviewed['state'])
    assert state.get('work_followups'), 'review must persist its followup'
    next(iter(state['work_followups'].values()))[field] = value
    raw_commit(tmp_path, state, 'tampered')
    with pytest.raises(ValueError, match='followup_state_invalid'):
        build_view(tmp_path)
