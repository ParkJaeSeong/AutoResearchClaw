"""Discovery must actually browse, retain provenance, and stop honestly."""
import importlib
import pytest


def api():
    try:
        return importlib.import_module('researchclaw.codex.literature_loop')
    except ModuleNotFoundError:
        pytest.fail('The independent literature discovery loop is missing')


def test_no_web_execution_cannot_be_presented_as_discovery():
    with pytest.raises(ValueError, match='no_observed_web_search'):
        api().audit_events([{'type': 'thread.started', 'thread_id': 't'}])
    result = api().audit_events([
        {'type': 'thread.started', 'thread_id': 't'},
        {'type': 'item.started', 'item': {'id': 'w', 'type': 'web_search', 'query': 'polymer'}},
        {'type': 'item.completed', 'item': {'id': 'w', 'type': 'web_search', 'query': 'polymer', 'action':{'type':'search','queries':['polymer']}}},
    ])
    assert result['web_calls'] == 1
    assert result['queries'] == ['polymer']


def test_url_open_alone_is_not_an_observed_search():
    with pytest.raises(ValueError, match='no_observed_search_query'):
        api().audit_events([{'type':'thread.started','thread_id':'t'},
            {'type':'item.completed','item':{'id':'w','type':'web_search','query':'https://a','action':{'type':'other'}}}])


def test_failed_worker_does_not_drop_successful_sibling_reports(tmp_path, monkeypatch):
    import json
    m = api()
    def host(*args):
        role = args[2]
        if role == 'methodology':
            raise RuntimeError('host unavailable')
        return dict(role=role,sources=[],sufficient=False,gaps=['missing'],next_queries=['retry'])
    monkeypatch.setattr(m,'research',host)
    out = tmp_path/'run'
    with pytest.raises(RuntimeError, match='host unavailable'):
        m.run_loop('unused',out,'topic')
    assert json.loads((out/'status.json').read_text())['completed_reports'] == 2
    assert len(json.loads((out/'reports.json').read_text())) == 2


def test_dedup_keeps_each_agents_reading_and_disagreement():
    rows = [dict(role='domain', sources=[dict(doi='10.1/ABC', url='https://a', title='A', finding='supports')]),
            dict(role='critical', sources=[dict(doi='https://doi.org/10.1/abc', url='https://b', title='A', finding='limited')])]
    merged = api().merge_sources(rows)
    assert len(merged) == 1
    assert [v['source']['finding'] for v in merged[0]['observations']] == ['supports', 'limited']


def test_initial_reports_are_blind_and_budget_does_not_mean_sufficient():
    m = api()
    assert 'SECRET_PEER' not in m.build_prompt('domain', 'topic', 1, [{'summary':'SECRET_PEER'}])
    assert 'SECRET_PEER' in m.build_prompt('domain', 'topic', 2, [{'summary':'SECRET_PEER'}])
    reports = [{'sufficient':False,'gaps':['missing direct observation']}]
    assert m.stop_reason(reports, 3, 3) == 'budget_reached_with_gaps'
    assert m.stop_reason(reports, 1, 3) is None
    assert m.stop_reason([{'sufficient':True,'gaps':[]}], 1, 3) is None
    assert m.stop_reason([{'sufficient':True,'gaps':[]}], 2, 3) == 'reviewed_candidate_set'
