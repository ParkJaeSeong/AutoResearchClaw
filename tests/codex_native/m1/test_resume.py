"""Resume reports returned research context and committed crash boundaries."""
from copy import deepcopy
import json

import pytest

from researchclaw.core.m1 import store
from researchclaw.core.m1.project import resume_project
from researchclaw.core.m1.packets import prepare_node, register_outputs
from researchclaw.core.m1.council import prepare_council
from tests.codex_native.m1.helpers import checkpoint, encoded, submission
from tests.codex_native.m1.test_assignments import assignments
from tests.codex_native.m1.test_budgets import case, return_base, plan, apply, budget_api, change_state


def test_resume_explains_decided_return_and_exhausted_budget(case):
    budget_api().set_return_budget(case, limit=0, note='Explicit user stop', command_id='stop')
    value = resume_project(case)
    assert value['action'] == 'await_user'
    assert value['budget']['exhausted'] is True
    assert 'm1_return_budget_exhausted' in value['wait_reasons']
    assert value['decision']['id'] == 'synthetic-decision'
    assert value['decision']['proposed_work']
    assert value['unresolved_issues'][0]['issue']['id'] == 'synthetic-issue-H1'


def test_public_return_r2_registration_and_new_independent_review_preserve_r1(case):
    before = store.read_head(case)
    object_bytes = {digest: store._read_file(store._store_path(case) / 'objects' / digest) for digest in before['objects']}
    result = apply(case, plan(case))
    resumed = resume_project(case)
    assert resumed['action'] == 'write_outputs'
    assert resumed['return_context']['reason_code'] == 'hypothesis_revision'
    assert resumed['return_context']['proposed_work']
    assert resumed['unresolved_issues'][0]['issue']['id'] == 'synthetic-issue-H1'
    packet = prepare_node(case, 'hypothesize', command_id='r2-prepare')['packet']
    path = 'hypotheses/hypotheses.json'
    old_ref = next(r for r in before['state']['artifacts'] if r['logical_path'] == path)
    old = json.loads(object_bytes[old_ref['sha256']])['hypotheses'][0]
    new = {**deepcopy(old), 'revision': 2, 'parent_revision': 1,
           'change_reason': 'Synthetic critique requires an observable comparison, not a mechanism claim.',
           'statement': 'Synthetic revised descriptive comparison under a shared context.'}
    manifest = submission(case, packet, {path: encoded({'schema_version': 1, 'hypotheses': [old, new]}),
        'hypotheses/hypotheses.md': b'Synthetic r2 narrows the earlier mechanism claim.'})
    registered = register_outputs(case, packet_id=packet['id'], submission=manifest, command_id='r2-register')
    assert registered['status'] == 'review_pending', registered
    assert resume_project(case)['action'] == 'await_review'
    session = prepare_council(case, attempt_id=result['attempt']['id'], assignments=assignments(), command_id='r2-review')['session']
    assert session['hypothesis_refs'] == [{'id': 'H1', 'revision': 2}]
    resumed = resume_project(case)
    assert resumed['action'] == 'collect_initials'
    assert len(resumed['pending_assignment_ids']) == 3
    assert resumed['return_context']['to_attempt_id'] == result['attempt']['id']
    assert resumed['budget']['returns_used'] == 1
    after = store.read_head(case)
    assert after['state']['attempts'][:len(before['state']['attempts'])] == before['state']['attempts']
    assert after['state']['approvals'] == before['state']['approvals']
    for digest, data in object_bytes.items():
        assert store._read_file(store._store_path(case) / 'objects' / digest) == data


@pytest.mark.parametrize('after_publish', [False, True])
def test_crash_at_head_publication_has_atomic_resume_and_idempotent_retry(case, monkeypatch, after_publish):
    value = plan(case)
    before = store.read_head(case)
    original = store._atomic_head
    def fail(base, commit_id):
        if after_publish:
            original(base, commit_id)
        raise OSError('injected HEAD boundary')
    with monkeypatch.context() as context:
        context.setattr(store, '_atomic_head', fail)
        with pytest.raises(OSError, match='injected HEAD'):
            apply(case, value)
    visible = resume_project(case)
    assert visible['budget']['returns_used'] == (1 if after_publish else 0)
    assert visible['current_node_id'] == ('hypothesize' if after_publish else 'review')
    result = apply(case, value)
    head = store.read_head(case)
    assert head['state']['returns_used'] == 1
    assert len(head['state']['attempts']) == len(before['state']['attempts']) + 1
    assert apply(case, value) == result
    assert store.read_head(case) == head


def test_resume_keeps_approval_wait_visible(case):
    from researchclaw.core.m1.approvals import current_corpus, record_corpus_approval
    record_corpus_approval(case, corpus_binding=current_corpus(case)['corpus_binding'], decision='reject',
        note='Explicit user rejection', command_id='reject')
    checkpoint(case, node='extract')
    resumed = resume_project(case)
    assert resumed['action'] == 'await_approval'
    assert resumed['wait_reasons']
    assert resumed['budget']['returns_used'] == 0


def test_resume_keeps_role_failure_visible(case):
    def failed(state):
        session = next(iter(state['sessions'].values()))
        session['status'] = 'role_failed'
        state['attempts'][-1]['status'] = 'role_failed'
    change_state(case, failed)
    result = resume_project(case)
    assert result['status'] == 'role_failed'
    assert result['action'] == 'await_user'
    assert result['wait_reasons']


def test_stale_decided_review_does_not_advertise_return_as_available(case):
    from researchclaw.core.m1.approvals import current_corpus, record_corpus_approval
    record_corpus_approval(case, corpus_binding=current_corpus(case)['corpus_binding'], decision='reject',
        note='Explicit user revocation', command_id='revoke-review-approval')
    result = resume_project(case)
    assert result['action'] == 'await_user'
    assert 'm1_corpus_approval_required' in result['wait_reasons']


def test_completed_authoring_with_stale_upstream_keeps_input_wait(case):
    checkpoint(case, node='hypothesize', files={'knowledge/extractions.jsonl': b'{}'})
    # Synthesis pins the original extraction, so change the consumed scope too.
    checkpoint(case, files={'scope/goal.md': b'Synthetic changed research scope.'})
    result = resume_project(case)
    assert result['action'] == 'await_user'
    assert result['wait_reasons']
