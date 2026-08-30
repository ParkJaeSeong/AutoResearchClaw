# Stage 12 Trustworthy Execution and Immutable Evidence Design

**Date:** 2026-08-30
**Status:** Approved design; implementation not started
**Scope:** Replace the generic Stage 12 result generator with an approved experiment-specific execution boundary and immutable evidence registration

## Purpose

Stage 12 must never turn placeholder behavior into scientific evidence. Stage 10
owns the experiment-specific implementation. Stage 12 freezes the approved
package and environment, hands execution explicitly to the user, and registers
only a result that can be traced to the exact approved code, configuration,
inputs, and metric implementation.

This design also closes the remaining recovery and time-of-check/time-of-use
gaps by preserving registered evidence in a project-local content-addressed
store. It does not implement Stage 13 refinement, laboratory execution, package
installation, external LLM calls, network access, or automatic experiment
execution by ResearchClaw.

## Non-Negotiable Trust Boundary

The workflow is:

```text
Stage 9 experiment design
  -> Stage 10 experiment-specific package and dry-run validation
  -> explicit execution approval
  -> Stage 12 immutable execution contract
  -> user-controlled external execution
  -> strict result validation and immutable evidence snapshot
  -> Stage 13
```

The following output is never research evidence:

- a placeholder or generic fallback calculation;
- a value derived from file size, row count, stdout parsing, or another proxy
  unless the approved experimental design explicitly defines that value as the
  metric and Stage 10 implements it;
- a package whose metric declaration cannot be connected to executable metric
  code;
- a development result, partial result, empty split, or provenance-incomplete
  result; or
- a result produced after any approved code, configuration, input, environment,
  or contract identity changed.

Schema validity is necessary but not sufficient for evidence eligibility.

## Component Responsibilities

### Stage 10 experiment package builder

Stage 10 produces an experiment-specific package containing:

- executable experiment code;
- canonical configuration;
- a dependency and interpreter compatibility declaration;
- deterministic seed and split configuration where applicable;
- a closed result schema;
- metric declarations linked to named implementation entry points; and
- a bounded dry-run fixture with known expected output.

The package must not contain a generic evidence-producing fallback. If an
experiment cannot yet be implemented, Stage 10 remains incomplete and Stage 12
cannot prepare execution.

### Package validator

The validator checks the package without claiming scientific success. It
verifies:

- the declared entry point and metric implementations exist;
- the dry-run fixture produces its known expected values;
- output is written only to the declared result path;
- required split roles and isolation keys are implemented;
- deterministic controls are present when required;
- prohibited network, download, package-installation, external-LLM, and
  nested-agent paths are absent; and
- the real execution path cannot silently fall back to development or
  placeholder behavior.

Passing dry-run validation makes a package eligible for approval. It does not
make its future result evidence eligible.

### Stage 12 contract preparer

Preparation remains non-executing. It binds:

- project and approval identity;
- design, package manifest, code, configuration, and resource-plan identities;
- every required input path, size, and SHA-256;
- the result schema and metric implementation identities;
- the exact executable argument vector;
- interpreter absolute path, version, and environment fingerprint;
- runtime and resource limits; and
- all execution prohibitions.

The preparer accepts only an interpreter that exists, is a regular executable,
and passed the Stage 10 package validation. It does not return an unverified
alias such as `python`. A contract prepared on a different machine or
environment must be prepared and approved again.

### External experiment runner

ResearchClaw never spawns the experiment. The user runs the exact argument
vector returned by Stage 12 from the project root. The runner:

- verifies the current contract, environment, package, and input identities;
- executes only the approved experiment-specific implementation;
- creates `experiment/results.json` exclusively;
- refuses to overwrite an existing result; and
- emits no evidence synthesized from stdout or stderr.

### Result validator and registrar

The registrar verifies the result's closed schema and scientific provenance,
then creates an immutable evidence snapshot. Stage 13 begins only after the
snapshot manifest and all referenced evidence objects are durable.

## Execution Environment Policy

