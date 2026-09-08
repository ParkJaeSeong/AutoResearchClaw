import importlib.util
import json

import pytest

from tests.codex_native.m1.helpers import corpus_files, encoded, extraction_files, jsonl


def validator():
    assert importlib.util.find_spec('researchclaw.core.m1.literature') is not None, 'literature validation is missing'
    from researchclaw.core.m1.literature import validate_literature
    return validate_literature


def check(node, files, inputs):
    return validator()(node, files, inputs)


def test_search_collect_screen_accept_traceable_content():
    corpus = corpus_files()
    for node, paths in [('search', ['literature/search_plan.yaml']),
                        ('collect', ['literature/candidates.jsonl', 'literature/search_log.jsonl']),
                        ('screen', ['literature/shortlist.jsonl', 'literature/screening_decisions.jsonl'])]:
        assert check(node, {path: corpus[path] for path in paths}, corpus) == ()


@pytest.mark.parametrize('mutation', ['query', 'source', 'search_id', 'access', 'reason', 'identity', 'omitted', 'duplicate'])
def test_literature_rejects_broken_provenance_or_screening(mutation):
    corpus = corpus_files()
    node = 'collect'
    if mutation in ('query', 'source'):
        row = json.loads(corpus['literature/search_log.jsonl'])
        row[mutation] = ''
        corpus['literature/search_log.jsonl'] = jsonl(row)
    elif mutation in ('search_id', 'access'):
        row = json.loads(corpus['literature/candidates.jsonl'])
        row['search_ids' if mutation == 'search_id' else 'access_status'] = ['absent'] if mutation == 'search_id' else 'unverified'
        corpus['literature/candidates.jsonl'] = jsonl(row)
    else:
        node = 'screen'
        path = 'literature/screening_decisions.jsonl' if mutation == 'reason' else 'literature/shortlist.jsonl'
        row = json.loads(corpus[path])
        if mutation == 'reason': row['reason'] = ' '
        if mutation == 'identity': row['url'] = 'https://example.org/different'
        corpus[path] = b'' if mutation == 'omitted' else jsonl(row, row) if mutation == 'duplicate' else jsonl(row)
    assert check(node, corpus, corpus)


@pytest.mark.parametrize('payload', [b'[]', b'{"queries": []}', b'queries: [one]\nsources: []'])
def test_search_requires_queries_sources_and_selection_criteria(payload):
    assert check('search', {'literature/search_plan.yaml': payload}, {})


def test_extraction_adapter_uses_trusted_project_identity_and_limits():
    inputs = corpus_files() | {'project.json': encoded({'project_id': 'm1-fixture'})}
    files = extraction_files('m1-fixture')
    assert check('extract', files, inputs) == ()
    for field, value in [('locator', ''), ('limitations', []), ('evidence_level', 'full_text')]:
        row = json.loads(files['knowledge/extractions.jsonl'])
        row[field] = value
        assert check('extract', files | {'knowledge/extractions.jsonl': jsonl(row)}, inputs)
    assert check('extract', extraction_files('wrong-project'), inputs)


@pytest.mark.parametrize('node', ['search', 'collect', 'screen', 'extract'])
def test_malformed_direct_input_returns_issues(node):
    assert check(node, {'literature/search_plan.yaml': b'\xff'}, {})


def test_extraction_cannot_upgrade_approved_access_declaration():
    inputs = corpus_files() | {'project.json': encoded({'project_id': 'm1-fixture'})}
    files = extraction_files('m1-fixture')
    manifest = json.loads(files['knowledge/extraction_manifest.json'])
    manifest['sources'][0]['access_status'] = 'full_text'
    manifest['summary'].update(full_text_sources=1, abstract_sources=0)
    row = json.loads(files['knowledge/extractions.jsonl'])
    row['evidence_level'] = 'full_text'
    assert check('extract', {'knowledge/extractions.jsonl': jsonl(row),
                             'knowledge/extraction_manifest.json': encoded(manifest)}, inputs)


def test_candidate_cannot_claim_provenance_from_search_with_zero_results():
    corpus = corpus_files()
    row = json.loads(corpus['literature/search_log.jsonl'])
    row['result_count'] = 0
    corpus['literature/search_log.jsonl'] = jsonl(row)
    assert check('collect', corpus, corpus)
