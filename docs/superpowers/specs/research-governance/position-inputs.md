# A06 position and rationale inputs

`validate_position_change(snapshot, payload)` accepts one complete `Position`
as `payload`. `snapshot` must come from `commands.read_policy_snapshot(root)`.
The validator requires a backed exact `Issue`, active assignment, and a backed
frozen review session with the exact closed shape `{id, project_id, input_binding,
participant_assignment_ids, frozen}`. The position assignment must be a session
participant, its producer must be that assignment's actor, and its input binding
must equal the session's immutable input binding. Missing later assignment or
session producers are prerequisites and fail closed; A06 creates neither.

An initial position has both `changed_from` and `change_kind` null. A changed
position uses a new position ID and event ID and names the exact immutable prior
Position revision. The prior position has the same issue and assignment.
`evidence_added` requires a new artifact/hash evidence identity (a newer HEAD
label alone is not new evidence), `reinterpretation` retains an exact evidence
identity, and `logic_correction` or `scope_changed` supplies a nonempty rationale
and at least one exact source reference.

`validate_rationale_links(snapshot, decision)` validates a complete `Decision`.
Claims and observations are exact immutable object references. Position refs are
exact registered `Position` records; verification refs are exact registered
`VerificationResult` records. Each claim rationale has at least one role position
and one verification result. Decision and dissent issue IDs name exact registered
issues, and dissent positions are exact positions declared by the decision.
Unknown, stale, or mismatched references return `ref_unknown`.

Each linked position needs a registered acknowledgement with the exact closed
shape `{id, project_id, assignment_id, producer_id, position_ref, claim_ref,
summary, disposition, acknowledged}`. It binds the exact position and claim,
copies the decision claim disposition's rationale into `summary`, copies its
disposition enum, and has `acknowledged=true`. Its assignment is the position's
assignment and its producer is that assignment's actual actor. A label, another
position's acknowledgement, or an acknowledgement of different summary or
disposition does not substitute and returns `position_ack_missing`.

Both interfaces return an ordered tuple of `{code, path, message}` errors and
perform no file, network, registration, command, CLI, or UI mutation. Passing
these structural and linkage checks does not establish scientific support.
