# Codex-Native Development Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicitly confirmed NumPy Ridge runner for validated synthetic fixtures that writes only `experiment/dev_results.json`.

**Architecture:** Expose the already-validated development manifest and CSV rows as a typed internal value, then pass them to a dedicated fixed-function numerical runner. The CLI registers only an explicit development command; it cannot execute project code or arbitrary commands.

**Tech Stack:** Python 3.11+, NumPy >=1.24, standard-library CSV/JSON, pytest, existing atomic persistence and event log.

**Spec:** `docs/superpowers/specs/2026-08-29-codex-native-development-execution-design.md`

## Global Constraints

- Never import or execute project code, including `experiment/code/main.py`.
- Never create or modify `experiment/results.json`, `experiment/resources.json`, durable state, approvals, or the Stage-10 snapshot.
- Require `--input-manifest`, `--development`, and `--confirm-development-run` on every run.
- Use fixed Ridge `alpha = 1.0`; do not add scikit-learn or install packages.
- Write only `experiment/dev_results.json` atomically after complete validation.
- Always mark results `development_only: true` and `evidence_eligible: false`.
- Observe every focused test fail for the missing behavior before implementation.

---

### Task 1: Expose a reusable validated fixture

**Files:**
- Modify: `researchclaw/core/execution_gate.py`
- Modify: `tests/codex_native/test_execution_gate.py`
- Modify: `tests/codex_native/helpers.py`

**Interfaces:**
- Produces `ValidatedDevelopmentInput(manifest_path, manifest_sha256, manifest, cell_rows, feature_rows)`.
- Produces `validate_development_input(project, path, *, record_event=True) -> tuple[DevelopmentInputStatus, ValidatedDevelopmentInput]`.
- Preserves `recheck_development_input(project, path) -> DevelopmentInputStatus`.

- [ ] **Step 1: Add a test-only runnable fixture builder**

Create `write_runnable_development_fixture(project)` in `tests/codex_native/helpers.py`. It writes one synthetic dataset with eight cells, six disjoint condition groups, split roles train/validation/calibration/test, cutoff 2, two feature rows per cell, and predictors `capacity_ah` and `internal_resistance_mohm`. The manifest records literal row counts and computed SHA-256 values.

- [ ] **Step 2: Write the failing typed-result test**

```python
def test_validate_development_input_returns_verified_rows(stage_12_missing_project):
    project, _ = stage_12_missing_project
    manifest = write_runnable_development_fixture(project)
    status, validated = execution_gate.validate_development_input(
        project, "experiment/input_manifest.dev.json", record_event=False
    )
    assert status.readiness == "ready_for_development"
    assert validated.manifest_sha256 == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert len(validated.cell_rows) == 8
    assert len(validated.feature_rows) == 16
```

- [ ] **Step 3: Run RED**

Run `pytest -q tests/codex_native/test_execution_gate.py::test_validate_development_input_returns_verified_rows`.

Expected: FAIL because the typed API does not exist.

- [ ] **Step 4: Implement the typed validation result**

Add the frozen dataclass, move the current `recheck_development_input` body into `validate_development_input`, return immutable row tuples, and make the old function a wrapper. `record_event=False` suppresses only the event, never validation.

- [ ] **Step 5: Verify GREEN and commit**

Run `pytest -q tests/codex_native/test_execution_gate.py` and expect all tests to pass.

```bash
git add researchclaw/core/execution_gate.py tests/codex_native/test_execution_gate.py tests/codex_native/helpers.py
git commit -m "refactor(codex): expose validated development inputs"
```

---

### Task 2: Implement the fixed NumPy Ridge runner

**Files:**
- Create: `researchclaw/core/development_execution.py`
- Create: `tests/codex_native/test_development_execution.py`

**Interfaces:**
- Consumes `validate_development_input(..., record_event=False)`.
- Produces `DevelopmentRunStatus` with `to_dict()`.
- Produces `run_development_experiment(project, input_manifest_path, max_seconds=120, *, clock=time.monotonic) -> DevelopmentRunStatus`.

