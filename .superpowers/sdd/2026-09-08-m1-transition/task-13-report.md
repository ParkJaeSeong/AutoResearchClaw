# Task 13 — Read-only return plans and dependency impacts

Implemented on `feature/m1-research-graph`, following approved Task 12 including
its exact JSON replay fix. Root committed its Task 12 acceptance while this
worker was active; the implementation's parent is `8e049c0`. Worker changes are
limited to `transitions.py`, `test_transitions.py`, the return-plan CLI route in
`m1_cli.py`, and this report. Root-owned UI/viewer, live project, transcript and
other documentation were not edited or staged. No agents were spawned.

## Public contract

```python
from researchclaw.core.m1.transitions import affected_attempts, plan_return

plan = plan_return(root, decision_id='decision-live-r1',
                   target_node_id='hypothesize', issue_ids=[...])
```

```sh
researchclaw-codex m1 return plan ROOT --decision ID --target NODE --issues ID [ID ...] --json
```

`affected_attempts` consumes projected attempts whose input/output refs are
ArtifactRef ID strings. It returns a sorted tuple of the complete recursive
consumer closure, including reversed dependency ordering and cycles, without
mutating inputs. No graph position or logical-path similarity creates an edge.

`plan_return` reads and verifies the current store; requires the registered
return decision, current decided review/session, exact input/approval binding,
its authorized graph return target and unique nonempty issue IDs belonging to
that same frozen session. It rejects M2/forward destinations, silent retargeting,
stale reviews/evidence/approval, foreign issues and blanket reset requests. Work
and rationale must be explicit and nonempty. A second read detects HEAD changes
during planning. There is no historical-head argument, mutation lock, fsync,
attempt creation, approval change, budget debit or object rewrite.

The proposed revision boundary is the authorized target node's exact latest
registered output ArtifactRefs. Their registered producer attempts and all
recursive consumers are affected. The producer is never advertised as fully
reusable. Unrelated attempts/artifacts remain reusable, and **all** old records
remain preserved, including affected records. Seeds are prospective revisions;
the plan does not assert that new bytes already exist or judge the scientific
adequacy of free-form proposed work. Registered issue context, target outputs
and proposed work make the scope reviewable; this is not semantic verification
of every natural-language instruction.

Required TransitionPlan fields are present:
`from_attempt_id,target_node_id,reason_code,issue_ids,affected_attempt_ids,approval_effects`.
The complete extra fields are
`schema_version,workflow_version,input_head,project_id,decision_id,session_id,rationale,proposed_work,changed_artifact_ids,reusable_attempt_ids,reusable_artifact_ids,content_origin,provenance_status,id,plan_hash`.

`reason_code` distinguishes scope, question, search, source, corpus selection,
extraction, synthesis and hypothesis revisions. `approval_effects.current`
contains `approval_id,corpus_binding,approved`; `approval_effects.after_change`
contains `approval_required,screen_required,approval_id,corpus_binding`.
If impacted outputs intersect the exact approved corpus refs, future screening
and approval are required and the future identity/binding are null. The current
approval remains unchanged. Hypothesis, extraction and synthesis-only revisions
preserve the corpus approval unless exact dependency edges reach corpus outputs.

`plan_hash` is SHA256 of the canonical complete plan body excluding `id` and
`plan_hash`; `id` is `return-` plus that hash. Sorted issue IDs and dependency
results make identical requests at the same HEAD deterministic. Unrelated HEAD
churn changes the hash because `input_head` is included. Task 14 must validate
both the current HEAD and the complete recomputed plan before applying one.

## Verification

- RED: `.venv/bin/python -m pytest tests/codex_native/m1/test_transitions.py -q`
  reported **31 failed in 14.14s**, from the missing planner and CLI route.
- Initial implementation run: **30 passed, 1 failed in 15.62s**. The shell's
  unavailable unqualified `python` prevented the CLI edit script from running;
  rerunning that edit with `.venv/bin/python` installed the intended route.
