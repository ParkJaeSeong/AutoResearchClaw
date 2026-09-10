"""Match new native submissions to saved host answers and disclosure packets."""
import json
from study_host import BASE, head, save
run=BASE/'selection-hypotheses-01'
h=head(); state=h['state']
artifact=json.loads((run/'artifact.json').read_text())
sessions={r['session_id'] for r in state['councils'].values() if r['attempt']==artifact['attempt']}
submissions=[r for r in state['council_submissions'].values() if r['session_id'] in sessions]
assert len(sessions)==1 and len(submissions)==9
hosts={}
for p in run.glob('*/answer.json'):
 events=[json.loads(s) for s in (p.parent/'events.jsonl').read_text().splitlines() if s.startswith('{')]
 assert all(e.get('item',{}).get('type') in (None,'agent_message','reasoning') for e in events)
 identity='codex-exec:'+next(e['thread_id'] for e in events if e['type']=='thread.started')
 assert identity not in hosts
 hosts[identity]=json.loads(p.read_text())
 packet=json.loads((p.parent/'packet.json').read_text())
 phase=p.parent.name.split('-')[-2]
 expected={'initial':(0,0),'response':(3,0),'final':(3,3)}[phase]
 assert (len(packet['disclosed_initials']),len(packet['disclosed_responses']))==expected
 assert not packet['disclosed_finals']
assert len(hosts)==9
for row in submissions:
 answer=hosts[row['host_id']]
 assert row['rationale']==answer['rationale'] and row['recommendation']==answer['recommendation']
 assert len(row['issue_proposals'])==len(answer['issues'])
 for issue, proposed in zip(row['issue_proposals'],answer['issues']):
  assert all(issue[k]==v for k,v in proposed.items())
assert not state.get('approval_bindings') and not state.get('verification_runs_used')
result=dict(head_id=h['id'],new_submissions=9,total_submissions=len(state['council_submissions']),
 answer_match=True,phase_disclosure_checked=True,role_tool_calls=0,
 recommendations={r['producer_id']:r['recommendation'] for r in submissions if r['phase']=='final'},
 open_issues=sum(v=='open' for v in state['issue_states'].values()),
 corpus_approved=False,experiments_executed=False,isolation='instructions_only',
 model_identity='codex-cli configured default; cross-model diversity unverified')
save(run/'audit.json',result)
print(json.dumps(result,ensure_ascii=False))
