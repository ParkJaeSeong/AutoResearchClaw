"""Read-only acceptance checks against actual CLI/host records, not fixtures."""
import hashlib
import json
from pathlib import Path
from live_host import BASE, ROOT
from researchclaw.core.research_graph import store
from researchclaw.core.research_graph.views import build_view

logs = [json.loads(line) for line in (BASE / 'command-log.jsonl').read_text().splitlines()]
first = next(row for row in logs if row['operation'] == 'council.submit')
submission = json.loads(Path(first['payload_file']).read_text())['submission']
selected = first['receipt']['head_id']
before = store.read_head(ROOT)['id']
historical = build_view(ROOT, head_id=selected)
serialized = json.dumps(historical, ensure_ascii=False)
for private in (submission['id'], submission['event_id'], submission['rationale'],
                hashlib.sha256(store._canonical(submission)).hexdigest()):
    assert private not in serialized, 'Partial real initial leaked through historical view'
assert historical['head_id'] == selected and historical['current_head_id'] == before
assert historical['councils'][0]['submitted_counts']['initial'] == 1
assert not historical['councils'][0]['disclosed_initials']
view = build_view(ROOT)
hosts = []
for path in (BASE / 'host-runs').glob('*/events.jsonl'):
    events = [json.loads(line) for line in path.read_text().splitlines() if line.startswith('{')]
    assert events[-1]['type'] == 'turn.completed', path
    assert all(e['item']['type'] in ('agent_message', 'reasoning') for e in events if e.get('item')), path
    hosts.append(next(e['thread_id'] for e in events if e['type'] == 'thread.started'))
assert len(hosts) == len(set(hosts)), 'Expected fresh independent role sessions'
assert store.read_head(ROOT)['id'] == before, 'Read-only check changed HEAD'
report = {'head_id': before, 'content_origin': view['content_origin'], 'native_nodes': len(view['nodes']),
          'registered_revisions': len(view['revisions']),
          'actual_fresh_host_sessions': len(hosts), 'actual_host_tool_calls': 0,
          'councils': len(view['councils']),
          'public_submissions': sum(len(c[key]) for c in view['councils'] for key in ('disclosed_initials', 'disclosed_responses', 'disclosed_finals')),
          'issue_states': [{'id': row['record']['id'], 'node': row['record']['origin']['node'],
                            'severity': row['record']['severity'], 'status': row['status']} for row in view['issues']],
          'historical_partial_initial_hidden': True, 'selected_head_preserved': True,
          'model_identity': 'unverified configured Codex CLI default', 'isolation_level': 'instructions_only',
          'synthetic_authority_only': True, 'real_corpus_approval': False, 'M2_experiments_executed': False}
(BASE / 'live-check-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))
