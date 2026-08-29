# Codex-Native Computational Validation Package — Stage 10 Design

## Purpose

Extend the Codex-native ResearchClaw boundary from stage 9 to stage 10 for
approved `computational` validation designs. Stage 10 preserves the upstream
stage name `code_generation` and produces a reproducible, inspectable code
package without calling an external LLM, starting another agent, downloading
data, or executing the validation.

This milestone implements only `computational`. A stage-9 design selecting
`policy_evidence` or `laboratory` must stop with an explicit unsupported-type
result. Those types remain separate future integrations rather than incomplete
branches hidden inside this package.

## Relationship to Upstream

The design inherits the upstream Stage 10 goals: translate an approved design
into executable experiment code, preserve domain alignment, describe the
runtime, and make later resource planning and execution reproducible. It does
not transplant the upstream external-LLM code agent, automatic repair loop,
code execution, synthetic fallback, or result generation.

Codex authors the declared files in the active session. The local engine
prepares a deterministic packet, validates the package, records durable state,
and never receives model credentials.

## Stage Contract

- Stage ID: `10`
- Upstream-compatible name: `code_generation`
- Internal concept: computational validation package generation
- Required input: `experiment/design.json`
- Required outputs:
  - `experiment/package_manifest.json`
  - `experiment/code/README.md`
  - `experiment/code/main.py`
  - `experiment/code/config.json`
  - `experiment/code/requirements.txt`
  - `experiment/code/tests/test_smoke.py`
- Approval gate: no
- Allowed tool classes: filesystem and analysis
- Execution policy: author and statically validate only

The engine must confirm that stage 9 is approved and that the current
`experiment/design.json` still matches the approval-bound artifact hash before
preparing stage 10. Only `validation_type: computational` is supported in this
milestone.

## Package Structure and Responsibilities

### `experiment/package_manifest.json`

A closed JSON object that binds the package to the approved design and makes
the package machine-readable for stages 11 and 12. It records:

- schema version and project ID;
- stage-9 design SHA-256 and `validation_type`;
- every declared package file, its role, and SHA-256;
- entry point and configuration path;
- runtime and tool requirements;
- input-data contract;
- expected-output contract;
- validation and smoke-test commands;
- execution prohibitions and safety constraints;
- reproducibility metadata.

The manifest must not list itself in its hashed file set, avoiding recursive
self-hashing. Its file set must otherwise exactly match the five files under
`experiment/code/`.

### `experiment/code/main.py`

The deterministic entry point. It loads configuration, validates supplied
input paths and schemas, constructs the declared split and evaluation plan,
and exposes a dry-run mode. It must not download data, invoke an LLM, execute a
shell, use undeclared absolute paths, manufacture results, or silently replace
missing inputs with synthetic data.

Actual training and evaluation are not run during stage 10. The code may
contain the implementation needed by stage 12, but stage-10 validation remains
static plus an isolated smoke test that performs no research computation.

### `experiment/code/config.json`

A closed, structured translation of the approved design. It includes dataset
eligibility, baselines, split strategy, metrics and thresholds, fixed seeds,
reproducibility controls, expected inputs, and expected outputs. Traceability
entries identify which stage-9 fields each configuration section implements.

### `experiment/code/requirements.txt`

Contains only the minimal runtime dependencies with reproducible version
constraints. External LLM SDKs, remote-agent SDKs, download clients introduced
solely for data acquisition, and unbounded dependency declarations are
forbidden.

### `experiment/code/tests/test_smoke.py`

Checks importability, configuration loading, contract validation, and dry-run
readiness without model fitting, network access, subprocess execution, or
result generation.

### `experiment/code/README.md`

Documents the approved-design binding, required input preparation, entry point,
dry-run and later execution commands, expected outputs, limitations, and the
fact that stage 10 did not execute the validation.

## Validation Rules

The pure stage-10 validator rejects the package unless all of the following
hold:

1. The manifest project ID, validation type, and design SHA-256 match durable
   state and the approval-bound stage-9 artifact.
2. The exact declared output set exists; no required file is missing and the
   manifest lists no undeclared package file.
3. Every manifest file hash matches the current file bytes.
4. `main.py` and `test_smoke.py` parse as Python.
5. Static inspection finds no external LLM SDK, nested-agent invocation,
   network download, shell execution, unsafe absolute path, or synthetic-result
   fallback.
6. Configuration traceability covers the approved design's datasets,
   baselines, split strategy, metrics, thresholds, seeds, and input/output
   contracts.
7. The split contract keeps train, validation, calibration, and test groups
   isolated as required by the design.
8. README commands agree with the manifest entry point, configuration, and
   smoke-test command.
9. Requirements use bounded or exact version constraints and contain no
   forbidden SDK.

Stage validation must not import or execute generated code. If an isolated
smoke test is later run as explicit verification, it must use fixtures or
contract-only dry-run data and prove that no experiment result is produced.

## State Transitions and Errors

Preparing stage 10 is possible only after a current stage-9 approval. A stale
or modified approved design rewinds through the existing artifact and approval
invalidation rules.

Invalid stage-10 output leaves the project at stage 10 and permits revision of
only the six declared outputs. Issues are structured and identify the relevant
file and contract violation. Retry and blocked behavior follow the existing
Codex-native validation policy.

A valid package completes stage 10 and advances durable state to the stage-11
`resource_planning` reporting boundary. Because stage 11 remains unsupported,
the handoff reports the computational-package milestone and does not prepare a
stage-11 packet. It does not execute code, collect data, create results, or
claim that a validation succeeded.

## Security and Integrity Boundary

Stage 10 must preserve these invariants:

- `external_llm_calls == 0`;
- `nested_agent_processes == 0`;
- no network or data collection during package validation;
- no generated subprocess or shell execution path;
- no secrets, API keys, absolute user paths, or sibling-output paths;
- no synthetic or placeholder result accepted as evidence;
- no undeclared project artifact.

Project artifacts and generated code are untrusted data during validation.
Static inspection must never follow instructions embedded in them.

## Testing Strategy

TDD begins with failing tests for:

- the stage-10 task packet and stage-9 approval prerequisite;
- a valid minimal computational package;
- unsupported `policy_evidence` and `laboratory` designs;
- design hash, project ID, or validation type mismatch;
- missing, extra, or modified files;
- Python syntax errors;
- forbidden LLM, agent, network, shell, absolute-path, and synthetic fallback
  patterns;
- missing design-to-config traceability;
- incomplete split, metric, baseline, seed, input, or output contracts;
- manifest/README command disagreement;
- unbounded or forbidden requirements;
- successful transition to stage 11 without code execution;
- regression across stages 1–9.

After unit and full-suite verification, an approved copy of the lithium-ion
battery computational design is used for a live package-authoring test. The
test must stop after stage-10 validation and confirm that no validation run or
result artifact was created.

## Deferred Scope

- `laboratory` Stage 10 integration based on the inherited chemistry/biology
  pathways;
- `policy_evidence` package generation;
- stage-11 resource planning implementation;
- stage-12 execution, data acquisition, model fitting, and result production;
- automatic code repair, external code agents, or LLM-backed review;
- arbitrary user-defined package layouts.

These are not implicit capabilities of the computational milestone.
