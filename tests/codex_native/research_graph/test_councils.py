"""B02 synthetic structural fixtures; real host observation is recorded separately."""
from copy import deepcopy
import importlib
import json
from uuid import uuid4
import pytest
from researchclaw.core.research_graph import commands, store


def uid():
    return str(uuid4())


def api():
    return importlib.import_module('researchclaw.core.research_graph.councils')


class Fixture:
    def __init__(self, root, prepare=True):
        self.root = root
        self.head = commands.init_project(root, topic='B02 synthetic', content_origin='synthetic')
        self.project = self.head['state']['project_id']
        self.source = self.register('fixture_inputs', {**self.envelope(), 'text': 'Shared source packet'})[0]
        self.author = self.assignment('author', 'owner')
        self.reviewers = [self.assignment(role, 'resolver') for role in ('domain', 'methodology', 'critical')]
        self.session = dict(id=uid(), project_id=self.project, input_binding=self.source,
                            participant_assignment_ids=[a['id'] for a in self.reviewers], frozen=True)
        self.council = {**self.envelope('coordinator'), 'session_id': self.session['id'], 'milestone': 'M1',
            'node': 'review', 'attempt': uid(), 'author_assignment_ids': [self.author['id']],
            'required_roles': {a['actor_id']: a['id'] for a in self.reviewers}, 'allowed_evidence_refs': [self.source], 'issue_ids': []}
        self.prepare_payload = dict(assignments=[self.author, *self.reviewers], review_session=self.session, council=self.council)
        if prepare:
            self.prepare()

    def envelope(self, producer='author'):
        return {**store._VERSION, 'project_id': self.project, 'id': uid(), 'event_id': uid(),
            'producer_id': producer, 'content_origin': 'synthetic', 'provenance_status': 'declared_only', 'observation_refs': []}

    def assignment(self, actor, role):
        return dict(id=uid(), project_id=self.project, actor_id=actor, role=role, milestone='M1', active=True)

    def register(self, collection, *records):
        state = deepcopy(self.head['state']); state.setdefault(collection, {}).update({r['id']: r for r in records})
        self.head = store.commit_record(self.root, expected_head=self.head['id'], command_id=uid(), state=state,
            event={**store._VERSION, 'type': 'synthetic_fixture_registered', 'payload': {}},
            objects={r['id']: store._canonical(r) for r in records})
        return [self.ref(r) for r in records]

    def ref(self, record):
        return dict(project_id=self.project, head_id=self.head['id'], artifact_id=record['id'], sha256=store._hash(store._canonical(record)))

    def snapshot(self):
        return commands.read_policy_snapshot(self.root)

    def prepare(self):
        result = commands.apply_command(self.root, operation='council.prepare', payload=self.prepare_payload,
                                        expected_head=self.head['id'], command_id=uid())
        self.head = store.read_head(self.root)
        return result

    def submission(self, index, phase='initial', **changes):
        actor = self.reviewers[index]
        record = {**self.envelope(actor['actor_id']), 'session_id': self.session['id'], 'assignment_id': actor['id'],
            'input_binding': self.source, 'phase': phase, 'rationale': f'private-{phase}-body-{index}',
            'evidence_refs': [self.source], 'positions': [], 'retained_position_refs': [], 'response_refs': [],
            'issue_proposals': [], 'recommendation': 'ready_with_limits' if phase == 'final' else None,
            'host_id': 'declared-codex-host', 'model_id': 'declared-model'}
        record.update(changes)
        return record

    def submit(self, submission, command_id=None, expected_head=None):
        result = commands.apply_command(self.root, operation='council.submit', payload={'submission': submission},
            expected_head=expected_head or self.head['id'], command_id=command_id or uid())
        self.head = store.read_head(self.root)
        return result

    def packet(self, index):
        return api().reviewer_packet(self.snapshot(), self.reviewers[index]['id'])

    def proposal(self, index=0):
        return {**self.envelope(self.reviewers[index]['actor_id']), 'origin': {'milestone': 'M1', 'node': 'review',
            'attempt': self.council['attempt'], 'local_issue_id': 'new-source-question'}, 'question': 'Does the source include controls?',
            'category': 'source', 'target_refs': [self.source], 'severity': 'major',
            'blocking_scope': [{'kind': 'handoff', 'milestone': 'M1', 'target_id': 'M2'}],
            'resolution_condition': 'Independent source comparison locates controls', 'owner_assignment_id': self.author['id']}

    def complete_phase(self, phase):
        for index in range(3):
            self.submit(self.submission(index, phase))