- [ ] **Step 1: Write the failing success test**

```python
def test_run_writes_non_evidentiary_metrics_without_mutating_gate(tmp_path):
    project, _ = build_stage_twelve_project(tmp_path / "project", readiness="needs_input")
    write_runnable_development_fixture(project)
    resources_before = (project.root / "experiment/resources.json").read_bytes()
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    status = run_development_experiment(
        project, "experiment/input_manifest.dev.json", max_seconds=120
    )
    result = json.loads((project.root / "experiment/dev_results.json").read_text())
    assert status.readiness == "development_run_complete"
    assert status.approval_eligible is False
    assert result["development_only"] is True
    assert result["evidence_eligible"] is False
    assert result["model"] == {
        "name": "ridge", "alpha": 1.0, "implementation": "numpy_closed_form"
    }
    assert result["aggregate_metrics"]["rmse_cycles"] >= result["aggregate_metrics"]["mae_cycles"]
    assert (project.root / "experiment/resources.json").read_bytes() == resources_before
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert not (project.root / "experiment/results.json").exists()
```

- [ ] **Step 2: Run RED**

Run `pytest -q tests/codex_native/test_development_execution.py::test_run_writes_non_evidentiary_metrics_without_mutating_gate`.

Expected: FAIL because `development_execution` does not exist.

- [ ] **Step 3: Implement aggregation and Ridge**

Parse labels and all feature columns except identifiers/cycle as finite floats. Average predictors per cell using only validated pre-cutoff rows. For each dataset require at least one train and one test cell. Fit only train cells:

```python
mean = train_x.mean(axis=0)
std = np.where(train_x.std(axis=0) == 0.0, 1.0, train_x.std(axis=0))
x = (train_x - mean) / std
design = np.column_stack([np.ones(len(x)), x])
penalty = np.eye(design.shape[1])
penalty[0, 0] = 0.0
beta = np.linalg.solve(design.T @ design + 1.0 * penalty, design.T @ train_y)
```

Apply train statistics to test cells. Report per-dataset and aggregate MAE/RMSE, role counts, group counts, ordered predictor names, NumPy version, and a zero-count leakage audit.

- [ ] **Step 4: Add RED tests for invalid values and splits**

Parameterize `""`, `"not-a-number"`, `"nan"`, and `"inf"`; update the mutated CSV hash in the manifest so each test reaches numeric validation. Add tests for an unknown split role and a dataset without test cells. Expect bounded error categories: `invalid_numeric_value`, `invalid_split_role`, and `missing_test_cells`.

- [ ] **Step 5: Implement the validation branches and verify GREEN**

Run `pytest -q tests/codex_native/test_development_execution.py` and expect all tests to pass.

- [ ] **Step 6: Commit**

```bash
git add researchclaw/core/development_execution.py tests/codex_native/test_development_execution.py
git commit -m "feat(codex): run bounded synthetic ridge validation"
```

---

### Task 3: Add deadline, atomic output, and bounded events

**Files:**
- Modify: `researchclaw/core/development_execution.py`
- Modify: `tests/codex_native/test_development_execution.py`

**Interfaces:**
- Uses `atomic_write_json(path, payload, prefix="dev-results-")`.
- Emits `development_execution_completed` or `development_execution_failed`.

- [ ] **Step 1: Write the failing timeout preservation test**

```python
def test_timeout_preserves_existing_result(tmp_path):
    project, _ = build_stage_twelve_project(tmp_path / "project", readiness="needs_input")
    write_runnable_development_fixture(project)
    result = project.root / "experiment/dev_results.json"
    result.write_bytes(b'{"prior":true}\n')
    ticks = iter([0.0, 0.1, 2.0])
    with pytest.raises(ValueError, match="development_timeout"):
        run_development_experiment(
            project, "experiment/input_manifest.dev.json",
            max_seconds=1, clock=lambda: next(ticks)
        )
    assert result.read_bytes() == b'{"prior":true}\n'
```

