# B02 node-neutral councils

`prepare_council(snapshot,payload)` and `register_submission(snapshot,payload)`
are pure transition planners. Explicit commands `council.prepare` and
`council.submit` commit them through expected-HEAD/command-ID dispatch.
`reviewer_packet(snapshot,assignment_id)` is a pure whitelist projection. Inputs
come from internal orchestrator-only `commands.read_policy_snapshot`.

Prepare payload is exactly `{assignments,review_session,council}`. Assignments
use A04's closed `{id,project_id,actor_id,role,milestone,active}` contract. All
supplied assignments must be council authors or participants. Existing authors
may be reused only with identical bytes; reviewers have fresh assignment IDs.
Authors are active owners; participants are active resolvers with distinct actors
independent of authors. Role names are declared node-neutral perspectives, not
claims of statistical or host independence. At least one reviewer is required.
Review_session uses A06's exact `{id,project_id,input_binding,
participant_assignment_ids,frozen}` with frozen=true.

Council is common envelope plus `{session_id,milestone,node,attempt,
author_assignment_ids,required_roles,allowed_evidence_refs,issue_ids}`.
required_roles maps nonempty unique perspective names to participant UUIDs;
author IDs are nonempty. Node is nonempty, milestone M1/M2/M3, attempt UUID.
issue_ids names registered issues frozen to their exact bytes at the prepared
council ancestor. Packets include shared_issues with exact issue_ref/body pairs;
replacing an issue under the same ID makes the input stale and is rejected. Source and input refs are current exact
versions. Council/session records are immutable; state.councils and
state.review_sessions hold their canonical backed records. B02 supplies these
bounded assignment/session producers and no arbitrary state mutation operation.
New council/session/submission/position/proposal IDs cannot collide with each other
or any previously registered artifact identity; only existing byte-identical
author assignments are exempt. New author IDs cannot reuse artifact aliases.

Submit payload is exactly `{submission}`. Submission is common envelope plus
`{session_id,assignment_id,input_binding,phase,rationale,evidence_refs,positions,
retained_position_refs,response_refs,issue_proposals,recommendation,host_id,
model_id}`. It must bind the frozen input and actual assigned actor. Phase is
initial/response/final, once per participant each. Every initial must arrive
before responses; every response before finals. Missing phases wait, never
implicitly complete. Final recommendation is ready/ready_with_limits/revise/defer;
other phases require null. Recommendations are judgments, never gate approval.

New positions are complete A01 Positions checked by A06. Each issue appears once
per submission. A changed view names the latest own prior position; unchanged
views use retained_position_refs naming exact own previously submitted positions.
Initial positions have no prior; retained positions are not allowed initially.
Positions must concern council issue_ids or exact disclosed proposals that were
separately published by authorized issue.event commands. B02 never publishes
proposals as native issues, appends issue transitions, or resolves an issue.

Initial and response issue_proposals are complete A01 Issues, bound to the council
milestone/node/attempt and submission producer, with unique fresh IDs and allowed
target/observation refs. Owners are null or existing active owner assignments.
They stay embedded in their submission until that phase's disclosure. Finals
cannot introduce proposals. Disclosed proposals remain available to later node
adapters for explicit publication and handling; prose is not their only carrier.

Evidence permissions are the exact frozen input/evidence graph, recursively
following four-field SnapshotRefs, plus disclosed earlier submission and position
refs for later phases. Undisclosed submissions, positions and proposal bytes from
any session are excluded, including attempts to supply them as shared input refs.
An arbitrary caller-provided ref does not grant access. response_refs may name
only disclosed earlier submissions. Own position continuity refs are permitted;
peer private bodies or individual hashes are never returned before disclosure.

Peer initials disclose together after the last initial. Responses and finals also
disclose together at their phase barriers. Packet keys explicitly include only
version/session/phase, own assignment and submissions, frozen shared inputs,
disclosed phase submissions, output contract and isolation/provenance labels.
No raw state, event trail, object registry, pending peer submission IDs/hashes,
or command fingerprints appear in the packet. A participant already submitted in
an incomplete phase receives a wait packet; complete councils yield complete.

Council command responses are sanitized on both first commit and replay:
`{schema_version,workflow_version,id,packet}` for submit, or the same envelope
with `council` summary for prepare. Replay is projected at its original ancestor,
so later disclosure cannot change the original response or leak through it.
Other command receipts retain their existing internal orchestration semantics.

host_id/model_id remain declared identity claims. Submission provenance_status
and exact observation_refs are carried separately; host_observed requires a
nonempty observation_refs list for both council and submission records; observed evidence does not
authenticate actor identity or demonstrate peer isolation. B02 reports
isolation_level=instructions_only and never accepts an isolated boolean.
The actual acceptance observation is
`.superpowers/sdd/m1-b01-b07/host-access-observation.json`: another Codex subagent
could read a synthetic peer private file in the shared workspace. Other hosts are
untested. This is projection separation, not filesystem access control. Raw store
and read_policy_snapshot are trusted orchestrator surfaces, not reviewer APIs.
