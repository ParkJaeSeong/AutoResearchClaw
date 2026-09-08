# Task 11 — Issues, responses and final positions

Implemented Task 11 in the isolated M1 worktree from `da71d3d`. This worker
changed only the council source, issue projection, CLI, focused tests, council
reference, and this report. It did not mutate the live project, author role
opinions, spawn agents, add a decision engine, or stage the controller-owned
Task 16 files present in the shared worktree.

## Validation evidence

- TDD RED: `.venv/bin/python -m pytest tests/codex_native/m1/test_issues.py
  tests/codex_native/m1/test_council.py -q` initially reported **14 failed, 37
  passed** for the absent issue validator, response/final registration, packet
  phases, and CLI routes. One test helper argument collision was corrected;
  its five cases were rerun and all then failed because the production issues
  module was absent.
- Focused GREEN: the same command finally reported **60 passed in 50.56s**,
  zero failures/skips. Separate RED/GREEN checks proved malformed issue IDs
  return a validation error and duplicate response references are rejected
  rather than crashing or being accepted.
- Scoped M1 and relevant legacy deliberation regression:
  `.venv/bin/python -m pytest tests/codex_native/m1
  tests/codex_native/test_task_packets.py tests/codex_native/test_deliberation.py
  -q` finally reported **348 passed in 63.41s**, zero failures/skips.
- `.venv/bin/python -m compileall -q` on the three owned Python files and
  `git diff --check` both completed with exit 0 and no diagnostics. The full
  repository suite was not run, per task scope.

## Public contract and lifecycle

`validate_response(response, *, issue_ids, assignment_ids)` returns structured
problems for an exact response record. Response stance is `accept`,
`partly_accept`, `challenge`, or `insufficient_evidence`; every stance requires
a nonempty rationale and a unique evidence-reference list.

`register_response(root, *, session_id, assignment_id, payload, command_id)`
accepts one exact caller-authored bundle per active role after initial
disclosure. The bundle binds session, assignment, role, declared host and input
version; it contains a required explanation, zero or more issue-linked
responses, and zero or more new issues. An empty list is accepted only as part
of a real submitted bundle with an explicit explanation. The engine never
manufactures a role's empty response. Response entries and new issues use the
assignment ID as identity, not the role name. New issues preserve the complete
Issue record; `related_issue_ids` links related records without merging or
overwriting their IDs, raisers, wording, targets or evidence.

After all three active assignments submit exactly one response bundle, the
engine freezes a sorted response snapshot and changes the session/review
attempt to `collecting_final_positions`. `register_final_position(...)` then
requires each role's exact identity and binding, one recommendation from
`ready`, `ready_with_limits`, `revise`, or `defer`, a nonempty opinion-change
explanation, overall rationale/evidence, and one disposition for every known
initial or response issue. A disposition may cite only registered responses to
that same issue. After all three positions the status is
`final_positions_complete`; no decision or progression is synthesized.

Assignments created by Task 10 remain unchanged with
`allowed_outputs:["initial"]`. Reviewer packets derive
`phase_allowed_outputs` and declare exact field types for initial, response and
final phases. They repeatedly state that `assignment_id` and new issue
`raised_by` equal `own_assignment.id`, never `role_id`. Exact command replay
returns its original receipt, an identical submission under a new command only
acknowledges the existing record, and changed second submissions fail.

`build_issue_threads(session)` keeps each source issue verbatim beside its
linked responses and each role's final disposition. Every issue stays `open`
until its raiser confirms resolution. A response-round issue additionally
needs one other role's resolved disposition; this is the explicit Task 11
ruling that prevents a newly raised objection from being cleared before
another role considers it. The projection records confirmation identities and
remaining opposition but does not decide whether the research advances.

CLI commands are:

```sh
researchclaw-codex m1 council response ROOT --session SESSION \
  --assignment ASSIGNMENT --submission response.json --command-id COMMAND --json
researchclaw-codex m1 council final ROOT --session SESSION \
  --assignment ASSIGNMENT --submission final.json --command-id COMMAND --json
```

## Actual host acceptance ownership

Root reported that the three existing actual role workers authored response
bundles against the frozen Task 10 snapshot and that all three bundles were
registered verbatim with this implementation. Root then supplied final-phase
packets to the same roles and registered all three returned final positions
verbatim. Root reported `final_positions_complete`; all three recommendations
were `revise`, with issue records remaining open and no new evidence or H1
revision invented. Root owns the live project, host observations, exact worker
files and acceptance documentation. This worker did not independently inspect,
edit or claim those artifacts.

## User check and limits

Read a completed role packet and inspect `issue_threads`: the preserved `issue`
identifies the original raiser and wording, `responses` shows which response
addressed it, `final_dispositions` shows each role's outcome and rationale, and
`status`, `resolution_confirmed_by` and `raiser_confirmed` show why opposition
remains. Final records are caller declarations with `declared_only` provenance;
the engine validates bindings and registered evidence IDs but does not
authenticate native host execution. Task 12 must evaluate the three final
positions, open blockers and approvals separately.
