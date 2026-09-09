# A07 gate assessment inputs

`assess_gate(commands.read_policy_snapshot(root), milestone=..., gate_id=...)`
is pure. It returns `ready`, unique ordered `reason_codes`, `required_actions`,
and sorted `unresolved_issue_ids`. These are declared policy checks, not scientific
certification, permission to execute, or approval authority. A07 registers no
prerequisites and offers no mutation operation. Missing future producers fail closed.

`state.gate_requirements[gate_id]` is a canonically object-backed closed record:
`{id, project_id, milestone, kind, target_id, input_binding,
author_assignment_ids, required_roles, submission_refs, source_refs,
approval_refs, decision_ref}`. `id` is a UUID; kind is `node`, `handoff`, or
`finalization`, matching Issue.blocking_scope exactly with milestone and target_id.
Handoff targets are the next milestone (M1→M2 or M2→M3).

`input_binding` is one current exact SnapshotRef. Authors are a nonempty unique
list of active owner assignment IDs at this milestone. `required_roles` maps
exactly the declared review perspectives to active resolver assignment IDs at
this milestone: M1 `domain, methodology, critical`; M2 `domain, methodology,
reproducibility`; M3 `domain, methodology, audit`; M3 finalization uses `source,
integrity`. Reviewer assignment IDs and actors must be distinct and differ from all author actors. Role perspectives
are declarations, not independent-host or statistical independence evidence.

`submission_refs` is a nonempty list of exact registered Positions covering every
required assignment, bound to input_binding and present in decision_ref's
position_refs. The complete backed Decision passes A06 `validate_rationale_links`,
including its registered-position policy validator and author acknowledgements.
Decision.gate_result is never consulted for readiness. `revise` requires at least
one dissent/position issue with a nonempty matching blocking_scope and an explicit
resolution_condition; otherwise `revise_binding_missing` requests correction.
A bound revise remains `revision_required` until the issue is resolved. Independently
of the coordinator next_action, required-role `oppose` submissions on unresolved
nonoptional issues require a nonempty blocking_scope and criterion; an unbound
opposition returns `opposition_binding_missing` for correction. Scoped opposition
continues through normal gate-scope and transfer checks.

`source_refs` is nonempty, exact, current object evidence. `approval_refs` is
nonempty, exact registered ApprovalBindings in `state.approval_bindings`, with
validity `valid`, binding equal to input_binding, and nonempty exact scope_refs
covering input_binding. Every existing_receipt_ref and observation_ref resolves.
Existing receipts are typed references into backed `state.approval_receipts`
records with exactly `{id, project_id, producer_id, decision, binding, scope_refs}`.
The prior receipt's decision must be `approved`, producer_id must be nonempty,
and binding/scope_refs must exactly equal the ApprovalBinding. Its referenced
ancestor must predate the first registration of that ApprovalBinding. This is
an existing-authority adapter prerequisite; A07 creates none. These bindings consume an existing receipt; they do not create or authenticate
approval authority. Expired/revoked/unknown/revalidation bindings never pass.

All issues are read from backed Issue records. Current state is derived from
backed, schema-valid, continuous native IssueEvents in verified commit event payloads,
never a mutable issue_events/issue_states projection or a
Decision ready flag. Imported historical state remains immutable and effectively
open absent native events. Unresolved issues from this milestone, or scoped to
this gate, remain listed, including optional improvements; optional severity does
not block. Superseded remains unresolved and cannot erase a scoped block.

A matching unresolved nonoptional scope blocks. Only M1 handoff→M2 empirical
issues whose latest event is transferred can pass after current destination
owner, fixed verification and acceptance are rechecked under A04's contract.
Transferred is still listed as unresolved. M2 integrity cannot transfer away.
Malformed or absent event history fails closed. Assessment preserves snapshot,
HEAD, and all referenced object bytes.

Declared prerequisite collections must be mappings in HEAD and referenced history;
null/list collections return `gate_collection_invalid`, without I/O or mutation.
