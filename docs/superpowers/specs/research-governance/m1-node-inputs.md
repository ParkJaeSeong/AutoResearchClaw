# B03 M1 node revisions and scope review

`m1.node.register` is a bounded native author-output producer, not an arbitrary
state patch. B03 supports only `scope` and `questions`. Its payload is exactly
`{artifact}`: the common envelope plus `node`, `attempt` (UUID), `previous_ref`
(null or exact SnapshotRef), `input_refs`, `content`, and `revision_reason`.

Scope content is exactly `{user_goal, user_constraints, agent_assumptions}`:
nonempty goal text and lists of nonempty constraint/assumption strings. User goal
and constraints are explicitly declared user inputs, separate from agent
assumptions; registration does not authenticate their authorship. Questions
content is exactly `{questions, agent_assumptions}`, with a nonempty list of
`{question, rationale}` records. Rationale explains why each question was selected.
Scope input_refs is empty; questions input_refs is exactly `{scope: SnapshotRef}`
and must match the current, reviewed scope revision.

Each registration creates a fresh immutable revision ID and attempt, keeps
`state.m1_node_revisions[id]`, updates `state.m1_node_heads[node]`, and publishes
the fixed logical object alias `m1/nodes/{node}`. Revisions require previous_ref
to be the exact current registered revision of the same node and a nonempty
revision_reason. First registration requires null previous_ref and null reason.
Old revision bytes are preserved. IDs/attempts cannot be reused. Current inputs
and observations must be exact and current; old council results do not review
new bytes or a new attempt.

Replacement validates the predecessor's exact registered identity separately
from its old consumed inputs: obsolete scope inputs may be replaced by reviewed
current scope inputs in a questions revision. The replacement's own input_refs
still undergo all currentness and upstream-review checks.

Before replacing a revision, every disclosed nonoptional proposal from its
council must already be published as the same native Issue via issue.event.
Otherwise registration rejects `m1_issue_publication_required` and preserves
HEAD. This publication boundary prevents a fresh council from erasing old
obligations and permits publication while original target refs are current.
Publication, not resolution, is required for editing: unresolved native issues
remain preserved and governed by scoped blocking after the new revision.
This precheck reads native councils/proposals scoped to the prior node/attempt;
it does not require the old council's author, independence or readiness policy
to succeed. A new revision can therefore repair an incorrectly declared setup
while preserving any disclosed nonoptional publication obligations.

Stored lineage uses `previous_ref_key`, a canonical JSON string encoding the
validated previous_ref, in place of the request's previous_ref. This intentional
historical linkage is not current evidence: B02 traverses embedded four-field
refs as current allowed inputs, which would otherwise reject every revision's
old lineage. A caller cannot encode arbitrary or private refs as lineage. Actual
input_refs remain full references and are checked for currentness.

`prepare_scope_council(snapshot, node_id=...)` consumes one verified snapshot and
returns a pure projection. It validates current node content and its upstream
review before considering the council. It exposes `council_binding` with M1,
node, attempt, exact input_binding, declared author actor and required perspectives
`domain`, `methodology`, `critical`; callers use the existing `council.prepare`
operation to register actual assignments/session/council, then `council.submit`.

The selected council must uniquely match node/attempt/current input. Its authors
must be active M1 owners whose actor matches the artifact producer, and its three
reviewers must be active, distinct M1 resolvers independent of the author. Backed
council and submission bodies must match their original native registration
events. Actual initials, responses and finals must all complete. Responses cite
every initial submission; finals cite every response submission. Final
recommendations are actual reviewer judgments. `revise` requires a new revision;
`defer` waits for input. Issue-free final judgments may have no Positions.

If a reviewer made formal Positions, their final must include or explicitly
retain each latest own stance. Retained exact authored Position references are
the author's acknowledgement; this projection creates no coordinator summary
or A06 Decision acknowledgement. B02 validates stance revisions and authorship.

Nonoptional private issue proposals must be explicitly published through
`issue.event` before the node can become ready. Published issues remain governed
by native append-only events: a matching unresolved nonoptional node scope
blocks, optional issues remain visible, and transferred/superseded are not
resolved. Forged issue_states do not bypass native status. No issue is invented
merely to force a Position into an issue-free council.

The projection has `ready`, `reason_codes`, `required_actions`, `node_ref`,
`council_binding`, `council_id`, `phase`, `unresolved_issue_ids`,
`unpublished_issue_ids`, `next_node`, and `content`. Missing phases or policy
blocks return nonready projections; invalid records/references raise ValueError.
Only reviewed scope exposes questions as next_node; only reviewed questions
exposes search. B03 does not implement search registration. Missing records are
not silently replaced by fixture prerequisites.

Per the user-approved G10/milestone boundary, scope/questions/search review
readiness uses B02's author-independent phase-complete judgments and A07's native
scoped-issue status semantics, **not** A07's mandatory approval_refs policy for
every discussion. Human approval is not added each round. A07 still applies at
explicit authority boundaries such as corpus/handoff. This pure review projection
is neither an approval nor an execution grant. Host/model identities remain
declared; synthetic structural validation is separate from actual research.
