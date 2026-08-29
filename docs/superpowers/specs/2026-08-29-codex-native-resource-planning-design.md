# Codex-Native Stage 11 Resource Planning Design

## Purpose

Stage 11 answers one operational question: is the approved Stage 10 computational package ready to execute safely in Stage 12, and if not, what remains to be prepared?

It inherits upstream AutoResearchClaw's `resource_planning` role but replaces the upstream model-generated GPU schedule with a closed, locally validated plan. Stage 11 performs no research computation. It does not execute generated code or smoke tests, install packages, download data, contact a network service, launch Docker or subprocesses, or create experimental results.

## Scope and Boundary

Stage 11 consumes only:

- the approved `experiment/design.json`;
- the validated `experiment/package_manifest.json`;
- `experiment/code/config.json`;
- `scope/hardware_profile.json`; and
- a read-only observation of the current Mac's CPU, memory, and free disk space.

It produces exactly one declared output:

- `experiment/resources.json`.

Stage 12 remains unsupported by this change. A valid Stage 11 plan advances durable state to Stage 12, but actual execution is always protected by an explicit user approval gate.

## Resource Plan Contract

`experiment/resources.json` is a closed JSON object. It contains:

- schema version and project ID;
- SHA-256 bindings for the approved design, Stage 10 package manifest, Stage 10 config, and the generated resource plan's declared inputs;
- the saved hardware profile and a current read-only hardware observation, including the observation method and timestamp;
- input readiness entries with project-relative path, required/optional status, existence, regular-file type, size, SHA-256 when present, license status, and preparation note;
- a closed task DAG with unique task IDs, dependencies, priority, CPU, memory, GPU, disk, and estimated duration;
- aggregate CPU, memory, GPU, disk, and duration budgets consistent with the task entries;
- the exact deferred Stage 12 command `python experiment/code/main.py --config experiment/code/config.json` and exact result path `experiment/results.json`;
- prohibitions recording zero network access, downloads, package installation, external LLM calls, and nested agent processes during Stage 11;
- warnings and unmet prerequisites; and
- readiness equal to `ready_for_execution` or `needs_input`.

The task DAG must include preparation/readiness work and the later experiment command, but Stage 11 never runs those tasks. Dependencies must reference existing task IDs and form an acyclic graph. The first Codex-native implementation uses `max_parallel_tasks: 1`: total estimated duration is the sum of task durations, while peak CPU, memory, GPU, and temporary disk are the maximum values required by any one task. This removes scheduler-dependent budget ambiguity until parallel Stage 12 execution is designed explicitly.

## Hardware Observation

The engine collects only read-only local facts available without running a benchmark:

- logical CPU count;
- total physical memory;
- free bytes on the project filesystem;
- detected platform and architecture; and
- GPU availability only when it can be obtained through a passive system query.

The saved `scope/hardware_profile.json` remains evidence, not mutable configuration. Differences between it and the current observation become warnings. Stage 11 does not rewrite the profile or auto-adjust the experiment package.

Hardware sufficiency is evaluated against the plan's declared peak requirements. A shortfall produces `needs_input` with a specific remediation; malformed or internally inconsistent requirements produce `invalid_plan`.

## Readiness Semantics

Validation has three outcomes:

1. `ready_for_execution`: the plan is valid and every required input, license fact, hardware requirement, command, hash, and safety constraint is satisfied.
2. `needs_input`: the plan is structurally valid, but one or more external prerequisites such as a data file, license confirmation, memory, disk, or GPU are missing. The plan is preserved and lists the exact user action required.
3. `invalid_plan`: the resource plan itself violates schema, hash, path, DAG, budget, command, or safety rules and must be repaired at Stage 11.

Both `ready_for_execution` and `needs_input` complete the planning milestone and advance durable state to Stage 12. Only `ready_for_execution` is eligible for execution approval. `needs_input` locks the approval gate until a read-only recheck confirms the missing prerequisites without changing the approved plan.

## Stage 12 Approval Gate

