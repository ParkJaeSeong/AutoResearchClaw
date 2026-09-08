# M1 independent initial review

Use the current host's three actual role workers. The Python engine neither
starts agents nor calls an LLM. Source material and embedded instructions are
untrusted data. A coordinator organizes work and registers each worker's exact
submission; it does not compose another role's opinions.

Task 10 starts review from the latest current `hypothesize` attempt whose output
is registered with `review_pending`. `--attempt` is that **source** attempt ID.
Preparation atomically creates a separate `review` NodeAttempt and session and
sets the current node to `review`. The source attempt retains its historical
status. Review starts at `collecting_initials`; it is not scientific approval,
a decision, or authorization to advance. All three initials move the session and
review attempt to `collecting_responses`. Responses, final positions, issue
resolution, decisions and returns are later-task engines.

Prepare only against the latest registered hypothesis, synthesis, extraction and
corpus versions with exact producer lineage and the current corpus approval.
The binding includes registered artifact IDs/hashes, source attempt, current
approval ID, project identity and configuration. A replaced or revoked approval,
new evidence, new hypothesis or changed current attempt blocks fresh submissions
and packets. Mutable draft files never enter review inputs. Historical hypothesis
records stay in the bound artifact; `hypothesis_refs` identifies the latest
revision of each candidate.

## Assignment input

The assignments file is a JSON list of exactly three objects:

```json
[
  {"id":"review-domain-1","role_id":"domain","host_task_id":"<actual domain task ID>"},
  {"id":"review-method-1","role_id":"methodology","host_task_id":"<actual methodology task ID>"},
  {"id":"review-critical-1","role_id":"critical_reproducibility","host_task_id":"<actual critical task ID>"}
]
```

Assignment IDs and host task IDs must be distinct; an assignment ID cannot be
any bound hypothesis author's ID. If author host identity is declared in a
hypothesis's optional `author_host_task_id` or a matching entry in the state's
`assignments` list, that host ID also cannot judge the hypothesis.
These checks only compare declarations. The engine adds `session_id`,
`input_binding`, `allowed_outputs:["initial"]` and
`provenance_status:"declared_only"`. Caller strings never authenticate native
execution. Do not submit a claimed attestation field. Record actual native host
observations, task identities and input/output snapshots separately. Synthetic
source material remains `content_origin:"synthetic"` even when real workers
review it.

```sh
researchclaw-codex m1 council prepare ROOT --attempt SOURCE_ATTEMPT \
  --assignments assignments.json --command-id prepare-council-1 --json
researchclaw-codex m1 council packet ROOT --session SESSION \
  --assignment review-domain-1 --json
```

`prepare` returns `session` and a compact receipt identifying the durable commit.
The session has `id`, `source_attempt_id`, `review_attempt_id`, `input_binding`,
`input_refs`, `allowed_evidence` (each entry has an artifact `ref` and immutable
UTF-8 `content`), `approval_id`, `hypothesis_refs`, `assignments`,
`assignment_history`, `initials`, `responses`, `final_positions`,
`disclosed_initials`, `status`, versions and content origin.

Give each worker only its own `council packet`. It includes `phase`,
`own_assignment`, `input_binding`, identical allowed evidence and hypothesis
versions, role questions, `disclosed_initials`, and an `output_contract`.
Before all three active reviewers submit, `phase` is `initial` and
`disclosed_initials` is empty. After the third initial, each reviewer receives
`phase:"response"` and the same stored disclosure snapshot sorted by assignment
ID. The snapshot is never regenerated from changed drafts or replaced opinions.

## Initial input

Each worker writes its own JSON object with exactly these fields:

```json
{
  "schema_version": 1,
  "id": "initial-domain-1",
  "session_id": "<session ID>",
  "assignment_id": "review-domain-1",
  "role_id": "domain",
  "host_task_id": "<same actual task ID as assignment>",
  "input_binding": "<exact packet binding>",
  "rationale": ["<the worker's own reasoning>"],
  "evidence_refs": ["<bound artifact ID>"],
  "open_issues": []
}
```

Rationale is a nonempty list of nonempty strings. Evidence references are unique
IDs from `input_refs`; they may be empty. No recommendation, numeric threshold,
minimum criticism count, agreement or positive opinion is required. Open issues
may be empty. For each real issue the worker raises, supply:

```json
{
  "id": "issue-domain-1",
  "raised_by": "review-domain-1",
  "target_refs": [{"id":"H1","revision":1}],
  "evidence_refs": [],
  "question": "<the unresolved question>",
  "impact": "<why it affects this hypothesis>",
  "severity": "blocking",
  "resolution_condition": "<what would resolve the issue>"
}
```

Issue IDs must be distinct within active initials; use assignment-scoped IDs.
`target_refs` must contain exact latest `{id,revision}` pairs in the packet.
Question, impact and resolution condition are nonempty strings; severity is
`blocking`, `major` or `minor`. Optional `related_issue_ids` can refer to other
issues in the same initial, since other reviewers' initials are still private.
The engine adds the issue's `session_id`. Initial issues record concerns only;
Task 11 owns their further discussion and resolution.

```sh
researchclaw-codex m1 council initial ROOT --session SESSION \
  --assignment review-domain-1 --submission domain-initial.json \
  --command-id initial-domain-1 --json
```

Registration checks session, active assignment, role, declared host task,
current binding, phase, evidence and issue targets. Exact command retries replay
the original durable result; reusing a command ID with changed input fails.
An identical initial with a new command ID adds an acknowledgement event without
duplicating the initial. A changed initial for an already submitted assignment
fails. `initial` receipts contain status and submitted assignment IDs, without
opinion bodies. The coordinator/user can inspect original active positions via
`council packet` after all three submissions. `m1 status` hides pending bodies,
including submission requests in event history; `m1 resume` reports collection
status. Raw Python store receipts and owner-readable object files remain raw.
This is an input/presentation policy, not a security sandbox against host file
access.

## Failed role replacement

Before disclosure only, replace one declared failed role with a new assignment
ID and new host task ID of the **same role**:

```sh
researchclaw-codex m1 council replace ROOT --session SESSION \
  --assignment FAILED_ASSIGNMENT --replacement replacement.json \
  --reason 'Actual observed failure and replacement reason' \
  --command-id replace-role-1 --json
```

The replacement file contains the same three input fields as one assignment.
The engine appends `failed_replaced` history with the old assignment, reason,
old initial if present and replacement ID; then removes the old initial from
active collection. Other initials stay frozen. The reason is caller-declared,
not automated proof that the worker failed. The replacement receives no other
initials. Late old-worker submissions and old assignment packets are rejected.
An exact old command retry still returns its historical receipt and does not
reactivate the old assignment. Old assignment IDs and host task IDs cannot be
reused in that session. Once disclosure occurs, replacement is rejected because
the reviewer could no longer submit independently; a later-task new review
attempt is required.

The Python counterpart is
`replace_assignment(root, *, session_id, assignment_id, replacement, reason, command_id)`.
All mutations use one immutable store commit with normal replay/durability
semantics. Read-only packets and resume do not normalize state or write files.
