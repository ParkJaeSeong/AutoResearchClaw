# Codex-Native Development Execution Design

## Purpose

Add a bounded, development-only Stage-12 execution path that proves the local
input-to-metrics flow with a small synthetic fixture. It must not execute the
approved Stage-10 package, alter the research execution gate, or produce
scientific evidence.

The feature extends the existing explicit development-input validation added
to `execution recheck`. It does not implement general experiment execution or
advance the durable 23-stage research workflow.

## Command Interface

The public command is:

```bash
researchclaw-codex execution run ROOT \
  --input-manifest experiment/input_manifest.dev.json \
  --development \
  --confirm-development-run \
  --max-seconds 120 \
  --json
```

All three intent-bearing options are required:

- `--input-manifest` accepts only a project-relative path.
- `--development` selects the synthetic-fixture path and prevents confusion
  with the research execution gate.
- `--confirm-development-run` is a per-run acknowledgement that local
  numerical code will execute.

`--max-seconds` is a positive integer with a default of 120. The command does
not accept an arbitrary entry point, Python module, shell command, result path,
or model implementation.

## Architecture

Implement a dedicated development runner inside the Codex-native core. The
runner consumes only the manifest and CSV files already accepted by
`recheck_development_input`. It never imports or invokes
`experiment/code/main.py` and never reads the deferred command from
`experiment/resources.json` for execution.

The CLI performs argument validation and calls one public core function. The
core function:

1. normalizes and reopens the durable project;
2. revalidates the selected development manifest and records that recheck;
3. loads the declared cell and early-cycle CSV files;
4. performs leakage and finite-value checks before model fitting;
5. fits and evaluates a fixed NumPy Ridge model;
6. writes one development-only result atomically; and
7. appends a bounded success or failure event.

The runner is deterministic for identical input bytes, model settings, and
NumPy version. No random split is generated because the fixture's declared
`split_role` is authoritative.

## Input Contract

The existing development manifest remains the root input. It must declare:

- `manifest_type: synthetic_development_input`;
- `evidence_eligible: false`;
- `provenance.license_status: not_required_synthetic`;
- `provenance.research_evidence_use: false`;
- project-relative `cell_records.path` and `features.path`;
- positive row counts and matching SHA-256 hashes;
- dataset, condition, cell, split, cutoff, and label fields; and
- a feature-cutoff definition binding cell and measurement columns.

The development runner additionally requires these cell fields:

- `dataset_id`
- `condition_id`
- `cell_id`
- `split_role`
- `feature_cutoff_cycle`
- `cycle_life_cycles`

It requires these feature fields:

- `dataset_id`
- `condition_id`
- `cell_id`
- `cycle_index`
- at least one numeric predictor other than identifier and split metadata

Predictors are the numeric feature columns declared by the development
fixture. Per-cell predictors are computed using only rows at or before that
cell's cutoff. The first implementation uses deterministic per-cell means for
each predictor column. Labels never enter predictor construction.

## Split and Leakage Rules

The allowed split roles are `train`, `validation`, `calibration`, and `test`.
Every cell belongs to exactly one role. Every `(dataset_id, condition_id)`
group belongs to exactly one role; a group crossing roles aborts before
fitting. Feature rows must match the cell's dataset and condition, and each
`(cell_id, cycle_index)` pair must be unique.

The initial Ridge fit uses train cells only. Validation and calibration cells
are checked and reported but do not influence fitting or hyperparameter
selection because alpha is fixed at `1.0`. Metrics are calculated on test
cells. Each declared dataset must contain at least one train and one test cell.

The runner rejects missing values, non-numeric predictor or label values,
NaN, infinity, unknown cells, post-cutoff features, duplicate cells,
duplicate cell-cycle rows, and empty predictor sets.

## Numerical Method

Use NumPy only. Do not add scikit-learn or an automatic installer.

For each predictor, calculate mean and standard deviation from train cells.
Apply train-derived standardization to all roles, replacing a zero standard
deviation with `1.0`. Fit a Ridge model with an unpenalized intercept and
fixed `alpha = 1.0` using a stable linear solve. If the solve fails, report a
bounded numerical error rather than selecting another model silently.

