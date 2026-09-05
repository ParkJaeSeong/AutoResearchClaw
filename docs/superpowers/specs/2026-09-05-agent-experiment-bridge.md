# Agent-authored experiment bridge

## Approved intent

The user approved a separation between agent-authored scientific code and a
repository-owned execution/registration boundary, and explicitly requested
implementation rather than more confirmation rounds. This is a product repair,
not permission to execute or approve the user's research project.

## Problem and acceptance boundary

Stage 10 currently demands exact canonical main.py bytes whose run_experiment
always raises. It also validates all declared input files as JSON. Stage 12
requires a package contract, a distinct known-answer fixture and self-test config
that the normal six-output authoring path cannot produce. Tests replace the
package after Stage 10 and manually rebind state; those tests do not demonstrate
the missing product path.

The repair is complete only when a fresh project can author an agent algorithm,
pass normal Stage 10 static validation, complete resource planning, obtain and
run the exact self-test argv, register it, record an explicit execution approval,
obtain and execute the exact research argv, register the actual result and enter
Stage 13 with immutable evidence. No post-validation replacement, manual state
rebinding, mock validator or prewritten research result is allowed in this gate.
The existing Stage 13 candidate branch must remain usable with the new baseline.

## Scope and interfaces

- Keep the transport/contract/result writer repository-owned. Agent-authored
  code is a separate experiment module, not an editable execution wrapper.
- Initial supported scientific interface is bounded scalar regression:
  `fit(train_rows, config) -> JSON-compatible model` and
  `predict(model, feature_rows, config) -> list[finite float]`.
  The runner selects train rows and strips targets from prediction inputs.
  A training-mean baseline and a fitted one-feature least-squares candidate
  must both be expressible by authored Python, not a fixed algorithm selector.
- The runner owns CSV decoding, finite-value and unique identity checks,
  disjoint cell/group partitions, target selection, MAE calculation, runtime
  measurement, contract/provenance binding and exclusive result publication.
  It may also support existing JSON inputs, but must never parse CSV as JSON.
- Metric support in this vertical slice is explicitly `mae`; reject unsupported
  metrics rather than copying an arbitrary name onto an MAE calculation. Units
  come unchanged from the approved design. Data column mappings are declared,
  not inferred from filenames or invented by a runtime heuristic.
- Permit only a statically checked pure numerical Python subset for authored
  algorithms: functions, local values, arithmetic, row/column indexing and
  bounded iteration over supplied data. Reject imports, file/process/network
  access, dynamic evaluation, introspection, dunder access and module-scope
  execution. This is not a general Python sandbox; disclose that limitation.
  Do not relax legacy capability checks globally to make a new package pass.
- Extend the declared authoring artifacts to cover the algorithm module and
  every package-contract/self-test input required by Stage 12. Hash every
  executed/read package file. Use a discriminated versioned format where
  necessary; validate legacy formats on their existing path, without silently
  converting previously approved files or evidence.
- The known-answer self-test must execute real metric code against an independent
  fixture, compare expected values and bind actual package/fixture/environment
  identities. Never mark a fixed report passed or reuse research inputs as the
  self-test. The trusted runtime must not import project code during validation.
- Preserve exact returned interpreter/argv/cwd, environment fingerprint checks,
  false-valued prohibitions, existing confirmation flags, immutable registration,
  no-overwrite semantics, and Stage 14 read-only waiting boundary.

## Compatibility and authority

- No external LLM API, provider configuration, model subprocess, new package
  installation, network call or paid service is part of the new runtime.
- Codex agents own algorithms and scientific decisions; CLI owns deterministic
  validation and evidence. Low MAE does not automatically approve a candidate.
- Existing user projects and installed plugin are unchanged during development.
  The approved project at Downloads/researchclaw-regression-path-test-20260905
  remains at Stage 10 until product verification and a separately authorized
  deployment/resume step.
- Preserve old approved evidence byte-for-byte. If a new contract format is
  needed, existing packages must either validate as before or receive an explicit
  unsupported-format action; never bless them with rewritten hashes.
- Do not implement Stage 14 analysis, a general experiment scheduler or a model
  provider. Do not claim scientific validity from a synthetic workflow pass.

## Verification

Use x=0..13, y=2*x+1 and 14 unique cell IDs in seven pairs. Partition train
x=0..5, validation 6..7, calibration 8..9, test 10..13. The train-only constant
baseline is 6 and independently derived test MAE is 18 arbitrary units. An
authored least-squares line fitted only to train has expected test MAE 0 within
1e-9 tolerance. These are test expectations, never runner-returned constants.
Mutating held-out targets must not change the fitted model or predictions.

Cover mutated algorithm/input/contract bytes, wrong self-test answer, unsupported
metric, group leakage, extra/missing input columns, changed interpreter, arbitrary
imports and missing approvals. Assert failure without publication where the
existing protocol requires it. Reuse existing evidence-store publication gates.
The decisive integration test starts no later than an approved Stage 9 fixture;
below that boundary synthetic setup approvals may be clearly labelled test data.
Above it only real public authoring/validation/approval/registration transitions
are allowed. No test helper package substitution is permitted.

Also test one new-baseline refinement candidate through the unchanged public
protocol. Test votes may be explicitly synthetic in automated tests; distinguish
this from later live three-agent scientific evaluation.