The execution contract stores an argument vector rather than a shell command.
The first element is the verified absolute interpreter path. The contract also
stores:

- Python implementation and full version;
- platform and architecture;
- dependency names and resolved versions required by the approved package;
- a canonical environment fingerprint; and
- the project-relative entry point and configuration path.

Stage 12 does not create a virtual environment, install packages, or repair an
environment. An environment mismatch fails closed and returns the project to
Stage 10 package validation. Moving a project to another host requires a new
environment binding and explicit approval.

## Immutable Evidence Store

Registered evidence is grounded in a project-local content-addressed store:

```text
.researchclaw/evidence/
  objects/<sha256>
  manifests/<registration-id>.json
  tmp/
  quarantine/results/<timestamp>-<sha256>.json
```

The registrar streams every approved input, executable package file,
configuration, execution contract, and result into `tmp/`. It verifies size and
SHA-256 while copying, fsyncs the temporary object, and atomically publishes it
as `objects/<sha256>`. Existing objects with the same verified identity are
reused.

The closed manifest binds:

- project, approval, contract, and registration identity;
- the evidence-object identity and semantic role of every input and package
  file;
- environment fingerprint;
- result object identity;
- metric implementation identities;
- split and runtime summaries; and
- creation time and schema version.

The manifest is written only after every object is durable. Project state moves
to Stage 13 only after the manifest is durable. Stage 13 grounds itself in this
manifest and immutable objects, not in mutable working-tree files.

Objects are created with exclusive, no-symlink operations and are never
modified in place. A hash collision or existing object with mismatched size or
bytes is a fatal integrity error.

## Registration Transaction

Registration uses the common project transaction lock and a bounded durable
journal. The ordered transaction is:

1. Validate current Stage 12 approval, contract, environment, package, inputs,
   and result.
2. Record the complete approved identity set in the pending journal.
3. Stream and publish immutable evidence objects.
4. Recheck the open source descriptors and copied object identities.
5. Write and fsync the immutable evidence manifest.
6. Persist the Stage 13 state referencing the manifest and result object.
7. Append the bounded registration event.
8. Revalidate the manifest and state/event identities, then clear the journal.

External mutation of a working-tree file after step 4 cannot alter registered
evidence because Stage 13 consumes the copied immutable object. A failure before
the manifest is durable leaves Stage 12 canonical. A failure after manifest
publication is recovered from the journal by verifying the immutable objects,
manifest, state, and event before completing or compensating the transaction.

## Existing Result and Recovery Policy

The runner never deletes or overwrites `experiment/results.json`. If the file
already exists, execution stops with an actionable category.

An unregistered or invalid result may be moved only by an explicit quarantine
operation. Quarantine:

- requires user confirmation;
- hashes the source before moving it;
- moves it atomically when possible to
  `.researchclaw/evidence/quarantine/results/<timestamp>-<sha256>.json`;
- records its original path, hash, reason, and event identity; and
- never accepts an already registered evidence object.

After quarantine, the contract, environment, package, and inputs must still
validate before the runner is offered again. Registered evidence requires a
separate, future rollback design and is not removable through quarantine.

Stage 12 control-artifact failures remain at Stage 12:

- stale or invalid execution contract -> `prepare_run`;
- existing invalid or unregistered result -> `quarantine_result`;
- valid result not yet registered -> `register_research_result`;
- invalid execution approval -> `approve_experiment_execution`; and
- invalid Stage 10 package or environment -> return to Stage 10 package
  validation.

A Stage 12 execution-contract failure must never fall through generic artifact
normalization to Stage 5. Stage 12 never advertises unsupported
`validate_stage` recovery.

## Storage and Garbage Collection Policy

Before registration, ResearchClaw calculates the maximum additional copy size,
accounts for already present verified objects, checks available disk space, and
reports expected new bytes and remaining capacity. There is no arbitrary
project-size limit, but insufficient space fails before evidence publication.

Storage is project-local. A global cross-project object store is out of scope
because it introduces ownership, portability, and deletion ambiguity.

Cleanup rules are:

