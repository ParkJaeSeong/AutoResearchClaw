# Task 14 — Atomic returns, explicit budgets and resumable revision context

Implemented on `feature/m1-research-graph` after approved Task 13. Root committed
its Task 13 acceptance during this work, so the implementation parent is
`8479261`. Worker changes are limited to `budgets.py`, `transitions.py`,
`project.py`, `packets.py`, `m1_cli.py`, `test_budgets.py`, `test_resume.py`, and
this report. No agents were spawned. Root-owned UI/viewer, live project,
transcript, and acceptance documentation were not edited or staged.

## Public workflow

```sh
researchclaw-codex m1 return apply ROOT --plan plan.json --command-id return-r1 --json
researchclaw-codex m1 node prepare ROOT --node hypothesize --command-id prepare-r2 --json
researchclaw-codex m1 resume ROOT --json
```

`apply_return(root, *, plan, command_id)` returns `receipt`, `transition`,
`attempt`, `packet`, and `budget`. It validates current HEAD and every field of
the freshly recomputed plan using exact canonical JSON. Stale plans fail with
`m1_head_conflict`; modified complete plans fail with `m1_return_plan_invalid`.
A matching command replays its original receipt even after HEAD advances; any
changed request under that command raises `m1_command_conflict`, including a
JSON boolean replacing an integer. Replay does not debit again.

One store commit appends the transition and new target attempt, stores its
prepared packet, switches `current_node_id`, and increases `returns_used` by
exactly one. Prior attempts, artifacts, decisions, submissions and approval
records remain unchanged. The new attempt has the next node revision and its
prior target attempt as parent, plus the return transition ID. It is fully
prepared, so the existing `node prepare` reuses the exact attempt and packet.
The only `packets.py` change extracts its existing in-memory draft constructor
for atomic use by application; it preserves the normal first-attempt behavior.
Mutable work directories may exist after a failed pre-HEAD publication, but
only published HEAD ancestry determines the current attempt and budget.

For hypotheses, write a cumulative envelope retaining the exact H1 revision 1
record and adding revision 2 with parent_revision 1, the same author identity,
and an explicit change_reason. Register through the existing packet API and
prepare a new council with this new attempt ID. Registration does not itself
select the candidate or settle the previous issues.

## Budget and repeated-work contract

`can_start_return(*, used, limit)` requires exact nonnegative integers and returns
`used < limit`. Exhaustion raises `m1_return_budget_exhausted` before application
creates work. `set_return_budget(root, *, limit, note, command_id)` is only an
explicit caller-declared user instruction, with a nonempty note and
`declared_only` provenance. It records old/new ceilings without changing usage
or authorizing research. A ceiling may be lowered below existing usage, which
exposes exhaustion while retaining history. It never increases automatically.
The equivalent CLI is:

```sh
researchclaw-codex m1 budget set ROOT --max-returns N --note TEXT --command-id ID --json
```

The no-new-basis hash uses the target node, consumed artifact logical paths and
SHA256 content, immutable research config (`topic`, `profile`, `content_origin`),
sorted issue question/impact/severity/resolution-condition content, exact
hypothesis target references and cited artifact logical paths/SHA256 content,
and sorted proposed-work text. It excludes HEAD, plan, decision, session, issue, assignment,
attempt and ArtifactRef UUIDs, plus budgets and usage. Consumed prior hypothesis
content is included, so a genuinely changed cumulative hypothesis is a changed
input. New record IDs with unchanged content, reordering the same work, or
changing the budget alone do not supply new work. A prior matching basis raises
`m1_no_new_basis`. Historical bases are recomputed from each transition's
immutable decision and its returned packet's pinned inputs and configuration;
the recorded `basis_hash` is audit data, not the authority for comparison.
This preserves correct comparison for the actual return already applied while
the projection was being refined, without rewriting that transition or receipt. Text/content identity is a structural guard, not a scientific
novelty judgment or semantic natural-language equivalence engine. Explicit new
search work may authorize a return before new source files exist.

## Resume and interruption

Resume reads one verified HEAD and adds explicit budget status, the last return
context, current decision, and unresolved issue threads. A valid decided return
advertises `plan_return`; exhaustion preserves `await_user` with the budget
reason. Revoked approval and stale inputs retain their waits. New review
collection retains its pending reviewer IDs and the earlier return reason.
Role/session failure is visible with `await_user` and an explicit reason.

After cumulative hypothesis registration, resume compares the packet's pinned
prior-hypothesis input alongside current upstream inputs. This avoids treating
the packet's own new output as stale input while still exposing a changed scope
or other consumed upstream input. Corpus approval waits remain visible.

