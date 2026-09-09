"""B03 synthetic native command paths, not fixture-seeded node prerequisites."""
from copy import deepcopy
import importlib
from uuid import uuid4

import pytest

from researchclaw.core.research_graph import commands, store


def uid():
    return str(uuid4())


def prepare(snapshot, node='scope'):
    return importlib.import_module('researchclaw.core.research_graph.m1_scope').prepare_scope_council(snapshot, node_id=node)


class Fixture:
    def __init__(self, root):
        self.root = root
        self.head = commands.init_project(root, topic='B03 synthetic', content_origin='synthetic')
        self.project = self.head['state']['project_id']
        self.artifact = self.node()

    def envelope(self, producer='author'):
        return {**store._VERSION, 'project_id': self.project, 'id': uid(), 'event_id': uid(),
            'producer_id': producer, 'content_origin': 'synthetic', 'provenance_status': 'declared_only', 'observation_refs': []}

    def node(self, name='scope', **changes):
        content = {'user_goal': 'Compare reproducible methods', 'user_constraints': ['Use open data'],
            'agent_assumptions': ['A public benchmark may represent intended use']} if name == 'scope' else {
            'questions': [{'question': 'Which method reproduces the gain?', 'rationale': 'Tests the declared comparison goal'}],
            'agent_assumptions': ['The published metric is comparable']}
        return {**self.envelope(), 'node': name, 'attempt': uid(), 'previous_ref': None,
            'input_refs': {}, 'content': content, 'revision_reason': None, **changes}

    def apply(self, operation, payload, command_id=None, expected_head=None):
        result = commands.apply_command(self.root, operation=operation, payload=payload,
            expected_head=expected_head or self.head['id'], command_id=command_id or uid())
        self.head = store.read_head(self.root)
        return result

    def register(self, artifact=None, **kwargs):
        self.artifact = artifact or self.artifact
        return self.apply('m1.node.register', {'artifact': self.artifact}, **kwargs)

    def node_ref(self):
        record = self.head['state']['m1_node_revisions'][self.artifact['id']]
        return dict(project_id=self.project, head_id=self.head['id'], artifact_id=f"m1/nodes/{self.artifact['node']}",
                    sha256=store._hash(store._canonical(record)))

    def snapshot(self):
        return commands.read_policy_snapshot(self.root)

    def check(self, node=None):
        snapshot = self.snapshot(); before = deepcopy(snapshot)
        objects = {p.name: p.read_bytes() for p in (store._store_path(self.root) / 'objects').iterdir()}
        try:
            return prepare(snapshot, node or self.artifact['node'])
        finally:
            assert snapshot == before and store.read_head(self.root)['id'] == self.head['id']
            assert {p.name: p.read_bytes() for p in (store._store_path(self.root) / 'objects').iterdir()} == objects

    def council_payload(self, author='author'):
        self.binding = self.check()['node_ref']
        self.author = dict(id=uid(), project_id=self.project, actor_id=author, role='owner', milestone='M1', active=True)
        self.reviewers = [dict(id=uid(), project_id=self.project, actor_id=role, role='resolver', milestone='M1', active=True)
                          for role in ('domain', 'methodology', 'critical')]
        self.session = dict(id=uid(), project_id=self.project, input_binding=self.binding,
                            participant_assignment_ids=[a['id'] for a in self.reviewers], frozen=True)
        self.council = {**self.envelope('coordinator'), 'session_id': self.session['id'], 'milestone': 'M1',
            'node': self.artifact['node'], 'attempt': self.artifact['attempt'], 'author_assignment_ids': [self.author['id']],
            'required_roles': {a['actor_id']: a['id'] for a in self.reviewers}, 'allowed_evidence_refs': [], 'issue_ids': []}
        return dict(assignments=[self.author, *self.reviewers], review_session=self.session, council=self.council)

    def council_prepare(self, **kwargs):
        self.apply('council.prepare', self.council_payload(**kwargs))
        self.submitted = {phase: [] for phase in ('initial', 'response', 'final')}

    def submit(self, index, phase, **extra):
        earlier = 'initial' if phase == 'response' else 'response'
        response_refs = self.submitted[earlier] if phase != 'initial' else []
        actor = self.reviewers[index]
        submission = {**self.envelope(actor['actor_id']), 'session_id': self.session['id'], 'assignment_id': actor['id'],
            'input_binding': self.binding, 'phase': phase, 'rationale': 'Explicit review judgment and response',
            'evidence_refs': [self.binding], 'positions': [], 'retained_position_refs': [], 'response_refs': response_refs,
            'issue_proposals': [], 'recommendation': 'ready' if phase == 'final' else None,
            'host_id': 'declared-fixture-host', 'model_id': 'declared-fixture-model', **extra}
        self.apply('council.submit', {'submission': submission})
        self.submitted[phase].append(dict(project_id=self.project, head_id=self.head['id'], artifact_id=submission['id'],
            sha256=store._hash(store._canonical(submission))))
        return submission

    def complete(self, final='ready'):
        for phase in ('initial', 'response', 'final'):
            for index in range(3):
                self.submit(index, phase, **({'recommendation': final} if phase == 'final' else {}))

    def issue(self, producer='domain', severity='major'):
        return {**self.envelope(producer), 'origin': {'milestone': 'M1', 'node': self.artifact['node'],
            'attempt': self.artifact['attempt'], 'local_issue_id': 'ambiguity'}, 'question': 'Is the scope sufficiently precise?',
            'category': 'scope', 'target_refs': [self.binding], 'severity': severity,
            'blocking_scope': [{'kind': 'node', 'milestone': 'M1', 'target_id': self.artifact['node']}],
            'resolution_condition': 'Independent review accepts precise comparison criteria', 'owner_assignment_id': self.author['id']}

    def publish(self, issue):
        actor = self.reviewers[0] if issue['producer_id'] == 'domain' else self.author
        event = {**self.envelope(actor['actor_id']), 'issue_id': issue['id'], 'from_status': None, 'to_status': 'open',
            'actor_assignment_id': actor['id'], 'rationale': 'Publish the scoped issue', 'verification_refs': [], 'successor_ids': []}
        self.apply('issue.event', {'issue': issue, 'event': event})


