# B07 native M1 handoff and work accounting

These explicit operations consume verified policy snapshots. Publication,
receiver acceptance, native Issue transfer, and gate readiness are separate.
None initializes M2, runs a verification, changes Issue status automatically,
creates corpus approval, or establishes scientific truth. Model/host identities
remain declared responsibilities under the existing council contract.

## Publication and immutable manifest

`m1.handoff.issue` / `issue_handoff(snapshot, payload)` accepts exactly
`{publication, review_ref}`. `publication` is the common envelope, with fresh
UUID identity/event and the actual M1 review author's producer identity;
`review_ref` is the exact current native review. No manifest body or ready bit
is accepted from the caller.

The producer derives and registers:

- An A01 `Handoff` with M1→M2, exact prepublication `source_head`, all current
  scope/questions/search/screen/collect/extract/synthesize/hypothesize/review
  artifacts and source/claim refs, all unresolved Issue IDs, empirical transfer
  proposals, limitations, and `acceptance_ref: null`.
- A manifest with exactly `id`, `project_id`, `handoff_id`, `node_refs`,
  `corpus_ref`, `source_refs`, `source_groups`, `hypotheses`,
  `rejected_alternatives`, `prior_issue_dispositions`, `open_questions`,
  `limitations`. All content derives from the same native B04/B05/B06 chain.
- A closed native gate record with `id`, `project_id`, `milestone: M1`,
  `kind: handoff`, `target_id: M2`, `profile: native_m1_handoff`,
  `input_binding` (review), `corpus_ref`, and `approval_ref`.

Manifest, gate, one package receiver assignment, and per-Issue Verification and
acceptance UUIDs derive deterministically from the publication UUID. Reserved
IDs do not create assignments or prepared checks. One package owner handles all
transfer questions, including reception of an issue-free package. A second
publication of the same exact review is rejected. Old bytes remain immutable.

Issuance checks current B05 evidence, the complete approved corpus component
(B04 exact four-ref scope), B06 accounting and actual independent native council
finals. It requires an open-question row for every unresolved Issue. Optional
issues remain listed; all nonoptional unresolved issues must be empirical with
complete transfer proposals and a native transferable status. Generic upstream
blocking reasons are deferred only after checking every current node and proving
that each concrete scoped blocker is one of those exact empirical proposals.
An unbound required opposition still requires correction. No general filtering
of blocking reasons or reuse of stored readiness is allowed.

Preserved shared Issue wrappers are historical context leaves in B02. Their
exact target metadata can name an earlier hypothesis or foreign A03 archive;
it is not automatically traversed/promoted as current evidence. Embedded private
IDs/hashes are still rejected before showing the Issue body, and explicitly
submitting a stale/foreign target as current evidence remains invalid.

## Receiver assignment, prepared checks, and acceptance

`m1.handoff.receiver.assign` accepts exactly `{handoff_ref, assignment}`.
The closed existing Assignment shape must use the reserved package ID, this
project, active M2 owner role, and a receiving actor distinct from the M1 author.
It records that explicit declaration after authentic current publication.

Ordinary `verification.prepare` creates each reserved per-Issue Verification.
The receiving owner/producer, one exact Issue, question, fixed resolution
criterion, method `experiment`, and budget ref must match the issued question.
`input_refs` is exactly the projection's `verification_input_refs`: the immutable
Handoff and manifest references followed by all issued artifact refs. A prepared
experiment is a question/plan, not evidence that an experiment ran.

`m1.handoff.accept` / `accept_handoff(snapshot, payload)` accepts exactly
`{acceptance, handoff_ref, receiver_assignment_id, verification_refs, limitations}`.
`acceptance` is a fresh common envelope produced by that receiving actor.
Verification refs cover every reserved check exactly once; no checks are needed
for an issue-free package. Acceptance creates an immutable package receipt and
one exact A04 `transfer_acceptances` record per proposal. It emits no IssueEvent
and does not rewrite the Handoff's original null acceptance_ref.

The recorded M1 owner must subsequently submit the existing explicit
`issue.event` transition to `transferred`, naming the exact reserved M2 owner,
Verification, and native acceptance. The B07 gate checks the actual M1 owner
assignment/actor as well as the accepted destination. An unrelated actor's event
cannot complete this handoff even if the generic Issue transition accepts it.

