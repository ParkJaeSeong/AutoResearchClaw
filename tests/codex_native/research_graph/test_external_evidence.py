"""External Atlas evidence stays immutable, reviewable, and provenance-safe."""
import base64
from copy import deepcopy
from uuid import uuid4

import pytest

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.views import build_view


def qa(answer="First answer", identity="qa-1"):
    return ("---\n"
            "schema_version: 1\n"
            f"id: {identity}\n"
            "question: What changed?\n"
            f"answer: {answer}\n"
            "consulted_pages: []\n"
            "candidates: []\n"
            "---\n").encode()


def apply(root, operation, payload, *, expected=None, command_id=None):
    return commands.apply_command(root, operation=operation, payload=payload,
        expected_head=expected or store.read_head(root)['id'], command_id=command_id or str(uuid4()))


def imported(root, data=None, **changes):
    data = data or qa()
    payload = dict(content_base64=base64.b64encode(data).decode(), sha256=store._hash(data),
                   filename='atlas-qa.md', producer_id='coordinator')
    payload.update(changes)
    return apply(root, 'external.evidence.import', payload)


def ref(view, collection, index=-1):
    return view[collection][index]['ref']


def review_payload(evidence_ref, question_ref=None):
    return dict(evidence_ref=evidence_ref, question_ref=question_ref or evidence_ref, status='limited',
                allowed_uses=['hypothesis review'], held_uses=['direct measurement'],
                limitations=['Atlas-declared provenance'], rationale='Useful with limits',
                producer_id='coordinator')


def test_import_is_idempotent_and_new_bytes_append_a_linked_version(tmp_path):
    initial = commands.init_project(tmp_path, topic='Atlas', content_origin='real')
    first = imported(tmp_path)
    first_view = build_view(tmp_path)
    replay = imported(tmp_path)
    assert replay['state']['external_evidence'] == first['state']['external_evidence']
    assert len(build_view(tmp_path)['external_evidence']) == 1

    second = imported(tmp_path, qa('Revised answer'))
    current = build_view(tmp_path)
    assert len(current['external_evidence']) == 2
    old = next(row for row in current['external_evidence'] if row['record']['qa']['answer'] == 'First answer')
    new = next(row for row in current['external_evidence'] if row['record']['qa']['answer'] == 'Revised answer')
    assert old['latest'] is False
    assert old['newer_ref'] == new['ref']
    assert new['record']['previous_ref'] == first_view['external_evidence'][0]['ref']
    assert new['latest'] is True
    assert build_view(tmp_path, head_id=first['id'])['external_evidence'][0]['latest'] is True
    assert build_view(tmp_path, head_id=initial['id'])['external_evidence'] == []
    assert len(second['state']['external_evidence']) == 2


@pytest.mark.parametrize('change', [
    {'sha256': '0' * 64}, {'content_base64': '!'}, {'filename': ''}, {'producer_id': ''}, {'extra': True},
])
def test_invalid_import_is_atomic(tmp_path, change):
    before = commands.init_project(tmp_path, topic='Atlas', content_origin='real')
    with pytest.raises(ValueError, match='external_evidence'):
        imported(tmp_path, **change)
    assert store.read_head(tmp_path)['id'] == before['id']


def test_same_qa_in_different_projects_has_distinct_identity(tmp_path):
    left, right = tmp_path/'left', tmp_path/'right'
    commands.init_project(left, topic='Left', content_origin='real')
    commands.init_project(right, topic='Right', content_origin='real')
    imported(left); imported(right)
    assert build_view(left)['external_evidence'][0]['record']['id'] != build_view(right)['external_evidence'][0]['record']['id']


def test_same_content_under_different_qa_ids_stays_distinct_and_is_flagged(tmp_path):
    commands.init_project(tmp_path, topic='Atlas', content_origin='real')
    imported(tmp_path, qa(identity='qa-one'))
    imported(tmp_path, qa(identity='qa-two'))
    rows = build_view(tmp_path)['external_evidence']
    assert len(rows) == 2
    assert {row['record']['atlas_qa_id'] for row in rows} == {'qa-one', 'qa-two'}
    assert all(len(row['possible_duplicate_refs']) == 1 for row in rows)
    assert rows[0]['possible_duplicate_refs'][0] == rows[1]['ref']
    assert rows[1]['possible_duplicate_refs'][0] == rows[0]['ref']


