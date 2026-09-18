# A09 next-work and resume inputs

`assess_next_work(commands.read_policy_snapshot(root), payload)` returns a pure
projection `{ready, reason_codes, required_actions, status, next_actions,
previous_status}`. It never executes, increments counters, registers work or
creates approval authority. Missing future prerequisite producers fail closed.
A09 does not initialize a ledger. Synthetic fixture registration is test-only.

Payload contains exactly `{work, resource_request, correction_ref,
correction_approval_ref, semantic_status, resume_ref}`, optionally plus `return_plan`.
The 2026-09-15 [evidence-driven return policy](../../../research/guides/return-policy.md)
requires that plan for declared returns in explicitly opted-in projects. It does
not change the recorded work schema or historical snapshots. Nullable refs default to
explicit null; semantic_status is `literal_only` or `uncertain`. Work is the common
research-graph envelope plus exactly `{assignment_id, milestone, node, question,
input_refs, work, acceptance_rule}`. The active owner assignment must match the
proposed producer and milestone. Text fields and input_refs are nonempty.
Envelope version fields use exact types (boolean true is not schema_version 1).
Every proposed input/observation is an exact current reference; historical work
inputs remain exact historical versions, never silently replaced with latest.

A signature hashes canonical JSON of `{milestone,node,question,input_refs,work,
acceptance_rule}`. Text uses Unicode NFC and collapsed whitespace only: scientific
case is preserved. input_refs becomes a sorted unique list of
`[project_id,artifact_id,sha256]`, after validating each full reference. Changing
UUID/event/producer/assignment metadata or only HEAD labels does not create work.
This is literal normalized comparison, not semantic/paraphrase certification.
Explicit semantic uncertainty returns `semantic_identity_uncertain` and awaits input.

`state.work_ledger_id` names one backed `state.work_ledgers[id]` record with exactly
`{id,project_id,work_refs}`. work_refs contains every current and historical
registered work record once; omission, duplicate or replacement fails closed.
An explicitly backed empty ledger permits the first work proposal. Work records
in `state.work_records` are closed `{id,project_id,work,resource_request,status,
correction_ref}` with status `pending|completed|failed|inconclusive|awaiting_input|
blocked_budget`. Every recorded attempt participates in repeat checks, regardless
of outcome; a new UUID or a failed attempt is not permission for a retry.
Every nonnull historical correction_ref must resolve the exact correction and prior
ledger work, and its replacement signature must bind that recorded attempt.
Record IDs/project IDs are UUIDs; custom prerequisite records use their ID as an
immutable object-input alias as well as their typed collection registration.

Corrections in `state.work_corrections` have exactly `{id,project_id,
previous_work_ref,replacement_signature,rationale,evidence_refs}`. Prior work is
an exact ledger record; replacement_signature is the proposed work signature;
rationale and exact current evidence_refs are nonempty. Duplicate evidence nodes
(project/artifact/digest, including different HEAD labels) are rejected; duplicates
cannot change the correction content fingerprint and regain a retry. A current
correction_approval_ref names an ApprovalBinding bound to the exact correction,
with scope including that correction and previous_work_ref. A07's backed prior
existing-receipt semantics apply. No bare approved boolean substitutes. A correction
already referenced by any recorded work cannot authorize another attempt; neither
a different HEAD label nor a copied correction ID with identical correction content
resets this use. Corrections never bypass budgets or missing input/authority.

resource_request is exactly `{returns,verification_runs,estimated_cost,cost_status}`.
Counts are nonnegative integers (booleans rejected). Cost is finite nonnegative
numeric when `known`, null when `unknown`. State's max_returns/returns_used and
max_verification_runs/verification_runs_used are checked separately against the
requested increments. An explicit `return_policy.mode=evidence_driven` exempts only
the return-count limit; counts and their historical limit remain stored. It does
not exempt verification or cost limits. execution_cost_limit is null or finite nonnegative numeric;
observed_cost follows state's known/unknown cost_status. With a cost limit, unknown
observed or estimated cost is `cost_unknown`/awaiting_input, never zero. A requested
increment beyond a limit, or positive work against an exhausted limit, is
blocked_budget. These are declared counters and costs, not execution permission.

resume_ref, when supplied, names an exact ledger work record. previous_status
preserves its recorded status. The same checks run on the concrete successor work;
resume does not reset budgets, forgive repeats, or mark failed/inconclusive work
completed. Status is `ready`, `awaiting_input`, or `blocked_budget`; next_actions
contains the proposed milestone/node and `assess_authorized_work` when ready,
otherwise concrete correction/wait actions. Ready means this narrow repeat/budget
assessment passed; existing execution approvals still apply. Reason/action order
is deterministic and inputs, HEAD and object bytes are preserved.