def test_prepare_creates_backed_closed_assignments_and_session_without_raw_receipt(tmp_path):
    f = Fixture(tmp_path, prepare=False); result = f.prepare()
    assert set(result) == {'schema_version', 'workflow_version', 'id', 'council'}
    assert result['council']['phase'] == 'initial'
    snapshot = f.snapshot()
    for collection, records in [('assignments', [f.author, *f.reviewers]), ('review_sessions', [f.session]), ('councils', [f.council])]:
        for record in records:
            assert snapshot['state'][collection][record['id']] == record
            assert store._canonical(record) == snapshot['_issue_context']['objects'][store._hash(store._canonical(record))]


def test_two_initials_hide_peer_bodies_hashes_and_third_discloses_all(tmp_path):
    f = Fixture(tmp_path); first, second = f.submission(0), f.submission(1)
    f.submit(first); result = f.submit(second)
    for projection in (f.packet(1), f.packet(2), result):
        text = json.dumps(projection)
        assert first['rationale'] not in text and store._hash(store._canonical(first)) not in text
        assert first['id'] not in text
    assert f.packet(2)['disclosed_initials'] == []
    third_result = f.submit(f.submission(2))
    assert len(third_result['packet']['disclosed_initials']) == 3
    assert first['rationale'] in json.dumps(third_result)
    assert f.packet(0)['phase'] == 'response'
    assert set(third_result) == {'schema_version', 'workflow_version', 'id', 'packet'}


def test_replay_redaction_uses_original_ancestor_and_stale_conflict_preserves_head(tmp_path):
    f = Fixture(tmp_path); first = f.submission(0); prior = f.head['id']; command_id = uid()
    result = f.submit(first, command_id=command_id)
    second = f.submission(1); f.submit(second); f.submit(f.submission(2))
    before = store.read_head(tmp_path)
    assert f.submit(first, command_id=command_id, expected_head=prior) == result
    assert second['rationale'] not in json.dumps(result)
    with pytest.raises(ValueError, match='research_graph_command_conflict'):
        f.submit({**first, 'rationale': 'changed'}, command_id=command_id, expected_head=prior)
    with pytest.raises(ValueError, match='research_graph_head_conflict'):
        f.submit(f.submission(0, 'response'), expected_head=prior)
    assert store.read_head(tmp_path) == before


def test_response_and_final_barriers_require_explicit_final_judgment(tmp_path):
    f = Fixture(tmp_path)
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='council_phase_invalid'):
        f.submit(f.submission(0, 'response'))
    assert store.read_head(tmp_path) == before
    f.complete_phase('initial')
    f.submit(f.submission(0, 'response')); assert f.packet(1)['disclosed_responses'] == []
    f.submit(f.submission(1, 'response')); f.submit(f.submission(2, 'response'))
    assert f.packet(0)['phase'] == 'final'
    with pytest.raises(ValueError, match='council_recommendation_invalid'):
        f.submit(f.submission(0, 'final', recommendation=None))
    f.complete_phase('final')
    packet = f.packet(0)
    assert packet['phase'] == 'complete' and len(packet['disclosed_finals']) == 3
    assert all(item['submission']['recommendation'] == 'ready_with_limits' for item in packet['disclosed_finals'])


