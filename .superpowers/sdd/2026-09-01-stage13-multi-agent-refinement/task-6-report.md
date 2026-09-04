# Task 6 implementation report

## Scope

- Added `finalize_refinement(project, decision_path)` for registered council decisions: `select_candidate`, `retain_baseline`, and `inconclusive`.
- Persists `refinement/final_selection.json` with the registered decision, retained immutable evidence, votes, supporting and dissenting roles, rationale, limitations, and Stage 14 questions.
- Advances Stage 13 to Stage 14 in one durable state write without modifying baseline results or candidate files.
- Replaced the unsupported Stage 13 handoff label with the verified refinement phase action. No Task 7 CLI was added.

## Safety properties

- No LLM or network calls and no deterministic metric ranking.
- Selected candidates require a registered immutable refinement evidence manifest and a final council round that evaluated and referenced that candidate result.
- Exact idempotence and recovery from interruption after final-selection publication but before state advancement.
- Tampered or unknown refinement session state fails closed during handoff.

## Verification

- Focused finalization: `5 passed, 83 deselected`.
- Selected candidate evidence paths: `2 passed, 102 deselected`.
- Stage 13 handoff: `2 passed, 4 deselected`.
- State models: `27 passed`.
- Earlier full refinement + handoff gate before the final parser hardening: `93 passed`.
- Broad refinement/execution/handoff/resume/Stage 12 gate: `246 passed, 1 failed`; the failure was a test fixture's 120-second wall deadline after the suite had run for about 62 minutes. The exact failed evidence-replacement case passed alone (`1 passed in 7.84s`).
- Required non-execution regression gate: `143 passed, 1 failed`; the failure was the known intermittent `execution_prerequisites_changed` Stage 11 fixture issue. The exact case passed alone (`1 passed in 2.04s`).
- Ruff, compileall, and `git diff --check`: clean.

## Concerns

- Long serial suites can exhaust synthetic 120-second refinement sessions before their run begins; this is test-runtime sensitivity, not a Task 6 behavior failure.
- The pre-existing Stage 11 fixture intermittently reports `execution_prerequisites_changed` in long combined suites; isolated rerun is green.