## Verification

- Initial TDD RED: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_budgets.py tests/codex_native/m1/test_resume.py -q`
  reported **37 failed in 9.55s**, reaching missing-feature assertions, missing
  CLI functionality and absent resume fields.
- During implementation, the canonical serializer correctly rejected a tuple
  in the basis projection; it was corrected to a JSON list. The repeated-review
  fixture was then strengthened to register unchanged hypothesis bytes, a fresh
  independent council and a fresh decision through public APIs, instead of
  trying to reactivate a stale historical source. Fresh frozen finals are used
  exactly as required by decision registration.
- Two added stale-resume tests reported **2 failed, 6 deselected in 6.67s**:
  a revoked review approval was incorrectly advertised as returnable and stale
  upstream inputs were incorrectly advertised as reviewable. Both were fixed.
- Focused GREEN: the initial command reported **40 passed in 120.58s**, with no
  failures/skips. It covers atomic one-debit application, preserved historical
  records/objects, exact replay after HEAD movement, complete plan validation,
  stale plans, budget validation/exhaustion/declaration/replay, public unchanged
  review rejection despite fresh IDs and a budget change, explicit new work,
  search before new files, both CLI commands, returned r2 registration and a new
  independent council, approval/role waits, and failures before/after HEAD.
- Additional reorder RED: the fresh-ID test with reordered work reported
  **1 failed, 32 deselected in 63.09s** because the repeated return was accepted.
  The basis now sorts work strings while the stored authored order is preserved.
- Final reorder/fresh-ID/new-work regression: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_budgets.py -k 'not_new_basis or additional_declared_work' -q`
  reported **3 passed, 30 deselected in 150.23s**, zero failures/skips.
- Scoped existing regression: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_transitions.py tests/codex_native/m1/test_project.py
  tests/codex_native/m1/test_packets.py tests/codex_native/m1/test_packet_cli.py
  tests/codex_native/m1/test_hypotheses.py tests/codex_native/m1/test_council.py
  tests/codex_native/m1/test_approvals.py tests/codex_native/m1/test_m1_cli.py -q`
  reported **175 passed in 366.37s**, zero failures/skips. This scoped suite ran
  alongside focused tests; the full 469-test baseline and repository suite were
  not repeated.
- Issue-evidence precision RED: `test_issue_bound_to_different_evidence_is_a_new_basis`
  reported **1 failed, 33 deselected in 54.70s**, because a different cited
  artifact was incorrectly collapsed into the same issue basis. Issue signatures
  now include exact target refs and cited artifact paths/content.
- Historical-cache RED: the fresh-ID case with a deliberately obsolete stored
  hash reported **1 failed, 33 deselected in 51.42s**, because only the cache was
  compared. Historical comparison now uses the committed returned packet inputs
  and configuration plus the recorded decision, never latest inputs or config.
- Final affected basis regression: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_budgets.py -k 'not_new_basis or additional_declared_work or different_evidence' -q`
  reported **4 passed, 30 deselected in 118.65s**, zero failures/skips. This
  covers fresh IDs and obsolete cached hashes with unchanged research, work
  reordering, genuinely additional work, and differently cited issue evidence.
  No broad regression was repeated after this localized projection change.
- Final `compileall -q` on the seven changed Python files exited 0.
  `git diff --check` and `git diff --cached --check` produced no diagnostics.
  The staged-name check contained exactly the eight worker-owned files above.

## Actual host acceptance

Root owns the actual return of its registered three-revise, six-open-issue
`decision-live-r1`, authoring H1 revision 2, and beginning a new independent
council. The actual workflow was provided as soon as the public synthetic
integration passed. No budget increase is planned; the configured ceiling is
2. This worker never accessed or modified the actual live project, supplied
reviewer dialogue, or replaced actual host evidence with the synthetic helper.
Root will record actual before/after and host execution evidence separately.

Root subsequently reported successful actual application with budget **1/2** and
new attempt `attempt-3e705049f5c9408594327098065e5802`; existing prepare reused its
attempt and packet. Root authored and publicly registered cumulative exact H1r1
plus H1r2, narrowing the claim without claiming new evidence, then prepared
`session-6de17ed4c0c648ce805801d5e5eb574a` in `collecting_initials` with fresh host
assignments. Root verified all pre-return **32 objects and 9 attempt records**
remain identical. Actual r2 workers were to launch during root's UI acceptance;
this is new-review waiting evidence, not completed actual r2 deliberation.
Root also reported that an assignment input containing unpermitted
`allowed_outputs` was correctly rejected; correcting only the root-authored
input to the documented three fields succeeded, requiring no product fix.
