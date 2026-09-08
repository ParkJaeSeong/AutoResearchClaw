# Task 10 — Independent initials and frozen disclosure

Implemented Task 10 in the isolated M1 worktree from `dfa63a0`. Source, tests,
reference documentation and this report only; no live-project writes, agent
spawning, external dependency, LLM runner, merge or push from this worker.
Root explicitly authorized the narrow `project.py` resume integration after
ruling that review must have a real NodeAttempt.

## Validation evidence

- TDD RED: `.venv/bin/python -m pytest tests/codex_native/m1/test_assignments.py tests/codex_native/m1/test_council.py -q` — **28 failed in 7.90s** because assignment/council implementations were missing.
- Initial GREEN: same command — **28 passed in 18.82s**.
- CLI/resume RED: council tests — **2 failed, 30 passed in 20.17s**; missing CLI council command and review resume requiring an authoring packet.
- CLI/resume GREEN: council tests — **32 passed in 20.35s**.
- Additional privacy RED: nested corpus CLI receipt exposed a pending initial — **1 failed in 2.65s**. Fixed recursive receipt projection.
- Final scoped command: `.venv/bin/python -m pytest tests/codex_native/m1 tests/codex_native/test_task_packets.py tests/codex_native/test_deliberation.py -q` — **325 passed in 36.53s**, zero failures/skips.
- Compileall of owned Python files and `git diff --check` completed with exit 0 and no diagnostics.
- All integration checkpoints are explicitly synthetic and declared-only. The full legacy suite was not run.

Coverage includes missing/duplicate roles, duplicate assignment/host IDs,
author self-review and known author-host reuse, shared exact inputs, missing
initial non-disclosure, frozen all-three disclosure, malformed/cross-bound
initials and issues, stale registered evidence/hypotheses, approval revocation
and replacement, ignored mutable drafts, duplicate submissions and IDs,
historical command replay, retry after visible publication/durability failure,
failed-role replacement before disclosure, rejection of late old-role output,
retained prior initial history, replacement identity reuse, read-only CLI
errors, status privacy including nested receipts, and review resume.

## Public contract and lifecycle

`prepare_council(root, *, attempt_id, assignments, command_id)` takes the latest
current **hypothesize source attempt**, structurally registered at
`review_pending`. It atomically creates a `review` NodeAttempt and session,
sets current node to `review`, and preserves the source historical status.
The review attempt starts at `collecting_initials`, with empty output refs and
scientific validation `not_performed`. No decision or approval is fabricated.

Session fields include versions, `id`, `source_attempt_id`, `review_attempt_id`,
`input_binding`, `input_refs`, `approval_id`, `hypothesis_refs`,
`author_assignment_ids`, `author_host_task_ids`, `allowed_evidence`,
`assignments`, `assignment_history`, `initials`, `responses`, `final_positions`,
`disclosed_initials`, `status`, and `content_origin`.

`allowed_evidence` entries contain the exact registered artifact `ref` and
immutable UTF-8 `content`. Binding includes the project, source attempt,
current approval ID, sorted artifact IDs/hashes and project configuration.
The latest hypothesis producer must consume the latest synthesis and extraction;
synthesis must consume the latest extraction and manifest; extraction must
consume the currently approved corpus. New evidence or approval requires a new
authorized review context; this worker does not implement that return engine.

Assignment input is exactly `{id,role_id,host_task_id}` for the three roles
`domain`, `methodology`, `critical_reproducibility`. IDs and hosts are distinct.
The engine adds `session_id,input_binding,allowed_outputs:["initial"],
provenance_status:"declared_only"`. Authors' assignment IDs cannot judge; known
author hosts from optional hypothesis `author_host_task_id` or matching entries
in the state's assignment list cannot judge under another ID. These are
comparison checks of declarations, not host authentication.

