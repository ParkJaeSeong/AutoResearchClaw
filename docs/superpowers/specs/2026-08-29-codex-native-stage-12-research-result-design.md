# Codex-Native Stage 12 Research Result Registration Design

**Date:** 2026-08-29  
**Status:** Approved design  
**Scope:** Explicit research execution handoff, result registration, and Stage 12 completion

## Purpose

Complete the Codex-native Stage 12 workflow without automatically executing generated research code or calling an external LLM. The workflow must preserve the upstream pipeline's useful experiment-to-refinement transition while strengthening execution consent, provenance binding, and evidence validation.

This design does not implement Stage 13 refinement. It establishes the trustworthy `experiment/results.json` and durable project state that Stage 13 will consume.

## Upstream Behavior and Adaptation

The upstream AutoResearchClaw Stage 12 selects an execution backend, may install missing dependencies, runs the experiment automatically, copies an emitted `results.json`, and may synthesize a result from parsed stdout metrics. It blocks obvious failures and empty or non-finite metrics. Stage 13 then performs an edit-run-evaluate loop; agent-based modes instead rerun Stage 12 atomically.

The Codex-native fork retains:

- Stage 12 as the producer of experimental results.
- A canonical structured result artifact.
- Rejection of failed, empty, or non-finite results.
- The Stage 12 to Stage 13 transition.
- Later refinement based on recorded experimental evidence.

The Codex-native fork improves:

- Execution is explicit and user-controlled rather than automatic.
- Dependency installation, downloads, external LLM calls, and nested agents remain prohibited.
- Stdout is never converted into research evidence.
- Results are bound to the approved project, design, code package, resource plan, and declared inputs.
- Development results can never be promoted into research results.
- Project state advances only after complete result validation.

## User Workflow

### 1. Prepare an execution handoff

```bash
researchclaw-codex execution prepare-run PROJECT --json
```

The command rechecks Stage 12 approval and all execution prerequisites. It does not import or execute the generated package. It writes `experiment/execution_contract.json` atomically and returns:

- the exact project-relative command declared by the resource plan;
- the expected result path;
- the execution contract path and SHA-256;
- the approved package, design, configuration, resource plan, and input identities;
- `readiness: ready_for_explicit_execution`;
- `approval_eligible: false` because approval has already occurred.

Repeated preparation is idempotent when all bound artifacts are unchanged. If a bound artifact changes, the old contract is not silently reused; preparation must fail and direct the project back to the relevant prior stage or approval gate.

### 2. Execute outside ResearchClaw

The user runs the exact returned command in the project root. ResearchClaw does not spawn it, install dependencies, enable network access, or create results from console output.

The command must write only the declared `experiment/results.json`. A result created at another path is not eligible for registration.

### 3. Register the result

```bash
researchclaw-codex execution register-result PROJECT \
  --result experiment/results.json \
  --confirm-research-result \
  --json
```

Registration reopens the project read-only for validation, reads regular files through the existing no-symlink project-file boundary, and performs all checks before a single atomic state transition.

## Execution Contract

`experiment/execution_contract.json` is a closed JSON object with these conceptual sections:

- `schema_version`
- `contract_id`
- `project_id`
- `created_at`
- `command`
- `result_path`
- `bindings`
- `inputs`
- `prohibitions`
- `result_template`

`bindings` records the SHA-256 of:

- `experiment/design.json`
- `experiment/package_manifest.json`
- `experiment/code/config.json`
- `experiment/resources.json`
- every file listed in the package manifest

`inputs` records each required input path, size, SHA-256, and confirmed license status from the validated resource plan. Input identity is captured at preparation and rechecked during registration.

`prohibitions` preserves the approved policy: no network, downloads, package installation, external LLM calls, nested agents, or ResearchClaw-managed execution.

The contract is stored as a normal project artifact only after successful preparation. Creating it does not complete Stage 12.

## Research Result Contract

`experiment/results.json` must be a closed, finite JSON object containing:

- `schema_version`
- `project_id`
- `execution_contract`
- `development_only`
- `evidence_eligible`
- `status`
- `metrics`
- `split_summary`
- `provenance`
- `runtime`

