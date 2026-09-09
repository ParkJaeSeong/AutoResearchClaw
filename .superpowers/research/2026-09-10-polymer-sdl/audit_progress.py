"""Read-only role-output and native-state audit; writes only the audit summary."""
import json
from study_host import BASE, REPO, head, save, snap
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.m1_search import prepare_search_council

h = head()
s = h['state']
hosts = {}
for run in (BASE / 'host-runs').iterdir():
    if not (run / 'answer.json').exists():
        continue
    events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines() if line.startswith('{')]
    assert all(e.get('item', {}).get('type') in (None, 'reasoning', 'agent_message') for e in events)
    identity = 'codex-exec:' + next(e['thread_id'] for e in events if e['type'] == 'thread.started')
    assert identity not in hosts
    hosts[identity] = json.loads((run / 'answer.json').read_text())
submissions = list(s['council_submissions'].values())
assert len(hosts) == len(submissions) == len({row['host_id'] for row in submissions})
for row in submissions:
    answer = hosts[row['host_id']]
    assert row['rationale'] == answer['rationale']
    assert row['recommendation'] == answer['recommendation']
    assert row['content_origin'] == 'real'
    assert len(row['issue_proposals']) == len(answer['issues'])
    for issue, proposed in zip(row['issue_proposals'], answer['issues']):
        assert all(issue[k] == v for k, v in proposed.items())
status = prepare_search_council(snap(), node_id='screen')
assert status['review_ready'] and not status['approved']
assert status['reason_codes'] == ['corpus_approval_required']
assert not s.get('approval_bindings') and not s.get('verification_runs_used')
old = store.read_head(REPO / '.superpowers/sdd/m1-ui-test/native-live-project')
assert old['id'] == '23e00ee20dc06c1ae2a55268765ccd0b01954270c109b250c147866d1d126fce'
result = dict(project_id=s['project_id'], head_id=h['id'],
    stage='scope, questions, search and screen reviewed; actual corpus decision pending',
    actual_host_sessions=len(hosts), actual_submissions=len(submissions), host_answers_match=True,
    role_tool_calls=0, open_issues=[dict(id=i, question=v['question'], severity=v['severity'],
        status=s['issue_states'][i]) for i,v in sorted(s['issues'].items()) if s['issue_states'][i]=='open'],
    corpus_approved=False, corpus_ref=status['corpus_ref'],
    model_training_or_experiments_executed=False, model_identity='configured default, unverified',
    isolation_level='instructions_only', browser='User confirmed direct browser display; automated control unverified',
    previous_synthetic_project_head_unchanged=True)
save(BASE / 'progress.json', result)
print(json.dumps({k:v for k,v in result.items() if k!='open_issues'}, ensure_ascii=False))
print(json.dumps({'open_issues':len(result['open_issues']), 'screen':status['reason_codes']}))
