"""Synthetic declared-only checkpoints; these do not exercise upfront councils."""
import json
from pathlib import Path
from uuid import uuid4

from researchclaw.core.m1 import store
from researchclaw.core.m1.project import init_project

MARKER = '합성 검사 자료'


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode()


def jsonl(*values):
    return b'\n'.join(encoded(value) for value in values) + b'\n'


def corpus_files():
    candidate = {'source_id': 'src-one', 'title': MARKER, 'url': 'https://example.org/synthetic',
                 'access_status': 'abstract', 'search_ids': ['search-one']}
    shortlist = {**candidate, 'decision': 'include', 'reason': MARKER + ': relevant'}
    return {
        'scope/goal.md': MARKER.encode(), 'scope/constraints.json': encoded({'note': MARKER}),
        'scope/questions.json': encoded({'questions': [MARKER]}),
        'literature/search_plan.yaml': encoded({'queries': ['synthetic evidence'], 'sources': ['example'],
            'inclusion_criteria': [MARKER], 'exclusion_criteria': ['outside scope']}),
        'literature/candidates.jsonl': jsonl(candidate),
        'literature/search_log.jsonl': jsonl({'search_id': 'search-one', 'query': 'synthetic evidence',
            'source': 'example', 'searched_at': '2026-09-08T00:00:00Z', 'result_count': 1}),
        'literature/shortlist.jsonl': jsonl(shortlist),
        'literature/screening_decisions.jsonl': jsonl({'source_id': 'src-one', 'decision': 'include',
                                                    'reason': shortlist['reason']}),
    }


def checkpoint(root, *, node=None, files=None):
    """Inject declared test state, never a product advancement API."""
    head = store.read_head(root)
    state = head['state']
    if node:
        state['current_node_id'] = node
    refs = []
    for path, data in (files or {}).items():
        refs.append({**store._VERSION, 'id': 'fixture-' + uuid4().hex, 'logical_path': path,
                     'sha256': store._hash(data), 'size': len(data), 'producer_attempt_id': 'fixture-checkpoint',
                     'content_origin': 'synthetic', 'provenance_status': 'declared_only'})
    state.setdefault('artifacts', []).extend(refs)
    if not state['attempts'] and node == 'screen':
        for node_id, paths in (
                ('scope', ['scope/goal.md', 'scope/constraints.json']),
                ('questions', ['scope/questions.json']),
                ('search', ['literature/search_plan.yaml']),
                ('collect', ['literature/candidates.jsonl', 'literature/search_log.jsonl'])):
            owned = [ref for ref in refs if ref['logical_path'] in paths]
            attempt_id = f'fixture-{node_id}'
            for ref in owned:
                ref['producer_attempt_id'] = attempt_id
            state['attempts'].append({**store._VERSION, 'id': attempt_id, 'node_id': node_id,
                'revision': 1, 'parent_attempt_id': None, 'input_refs': [], 'output_refs': owned,
                'status': 'completed', 'provenance_status': 'declared_only', 'content_origin': 'synthetic',
                'note': MARKER + ': injected checkpoint; no council execution claimed'})
    return store.commit_record(root, expected_head=head['id'], command_id='fixture-' + uuid4().hex,
        state=state, event={**store._VERSION, 'type': 'synthetic_test_checkpoint',
                           'payload': {'note': MARKER, 'provenance_status': 'declared_only'}}, objects=files or {})


def submission(root, packet, files):
    refs = {}
    for logical, data in files.items():
        path = f"{packet['work_dir']}/{logical}"
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        refs[logical] = {'path': path, 'sha256': store._hash(data), 'size': len(data)}
    return {'schema_version': 1, 'files': refs}


def corpus_checkpoint(root: Path) -> dict:
    from researchclaw.core.m1.approvals import current_corpus
    from researchclaw.core.m1.packets import prepare_node, register_outputs
    init_project(root, topic=MARKER, profile='materials_ai', max_returns=2, content_origin='synthetic')
    files = corpus_files()
    screen = {path: files.pop(path) for path in ('literature/shortlist.jsonl', 'literature/screening_decisions.jsonl')}
    checkpoint(root, node='screen', files=files)
    packet = prepare_node(root, 'screen', command_id='screen-prepare')['packet']
    result = register_outputs(root, packet_id=packet['id'], submission=submission(root, packet, screen), command_id='screen-register')
    assert result['status'] == 'review_pending', result
    return {'root': root, 'head_id': result['receipt']['id'], 'artifact_refs': result['artifacts'], **current_corpus(root)}


