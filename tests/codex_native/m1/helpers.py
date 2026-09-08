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