def test_native_scope_registration_separates_goal_assumptions_and_waits_for_council(tmp_path):
    f = Fixture(tmp_path); f.register(); result = f.check()
    assert result['content'] == f.artifact['content']
    assert result['ready'] is False and result['reason_codes'] == ['council_required']
    assert result['next_node'] is None and result['phase'] == 'awaiting_council'
    assert result['council_binding']['author_actor_id'] == 'author'
    assert result['council_binding']['input_binding'] == result['node_ref']


def test_actual_issuefree_independent_three_phase_review_allows_questions_without_approval(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete()
    result = f.check()
    assert result['ready'] is True and result['reason_codes'] == []
    assert result['phase'] == 'complete' and result['next_node'] == 'questions'
    assert not f.head['state'].get('issues') and not f.head['state'].get('approval_bindings')
    assert all(not r['positions'] for r in f.head['state']['council_submissions'].values())


def test_missing_final_review_never_allows_search(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare()
    for phase in ('initial', 'response'):
        for i in range(3): f.submit(i, phase)
    assert f.check()['reason_codes'] == ['council_final_required']
    head = f.head['id']
    with pytest.raises(ValueError, match='^m1_upstream_review_required$'):
        f.register(f.node('questions', input_refs={'scope': f.binding}))
    assert store.read_head(tmp_path)['id'] == head


def test_reviewed_questions_explain_selection_and_expose_search_only_after_final(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete(); scope = f.check()['node_ref']
    f.register(f.node('questions', input_refs={'scope': scope})); f.council_prepare()
    assert f.check()['next_node'] is None
    f.complete(); result = f.check()
    assert result['ready'] is True and result['next_node'] == 'search'
    assert result['content']['questions'][0]['rationale'] == 'Tests the declared comparison goal'


def test_author_self_review_rejected_by_real_council_command_and_preserves_head(tmp_path):
    f = Fixture(tmp_path); f.register(); payload = f.council_payload()
    payload['assignments'][1]['actor_id'] = 'author'; head = f.head['id']
    with pytest.raises(ValueError, match='^council_assignment_invalid$'):
        f.apply('council.prepare', payload)
    assert store.read_head(tmp_path)['id'] == head


def test_declared_council_author_must_match_actual_node_producer(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(author='another-author')
    with pytest.raises(ValueError, match='^m1_council_author_mismatch$'):
        f.check()


def test_ambiguity_revision_keeps_old_bytes_and_requires_new_attempt_and_council(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete('revise')
    assert f.check()['reason_codes'] == ['revision_required']
    prior = f.check()['node_ref']; old = (store._store_path(tmp_path) / 'objects' / prior['sha256']).read_bytes()
    revision = f.node(previous_ref=prior, revision_reason='Clarify intended comparison',
        content={'user_goal': 'Compare reproducibility on the declared dataset', 'user_constraints': ['Use open data'], 'agent_assumptions': []})
    f.register(revision)
    assert f.check()['reason_codes'] == ['council_required']
    f.council_prepare(); f.complete()
    assert f.check()['ready'] is True
    assert (store._store_path(tmp_path) / 'objects' / prior['sha256']).read_bytes() == old


@pytest.mark.parametrize('fault', ['attempt', 'previous_ref', 'revision_reason'])
def test_invalid_revision_refused_and_head_preserved(tmp_path, fault):
    f = Fixture(tmp_path); f.register(); prior = f.check()['node_ref']; head = f.head['id']
    revision = f.node(previous_ref=prior, revision_reason='Clarify ambiguity')
    revision[fault] = f.artifact['attempt'] if fault == 'attempt' else None
    with pytest.raises(ValueError, match='^m1_revision_invalid$'):
        f.register(revision)
    assert store.read_head(tmp_path)['id'] == head


def test_registration_replay_conflict_and_unknown_node_are_bounded(tmp_path):
    f = Fixture(tmp_path); command = uid(); initial = f.head['id']; result = f.register(command_id=command)
    assert f.register(command_id=command, expected_head=initial) == result
    head = f.head['id']
    with pytest.raises(ValueError, match='^research_graph_command_conflict$'):
        f.register({**f.artifact, 'producer_id': 'different'}, command_id=command, expected_head=initial)
    with pytest.raises(ValueError, match='^m1_node_invalid$'):
        f.register(f.node('search'))
    assert store.read_head(tmp_path)['id'] == head


def test_unbound_response_is_not_counted_as_actual_response(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare()
    for i in range(3): f.submit(i, 'initial')
    for i in range(3): f.submit(i, 'response', response_refs=[])
    for i in range(3): f.submit(i, 'final')
    assert f.check()['reason_codes'] == ['council_response_binding_missing']


def test_unpublished_nonoptional_issue_proposal_blocks_ready_judgments(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); proposal = f.issue()
    f.submit(0, 'initial', issue_proposals=[proposal])
    for i in (1, 2): f.submit(i, 'initial')
    for phase in ('response', 'final'):
        for i in range(3): f.submit(i, phase)
    result = f.check()
    assert result['reason_codes'] == ['issue_publication_required']
    assert result['unpublished_issue_ids'] == [proposal['id']]


@pytest.mark.parametrize('severity,ready', [('major', False), ('optional', True)])
def test_native_scoped_issue_status_preserved_and_optional_does_not_block(tmp_path, severity, ready):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete()
    issue = f.issue(severity=severity); f.publish(issue)
    result = f.check()
    assert result['ready'] is ready and result['unresolved_issue_ids'] == [issue['id']]
    assert result['reason_codes'] == ([] if ready else ['blocking_issue_unresolved'])


def test_later_scope_revision_makes_questions_input_stale(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete(); prior = f.check()['node_ref']
    f.register(f.node('questions', input_refs={'scope': prior})); f.council_prepare(); f.complete()
    f.register(f.node(previous_ref=prior, revision_reason='Correct the declared scope'))
    with pytest.raises(ValueError, match='^issue_reference_stale$'):
        f.check('questions')


@pytest.mark.parametrize('retained,ready', [(False, False), (True, True)])
def test_formal_position_requires_final_authored_stance_acknowledgement(tmp_path, retained, ready):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); issue = f.issue(severity='optional')
    f.submit(0, 'initial', issue_proposals=[issue])
    for i in (1, 2): f.submit(i, 'initial')
    f.publish(issue)
    actor = f.reviewers[0]
    position = {**f.envelope(actor['actor_id']), 'assignment_id': actor['id'], 'session_id': f.session['id'],
        'input_binding': f.binding, 'issue_id': issue['id'], 'stance': 'conditional', 'rationale': 'Preserve scope limitation',
        'evidence_refs': [f.binding], 'changed_from': None, 'change_kind': None}
    f.submit(0, 'response', positions=[position])
    position_ref = dict(project_id=f.project, head_id=f.head['id'], artifact_id=position['id'],
                        sha256=store._hash(store._canonical(position)))
    for i in (1, 2): f.submit(i, 'response')
    f.submit(0, 'final', retained_position_refs=[position_ref] if retained else [])
    for i in (1, 2): f.submit(i, 'final')
    result = f.check()
    assert result['ready'] is ready
    assert result['reason_codes'] == ([] if ready else ['council_final_position_missing'])


def test_forged_issue_states_cannot_erase_native_scope_block(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete(); issue = f.issue(); f.publish(issue)
    state = deepcopy(f.head['state']); state['issue_states'][issue['id']] = 'resolved'
    f.head = store.commit_record(tmp_path, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'synthetic_forged_projection', 'payload': {}}, objects={})
    assert f.check()['reason_codes'] == ['blocking_issue_unresolved']


def test_replaced_backed_final_body_cannot_reuse_earlier_native_event(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete('revise')
    state = deepcopy(f.head['state']); final = next(r for r in state['council_submissions'].values() if r['phase'] == 'final')
    final['recommendation'] = 'ready'
    f.head = store.commit_record(tmp_path, expected_head=f.head['id'], command_id=uid(), state=state,
        event={**store._VERSION, 'type': 'synthetic_forged_record', 'payload': {}},
        objects={final['id']: store._canonical(final)})
    with pytest.raises(ValueError, match='^m1_native_record_invalid$'):
        f.check()


@pytest.mark.parametrize('node', [[], {}, None])
def test_malformed_node_discriminator_refused_as_policy_error(tmp_path, node):
    f = Fixture(tmp_path); artifact = f.node(); artifact['node'] = node; head = f.head['id']
    with pytest.raises(ValueError, match='^m1_node_invalid$'):
        f.register(artifact)
    assert store.read_head(tmp_path)['id'] == head


def test_questions_revision_can_replace_obsolete_scope_input_with_reviewed_current_scope(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); f.complete(); scope_v1 = f.check()['node_ref']
    f.register(f.node('questions', input_refs={'scope': scope_v1})); f.council_prepare(); f.complete()
    questions_v1 = f.check()['node_ref']
    f.register(f.node(previous_ref=scope_v1, revision_reason='Update scope after review'))
    f.council_prepare(); f.complete(); scope_v2 = f.check()['node_ref']
    f.register(f.node('questions', previous_ref=questions_v1, input_refs={'scope': scope_v2},
        revision_reason='Update questions for the reviewed scope'))
    f.council_prepare(); f.complete()
    assert f.check()['ready'] is True and f.check()['next_node'] == 'search'
    assert f.head['state']['m1_node_revisions'][f.artifact['id']]['input_refs'] == {'scope': scope_v2}


def test_revision_cannot_erase_disclosed_issue_publication_but_published_issue_allows_edit(tmp_path):
    f = Fixture(tmp_path); f.register(); f.council_prepare(); proposal = f.issue()
    f.submit(0, 'initial', issue_proposals=[proposal])
    for i in (1, 2): f.submit(i, 'initial')
    for phase in ('response', 'final'):
        for i in range(3): f.submit(i, phase, **({'recommendation': 'revise'} if phase == 'final' else {}))
    prior = f.check()['node_ref']; head = f.head['id']
    revision = f.node(previous_ref=prior, revision_reason='Clarify the proposed ambiguity')
    with pytest.raises(ValueError, match='^m1_issue_publication_required$'):
        f.register(revision)
    assert store.read_head(tmp_path)['id'] == head
    f.publish(proposal)
    f.register(revision)
    assert f.head['state']['m1_node_heads']['scope'] == revision['id']
    assert f.head['state']['issues'][proposal['id']] == proposal
    assert f.check()['unresolved_issue_ids'] == [proposal['id']]