def extraction_files(project_id):
    claim = {'claim_id': 'claim-one', 'source_id': 'src-one', 'claim': MARKER + ': observation',
             'evidence_summary': MARKER + ': abstract reports observation', 'evidence_level': 'abstract',
             'locator': 'Abstract', 'source_url': 'https://example.org/synthetic',
             'applicability': ['synthetic check'], 'limitations': ['Full text was not accessed']}
    manifest = {'schema_version': 1, 'project_id': project_id, 'generated_at': '2026-09-08T00:00:00Z',
                'sources': [{'source_id': 'src-one', 'decision': 'include', 'access_status': 'abstract',
                             'accessed_at': '2026-09-08T00:00:00Z', 'access_url': 'https://example.org/synthetic',
                             'claim_count': 1, 'failure_reason': None}],
                'summary': {'included_sources': 1, 'processed_sources': 1, 'claim_count': 1,
                            'full_text_sources': 0, 'abstract_sources': 1, 'metadata_only_sources': 0,
                            'unavailable_sources': 0}}
    return {'knowledge/extractions.jsonl': jsonl(claim), 'knowledge/extraction_manifest.json': encoded(manifest)}


def build_evidence_case(root: Path) -> dict:
    from researchclaw.core.m1.approvals import record_corpus_approval
    from researchclaw.core.m1.packets import prepare_node, register_outputs
    case = corpus_checkpoint(root)
    record_corpus_approval(root, corpus_binding=case['corpus_binding'], decision='approve',
                          note=MARKER + ': test declaration only', command_id='corpus-approve')
    checkpoint(root, node='extract')  # Task17 council advancement intentionally not simulated as public work.
    packet = prepare_node(root, 'extract', command_id='extract-prepare')['packet']
    files = extraction_files(store.read_head(root)['state']['project_id'])
    result = register_outputs(root, packet_id=packet['id'], submission=submission(root, packet, files), command_id='extract-register')
    assert result['status'] == 'review_pending', result
    checkpoint(root, node='synthesize')  # Synthetic declared-only checkpoint; no independent review claimed.
    packet = prepare_node(root, 'synthesize', command_id='synthesize-prepare')['packet']
    synthesis = {'claims': ['claim-one'], 'agreements': [], 'conflicts': [], 'gaps': [],
                 'limitations': [MARKER + ': full text was not accessed; no verified gaps asserted']}
    files = {'knowledge/synthesis.json': encoded(synthesis),
             'knowledge/synthesis.md': (MARKER + ': observation [claim-one]; abstract only.').encode()}
    result = register_outputs(root, packet_id=packet['id'], submission=submission(root, packet, files),
                              command_id='synthesize-register')
    assert result['status'] == 'review_pending', result
    return {**case, 'head_id': result['receipt']['id'], 'artifact_refs': store.read_head(root)['state']['artifacts']}


