"""Re-audit every finished role from raw CLI events; preserve original reports."""
import json
from datetime import datetime, timezone
from pathlib import Path
from researchclaw.codex.literature_loop import audit_events, merge_sources, save

BASE = Path(__file__).resolve().parent
RUN = BASE / 'discovery-runs/restart-01'
reports, runs = [], []
for directory in sorted(RUN.iterdir()):
    if not directory.is_dir():
        continue
    events = [json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines() if line.startswith('{')]
    try:
        observed = audit_events(events)
    except ValueError:
        if (directory/'report.json').exists():
            raise
        runs.append(dict(run=directory.name, finished=False, status='awaiting_observed_search'))
        continue
    row = dict(run=directory.name, host_id=observed['host_id'], web_calls=observed['web_calls'],
               observed_queries=len(observed['queries']), finished=(directory/'report.json').exists())
    if row['finished']:
        report = json.loads((directory/'report.json').read_text())
        answer = json.loads((directory/'answer.json').read_text())
        assert all(report[k] == answer[k] for k in ('summary','queries','gaps','next_queries','sufficient','disagreements'))
        assert len(report['sources']) == len(answer['sources'])
        for source, declared in zip(report['sources'],answer['sources']):
            assert all(source[k] == v for k,v in declared.items())
            source['query_observed'] = source['query'] in observed['queries']
        report['observed'] = observed
        row.update(candidate_records=len(report['sources']),
                   unverified_query_links=sum(not s['query_observed'] for s in report['sources']))
        reports.append(report)
    runs.append(row)
summary = dict(as_of=datetime.now(timezone.utc).isoformat(), status=json.loads((RUN/'status.json').read_text()),
               runs=runs, finished_reports=len(reports),
               unique_reported_candidates=len(merge_sources(reports)),
               count_scope='completed reports only; not all search-engine hits, not all full texts read',
               m1_complete=False, native_corpus_updated=False)
save(RUN/'audited-reports.json',reports)
save(BASE/'discovery-audit.json',summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