def test_private_structured_proposals_survive_disclosure_without_becoming_issues(tmp_path):
    f = Fixture(tmp_path); proposal = f.proposal()
    f.submit(f.submission(0, issue_proposals=[proposal]))
    assert proposal['question'] not in json.dumps(f.packet(1))
    assert proposal['id'] not in f.head['state'].get('issues', {})
    f.submit(f.submission(1)); f.submit(f.submission(2))
    assert proposal in f.packet(1)['disclosed_initials'][0]['submission']['issue_proposals'] or any(
        proposal in item['submission']['issue_proposals'] for item in f.packet(1)['disclosed_initials'])
    assert f.head['state'].get('issue_events', []) == []
    f.submit(f.submission(0, 'response', issue_proposals=[{**f.proposal(), 'id': uid(), 'event_id': uid()}]))
    assert f.packet(1)['disclosed_responses'] == []


@pytest.mark.parametrize('fault', ['actor', 'binding', 'duplicate', 'foreign_response', 'undeclared_evidence'])
def test_submission_binding_and_access_refusals_preserve_head(tmp_path, fault):
    f = Fixture(tmp_path); first = f.submission(0); f.submit(first)
    bad = f.submission(1)
    if fault == 'actor': bad['producer_id'] = 'coordinator'
    if fault == 'binding': bad['input_binding'] = {**f.source, 'artifact_id': 'wrong'}
    if fault == 'duplicate': bad = f.submission(0)
    if fault == 'foreign_response': bad['response_refs'] = [f.ref(first)]
    if fault == 'undeclared_evidence': bad['evidence_refs'] = [f.ref(first)]
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='council_'):
        f.submit(bad)
    assert store.read_head(tmp_path) == before


@pytest.mark.parametrize('nested', [False, True])
def test_prepare_cannot_launder_undisclosed_other_session_artifacts_as_shared_input(tmp_path, nested):
    f = Fixture(tmp_path); first = f.submission(0, issue_proposals=[f.proposal()]); f.submit(first)
    private_ref = f.ref(first)
    if nested:
        private_ref = f.register('fixture_inputs', {**f.envelope(), 'nested': private_ref})[0]
    new_reviewers = [f.assignment(f'next-{i}', 'resolver') for i in range(3)]
    session = {**f.session, 'id': uid(), 'input_binding': private_ref, 'participant_assignment_ids': [a['id'] for a in new_reviewers]}
    council = {**f.council, 'id': uid(), 'event_id': uid(), 'session_id': session['id'],
        'required_roles': {str(i): a['id'] for i, a in enumerate(new_reviewers)}, 'allowed_evidence_refs': [private_ref]}
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='council_private_input'):
        commands.apply_command(tmp_path, operation='council.prepare', payload={'assignments': [f.author, *new_reviewers], 'review_session': session, 'council': council}, expected_head=f.head['id'], command_id=uid())
    assert store.read_head(tmp_path) == before


def test_declared_host_labels_never_claim_enforced_isolation_and_pure_packet(tmp_path, monkeypatch):
    f = Fixture(tmp_path); f.submit(f.submission(0))
    snapshot = f.snapshot(); before = deepcopy(snapshot)
    def forbidden(*args, **kwargs):
        raise AssertionError('pure packet performed I/O')
    monkeypatch.setattr(store, '_history', forbidden); monkeypatch.setattr(store, '_read_file', forbidden)
    packet = api().reviewer_packet(snapshot, f.reviewers[1]['id'])
    assert packet['isolation_level'] == 'instructions_only'
    assert packet['identity_provenance'] == 'declared_only'
    assert snapshot == before


def test_prepare_rejects_duplicate_actor_and_malformed_closed_session(tmp_path):
    f = Fixture(tmp_path, prepare=False); f.reviewers[1]['actor_id'] = f.reviewers[0]['actor_id']
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='council_assignment_invalid'):
        f.prepare()
    assert store.read_head(tmp_path) == before
    f.reviewers[1]['actor_id'] = 'methodology'; f.session['isolated'] = True
    with pytest.raises(ValueError, match='council_session_invalid'):
        f.prepare()


def test_disclosed_response_refs_are_exact_and_cannot_point_to_initial_during_initial_phase(tmp_path):
    f = Fixture(tmp_path); f.complete_phase('initial')
    reference = f.packet(0)['disclosed_initials'][0]['submission_ref']
    f.submit(f.submission(0, 'response', response_refs=[reference]))
    assert f.packet(0)['phase'] == 'response_wait'


