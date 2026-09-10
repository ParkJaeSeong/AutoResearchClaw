# Discovery UI and research synthesis implementation plan

User approved connecting actual discovery results to existing UI, then narrowing
sources and developing material/hypothesis proposals. Existing worktree is used.

Architecture: dedicated read-only `/api/discovery` for an explicitly configured
run directory, alongside unchanged native `/api/view`. The UI polls both; an
unchanged native HEAD must not hide discovery updates. Historical HEAD selection
does not mix latest exploration into historical native records. No corpus consent
or native verified evidence is manufactured from exploration reports.

- [x] Backend: add `researchclaw/codex/discovery_view.py`, viewer `--discovery-root`
  wiring and GET endpoint. Validate run topic matches project, constrain file
  access, expose only report fields (never prompts/raw telemetry). Reused reports
  remain included; incomplete peer rounds remain undisclosed. Tests cover topic
  mismatch, partial rounds, update with same native HEAD, no mutation and invalid
  paths. Command: `.venv/bin/python -m pytest tests/codex_native/test_discovery_view.py -q`.
- [x] Frontend: add `research_ui/discovery.js`, render same-page status/role counts,
  searchable source list, source-specific interpretation and limitations, round
  reports and disagreements, provisional selection/hypotheses. Poll independently;
  retain last good snapshot on failure; use textContent and safe HTTP(S) links.
  Test rendering, filtering, stale/error state and updates without HEAD changes.
- [x] Research: assess completed9 reports/197 candidate records; record draft
  selection groups and hypotheses in `restart-02/selection.json` and concise user
  document. Retain low-access/contrary sources and unresolved issues. No fabricated
  scientific verification, equipment, private data or user corpus approval.
- [x] Integration: restart only the study viewer on8768 with explicit discovery
  root, verify real API counts and both datasets on one screen, run relevant
  tests and independent code review, preserve original run/native project bytes.

API contract: schema_version, revision digest, available, status, round,
max_rounds, completed_reports, unique_candidates, candidate_records, m1_complete,
roles[{role,round,status,last_activity_at,web_calls}], reports (scientific fields
only), sources[{key,title,observations[{role,round,source}]}], limitations[],
selection (null or {status,summary,groups[{id,title,reason,source_keys}],
hypotheses[{id,statement,test,limits}],unresolved[]}). All counters refer to
reported candidates rather than search-engine hits or full-text reads.

Validation: 15 Python tests and16 JS tests passed; actual Chrome UI and197/245/9 counts verified. Independent review corrections included failed-role status and agent-declared provenance labels.