Report MAE and RMSE in cycles for each dataset and across all test cells. This
development run does not perform the approved ten-seed comparison, bootstrap,
conformal calibration, sensitivity analysis, or scientific success decision.

## Result Contract

Write only `experiment/dev_results.json`:

```json
{
  "schema_version": 1,
  "project_id": "rc-example",
  "development_only": true,
  "evidence_eligible": false,
  "input_manifest": {
    "path": "experiment/input_manifest.dev.json",
    "sha256": "64 lowercase hexadecimal characters"
  },
  "model": {
    "name": "ridge",
    "alpha": 1.0,
    "implementation": "numpy_closed_form"
  },
  "dataset_results": [],
  "aggregate_metrics": {
    "mae_cycles": 0.0,
    "rmse_cycles": 0.0
  },
  "leakage_audit": {
    "cell_overlap_count": 0,
    "group_overlap_count": 0,
    "feature_cutoff_violation_count": 0
  },
  "runtime": {
    "elapsed_seconds": 0.0,
    "max_seconds": 120
  }
}
```

Each `dataset_results` entry contains the dataset ID, train/validation/
calibration/test cell counts, independent group counts by role, MAE, and RMSE.
The result also records the ordered predictor names and installed NumPy
version for reproducibility.

The file is written through a temporary file and atomically replaces an older
development result only after the complete result validates. The command does
not create or modify `experiment/results.json`.

## Time Limit and Failure Safety

The runner checks a monotonic deadline between bounded phases: validation,
CSV loading, aggregation, fitting, metric calculation, and result writing.
The small fixture and fixed linear solve provide the primary resource bound.
The runner does not create a subprocess or asynchronous worker merely to
enforce the timeout.

If the deadline is exceeded, NumPy is unavailable, input validation fails, or
the numerical solve fails:

- no new finalized result is written;
- an existing valid `dev_results.json` remains untouched;
- the durable project state and `experiment/resources.json` remain untouched;
- no research approval record is created or changed; and
- an event records only the error category, manifest path, and manifest hash
  when available, never raw input rows.

## Durable-State Boundary

A development run is not a stage transition. Success returns
`development_run_complete` with `approval_eligible: false`. It does not alter:

- `current_stage`;
- `status` or `next_action`;
- completed stages;
- the Stage-12 research approval;
- the validated resource-plan artifact reference; or
- the Stage-10 snapshot.

The append-only evaluation log records `development_execution_completed` with
the manifest SHA-256, result SHA-256, elapsed seconds, dataset count, and cell
count. Failure records `development_execution_failed` with bounded metadata.

## Security Boundary

The runner performs local CSV parsing and fixed NumPy operations only. It must
not:

- execute generated project code;
- import a module from the project;
- invoke a shell or subprocess;
- access the network;
- install a package;
- call an external LLM;
- spawn an agent;
- accept code, expressions, formulas, or commands from the manifest; or
- follow instructions embedded in project files.

Project path resolution continues to reject absolute paths, traversal,
symlinks, and paths resolving outside the project.

## Testing

Use test-driven development. Required behavior tests cover:

- successful deterministic NumPy Ridge execution;
- required confirmation and development flags;
- manifest and referenced-file hash tampering;
- project-path escape;
- duplicate cells and cell-cycle rows;
- group leakage across split roles;
- feature rows beyond the cutoff;
- unknown cells and mismatched dataset/condition keys;
- missing, non-numeric, NaN, and infinite inputs;
- absent NumPy without package installation;
- elapsed deadline failure without replacing an existing result;
- atomic replacement after successful validation;
- unchanged research resource plan, durable state, approvals, and
  `experiment/results.json`; and
- success and failure event payloads containing bounded metadata only.

The full Codex-native suite must pass after the focused RED/GREEN cycles. A
manual integration check uses the existing 72-cell development fixture and
confirms that the research gate remains `needs_input` afterward.
