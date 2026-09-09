# A05 verification registration inputs

`verification.prepare` is the fixed operation for freezing verification work.
Its closed payload is `{verification: Verification}`. The record must name one
or more unique existing issues whose `resolution_condition` exactly equals its
nonempty `acceptance_rule`. Its active owner assignment must have role `owner`,
and the record producer must equal that assignment's actor. Budget, input, and
observation refs must be exact and current when prepared. A Verification ID or
event ID cannot replace an existing registration; changed questions, inputs, or
criteria require a new Verification ID.

`verification.result` is the fixed result-registration operation. Its closed
payload is `{verification_ref: SnapshotRef, result: VerificationResult}`. The
typed ref must name the exact current immutable Verification revision, and that
revision's issues, owner assignment, budget, inputs, and observations must still
be current. `result.verification_id` and both producer identities remain bound
to it. Result output and observation refs must also be exact and current.

`supported` and `refuted` require at least one output ref and `checked_scope`
must contain the frozen acceptance rule verbatim. `failed` and `inconclusive`
may have empty output refs and checked scope because the fixed criterion may not
have been evaluated; each requires a nonempty limitation explaining the gap.
All four outcomes remain distinct records. Registration never appends an IssueEvent
or changes `state.issue_states`; A04 policy separately decides whether a later,
independently produced issue event can resolve or reopen an issue.

Only `commands.apply_command` supplies `_issue_context` with verified ancestry
and immutable object bytes. Neither public payload accepts that private key.
Both handlers return pure transition plans and perform no filesystem, network,
experiment, assignment, budget, issue-resolution, CLI, or UI action.
