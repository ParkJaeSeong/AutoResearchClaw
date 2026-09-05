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

## Exact v2 wire schema (chosen before implementation)

Manifest discriminator is integer `schema_version: 2`. Its exact keys are
`schema_version, project_id, design_sha256, validation_type, entry_point,
config_path, files`; files entries are exactly `path, role, sha256`.
Stage 10 packets declare `profile_context.agent_regression_v2_outputs`: manifest,
`experiment/package_contract.json`, `experiment/self_test_fixture.json`, and
`experiment/code/{README.md,main.py,algorithm.py,config.json,self_test_config.json}`.
The manifest binds every other file in this closed set. The manifest itself is
bound by existing Stage 10 artifact registration and subsequent execution evidence.
V1 packets and validators retain their existing path. V2 is explicitly selected by
the authored manifest discriminator, never by inferred scientific content.

V2 package contract keys are the v1 keys plus `algorithm_path, runtime_sha256`.
Runtime identity is a closed mapping of repository module filenames to their
SHA-256 digests, covering `agent_experiment.py`, `agent_experiment_runtime.py`,
and `execution_environment.py`. A runtime change requires reauthoring/validation;
same-version changed runtime code cannot silently execute approved evidence.
The wrapper is exact canonical bytes importing the repository runtime `main`.
V2 returned commands dispatch directly to the installed trusted module as
`<verified interpreter> -P -m researchclaw.core.agent_experiment_runtime <suffix>`.
They never execute the project wrapper before checking its hash. `-P` suppresses
unsafe script/current-directory imports; the installed environment and module
search configuration must still be trusted. Actual interpreter flags/module and
arguments from `sys.orig_argv` must match the prepared command; only its launcher
slot is normalized to the independently fingerprinted interpreter (macOS framework
launchers rewrite that slot to Python.app). V1 launch dispatch is unchanged.
Baseline v2 self-test preparation appends the derived launch flag
`--self-test-environment <prepared environment fingerprint>` after the authored
closed suffix, without writing preparation state. The runtime requires that
fingerprint to match before publication; replacing only the interpreter cannot
silently rederive authority. Candidate self-test context already binds its
environment and remains unchanged. This derived flag is not an authored schema
field or an addition to `self_test.argv_suffix`.
Metrics are exactly one `{name: mae, unit: <approved>, implementation:
researchclaw.core.agent_experiment:mean_absolute_error}` entry. Dependencies are
empty. Prohibitions are exactly network_access, external_llm_calls,
nested_agent_processes, all literal false. Self-test/execution keys retain v1
shape. Self-test input is exactly `{schema_version: 2, fixture_path: <declared>}`;
the distinct JSON fixture is exactly `{targets: [...], predictions: [...]}`.
This known answer exercises the real repository MAE implementation independently
of candidate science, so candidate and baseline share the same metric check.

Research config exact keys: `schema_version, project_id, design_sha256,
input_contract, split_strategy, columns, parameters, metrics`.
`input_contract` is exactly `{required_paths: [<one project-relative CSV>]}`;
`split_strategy` is exactly `{isolation_key: <identity column>, overlap_policy:
disjoint, groups: [train, validation, calibration, test]}`. `columns` is exactly
`{identity, group, split, target, features: [<one or more feature column names>]}`;
all mapped names must be distinct. CSV headers equal this declared set; IDs are
unique, all four roles nonempty, and groups cannot cross roles. Numeric features
and targets are finite. Algorithm receives only numeric feature/target mappings
for train and only numeric feature mappings for prediction; `parameters` is the
only algorithm config. Model must be finite JSON. Before serialization, traversal
is bounded to 10,000 value/key occurrences (including repeated shared objects),
depth 64 and 1 MiB cumulative string bytes; serialized JSON is at most 1 MiB.
Scalar MAE uses only test rows.
Comparisons accept only finite numeric scalar operands, with native chained
short-circuit behavior. `min` and `max` accept finite numeric scalar arguments or
a list/tuple/generator of finite numeric scalars, capped at 100,000 items. These
checks occur before any comparison, excluding recursive collection comparisons
that can consume exponential C-level work outside the authored opcode budget.
Dictionary keys and subscript indices are checked before implicit hashing or
equality: only finite numeric scalars or strings of at most 65,536 characters
are permitted. This applies to dictionary construction, lookup and subscript
Store targets in loops/comprehensions. Dictionary unpacking is statically
prohibited; direct subscript assignment remains prohibited. Returned model
objects still require JSON-compatible string keys. Tuples remain usable as
values, but never as dictionary keys or indices.

Candidate local paths are `code/model.py`, `code/algorithm.py`,
`config/config.json`, `tests/self_test_config.json`, `tests/self_test_fixture.json`,
`package_metadata/{package_contract.json,package_manifest.json}` and optional
README is not part of candidate closure. The trusted runtime handles existing
refinement context flags. All self-test and result schemas stay v1 and
reuse existing registration and publication gates. Runtime imposes bounded
algorithm source, row count and instruction budget; it is not a general Python
sandbox.

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