The frozen B06 proposal retains its original M1 owner. Its narrow validation
bridge permits the later effective M2 owner only when the immutable review is
bound to this authentic issued manifest, the exact receiver acceptance exists,
and the original M1 owner produced the exact native transfer event. No frozen
review/council/Issue bytes change; arbitrary owner changes remain invalid.

## Pure status and native gate profile

`handoff_status(snapshot, handoff_id=UUID)` returns `status`, `gate_ready`,
`reason_codes`, `required_actions`, `handoff_ref`, `gate_id`, `manifest`,
`receiver_assignment_id`, `transfer_proposals`, `transfer_acceptance_ids`,
`verification_input_refs`, and `unresolved_issue_ids`.

Status is `issued_awaiting_acceptance` until the explicit receipt exists, then
`accepted`. Acceptance remains historical even if a new current blocker appears;
`gate_ready` is assessed separately. Empirical acceptance without native owner
transfer yields `native_transfer_required`. Changes to consumed node/source
bytes or current corpus authority yield `stale_handoff`. Every fresh assessment
considers current Issues, including Issues raised after publication.

A07 dispatches only the exact closed `native_m1_handoff` profile for M1→M2.
Its records must reconstruct the actual native publication at its original
ancestor; arbitrary backed profile/ready records are insufficient. Default A07
Position/Decision gate behavior is unchanged. The native profile rechecks
current complete evidence, mandatory domain/methodology/critical council
perspectives and independent actors, scoped corpus authority, Issue/transfer
bindings, and the work ledger/budget. It reports structural eligibility only.

A private node-result cache exists only within one internally created assessment
snapshot. Each public B07 call starts with an empty cache, even if given an
internal wrapper. Historical reconstruction has a separate empty cache. No
public payload accepts cached results; no global or cross-HEAD cache exists.

## Bounded work producer and ledger refresh

`m1.work.record` accepts exactly
`{record_id, source_kind: council|verification, source_ref}`.
A council unit becomes eligible after all native B02 phases/finals; a Verification
unit becomes eligible at native A05 preparation. The source must be native,
exact, and tied to its real assignments/node or Issue. Same source units cannot
be recorded twice by changing IDs or HEAD labels.

The derived A09 work record is exactly
`{id, project_id, work, resource_request, status, correction_ref: null}`.
Work uses the existing closed common envelope and descriptor. Council inputs are
its consumed session input; Verification inputs are the actual prepared inputs.
Fresh result/council/work envelopes do not replace consumed inputs. Owner and
producer come from actual responsible assignments. Council final defer→
awaiting_input, revise→inconclusive, otherwise completed. A check with no result
is pending; supported/refuted→completed check, failed/inconclusive stay explicit.
Latest results use native event order, never UUID order. Status is frozen when
recorded; later results do not rewrite an earlier pending work record.

`work_ledger.refresh` accepts exactly `{ledger_id}` and is a separate ancestor
step. It requires complete source coverage and enumerates all immutable native
work records with their original refs. It backs the exact A09 ledger and derives
`returns_used` from all native node replacements and `verification_runs_used`
from distinct native Verification IDs in actual checking events. Preparing a
check alone does not charge a begun check. Results, repeated refreshes, or new
record IDs do not double-charge. Resource fields on an individual record are
frozen increments at recording time; aggregate counters independently use the
full native event/revision history.

These counts describe recorded node replacements and declared begun checks,
not model calls, measured compute, or experimental telemetry. No native cost
telemetry is available: resource estimates and aggregate observed cost remain
null/unknown, never zero. Configured maxima and cost limits are preserved;
missing configuration is not initialized by this adapter. Past work is recorded
even if already over limit, and subsequent assessment reports exhausted budget.
The current ledger must cover every eligible native unit and current counts.

The handoff invokes A09 with a concrete author-owned publication descriptor and
zero additional return/check increments (publication itself runs neither), while
keeping estimated cost unknown. Existing exceeded counters still block via the
accounting check; configured cost limits cannot reinterpret unknown as zero.
A09's one-use exact approved-correction rules are unchanged. This adapter creates
no correction approvals or generic state patches. `work_sources` lists native
units/record coverage; `accounting_status` reports missing record/refresh actions.