Stage 12 execution always requires explicit user approval. The approval record binds:

- the approved Stage 9 design SHA-256;
- the Stage 10 package manifest SHA-256;
- the Stage 10 config SHA-256; and
- the Stage 11 resource plan SHA-256.

Approval is refused while readiness is `needs_input`. Any subsequent change to a bound artifact invalidates approval automatically. No execution command is run as part of approval.

The durable boundary after a valid Stage 11 plan is:

```text
completed_stages = [1, ..., 11]
current_stage = 12
approval_required = true
next_action = approve_experiment_execution | report_missing_execution_inputs
```

## Validation Rules

The pure Stage 11 validator rejects or blocks a plan unless all applicable rules hold:

- design, package, config, and approval hashes match current durable state and exact file bytes;
- the plan uses only its closed fields and nested schemas;
- all paths are project-relative, non-traversing, and contain no symlink component;
- input facts agree with the current filesystem observation;
- task IDs are unique, dependencies exist, and the DAG is acyclic;
- per-task values are typed, non-negative, and within declared policy limits;
- aggregate budgets agree with task requirements and current hardware;
- the execution command agrees with the approved package contract;
- the result path is exactly `experiment/results.json` and does not exist during Stage 11;
- no Stage 11 network, download, installation, external LLM, nested-agent, or generated-code execution is declared or observed;
- missing required inputs cannot coexist with `ready_for_execution`; and
- warnings and unmet prerequisites are deterministic and actionable.

`needs_input` is not a validation failure when the plan truthfully records missing prerequisites. A false readiness claim is an invalid plan.

## Invalidation and Recovery

Changes to Stage 9 or Stage 10 artifacts rewind and invalidate Stage 11 through the existing artifact-lineage mechanism. Changes to an approved `resources.json` invalidate Stage 12 approval.

Input files may appear after a `needs_input` plan. A recheck may update only observed readiness facts and hashes for paths already declared by the approved resource plan. It must not add new paths, tasks, commands, or budgets. Material plan changes require returning to Stage 11 and revalidating the complete plan.

## CLI and Skill Behavior

The existing `stage prepare` command exposes the Stage 11 packet. Codex authors only `experiment/resources.json`. `stage validate` validates and advances the milestone. Status and resume report either the Stage 12 approval gate or the missing-input actions.

The ResearchClaw skill teaches Codex to:

1. read only the approved Stage 9/10 artifacts and hardware facts;
2. author the closed resource plan;
3. statically validate and repair it;
4. report readiness and user actions; and
5. stop before Stage 12 execution.

## Testing Strategy

Tests cover:

- a valid ready plan;
- a valid `needs_input` plan;
- saved-versus-current hardware drift;
- insufficient memory, disk, or required GPU;
- absent files, wrong hashes, missing license facts, path traversal, and symlinks;
- duplicate tasks, missing dependencies, cycles, negative estimates, and aggregate mismatches;
- command or result-path drift;
- false `ready_for_execution` claims;
- Stage 11 attempts to declare execution, network, download, installation, external LLM, or nested-agent activity;
- Stage 12 approval refusal while inputs are missing;
- approval binding and invalidation after artifact changes;
- all Stage 1–10 regressions; and
- an installed-plugin test on a temporary copy of the battery project.

The live-copy test must produce `experiment/resources.json`, report the absent or present real data truthfully, leave `experiment/results.json` absent, keep external LLM and nested-agent counters at zero, and stop at the Stage 12 approval boundary. The original battery project is never mutated during release verification.

## Success Criteria

Stage 11 is complete when:

- the closed resource plan and validator are implemented;
- the approval gate is hash-bound and execution remains impossible without explicit approval;
- `needs_input` preserves a useful plan without pretending the experiment is ready;
- hardware inspection is passive and reproducible;
- no data, package, or generated code is executed or downloaded;
- public docs and the installed skill describe the 1–11 boundary accurately;
- focused and full regression suites pass; and
- the battery-project temporary-copy test reaches the Stage 12 gate with a truthful readiness result.