Initial input is exactly `{schema_version:1,id,session_id,assignment_id,role_id,
host_task_id,input_binding,rationale,evidence_refs,open_issues}`. Rationale is a
nonempty string list; evidence is a unique list of bound artifact IDs and may
be empty. Open issues may be empty; no recommendation or criticism count is
forced. Each issue has `id,raised_by,target_refs,evidence_refs,question,impact,
severity,resolution_condition`, with optional `related_issue_ids`. `raised_by`
must be the own assignment ID, not role name. Targets are exact latest
hypothesis `{id,revision}` pairs; severity is `blocking`, `major` or `minor`.
The engine binds issue `session_id`; related issues must belong to that same
initial. Initial records add submission hash and declared-only provenance.

`register_initial(root, *, session_id, assignment_id, payload, command_id)`
checks the current binding and active assignment. All three initials atomically
freeze one snapshot sorted by assignment ID and change session/review attempt
to `collecting_responses`. Mutation responses contain status/identifiers and
compact receipt metadata, without raw state or initial bodies.
`reviewer_packet(session, assignment_id)` returns only own assignment, shared
inputs, role questions, output contract and permitted disclosure. Before all
three, phase is `initial` and disclosure empty; afterwards phase is `response`
with the stored snapshot. Response registration is explicitly unavailable.

CLI supports `m1 council prepare`, `initial`, `packet`, and `replace`, as detailed
in `skills/researchclaw/references/m1-council.md`. `m1 resume` understands the
review session without an authoring packet. CLI status/receipt projections hide
pending initial bodies, including event requests and replaced-role histories.
After disclosure original positions are available through each reviewer packet.
Raw store receipts/files remain readable to the host; this is not a filesystem
sandbox or protection against malicious host access.

## Failure, replay and replacement

Exact command replay returns the original durable result, including after other
submissions, replacement, or a failed durability acknowledgement. A reused
command ID with changed input fails. An identical initial under a new command
adds an acknowledgement event without a duplicate opinion. Changed already
submitted initials fail. A second prepare command for the same source fails
`m1_council_exists` instead of creating a duplicate review attempt.

`replace_assignment(root, *, session_id, assignment_id, replacement, reason,
command_id)` and `council replace` are supported only before disclosure.
Replacement has the same role but new assignment and host IDs. The session
retains the failed assignment, declared reason and old initial if present in
`assignment_history`, removes that initial from active collection, and freezes
all other initials. Late old-role submissions fail; exact historical command
replay does not restore the role. IDs/hosts from old assignments cannot be
reused in that session. Post-disclosure replacement fails because initial
independence can no longer be restored within this session.

## Actual host acceptance ownership

Root reported separate actual host execution and registration for session
`session-911e9f6673a04cf78297e48140334847`, review attempt
`attempt-180a771786414c4d8eef10a255db1a51`. It observed two initials remain
undisclosed and all three receive one identical response-phase snapshot.
Root reported six worker-authored issues (three blocking, three major).
One domain worker corrected its own `raised_by` schema error without changing
its opinion text. This prompted clearer output-contract guidance; validation
was not weakened. Root owns the raw worker files, live registration and
`live-host-observations.json`; this worker did not independently execute that
acceptance. The underlying research material remains synthetic. Native host
observations are separate from the engine's persistent `declared_only` label.

## Limits and next task

No response, final-position, resolution, decision, return or generalized upfront
council engine is implemented. Review session `responses` and `final_positions`
remain empty. Task 11 must interpret the now response-phase live session
compatibly: existing immutable assignment records retain their initial
`allowed_outputs:["initial"]`; add phase-specific response authorization/output
contracts without rewriting historical assignments, prepared snapshots or
input bindings. The response engine should consume original structured issues
and frozen initial identities rather than having the coordinator invent them.

Self-review checked exact source/evidence/approval lineage, truthful provenance,
non-disclosure through mutation and CLI receipts, durable replay, frozen
initials, replacement history, and source-node preservation. No unresolved
Task 10 implementation blocker remains; root's independent review is next.

Owned files: `researchclaw/core/m1/assignments.py`, `council.py`, `project.py`;
`researchclaw/codex/m1_cli.py`; `tests/codex_native/m1/test_assignments.py`,
`test_council.py`; `skills/researchclaw/references/m1-council.md`; this report.