Required invariants:

- `development_only` is `false` and `evidence_eligible` is `true`.
- `status` is `completed`; partial and failed results are not registered.
- The project ID and execution contract ID/SHA-256 match the current contract.
- `metrics` is non-empty and every numeric metric is finite. Boolean values are not metrics.
- `split_summary` contains non-negative cell and independent-group counts for every declared split and identifies the isolation key.
- Split overlap and leakage counts are zero.
- `provenance` repeats the design, package, resource-plan, and input identities from the execution contract.
- Runtime values are finite, non-negative, and do not exceed the approved execution budget.
- The result is a project-relative regular file and is not `experiment/dev_results.json`.

The current Stage 10 code generator predates the execution contract. Therefore `prepare-run` also emits a bounded result-template section in its JSON response and execution contract. The user or executing program must use that template to include the contract identity. Future Stage 10 work may generate this integration directly, but registration does not weaken its contract for legacy packages.

## Registration and State Transition

Successful registration performs one state update:

- add or replace the `experiment/results.json` artifact reference;
- retain the execution contract artifact reference;
- append Stage 12 to `completed_stages` exactly once;
- set `current_stage` to `13`;
- set status to `ready`;
- set `next_action` to `prepare_stage`;
- clear the prior Stage 12 error state;
- append a `research_result_registered` event containing only bounded identities and counts.

The event records the contract and result SHA-256 values, result path, metric count, and input count. It does not duplicate metrics, source data, stdout, stderr, or secrets.

Validation failure leaves state, approval records, result contents, resources, and contract unchanged. A bounded `research_result_registration_failed` event may record an error category plus known contract/result identities; it must not record untrusted result payloads.

## Compatibility and Stage 13 Boundary

Stage 13 will depend on the registered artifact, not merely on the existence of `experiment/results.json`. Its implementation must verify the state artifact SHA-256 before reading results.

The core contracts already define Stage 13 as `iterative_refine`, taking `experiment/results.json` and producing `experiment/iterations.jsonl`. Support for preparing and validating Stage 13 remains a separate change. This Stage 12 work may extend the supported-stage boundary only far enough to represent a completed Stage 12 and a ready Stage 13 state; it must not claim Stage 13 implementation is complete.

## Failure Categories

Errors use stable, bounded categories, including:

- `execution_approval_invalid`
- `execution_prerequisites_changed`
- `execution_contract_invalid`
- `execution_contract_stale`
- `research_result_file_invalid`
- `research_result_schema_invalid`
- `research_result_project_mismatch`
- `research_result_contract_mismatch`
- `research_result_provenance_mismatch`
- `research_result_split_invalid`
- `research_result_leakage_detected`
- `research_result_metrics_invalid`
- `development_result_not_registerable`

CLI errors remain on stderr with exit code 2; JSON mode keeps stdout empty on failure.

## Testing

Implementation follows test-driven development and covers:

- preparation after a valid Stage 12 approval;
- idempotent preparation with unchanged bindings;
- stale approval, package, resource, or input rejection;
- confirmation flag requirement;
- successful result registration and exact Stage 13 transition;
- malformed, non-finite, empty, partial, or mismatched result rejection;
- development-result and wrong-path rejection;
- split-count, group-isolation, and leakage rejection;
- symlink, directory, and path-escape rejection;
- no subprocess, package installation, network, or LLM invocation;
- no state mutation on every failure path;
- bounded event payloads;
- existing development execution and all Codex-native regression tests.

An integration test will prepare a real Stage 12 project, create a small contract-bound fixture result without running a costly experiment, register it, and verify that state moves to Stage 13 while all upstream artifacts remain byte-identical.

## Non-Goals

- Automatically executing generated research code.
- Installing or resolving experiment dependencies.
- Converting stdout into results.
- Promoting development fixtures or development metrics.
- Deciding whether scientific findings are publishable.
- Implementing the Stage 13 refinement algorithm.
- Supporting laboratory execution before its own result contract is designed.