def test_unhashable_review_status_is_a_validation_error(tmp_path):
    commands.init_project(tmp_path, topic='Atlas', content_origin='real'); imported(tmp_path)
    evidence = ref(build_view(tmp_path), 'external_evidence')
    payload = review_payload(evidence); payload['status'] = []
    with pytest.raises(ValueError, match='external_review_invalid'):
        apply(tmp_path, 'external.review.record', payload)


def test_review_and_question_require_exact_same_project_refs(tmp_path):
    commands.init_project(tmp_path, topic='Atlas', content_origin='real'); imported(tmp_path)
    evidence = ref(build_view(tmp_path), 'external_evidence')
    reviewed = apply(tmp_path, 'external.review.record', review_payload(evidence))
    review = ref(build_view(tmp_path), 'external_reviews')
    decision = apply(tmp_path, 'external.decision.record', dict(review_ref=review, title='Draft conclusion',
        conclusion='Proceed only with a bounded comparison', rationale='No council has completed yet',
        limitations=['Coordinator draft'], submission_refs=[], prior_ref=None, producer_id='coordinator'))
    decision_view = build_view(tmp_path)
    assert decision_view['external_decisions'][0]['record']['review_status'] == 'coordinator_only'
    apply(tmp_path, 'external.question.record', dict(decision_ref=ref(decision_view, 'external_decisions'),
        question='Which direction was measured?', missing_evidence='Orientation-resolved values',
        decision_impact='May reverse the comparison', scope='Atlas sources', producer_id='coordinator'))
    view = build_view(tmp_path)
    assert len(view['external_reviews']) == len(view['external_decisions']) == len(view['external_questions']) == 1
    assert 'sent' not in view['external_questions'][0]['record']
    assert reviewed['state']['external_reviews'] and decision['state']['external_decisions']

    other = tmp_path/'other'; commands.init_project(other, topic='Other', content_origin='real'); imported(other)
    foreign = ref(build_view(other), 'external_evidence')
    with pytest.raises(ValueError, match='external_review'):
        apply(tmp_path, 'external.review.record', review_payload(evidence, foreign))


def test_strict_payloads_and_forged_public_records_are_rejected(tmp_path):
    commands.init_project(tmp_path, topic='Atlas', content_origin='real'); imported(tmp_path)
    evidence = ref(build_view(tmp_path), 'external_evidence')
    bad = review_payload(evidence); bad['approved'] = True
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='external_review'):
        apply(tmp_path, 'external.review.record', bad)
    assert store.read_head(tmp_path)['id'] == before['id']

    forged = deepcopy(build_view(tmp_path)['external_evidence'][0]['record'])
    forged['id'] = str(uuid4())
    store.commit_record(tmp_path, expected_head=before['id'], command_id='forge',
        state={**before['state'], 'external_evidence': {**before['state']['external_evidence'], forged['id']: forged}},
        event={**store._VERSION, 'type': 'imported', 'payload': {}}, objects={forged['id']: store._canonical(forged)})
    with pytest.raises(ValueError, match='external_evidence_native'):
        build_view(tmp_path)


@pytest.mark.parametrize(('status', 'allowed', 'held'), [
    ('use', [], []), ('limited', [], ['measurement']), ('hold', ['hypothesis'], ['measurement']),
    ('exclude', ['hypothesis'], []), ('hold', [], []),
])
def test_review_status_requires_a_meaningful_use_disposition(tmp_path, status, allowed, held):
    commands.init_project(tmp_path, topic='Atlas', content_origin='real'); imported(tmp_path)
    evidence = ref(build_view(tmp_path), 'external_evidence')
    payload = review_payload(evidence); payload.update(status=status, allowed_uses=allowed, held_uses=held)
    with pytest.raises(ValueError, match='external_review_uses_invalid'):
        apply(tmp_path, 'external.review.record', payload)