- [ ] **Step 2: Add failing event-boundary tests**

On success, require exactly the manifest path/hash, result path/hash, elapsed seconds, dataset count, and cell count. On failure, permit only manifest path, manifest hash when available, and `error_category`; prohibit raw rows, labels, predictions, and exception representations.

- [ ] **Step 3: Run RED**

Run `pytest -q tests/codex_native/test_development_execution.py -k 'timeout or event'`.

Expected: FAIL because phase deadlines and execution events are absent.

- [ ] **Step 4: Implement bounded phases and atomic finalization**

Validate `max_seconds` as a positive integer. Capture `started = clock()` and check `clock() - started > max_seconds` after fixture validation, aggregation, each dataset fit, metrics, and before writing. Build the complete payload in memory, write it atomically, hash the finalized file, then append success. Catch bounded development errors, append the sanitized failure event, and re-raise without replacing an existing result.

- [ ] **Step 5: Verify and commit**

Run `pytest -q tests/codex_native/test_development_execution.py`.

```bash
git add researchclaw/core/development_execution.py tests/codex_native/test_development_execution.py
git commit -m "fix(codex): bound development execution failures"
```

---

### Task 4: Expose the explicit CLI and document it

**Files:**
- Modify: `researchclaw/codex/cli.py`
- Modify: `tests/codex_native/test_cli.py`
- Modify: `README.md`
- Modify: `skills/researchclaw/SKILL.md`
- Modify: `skills/researchclaw/references/resource-planning.md`
- Modify: `tests/codex_native/test_public_docs.py`

**Interfaces:**
- Produces `execution run ROOT --input-manifest PATH --development --confirm-development-run [--max-seconds N] [--json]`.

- [ ] **Step 1: Write failing CLI tests**

Write one real success test asserting `development_run_complete` and `approval_eligible: false`. Parameterize omission of each required intent flag; every omission must return 2, keep stdout empty, name the missing flag on stderr, and leave `dev_results.json` absent.

- [ ] **Step 2: Run RED**

Run `pytest -q tests/codex_native/test_cli.py -k execution_run`.

Expected: FAIL because `execution run` is unregistered.

- [ ] **Step 3: Implement the CLI route**

Register only the development run branch. Default `--max-seconds` to 120 and reject zero/negative values. Route the complete intent set to `run_development_experiment`; provide no research-mode or arbitrary-command fallback. Non-JSON output is `stage 12: development_run_complete`.

- [ ] **Step 4: Verify CLI GREEN**

Run `pytest -q tests/codex_native/test_cli.py -k 'execution_run or execution_recheck'`.

- [ ] **Step 5: Update public guidance**

Document the exact command, NumPy-only Ridge model, `dev_results.json`, per-run confirmation, and unchanged research gate. Agent guidance must stop after reporting the development result and must not call it research execution.

- [ ] **Step 6: Run full verification and the 72-cell integration**

```bash
pytest -q tests/codex_native
git diff --check
PYTHONPATH=. /opt/homebrew/opt/python@3.11/bin/python3.11 -m researchclaw.codex.cli execution run /Users/jspark/Documents/Codex/2026-08-29/re/work/battery_life_ai_ready_data --input-manifest experiment/input_manifest.dev.json --development --confirm-development-run --max-seconds 120 --json
```

Verify Stage 12 remains `awaiting_approval`, research readiness remains `needs_input`, `resources.json` retains its pre-run hash, `dev_results.json` exists, and `results.json` does not.

- [ ] **Step 7: Commit and push**

```bash
git add researchclaw/codex/cli.py tests/codex_native/test_cli.py README.md skills/researchclaw/SKILL.md skills/researchclaw/references/resource-planning.md tests/codex_native/test_public_docs.py
git commit -m "feat(codex): expose confirmed development execution"
git push
```