def build_review_case(root: Path, *, outcome: str) -> dict:
    """Public registration from explicit synthetic checkpoints, never host evidence."""
    from researchclaw.core.m1.council import (
        prepare_council, register_initial, register_response, register_final_position,
    )
    from researchclaw.core.m1.decisions import register_decision
    from researchclaw.core.m1.packets import prepare_node, register_outputs
    if outcome not in ('ready', 'return_hypothesis'):
        raise ValueError('outcome must be ready or return_hypothesis')
    ready = outcome == 'ready'
    build_evidence_case(root)
    checkpoint(root, node='hypothesize')  # Earlier council advancement is a declared fixture only.
    packet = prepare_node(root, 'hypothesize', command_id='hypothesis-prepare')['packet']
    hypothesis = {'id': 'H1', 'revision': 1, 'parent_revision': None,
        'author_assignment_id': 'synthetic-author', 'change_reason': None,
        'statement': MARKER + ': the observed difference depends on context.',
        'claim_refs': ['claim-one'], 'gap_refs': [],
        'predicted_observation': 'The difference diminishes under a shared context.',
        'falsification_condition': 'The difference persists under comparable conditions.',
        'alternatives': ['Selection effects explain the observation.'],
        'feasibility_notes': MARKER + ': access is not verified.',
        'open_design_questions': ['Which conditions and measurements should M2 use?'],
        'disposition': 'draft'}
    files = {'hypotheses/hypotheses.json': encoded({'schema_version': 1, 'hypotheses': [hypothesis]}),
             'hypotheses/hypotheses.md': (MARKER + ': H1 is a synthetic unreviewed candidate.').encode()}
    registered = register_outputs(root, packet_id=packet['id'], submission=submission(root, packet, files),
                                  command_id='hypothesis-register')
    assert registered['status'] == 'review_pending', registered
    assignments = [{'id': 'synthetic-' + role, 'role_id': role, 'host_task_id': 'declared-host-' + role}
                   for role in ('domain', 'methodology', 'critical_reproducibility')]
    session = prepare_council(root, attempt_id=packet['attempt_id'], assignments=assignments,
                              command_id='council-prepare')['session']
    issue_ids = [] if ready else ['synthetic-issue-H1']
    evidence = [session['input_refs'][0]['id']]
    for assignment in assignments:
        identity = {'schema_version': 1, 'session_id': session['id'],
            'input_binding': session['input_binding'], 'assignment_id': assignment['id'],
            'role_id': assignment['role_id'], 'host_task_id': assignment['host_task_id']}
        issues = []
        if not ready and assignment['role_id'] == 'domain':
            issues = [{'id': issue_ids[0], 'raised_by': assignment['id'],
                'target_refs': [{'id': 'H1', 'revision': 1}], 'evidence_refs': evidence,
                'question': MARKER + ': does the comparison establish the proposed mechanism?',
                'impact': 'The causal claim remains unsupported.', 'severity': 'blocking',
                'resolution_condition': 'Revise the mechanism claim against the observed evidence.'}]
        register_initial(root, session_id=session['id'], assignment_id=assignment['id'],
            payload={**identity, 'id': 'initial-' + assignment['id'], 'rationale': [MARKER + ': synthetic initial'],
                     'evidence_refs': evidence, 'open_issues': issues}, command_id='initial-' + assignment['id'])
    for assignment in assignments:
        identity = {'schema_version': 1, 'session_id': session['id'],
            'input_binding': session['input_binding'], 'assignment_id': assignment['id'],
            'role_id': assignment['role_id'], 'host_task_id': assignment['host_task_id']}
        replies = [] if ready else [{'id': 'reply-' + assignment['id'], 'issue_id': issue_ids[0],
            'assignment_id': assignment['id'], 'stance': 'accept',
            'rationale': MARKER + ': revision remains necessary.', 'evidence_refs': evidence}]
        register_response(root, session_id=session['id'], assignment_id=assignment['id'],
            payload={**identity, 'id': 'response-' + assignment['id'], 'rationale': MARKER + ': synthetic response',
                     'responses': replies, 'new_issues': []}, command_id='response-' + assignment['id'])
    for assignment in assignments:
        identity = {'schema_version': 1, 'session_id': session['id'],
            'input_binding': session['input_binding'], 'assignment_id': assignment['id'],
            'role_id': assignment['role_id'], 'host_task_id': assignment['host_task_id']}
        dispositions = [] if ready else [{'issue_id': issue_ids[0], 'status': 'open',
            'rationale': MARKER + ': the resolution condition remains unmet.',
            'response_ids': ['reply-' + a['id'] for a in assignments], 'evidence_refs': evidence}]
        register_final_position(root, session_id=session['id'], assignment_id=assignment['id'],
            payload={**identity, 'recommendation': 'ready_with_limits' if ready else 'revise',
                'change_rationale': MARKER + ': no opinion change after the synthetic response round.',
                'issue_dispositions': dispositions, 'rationale': MARKER + ': design readiness only.' if ready
                else MARKER + ': the hypothesis requires revision.', 'evidence_refs': evidence},
            command_id='final-' + assignment['id'])
    session = store.read_head(root)['state']['sessions'][session['id']]
    finals = session['disclosed_final_positions']
    payload = {'schema_version': 1, 'id': 'synthetic-decision', 'session_id': session['id'],
        'input_binding': session['input_binding'], 'positions': finals,
        'hypothesis_dispositions': [{'hypothesis_ref': {'id': 'H1', 'revision': 1},
            'disposition': 'selected' if ready else 'revise', 'rationale': MARKER + ': all final views considered.',
            'issue_ids': issue_ids, 'final_assignment_ids': sorted(a['id'] for a in assignments)}],
        'selected_hypothesis_ids': ['H1'] if ready else [], 'dissent': [] if ready else finals,
        'limitations': [MARKER + ': abstract-only, declared_only; no actual role execution evidence.'],
        'issue_ids': issue_ids, 'rationale': MARKER + ': preserve the three synthetic final opinions.',
        'ready': ready, 'reason_codes': [] if ready else ['no_selected_hypothesis', 'open_blockers', 'opposed_final_role'],
        'next_action': 'handoff' if ready else 'return', 'return_target': None if ready else 'hypothesize',
        'proposed_work': [] if ready else ['Revise the mechanism claim against the observation.']}
    result = register_decision(root, session_id=session['id'], payload=payload, command_id='decision-register')
    return {'root': root, 'head_id': result['receipt']['id'], 'review_attempt_id': session['review_attempt_id'],
            'decision_id': result['decision_id'], 'hypothesis_id': 'H1'}
