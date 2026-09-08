# A03 implementation report

Dependency: A02 commit 599dcd3 independently Approved by root. Scope: explicit M1 import and narrow CLI import/inspect wiring. Worker used isolated pytest fixtures only; no actual live source or root acceptance target was mutated.

## APIs and migration schema

`migration.import_m1(source: Path, target: Path, *, source_head: str, command_id: str) -> dict` returns the internal immutable genesis receipt. It verifies current M1 reachable history, selects only ancestry through the requested source head, copies exact original canonical commit bytes and every selected registered object, constructs the complete native projection, and calls `store.initialize_record` once. Source reads create no source locks or files. Selected immutable bytes are rechecked before publication; subsequent source HEAD advances do not replace the selected snapshot.

State additions:
- `issues`: global UUID → A01 canonical Issue; owner remains null, category is other, severity/question/resolution condition preserved. Origin node is review and attempt maps the exact legacy review_attempt_id.
- `imported_issue_states`: UUID → original canonical disclosed `source_status` (open/resolved), pending_policy_revalidation import state, original session/local IDs, original_target_refs, target_mappings, and specific target limitations. No IssueEvent or inferred reviewer-authored resolution is created.
- `source_archive`: format_version=1, exact source_root/source_project_id/head_id, deterministic archived project UUID, original source_content_origin, commit ID→copied object SHA256, all selected source object refs, typed deterministic ID maps, read-only session metadata, and provenance limitations.
- `source_archive.id_map`: attempts maps both exact source/review attempt IDs; sessions maps original session IDs; issues nests original session ID→local ID→global UUID. UUID5 namespace is derived from original source project identity. Imported target project UUID binds source path and selected head, enabling byte-identical replay after target HEAD advances.
- `sessions` and `issue_events` are empty: historical councils are archived only.

Exact target resolution matches the session's single hypotheses input artifact to the selected registered artifact, verifies registered hash/size, and finds the unique original hypothesis ID+revision in the copied JSON. Native SnapshotRefs name the archived source UUID, original selected source head, original artifact ID and hash; per-target mappings preserve `/hypotheses/N`. Missing/ambiguous targets receive explicit limitations and never use a newer artifact. Evidence refs are not substituted as targets. Legacy `research` content_origin maps explicitly to `real`; synthetic/real/mixed retain their values, originals remain in archive metadata, unknown origins reject.

`migration.import_summary(head)` is an allowlist of source IDs/head, issue counts/status counts, import state, archived session count and limitations. Both `research import-m1 SOURCE TARGET --source-head HASH --command-id ID --json` and `research inspect TARGET --json` return safe summaries with `head_id`, versions, project/content origin, object/event counts and the import summary. Neither public response includes internal state/events/object refs, private initials or archive bodies. Python import returns an internal receipt for storage integration.

## Verification

RED observations: importer absent (10 deliberate failures); CLI import parser absent; review origin used wrong source attempt; legacy research origin rejected; malformed session shapes escaped as type errors; unknown pending-session origin accepted; public CLI initially returned internal receipt; exact target refs initially absent. Each was observed before its implementation/fix.

Focused migration+CLI: 21 passed in 0.47s. Earlier combined research graph + M1 store/project/CLI/packet CLI + codex CLI regression: 320 passed in 87.55s; this preceded the final exact-target extension, whose impacted suite is recorded below.

Coverage includes six open r1 issues surviving empty/pending r2, original source bytes/mtime/modes unchanged, selected historical isolation and exact commit/object copying, private pending initials absent from projections/public CLI, deterministic IDs and duplicate local IDs across sessions, canonical resolved status without native resolution events, replay after target/source advance, changed source/head command conflict, overlapping roots, nonempty targets, symlinks, unreachable/corrupt source, interrupted publication without completed HEAD, malformed legacy state, and exact artifact/revision target mapping.

Limitations: these are structural synthetic fixtures, not host-observed independence, real research acceptance, M1 readiness, M2 initialization, browser validation, installation or execution. Import preserves source claims as declared-only; policy/approval revalidation remains required. Archive data is read-only by workflow contract and reachable only through internal storage, not a newly exposed raw CLI route. No new lifecycle handlers, schema edits or execution authority were introduced. Root performs actual-data acceptance independently.

Final impacted regression: `.venv/bin/python -m pytest tests/codex_native/research_graph tests/codex_native/m1/test_store.py tests/codex_native/m1/test_project.py tests/codex_native/m1/test_views.py -q` — 206 passed in 9.67s. `git diff --check` clean. Independent A03 review remains root's next step.