def test_unknown_assignment_and_bare_snapshot_fail_closed(tmp_path):
    f = Fixture(tmp_path)
    with pytest.raises(ValueError, match='council_assignment_invalid'):
        api().reviewer_packet(f.snapshot(), uid())
    with pytest.raises(ValueError, match='issue_context_missing'):
        api().reviewer_packet(f.head, f.reviewers[0]['id'])


def test_published_proposal_positions_use_a06_and_unchanged_final_retains_exact_position(tmp_path):
    f = Fixture(tmp_path); proposal = f.proposal()
    f.submit(f.submission(0, issue_proposals=[proposal])); f.submit(f.submission(1)); f.submit(f.submission(2))
    actor = f.reviewers[0]
    event = {**f.envelope(actor['actor_id']), 'issue_id': proposal['id'], 'from_status': None, 'to_status': 'open',
        'actor_assignment_id': actor['id'], 'rationale': 'Explicit publication after disclosure', 'verification_refs': [], 'successor_ids': []}
    f.head = commands.apply_command(tmp_path, operation='issue.event', payload={'issue': proposal, 'event': event}, expected_head=f.head['id'], command_id=uid())
    position = {**f.envelope(actor['actor_id']), 'assignment_id': actor['id'], 'session_id': f.session['id'],
        'input_binding': f.source, 'issue_id': proposal['id'], 'stance': 'conditional', 'rationale': 'Requires source comparison',
        'evidence_refs': [f.source], 'changed_from': None, 'change_kind': None}
    f.submit(f.submission(0, 'response', positions=[position])); position_ref = f.ref(position)
    original_path = store._store_path(tmp_path) / 'objects' / position_ref['sha256']; old = original_path.read_bytes()
    f.submit(f.submission(1, 'response')); f.submit(f.submission(2, 'response'))
    bad = f.submission(1, 'final', retained_position_refs=[position_ref])
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='council_position_invalid'):
        f.submit(bad)
    assert store.read_head(tmp_path) == before
    f.submit(f.submission(0, 'final', retained_position_refs=[position_ref], recommendation='revise'))
    assert original_path.read_bytes() == old
    assert f.head['state']['issues'][proposal['id']] == proposal
    assert f.head['state']['issue_states'][proposal['id']] == 'open'


def test_register_submission_returns_pure_plan_without_mutating_snapshot(tmp_path, monkeypatch):
    f = Fixture(tmp_path); snapshot = f.snapshot(); payload = {'submission': f.submission(0)}
    before, before_payload = deepcopy(snapshot), deepcopy(payload)
    def forbidden(*args, **kwargs):
        raise AssertionError('pure submission planner performed I/O')
    monkeypatch.setattr(store, '_history', forbidden); monkeypatch.setattr(store, '_read_file', forbidden)
    plan = api().register_submission(snapshot, payload)
    assert set(plan) == {'state_patch', 'event', 'object_inputs'}
    assert snapshot == before and payload == before_payload


def test_prepare_and_submit_reject_identity_alias_collision_before_commit(tmp_path):
    f = Fixture(tmp_path, prepare=False); f.council['id'] = f.source['artifact_id']
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='council_identity_exists'):
        f.prepare()
    assert store.read_head(tmp_path) == before
    f.council['id'] = uid(); f.prepare()
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match='council_identity_exists'):
        f.submit(f.submission(0, id=f.source['artifact_id']))
    assert store.read_head(tmp_path) == before


def test_existing_issue_is_shared_at_prepared_exact_version_and_stale_replacement_rejected(tmp_path):
    f = Fixture(tmp_path, prepare=False)
    f.register('assignments', f.author)
    issue = f.proposal(); f.register('issues', issue)
    f.council['issue_ids'] = [issue['id']]; f.prepare()
    packet = f.packet(0)
    assert packet['shared_issues'][0]['issue'] == issue
    assert packet['shared_issues'][0]['issue_ref']['sha256'] == store._hash(store._canonical(issue))
    f.register('issues', {**issue, 'question': 'Changed after preparation'})
    with pytest.raises(ValueError, match='issue_reference_stale'):
        f.packet(0)
