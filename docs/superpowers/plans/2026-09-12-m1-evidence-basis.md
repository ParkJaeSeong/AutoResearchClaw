# M1 Evidence Basis B1 Implementation Plan

> **For agentic workers:** Execute this approved B1 plan inline, with tests before implementation and a review checkpoint before delivery.

**Goal:** Register and inspect an immutable question-bound Atlas evidence basis without changing M1 readiness.
**Architecture:** A pure m1_evidence_basis policy validates real questions, QA versions, reviews and exact answer excerpts. Existing command dispatch and public projection deliver the record and claim references; no new HTTP mutation or UI form.
**Tech Stack:** Existing Python graph store, pytest, public research apply/inspect CLI.
**Spec:** ../specs/2026-09-12-atlas-m1-evidence-route-design.md

## Constraints

B1 only. Preserve all prior state fields. No approvals, node completion, real question changes, or fake council. Current question ref and exact question text required. use/limited and exact allowed use required. Original QA bytes and history retained. Coverage is closed {covered,missing,decision_impact}, all nonblank strings; limitations is text list. Claim fields are exactly those in the approved spec. Conflicting judgments are disclosed in projection; semantic agreement is not machine-certified.

## Task 1: Registration policy and immutable claim objects

Files: create core/research_graph/m1_evidence_basis.py and tests/codex_native/research_graph/test_m1_evidence_basis.py; extend commands.py.
Interface: register_basis(snapshot,payload) -> state_patch/event/object_inputs. Collection m1_evidence_bases; event m1_evidence_basis_registered with record_id. Each claim preserves its logical claim_id and gets a zero-based immutable object alias m1/evidence_basis/BASIS_ID/claims/CLAIM_INDEX. Revisions use previous_ref and revision_reason; a root basis identifies one series, revisions may target a new question revision with an explicit reason.

- [x] Create a synthetic native scope/question via existing public Fixture. Import QA and register review through public commands.
- [x] Assert apply('m1.evidence_basis.register', payload) saves claims, leaves prior fields unchanged, and identical command replay returns the same HEAD. Observe unknown_operation first.
- [x] Implement closed payload/type/ref validation; check question currentness and literal question membership, QA latest version, authored review and matching QA, allowed use, exact nonblank excerpt, unique claim IDs.
- [x] Reject malformed/foreign/missing references, held/excluded uses, invented excerpts, stale QA/question, wrong predecessor and missing revision reason atomically.

## Task 2: Public query, revisions and change warnings

Files: same policy/tests; extend views.py.
Interface: basis_records(snapshot) returns verified history-ordered records; basis_status(snapshot,record) returns current/reason_codes plus superseded flag separately. Public m1_evidence_bases entries include record/ref/artifact_id, current, reason_codes, superseded, claims [{record,ref,artifact_id}]. Current indicates current inputs, not scientific readiness. Additional review refs for selected QA are exposed as review_candidates for coordinator assessment, never automatically selected.

- [x] Assert old QA import changes current basis reason to evidence_basis_qa_updated but historical view remains current.
- [x] Assert question revision changes only dependent basis status; revised basis retains old objects and previous_ref.
- [x] Validate stored identity, native event and claim bytes before projection; reject forged generic store records.
- [x] Run new tests plus external evidence/viewer/CLI tests. Run graph UI suites to check the additive view field.

## Delivery

- [x] Document CLI payload and exact output semantics, including B2–B6 still pending and current case question mismatch.
- [x] Verify diff, scoped tests, and served additive field after restarting only this task's viewer.
- [x] Commit only B1 code, tests and explicit docs. Preserve existing research work and long-lived worktree.

## Verification result

RED: unknown_operation before registration; later-head predecessor fork, omitted alternate-head review and hidden deleted collection reproduced before fixes. Final scoped Python run: 61 passed in 101.56s (new B1 tests 24 plus external evidence, adapters, viewer and views). Existing UI suites: 49 passed. Independent scoped review found no remaining blockers after fixes. Server GET /api/view exposes m1_evidence_bases; real project HEAD remains 97bbb95b1d60936c3d51276a1b849bf74ca4f35439ba02605ae8a069c77d44a3 with no basis artificially registered. No full M1 regression rerun because no gate/council policy changed.
