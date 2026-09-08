# Task 12 — Hypothesis dispositions and next-action decisions

Implemented on `feature/m1-research-graph` from Task 11 commit `82fd0ca`.
This worker owns only `decisions.py`, `test_decisions.py`, the council decide CLI
route, the synthetic review helper, the council reference, and this report. It
has not edited or staged the root-owned UI/viewer, live project, transcript,
progress or C verification files, and has not spawned agents.

## Implementation and contract

`assess_readiness` collects every reason before computing readiness. It rejects
missing, duplicate and invalid roles, stale approval, absent selection, open
blockers and nonproceeding final recommendations. Missing/invalid prerequisites
or a defer recommendation yield `defer`; otherwise blockers or revise yield
`return`; no selection alone yields `stop`; passing every gate yields `handoff`.
The only success wording is **설계로 인계 가능**. No score or majority vote is
computed. Open nonblocking issues remain visible and can accompany
`ready_with_limits`.

`register_decision(root, *, session_id, payload, command_id)` binds a coordinator
submission to the current review, exact registered evidence, current approval,
and all three frozen final objects. It requires one disposition per latest
candidate revision, with reasons, every issue targeting that candidate and all
three final assignment references. `selected_hypothesis_ids` must exactly match
the selected disposition set. Authored hypothesis disposition labels cannot
supply readiness, and the decision does not rewrite hypothesis artifacts.

The `positions` array must equal the frozen disclosure, including exact JSON
types. `dissent` must preserve every exact final object whose role recommends
revise/defer or leaves an issue open. `issue_ids` must cover the complete session.
Stored issue threads preserve the original issues, responses, role dispositions
and raiser confirmation rule. The coordinator cannot alter opinions, omit a
candidate or dissent, invent evidence or override the pure readiness result;
policy conflicts raise `m1_decision_conflict`.

The exact payload is documented in
`skills/researchclaw/references/m1-council.md`. It includes explicit nonempty
rationale and proposed work for return/defer/stop. A return requires a nonempty
`return_target`; Task 13 owns graph-target validity and actual transitions.

The public CLI is:

```sh
researchclaw-codex m1 council decide ROOT --session SESSION \
  --submission decision.json --command-id COMMAND --json
```

Registration appends `state.decisions`, preserves source/review IDs and approval
identity, adds exact issue threads and `declared_only` provenance, and records
`decision_id` on the session and review attempt. Both become `decided`; the
current node remains `review` and the hypothesis author attempt is unchanged.
An exact command replay returns its original receipt. An identical payload under
a new command acknowledges the existing decision; a changed second decision
fails. No M2 execution or final handoff package is created. Existing council
resume maps this new terminal deliberation status to `await_user`; later graph
integration owns progression from the recorded decision.

`build_review_case(root, *, outcome)` accepts only `ready` or
`return_hypothesis`. Starting from `build_evidence_case` and an explicitly
synthetic earlier checkpoint, it registers hypotheses and all three roles'
initials, responses, finals and decision through public APIs. Its exact return
keys are `root`, `head_id`, `review_attempt_id`, `decision_id`, `hypothesis_id`.
Both outcomes are synthetic and declared_only, with no actual host execution
claim. Invalid outcomes fail before creating the project.

## Verification

- TDD RED: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_decisions.py -q` reported **41 failed in 47.71s**.
  The engine, CLI route and public review helper were absent. Tests reached
  explicit missing-feature assertions (and the absent CLI route).
- Focused GREEN: the same command reported **41 passed in 59.15s**, zero
  failures/skips. Coverage includes every readiness gate, malformed roles and
  payloads, exact frozen finals, dissent and candidate completeness, current
  approval/evidence binding, replay, preserved author attempts, CLI registration,
  and both public synthetic outcomes.
- Two additional integration cases verify independent selected/deferred/rejected
  candidate reasons despite contrary authored labels, and preserved open minor
  dissent with ready-with-limits recommendations. These execute in the scoped
  regression recorded below.
- Scoped M1 and relevant legacy regression: `.venv/bin/python -m pytest
  tests/codex_native/m1 tests/codex_native/test_task_packets.py
  tests/codex_native/test_deliberation.py tests/codex_native/test_research_decision.py
  -q` reported **469 passed in 254.16s (0:04:14)**, zero failures/skips. This
  includes all 43 decision tests and the root-owned seven viewer tests present
  at collection. The full repository suite was not run, per task scope.
- `compileall -q` on the four changed Python files completed with exit 0, and
  `git diff --check` produced no diagnostics.

## Actual host acceptance (root-owned evidence)

Root reported successful public registration of `decision-live-r1` from its
exact independently authored frozen final opinions and supplied coordinator
payload. The result is `ready:false`,
`reason_codes:["no_selected_hypothesis","open_blockers","opposed_final_role"]`,
`next_action:"return"`, `return_target:"hypothesize"`. All three actual final
positions recommend revise; all six open issues are preserved. The receipt is
root-owned `live-decision-receipt-r1.json`. This worker did not modify live
inputs, role opinions or evidence to manufacture readiness, and did not
independently inspect the root's host execution transcript. Root owns the
final-code CLI replay and host acceptance record.

## User check and remaining scope

For any stored decision, trace each `hypothesis_dispositions` entry through its
exact hypothesis reference, candidate issue IDs and all three final assignment
IDs to `positions`; inspect `dissent` and `issue_threads` for preserved concerns,
responses and resolution conditions. `rationale`, `proposed_work`, readiness
reason codes and the next action explain why the candidate proceeds or returns.
The engine validates declared records and references, not scientific truth or
native worker execution authenticity. Return planning, execution limits and
M1 finalization remain later tasks.

## Review fix round 1 — Exact JSON command replay

Independent review found that the shared `packets._replay` compared decoded
request dictionaries with Python equality before decision validation. That
comparison treated JSON `1` and `true` (or `false` and `0`) as identical and
replayed an existing receipt for a changed request. The stored decision was
not rewritten, but the command-conflict contract was violated.

The fix compares both requests using the existing `store._canonical` bytes;
no new serializer or normalization policy was introduced. Regression cases
change top-level `schema_version:1` to `true`, frozen final `schema_version:1`
to `true`, and `ready:false` to `0` under the original command ID. Each must
raise `m1_command_conflict`, preserve the exact HEAD bytes, and still replay the
unchanged original request with the original receipt and unchanged HEAD.

- RED: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_decisions.py::test_command_replay_rejects_json_numeric_boolean_changes_without_mutating_state
  -q` reported **3 failed in 6.65s**, each because no `ValueError` was raised.
- GREEN and shared replay regression: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_decisions.py tests/codex_native/m1/test_council.py
  tests/codex_native/m1/test_issues.py tests/codex_native/m1/test_artifacts.py
  tests/codex_native/m1/test_packet_cli.py tests/codex_native/m1/test_packets.py
  tests/codex_native/m1/test_approvals.py -k 'replay or durable_idempotent or
  persists_packet_reuses' -q` reported **13 passed, 149 deselected in 14.50s**,
  zero failures/skips. The earlier 469-test regression was not repeated.
- The fix changes only the shared request comparison, its three regression
  cases, and this report. Root-owned UI, live project and acceptance files
  remain untouched.
