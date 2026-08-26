# Task 2 Report: Codex-native stage contracts and materials/AI profile

## Status

Implemented the 23-stage contract registry and the package-relative `materials_ai` research profile.

## Changes

- Added `researchclaw/core/contracts.py` with frozen `StageContract` and `Phase` dataclasses.
- Added all stages 1–23 with the specified stable names, project-relative artifact paths, phase grouping, and approval gates at stages 5, 9, and 20.
- Added `get_contract(stage_id)` with an explicit unknown-stage error.
- Added `researchclaw/core/profiles.py` with frozen `ResearchProfile` and YAML loading relative to the package module.
- Added `researchclaw/core/data/profiles/materials_ai.yaml` with MatBench, Materials Project, and NOMAD sources; materials-specific quality checks; and MAE, RMSE, and uncertainty guidance.
- Added focused contract and profile tests under `tests/codex_native/`.

## TDD evidence

The focused tests were run before implementation and failed during collection with the expected missing-module errors for `researchclaw.core.contracts` and `researchclaw.core.profiles`. After implementation, the same command passed all 3 tests.

## Verification

- `.venv/bin/pytest tests/codex_native/test_contracts.py tests/codex_native/test_profiles.py -v`: 3 passed.
- `.venv/bin/pytest -q`: 2956 passed, 56 skipped, 1 warning in 91.24s.
- `git diff --check`: no whitespace errors.
- Confirmed no `llm` or `acp` imports/references in `researchclaw/core`.

## Concerns

The repository-wide test run retains one pre-existing `RuntimeWarning` in `researchclaw/servers/ssh_executor.py` (`AsyncMockMixin._execute_mock_call` was never awaited); it is unrelated to Task 2.
