# A04 issue policy inputs

`issue.event` is the fixed command operation. Its closed payload is
`{issue: Issue | null, event: IssueEvent}` using A01 records. Supply Issue only
for initial `null → open`; existing Issue bytes never change. Events append to
`state.issue_events` (a list); `state.issue_states` is a current projection.
Status validation uses the event trail, never caller-supplied status patches.

A04 does not create assignments, verification work/results, transfer acceptances,
or approvals. Until the prerequisite producers exist, absent registrations fail
closed. No automatic runtime seed or prerequisite-write CLI is provided.
Synthetic test registration uses the low-level store only in test fixtures.

Already registered prerequisites use these bounded input contracts:

- `state.assignments[id]`: exactly `{id, project_id, actor_id, role, milestone,
  active}`; UUID id/project, nonempty actor_id, role `owner|resolver`, milestone
  `M1|M2|M3`, and active must be true when used. This is declared responsibility,
  not host authentication. Different assignment IDs do not establish independent
  actors. Future B02 owns registration and identity provenance.
- `state.verifications[id]`, `state.verification_results[id]`: A01 Verification
  and VerificationResult. Checking event verification_refs name Verification
  records; resolution/reopen refs name VerificationResult records. A result must
  link the same issue and exact Verification revision fixed by checking.
  Verification acceptance_rule equals Issue resolution_condition. Result
  checked_scope includes that exact condition, with nonempty real referenced
  output bytes. `supported` records satisfaction of the fixed check; it does not
  prove the hypothesis scientifically true. A05 owns work/result creation and
  scientific sufficiency; A04 validates recorded linkage.
- `state.transfer_acceptances[id]`: exactly `{id, project_id, issue_id,
  owner_assignment_id, verification_id, to_milestone, accepted, producer_id}`.
  accepted must be true; producer_id equals destination owner's actor_id.
  Destination, owner and verification must agree; the ancestor where acceptance
  first appeared must contain the same current verification and assignment
  records. Changed prerequisites require a new acceptance.

Each prerequisite registration must have matching canonical immutable object
bytes in the verified snapshot. A four-field SnapshotRef must name this project,
an exact verified ancestor, artifact identity and matching SHA256 bytes registered
there. Typed refs also match that ancestor's collection entry and current entry.
General evidence refs bind the artifact's logical object-input name at that
ancestor and must remain current. Foreign, missing, fabricated and stale refs
fail closed; source archive references are not silently reinterpreted.

Only commands injects `_issue_context` into the handler's private snapshot,
containing verified ancestry records and object bytes. It is not accepted in the
payload, persisted or returned. The pure policy performs no filesystem I/O. A
bare receipt without this trusted context cannot prove prerequisites. This is an
internal caller trust boundary, not a signature or external authentication API.

Checking needs an owner and referenced verification; optional owner_assignment_id
on the checking event assigns an unassigned import without changing Issue.
Transfer records the accepted destination owner but remains unresolved. Resolution
requires checking first, a supported result first registered after checking, and
an evidence-linked resolver event. Resolver actor must differ from current issue
owner, original issue producer, verification owner/producer and result producer.
A new refuted result first registered after resolution may reopen that issue;
existing conflicting evidence cannot be relabeled as new. Supersession preserves
the original and names existing unresolved successor issues; it is not resolution.

Imported `source_status` and `pending_policy_revalidation` remain immutable
historical metadata, including imported historical `resolved`. Without a native
event the effective policy state is open. Such an issue must pass native checking
and resolution; an unassigned import needs an explicit checking assignment.
