# Task16 implementation complete; browser visual acceptance blocked

Authorized scope: connect Tasks08–16 to a local read-only UI. Root owns UI under Sites skill. No external deployment, push, merge, or Task17+ integration.

## Delivered

- `researchclaw-codex m1 view ROOT --port PORT` prints the actual loopback URL and runs until interrupted. Final live CLI server: http://127.0.0.1:8766/ (session45216).
- Fixed verified project root; static allowlist; GET view + registered visible raw artifact with identity/hash/size checks; Host/Origin restrictions; modifying methods405; inert text, CSP/no-store.
- Three-second serial polling, unchanged HEAD skips render, retained selections/disclosures/scroll, timeout/error and last-update display. Read-only UI shows current node separately from selected node, session roles/initials/responses/finals, issues, candidate decisions, sources, prior attempts and exact same-hypothesis parent/child comparisons.
- Actual synthetic-checkpoint project: three real r1 host roles, 6 issues,12 responses,3 revise final positions,1 return decision, return budget1/2, H1r1→r2, second review with three fresh actual independent host initials. No r2 responses/finals/ready decision or actual experiments. Registered provenance remains declared_only, not signed host authentication.

## Verification

TDD history: polling missing implementation RED4→GREEN4; selection RED2→GREEN2; viewer missing module RED5→GREEN5; CLI missing route RED1, then None-redactor integration failure fixed. Final Python command:
`.venv/bin/python -m pytest tests/codex_native/m1/test_viewer.py tests/codex_native/m1/test_views.py tests/codex_native/m1/test_m1_cli.py tests/codex_native/m1/test_resume.py -q`
**40 passed in19.78s**, including9 viewer tests (real build_view HTTP integration and immutable project reads). Initial command typo test_cli.py yielded no tests; corrected to test_m1_cli.py above.

Independent review found two real-schema mismatches: current node selection used demo status; multi-candidate comparison used first two refs. RED2 reproduced; fixed current_node_id/current plus aria-current and parent/child identity matching for all decision-pinned candidates. Post-task-review `node --test tests/ui/m1/*.test.mjs`: **16 passed**. Independent scoped re-review Approved, no induced findings; reviewer independently reran16 tests. `git diff --check` passed.

Final CLI HTTP checks: all seven UI/API routes200/no-store; all visible actual artifacts200/plain text; current review;2 sessions; r2 collecting_responses with3 disclosed initials;1 decision;6 issues;12 responses;21 artifacts. Selected session by stable ID (initial acceptance script incorrectly assumed array-last meant chronological-latest; corrected script, no product change). Node helpers on actual registered view validate exact H1r1→r2 with no missing references. Original32 objects and9 old attempts preserved after return/revision/second submissions.

Independent r2 privacy HTTP checks: after first and second registration zero initials disclosed and original rationale absent; after third all3 disclosed. These are API assertions, not browser polling observations. Transcript contains unchanged actual worker payloads and host observation hashes.

## Unfinished acceptance / explicit blocker

CUA Chrome navigation and final reload of8766 return ERR_BLOCKED_BY_CLIENT while CLI HTTP requests succeed. User informed and async direct-browser check requested. No browser security setting changed/bypassed. Actual 360/736px light/dark layout, long/script text rendering, clicked navigation and scroll preservation, and visual disconnection/recovery **not verified**. Code implementation/review approval does not complete this visual acceptance. Keep Task16 status implementation complete / visual acceptance pending.

Full legacy baseline was previously interrupted; scoped passing results do not imply whole repository green. Task17–20 full early-node integration/handoff/install are outside authorized slice.

Final integration review additionally found missing registered decision/return route labels. Added title/id and explicitly permitted-route fallbacks; regression RED1 then final Node17 passed. No executed-return detail/reuse-list UI claim; actual decision rationale and pinned revision comparison are connected.

Final integration Approved after navigation fixes; final full Node suite17passed, independent reviewer scoped selection/navigation5passed. Python final40passed remains applicable (no subsequent Python changes). Visual acceptance pending.