- temporary files left by interrupted writes may be removed automatically only
  after proving that no active journal references them;
- objects referenced by a durable manifest are never automatically deleted;
- unreferenced published objects are listed first with
  `evidence gc --dry-run` and their total size;
- actual garbage collection requires explicit user confirmation and records a
  bounded event; and
- garbage collection rechecks references while holding the project transaction
  lock before deleting anything.

## Error Categories

The public boundary uses stable, bounded categories, including:

- `experiment_package_not_executable`
- `experiment_metric_implementation_invalid`
- `execution_environment_unavailable`
- `execution_environment_changed`
- `execution_contract_stale`
- `research_result_already_exists`
- `research_result_quarantine_required`
- `research_result_scientifically_invalid`
- `research_result_provenance_mismatch`
- `evidence_storage_insufficient`
- `evidence_object_integrity_failure`
- `evidence_registration_interrupted`
- `project_transaction_pending`

CLI failures use exit code 2, place diagnostics on stderr, and keep JSON stdout
empty. Untrusted payloads, raw input data, stdout, stderr, and secrets are never
copied into event records.

## Required Quality Gates

These are release-blocking requirements, not recommendations.

### Scientific validity

- Known-answer miniature experiments must produce the mathematically expected
  metric values.
- Every registered metric must map to an approved implementation identity.
- Placeholder calculations, input-size proxies, empty splits, development
  results, and incomplete provenance must be rejected.

### Real execution and reproducibility

- Integration tests execute the returned argument vector without adding a
  test-only interpreter alias or modifying `PATH`.
- The exact flow must cover preparation, external execution, evidence snapshot,
  registration, and Stage 13 grounding.
- Repeated execution with identical package, input, environment, and seed must
  reproduce the required metrics and provenance within explicitly approved
  tolerances.

### Mutation and recovery defense

- Fault injection covers every journal, object, manifest, state, and event
  durability boundary.
- Adversarial tests mutate code, configuration, inputs, contract, result, and
  environment before, during, and after validation.
- No such mutation may promote mutable or mismatched bytes to Stage 13.
- The full quarantine -> reprepare -> execute -> register recovery chain must be
  exercised, not merely its action labels.
- A stale Stage 12 contract must remain at Stage 12 and complete the reprepare
  path end to end.

### Evidence storage

- Tests cover content deduplication, interrupted copies, orphan cleanup,
  manifest protection, hash mismatch, symlink/path escape, disk exhaustion, and
  concurrent registration or garbage collection.
- Registered objects must remain readable and unchanged after mutable source
  files are edited or removed.

### Performance

- Normal CI streams a 32 MiB input while enforcing a bounded-memory threshold.
- An opt-in benchmark streams at least 1 GiB and reports throughput, peak
  memory, deduplication savings, and evidence-publication time.
- JSON contracts, journals, manifests, results, and event records retain
  explicit byte caps before allocation or durable write.

### Final merge gate

The branch is not mergeable until all focused and full regression suites pass,
the real exact-command scenario passes, `git diff --check` passes, and an
independent reviewer confirms that all prior Critical and Important findings
are closed. A green unit-test count alone is insufficient.

## Compatibility and Migration

Existing Stage 12 execution contracts and generic-runner results are not
trusted under this design. They must not be silently upgraded or registered.
Projects at Stage 12 must return to Stage 10 package validation, generate the
new package/environment bindings, receive explicit execution approval, and
prepare a new contract.

Projects already at Stage 13 whose result was registered under the earlier
contract require an audit command before further refinement. The audit reports
the legacy status and does not synthesize an immutable evidence manifest.
Automatic migration of legacy evidence is out of scope.

## Non-Goals

- ResearchClaw-managed automatic experiment execution.
- Automatic dependency installation or environment repair.
- External LLM or nested-agent calls from the runtime.
- Laboratory instrument execution or laboratory evidence contracts.
- A global evidence store shared across projects.
- Deleting or rolling back registered evidence.
- Implementing the Stage 13 refinement algorithm.