- Focused GREEN: the same test command reported **31 passed in 16.06s**.
- Relevant regression: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_transitions.py tests/codex_native/m1/test_m1_cli.py
  tests/codex_native/m1/test_packet_cli.py tests/codex_native/m1/test_approvals.py -q`
  reported **59 passed in 19.56s**, zero failures/skips. The prior 469-test M1
  baseline and full legacy suite were not repeated.
- `compileall -q` on the three changed Python files exited 0, and
  `git diff --check` produced no diagnostics.
- Tests snapshot every project file's bytes and mtime plus directory mtimes;
  valid and rejected planning preserve them. Tests also cover exact ID closure,
  no ordering-based invalidation, all eight targets, producer reuse exclusion,
  current/future approval separation, stale inputs and concurrent HEAD change.

## Root-owned actual acceptance

Root reported that read-only planning for the actual three-revise decision
`decision-live-r1` succeeded with all six issue IDs. Its saved plan ID is
`return-9c7d826584cf677260ef97a104777f178a9598740d34068ff48602b70685c134`.
The target is `hypothesize`; two attempts (the prior hypothesis and review) are
affected, seven earlier attempts remain reusable, and the existing approval is
preserved with `after_change.approval_required:false`. Root reported a byte,
mtime and mode snapshot unchanged and saved its own `live-return-plan-r1.json`.
Earlier synthetic checkpoint provenance remains declared. This worker did not
access or mutate the root's actual project. No plan was applied; Task 14 owns
new attempts and budgets. Root owns independent review of this exact commit.

## Review fix round 1 — Scoped edits are not global resets

Independent review demonstrated that the broad reset phrase check rejected the
valid immutable decision work: “Delete all unsupported causal claims from H1 and
retain the evidence-backed descriptive prediction.” The prior regex matched
`delete all` without examining what was being deleted. The same issue affected
`redo all predictions` and `start over with H1 wording`.

The check now targets explicit whole-project/workflow/graph reset language,
all-stage/node resets, and unqualified standalone reset requests. Scoped edits
no longer trigger it merely because they contain `delete all`, `redo all`, or
`start over`. The authorized target and exact artifact dependency closure
continue to enforce the actual revision boundary. This is a narrow phrase-check
fix, not a general natural-language interpretation layer.

- RED: `.venv/bin/python -m pytest tests/codex_native/m1/test_transitions.py
  -k 'scoped_hypothesis_edits or blanket_reset' -q` reported **4 failed,
  4 passed, 28 deselected in 5.32s**. Three scoped H1 instructions incorrectly
  raised `m1_return_work_required`; an explicit whole-workflow restart was
  incorrectly accepted.
- GREEN: `.venv/bin/python -m pytest tests/codex_native/m1/test_transitions.py
  -k 'scoped_hypothesis_edits or blanket_reset or hypothesis_plan_reuses' -q`
  reported **9 passed, 27 deselected in 5.04s**. Accepted instructions preserve
  their exact work text, affect only hypothesis/review attempts, retain source,
  extraction and synthesis reuse, and preserve current corpus approval.
  Accepted and rejected requests preserve project bytes and mtimes.
- `git diff --check` produced no diagnostics. No broader suite was repeated.
  The root-owned actual plan/project and all UI/viewer files remain untouched.

## Review fix round 2 — Standalone “Start over.”

Re-review found that narrowing the phrase check also allowed the unspecified
standalone instruction “Start over.” Added one anchored alternative accepting
only surrounding whitespace and terminal punctuation around `start over`.
Scoped wording such as “Start over with H1 wording while retaining the
registered evidence.” remains accepted.

- RED: `.venv/bin/python -m pytest tests/codex_native/m1/test_transitions.py
  -k 'scoped_hypothesis_edits or blanket_reset' -q` reported **3 failed,
  8 passed, 28 deselected in 7.11s**. Standalone instructions with no punctuation,
  a period, or an exclamation mark and surrounding spaces were accepted.
- GREEN: the identical command reported **11 passed, 28 deselected in 5.41s**.
  Existing scoped H1 edits remain accepted and read-only snapshots remain
  unchanged for accepted and rejected requests.
- `git diff --check` produced no diagnostics. The implementation change is one
  regex alternative; only the planner and its tests are committed. Root-owned
  UI, live project/plan and acceptance files remain untouched.
