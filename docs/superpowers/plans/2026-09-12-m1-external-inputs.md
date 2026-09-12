# B2 External M1 Inputs Implementation Plan

**Goal:** Let synthesize/hypothesize/review consume one explicit current Atlas evidence basis, retaining native collection semantics and council requirements.
**Spec:** ../specs/2026-09-12-atlas-m1-evidence-route-design.md (approved B2).
**Architecture:** A separate m1_external_inputs policy resolves current basis/claims. Existing node records admit exactly either their legacy parents or external parents. Shared scientific content/council validation is reused. No gate/handoff eligibility extension (B5), UI form (B4), or real question rewrite (B6).

## Contracts

External input_refs keys:
- synthesize: questions,evidence_basis
- hypothesize: questions,evidence_basis,synthesize
- review: questions,evidence_basis,synthesize,hypothesize

Presence of evidence_basis selects the external contract; no automatic global route selection. No mixed parent keys. Parents must bind to the same question and immutable basis version. Basis must be native, current, and not superseded. Only claim objects belonging to that basis can be cited as evidence/counterevidence. Scope/allowed use remain traceable through claim objects. Semantic scope compliance remains an actual council task; structural validation does not certify science.

Legacy records retain their shape/bytes. Question review is still required before authorship; downstream draft revisions may be authored while their own prior councils are pending as before. Any node review readiness rechecks basis and parent coherence. Updated QA or superseded basis requires explicit node revisions; no historical rewrite.

## Tasks

- [x] Write failing public-command tests in test_m1_external_inputs.py using the B1 synthetic fixture: complete question review, register a basis, then synthesize without screen/collect/extract.
- [x] Create m1_external_inputs.py: external_parents(node), uses_external(artifact), external_evidence(snapshot,artifact). Return ready, reason_codes, basis_ref, corpus_ref=None, source_groups=None, extraction_refs containing only admitted claim refs, and inherited limitations.
- [x] Update m1_nodes._shape/register_node/_review_node to recognize closed external inputs and reuse actual node councils. Skip only the basis key in native-parent recursion; validate it through external_evidence.
- [x] Update m1_review.validate_content to consume the selected route, preserving content and issue rules. prepare_hypothesis_review selects the explicit synthesize route and reports missing later nodes without legacy collection reasons.
- [x] Test full synthetic three-node authorship and real command-based council phases, absent councils blocked, raw QA/outside claims/mixed basis/legacy keys rejected, QA updates invalidate current but preserve historical views, basis supersession requires repair.
- [x] Review changed contracts independently; fix reproduced blockers.
- [x] Run external-input/basis/legacy scope tests and representative legacy synthesis tests, plus existing UI tests. Restart local viewer and verify current project HEAD unchanged. Document CLI inputs and B2/B3/B5 boundaries; commit only task files.

## Review findings and fixes

Real native-baseline regression reproduced reverse route mixing; shared validate_parent_routes now rejects it during registration and readiness. Independent review also reproduced external reasoning reusing an approved native corpus for handoff. Pending B5, native-only route guards now protect both eligibility and historical package reconstruction. No external handoff authorization is added.

Verification so far: external-input/basis/legacy scope 61 passed (182.93s); representative legacy review + reverse-mixing + missing-prerequisite 3 passed (205.88s). Completed native regression snapshot also accepted by the final native-only handoff guard in a fresh process. UI 49 passed. Live server updated; real project HEAD and four registered nodes unchanged. Final external-handoff public-command regression: 1 passed in 124.59s; eligibility and public publication both rejected atomically. Total selected Python tests: 65 passed. Independent re-review: no remaining blockers.
