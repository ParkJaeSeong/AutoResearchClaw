# A08 dependency impact inputs

`plan_revalidation(commands.read_policy_snapshot(root), changed_refs=[...])` is
pure. It consumes verified history and object bytes, preserves the snapshot,
HEAD and old objects, and returns an uncommitted plan. There is no dependency,
approval or event producer, command registration, execution or approval authority.
Missing or invalid prerequisite references fail closed.

Each changed_refs entry is the UTF-8 canonical JSON string of exactly
`{project_id, head_id, artifact_id, sha256}` (the store's canonical encoding:
sorted keys, compact separators). It identifies the old version whose dependents
must be reconsidered, even after a newer analysis has been registered. Bare IDs,
hashes, extra fields, noncanonical JSON and unknown references are rejected.
An empty list validates the graph and reports reuse without an event plan.

Every supplied reference is independently checked against its named ancestor:
same project, reachable head, digest present at that head, verified bytes, and
artifact binding. Generic artifacts use the historical logical object alias.
Typed UUID references resolve records in the fixed collections `issues`,
`verifications`, `verification_results`, `positions`, `decisions`, `handoffs`,
`dependencies`, `approval_bindings`, and `approval_receipts`; they do not require
the UUID itself to be the object alias. Typed schema records must pass their
closed contract. Multiple typed collections claiming one referenced ID are
ambiguous and rejected. Currentness compares the latest alias or typed record;
historical reference validity does not imply currentness.

`state.dependencies` is a UUID-keyed map of canonically object-backed Dependency
records. All four relation labels use the same direction: `from_ref` is the
upstream input and `to_ref` is the dependent output. For `derived_from`, the
**to** object is derived from the **from** object. `supports`, `tests`, and
`reports` also propagate change from input to dependent result. The complete
graph must be acyclic, including disconnected components. `origin_group_id`
remains provenance metadata; the literal `unknown` never establishes independence.

After validating every full reference, node identity is
`(project_id, artifact_id, sha256)`. The same immutable version referenced from
two valid ancestor heads is one node; a different digest or artifact is another
node. The representative output reference is the lexicographically smallest
canonical full reference encountered for that node. Traversal includes changed
seeds and downstream descendants only. Unrelated predecessors and branches are
not affected, and new versions are never silently substituted for old ones.

`state.approval_bindings` is a UUID-keyed map of backed ApprovalBinding records.
The [A07 existing-receipt adapter](gate-inputs.md) applies: a typed, backed, current
receipt with exactly `{id, project_id, producer_id, decision, binding, scope_refs}`
must have decision `approved`, nonempty producer, matching binding/scope and a
referenced head before the binding's first registration. Scope includes binding.
All scope and observation references resolve. A08 uses historical scope checking
because changed old versions must remain inspectable; it does not use A07's
current-only gate helper. This is a receipt consumer, not authentication or an
approval producer.

An approval needs revalidation when its own node, binding or any scope_ref is
affected, even when no edge points to the approval. Reuse requires validity
`valid`, current scope and observations, a valid existing receipt, and no impact.
Revoked, expired, unknown, already-needs-revalidation and stale approvals are
never reusable, including when an approval is itself a DAG node. A revalidation
descriptor does not change or revive an approval's original validity.

The returned closed projection has:

- `affected_refs`: unique exact references for seeds and downstream nodes.
- `approval_checks`: one entry per current registered binding, ordered by ID,
  with `{approval_ref, reason_codes, reusable}`. Reasons are `needs_revalidation`
  for impact, then `approval_not_current` for nonvalid/stale status, when present.
- `reusable_refs`: current unaffected graph nodes and eligible approval refs,
  ordered by canonical reference. Scope-only source objects are not graph nodes.
- `event_plan`: null for no affected nodes, otherwise the versioned store event
  descriptor `{schema_version, workflow_version, type: needs_revalidation,
  payload: {changed_refs, affected_refs, approval_refs}}`. Approval refs include
  impacted bindings only. Lists of references are canonical-order deterministic.

The event descriptor is explicit proposed append-only work, **not a committed
event** or a command handler transition. A future authorized producer must add
the usual command identity and expected-HEAD handling through the sole dispatcher.
A08 does not patch approval validity, issue status, old records or HEAD. Repeating
the pure call produces a plan again and has no event or counter side effect.

Invalid input raises ValueError. A08 reasons include
`dependency_changed_refs_invalid`, `dependency_reference_invalid`,
`dependency_reference_ambiguous`, `dependency_collection_invalid`,
`dependency_record_invalid`, `dependency_cycle`, and `dependency_approval_invalid`.
Existing `_Inputs` context/backing/current-receipt errors remain unchanged.
These checks establish structural impact over recorded provenance, not scientific
correctness, independent evidence, authentic authority, or actual research success.
