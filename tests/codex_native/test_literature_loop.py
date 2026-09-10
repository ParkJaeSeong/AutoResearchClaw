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


def test_monitor_does_not_kill_host_when_poll_interval_expires(tmp_path):
    import subprocess
    class Process:
        pid = 123
        calls = 0
        def wait(self, timeout):
            self.calls += 1
            if self.calls < 3:
                raise subprocess.TimeoutExpired('host',timeout)
            return 0
        def kill(self):
            pytest.fail('Monitoring must not kill ongoing research')
    process = Process()
    assert hasattr(api(),'wait_for_host'), 'Non-destructive host monitoring is missing'
    assert api().wait_for_host(process,tmp_path,interval=0.01) == 0
    assert process.calls == 3


def test_resume_reuses_finished_roles_and_retries_only_missing_work(tmp_path, monkeypatch):
    import inspect
    import json
    m = api()
    assert 'resume_from' in inspect.signature(m.run_loop).parameters, 'Resumable discovery is missing'
    old = tmp_path/'old'; old.mkdir()
    (old/'run.json').write_text(json.dumps({'topic':'topic'}))
    for n,role in [(1,r) for r in m.ROLES] + [(2,'critical')]:
        d=old/f'round-{n}-{role}'; d.mkdir()
        (d/'report.json').write_text(json.dumps(dict(role=role,round=n,sources=[],
            sufficient=True,gaps=[],next_queries=[])))
    calls=[]
    def host(*args, **kwargs):
        role,n=args[2],args[4]; calls.append((n,role))
        assert len(args[5])==3 and all(r['round']==1 for r in args[5])
        return dict(role=role,round=n,sources=[],sufficient=True,gaps=[],next_queries=[])
    monkeypatch.setattr(m,'research',host)
    result=m.run_loop('unused',tmp_path/'new','topic',resume_from=old)
    assert sorted(calls)==[(2,'domain'),(2,'methodology')]
    assert len(result)==6


def test_default_run_has_no_hard_timeout():
    import inspect
    assert 'timeout' not in inspect.signature(api().run_loop).parameters


def test_resume_keeps_complete_events_before_truncated_tail(tmp_path):
    import json
    (tmp_path/'run.json').write_text(json.dumps({'topic':'topic'}))
    d=tmp_path/'round-2-domain'; d.mkdir()
    event={'type':'item.completed','item':{'type':'web_search','id':'w','query':'polymer'}}
    raw=json.dumps(event)+'\n'+ '{"type":"item.'
    (d/'events.jsonl').write_text(raw)
    _, recovery=api().resume_inputs(tmp_path,'topic')
    assert recovery[(2,'domain')]['completed_web_actions']==[event['item']]
    assert recovery[(2,'domain')]['trailing_partial_event'] is True
    assert (d/'events.jsonl').read_text()==raw
    (d/'events.jsonl').write_text('{broken}\n'+json.dumps(event)+'\n')
    with pytest.raises(json.JSONDecodeError):
        api().resume_inputs(tmp_path,'topic')
