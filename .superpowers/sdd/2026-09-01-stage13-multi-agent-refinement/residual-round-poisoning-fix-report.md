# Residual round-poisoning fix report

## Status and scope

Implemented the focused Stage 13 residual fix. A retry submitted as the first assessment of a newly selected round is now fully validated and rejected before the new round descriptor can be published. No Tasks 4–8 work or unrelated restructuring was performed.

## Root cause

`register_refinement_assessment()` selected a new round and validated the submission with `_assessment_attempt()`, then immediately persisted the new `round.json` through `_write_registered_record()`. Retry ordering was checked only later, after `_assessment_history()` returned an empty initial slot. The call therefore raised `refinement_retry_order_invalid` only after both the descriptor file and its state artifact reference were durable.

That durable descriptor bound the new round to the rejected retry's evaluated-artifact set. A later valid initial assessment using a different registered candidate result then encountered the incomplete round and failed exact binding validation.

## RED → GREEN → REFACTOR

### RED

Added `test_rejected_first_retry_does_not_poison_new_round_binding`, which:

1. Completes round 1.
2. Registers candidate 1 and submits a syntactically and authoritatively valid retry as round 2's first assessment.
3. Expects `refinement_retry_order_invalid`.
4. Requires no `round-002` directory and no project-state change.
5. Registers candidate 2 and proves a valid initial assessment can create round 2 using the different evidence set `[evidence packet, candidate 2]`.

Command:

```text
uv run pytest tests/codex_native/test_refinement.py::test_rejected_first_retry_does_not_poison_new_round_binding -vv
```

Pre-fix result:

```text
FAILED tests/codex_native/test_refinement.py::test_rejected_first_retry_does_not_poison_new_round_binding
E       AssertionError: assert not True
E        +  where True = round_two.exists()
1 failed in 2.41s
```

This is the intended failure: the request raised the correct ordering error, but `round-002` was already durable.

### GREEN

Made the smallest production change in `register_refinement_assessment()`:

- Compute `wants_retry` once.
- Preserve `_assessment_attempt()` before the ordering error so schema, artifact, producer, and retry-authority validation behavior remains unchanged.
- When round selection indicates a new descriptor must be created, raise `refinement_retry_order_invalid` for a validated retry before `_write_registered_record()`.
- Leave the existing history-based retry-order check in place for already durable round descriptors.

Focused result:

```text
tests/codex_native/test_refinement.py::test_rejected_first_retry_does_not_poison_new_round_binding PASSED
1 passed in 2.44s
```

### REFACTOR

No structural refactor was warranted. Reusing the single `wants_retry` value removes repeated membership checks while keeping the change local to registration ordering.

## Regression and quality verification

Focused Stage 13 plus relevant state/contracts gate:

```text
uv run pytest tests/codex_native/test_deliberation.py tests/codex_native/test_refinement.py tests/codex_native/test_state.py tests/codex_native/test_contracts.py -q
91 passed in 108.61s (0:01:48)
```

Quality checks:

```text
git diff --check
# exit 0, no output

uv run ruff check researchclaw/core/refinement.py tests/codex_native/test_refinement.py
# exit 0, no diagnostics
```

## Files changed

- `researchclaw/core/refinement.py`
- `tests/codex_native/test_refinement.py`
- `.superpowers/sdd/2026-09-01-stage13-multi-agent-refinement/residual-round-poisoning-fix-report.md`

## Requirement and preservation review

- Pre-publication rejection: the new-round path rejects a validated first-record retry before descriptor persistence.
- No durable poison: the regression checks both absence of the entire new-round directory and equality of project state before and after rejection, covering `round.json`, its artifact reference, and `next_action`/other state drift.
- Different later binding: candidate 1 is used by the rejected retry; candidate 2 is used by the succeeding valid initial assessment, and the persisted binding is asserted exactly.
- Monotonic allocation and exact artifact binding: `_select_assessment_round()` and `_load_round_binding()` are unchanged.
- Idempotence and crash recovery: `_write_registered_record()`, orphan adoption, and existing-record branches are unchanged.
- Existing assessment/retry behavior: retry payload validation still occurs before the ordering error, and the existing-round history check remains intact.
- Scope: no Tasks 4–8 code or unrelated files were changed.

## Self-review

The diff is limited to one pre-persistence ordering guard, one regression test, and this report. Removing or moving the guard after `_write_registered_record()` makes the regression fail at the durable-directory assertion. Failing to preserve the later request's own evidence set is caught by the exact `evaluated_artifacts` assertion. The state-equality assertion catches a descriptor reference or any other project-state mutation even if filesystem cleanup were added later.

No correctness concerns remain from the focused review. The rejected submission file itself remains user-provided input under `submissions/`; the fix prevents only durable round side effects, as required.
