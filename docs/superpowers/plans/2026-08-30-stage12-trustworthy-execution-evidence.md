# Stage 12 Trustworthy Execution and Immutable Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic Stage 12 evidence generator with an approved experiment-specific external execution flow whose result is preserved in an immutable, content-addressed evidence store before Stage 13.

**Architecture:** Stage 10 defines and statically validates an experiment-specific package plus a known-answer self-test contract; the user runs that self-test explicitly and registers its report before execution approval. Stage 12 binds a verified absolute interpreter and environment fingerprint, returns an exact argument vector without executing it, validates the produced result, snapshots every evidence byte into a project-local content-addressed store, and advances only when the immutable manifest, state, and event form one recoverable transaction.

**Tech Stack:** Python 3.11+, standard-library `argparse`, `ast`, `hashlib`, `json`, `os`, `pathlib`, `platform`, `shutil`, `stat`, `sys`, existing ResearchClaw project transactions/events/atomic persistence, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-stage12-trustworthy-execution-evidence-design.md`

## Global Constraints

- ResearchClaw never spawns the generated experiment or its known-answer self-test.
- Stage 10 may not expose an evidence-producing generic fallback or input-size proxy.
- Only an explicitly run, registered known-answer self-test can make a package approval-eligible.
- The execution contract stores a verified absolute interpreter argument vector, never a shell string or unverified `python` alias.
- No automatic package installation, virtual-environment creation, downloads, network access, external LLM calls, or nested agents.
- The external runner exclusively creates `experiment/results.json` and never overwrites it.
- Stage 13 grounds registered evidence in immutable content-addressed objects and a closed manifest, not mutable working-tree files.
- Existing generic-runner contracts and results are legacy-untrusted and cannot be silently migrated.
- Every task follows RED -> minimal GREEN -> focused regression -> commit.
- Push and merge remain prohibited until the final release gate and explicit publication approval.

## File Structure

- Create `researchclaw/core/experiment_package_contract.py`: closed Stage 10 experiment/self-test contract, metric-entry-point binding, and self-test report validation.
- Create `researchclaw/core/execution_environment.py`: verified interpreter resolution and canonical environment fingerprint.
- Create `researchclaw/core/evidence_store.py`: streaming content-addressed object publication, manifests, capacity checks, quarantine, and garbage-collection planning.
- Create `researchclaw/core/evidence_registration.py`: bounded pending journal and immutable evidence registration transaction.
- Modify `researchclaw/core/computational_package.py`: remove the generic `_run_bounded_experiment`, emit the experiment-specific contract/scaffold boundary, and delegate new validation.
- Modify `researchclaw/core/research_execution.py`: bind the new package/environment, delegate immutable registration, and retain public preparation/registration APIs.
- Modify `researchclaw/core/handoff.py`: Stage 12-specific recovery classification and actionable quarantine/reprepare commands.
- Modify `researchclaw/core/models.py`: add `quarantine_result`, `validate_experiment_package`, and `audit_legacy_evidence` next actions.
- Modify `researchclaw/codex/cli.py`: explicit self-test registration, quarantine, evidence audit, and garbage-collection commands.
- Modify `tests/codex_native/helpers.py`: experiment-specific known-answer fixture and immutable-evidence helpers.
- Create `tests/codex_native/test_experiment_package_contract.py`.
- Create `tests/codex_native/test_execution_environment.py`.
- Create `tests/codex_native/test_evidence_store.py`.
- Create `tests/codex_native/test_evidence_registration.py`.
- Create `scripts/verify_stage12_evidence.sh`: repository-local release-gate command sequence.
- Modify `tests/codex_native/test_computational_package.py`, `test_research_execution.py`, `test_handoff.py`, `test_cli.py`, `test_public_docs.py`, and `test_stage12_final_fix_wave.py`.
- Modify `README.md`, `AGENTS.md`, `skills/researchclaw/SKILL.md`, and the relevant `skills/researchclaw/references/*.md` execution guidance.

---

### Task 1: Define the experiment-specific package and known-answer self-test contract

**Files:**
- Create: `researchclaw/core/experiment_package_contract.py`
- Create: `tests/codex_native/test_experiment_package_contract.py`
- Modify: `tests/codex_native/helpers.py`

**Interfaces:**
- Produces `EXPERIMENT_PACKAGE_CONTRACT_PATH = "experiment/package_contract.json"`.
- Produces `SELF_TEST_REPORT_PATH = "experiment/self_test_report.json"`.
- Produces frozen `ValidatedExperimentPackage(contract_sha256: str, metric_entrypoints: Mapping[str, str], self_test_argv: tuple[str, ...], execution_argv: tuple[str, ...])`.
- Produces `validate_experiment_package_contract(project: ResearchProject) -> ValidatedExperimentPackage`.
- Produces `validate_registered_self_test(project: ResearchProject, package: ValidatedExperimentPackage) -> ArtifactRef`.

- [ ] **Step 1: Add a real known-answer fixture**

Add `build_known_answer_experiment_package(root)` to `tests/codex_native/helpers.py`. Its generated `experiment/code/main.py` must compute mean absolute error from fixture predictions and targets rather than inspecting byte counts:

```python
def mean_absolute_error(targets: list[float], predictions: list[float]) -> float:
    return sum(abs(a - b) for a, b in zip(targets, predictions, strict=True)) / len(targets)

def run_experiment(config: dict[str, object]) -> dict[str, object]:
    targets = [1.0, 2.0, 3.0, 4.0]
    predictions = [1.5, 1.5, 2.5, 4.5]
    return {"mae": mean_absolute_error(targets, predictions)}
```

The package contract must bind `mae` to `experiment.code.main:mean_absolute_error`, declare expected self-test value `0.5`, tolerance `0.0`, and use separate self-test and full-execution argument vectors.
The generated entry point must handle `--self-test` by running only the closed
fixture and exclusively creating `experiment/self_test_report.json`; the normal
path must call `run_experiment(config)` and exclusively create
`experiment/results.json`.

- [ ] **Step 2: Write closed-contract RED tests**

```python
def test_package_contract_binds_metric_to_known_answer_implementation(tmp_path):
    project = build_known_answer_experiment_package(tmp_path / "project")
    validated = validate_experiment_package_contract(project)
    assert validated.metric_entrypoints == {
        "mae": "experiment.code.main:mean_absolute_error"
    }
    assert validated.self_test_argv[-1] == "--self-test"
```

Add parameterized failures for missing entry point, extra contract keys, duplicate metric names, non-finite expected value/tolerance, empty fixture, same self-test and research input, input-size/file-size proxy AST, and a fallback that marks placeholder output evidence-eligible.

- [ ] **Step 3: Run RED**

Run: `pytest -q tests/codex_native/test_experiment_package_contract.py`

Expected: collection fails because `researchclaw.core.experiment_package_contract` does not exist.

- [ ] **Step 4: Implement the closed package contract parser**

Use bounded duplicate-key-rejecting JSON. Require exact root keys:

```python
PACKAGE_KEYS = {
    "schema_version", "entry_point", "config_path", "result_path",
    "metrics", "self_test", "execution", "dependencies", "prohibitions",
}
METRIC_KEYS = {"name", "unit", "implementation"}
SELF_TEST_KEYS = {"argv_suffix", "fixture_path", "expected_metrics"}
```

Require every metric implementation to resolve to a top-level function in a package-manifest Python file. Reject AST flows in the metric call graph that use `os.path.getsize`, `Path.stat`, `st_size`, `len(raw_bytes)`, or package fallback functions as the returned metric value. Retain the existing static capability prohibitions by calling focused helpers extracted from `computational_package.py` rather than duplicating them.

- [ ] **Step 5: Implement self-test report validation**

The externally produced report is a closed object with package-contract identity, fixture identity, environment fingerprint, per-metric actual/expected/tolerance, `passed: true`, and `development_only: true`. Validate `abs(actual - expected) <= tolerance`, exact metric set, finite values, and all current package identities. Record it as an artifact only through a later explicit CLI registration path; this pure validator must not mutate state.

- [ ] **Step 6: Verify and commit**

Run:

```bash
pytest -q tests/codex_native/test_experiment_package_contract.py
pytest -q tests/codex_native/test_computational_package.py -k 'contract or capability or traceability'
git diff --check
```

Expected: all selected tests pass.

```bash
git add researchclaw/core/experiment_package_contract.py tests/codex_native/test_experiment_package_contract.py tests/codex_native/helpers.py
git commit -m "feat(codex): define experiment-specific package evidence"
```

---

### Task 2: Remove the generic evidence generator and require registered self-test evidence

**Files:**
- Modify: `researchclaw/core/computational_package.py`
- Modify: `researchclaw/core/experiment_package_contract.py`
- Modify: `researchclaw/core/approval.py`
- Modify: `researchclaw/codex/cli.py`
- Modify: `tests/codex_native/test_computational_package.py`
- Modify: `tests/codex_native/test_approval.py`
- Modify: `tests/codex_native/test_cli.py`

**Interfaces:**
- Consumes `validate_experiment_package_contract` and `validate_registered_self_test` from Task 1.
- Produces `register_experiment_self_test(project: ResearchProject, report_path: str) -> ArtifactRef`.
- Changes Stage 12 approval eligibility to require the current registered self-test artifact.

- [ ] **Step 1: Write the fabricated-evidence regression**

```python
def test_canonical_package_has_no_generic_input_byte_metric_runner():
    source = canonical_computational_scaffold()["experiment/code/main.py"]
    assert "total_input_bytes" not in source
    assert "_run_bounded_experiment" not in source
    assert "st_size" not in source
```

Add an end-to-end test proving that execution approval fails with `experiment_self_test_required` before a self-test report is explicitly registered.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/codex_native/test_computational_package.py::test_canonical_package_has_no_generic_input_byte_metric_runner tests/codex_native/test_approval.py -k self_test`

Expected: the scaffold assertion fails and the approval test lacks the new gate.

- [ ] **Step 3: Delete the generic non-dry execution path**

Remove `_run_bounded_experiment` and any scaffold code that maps input sizes or files to metrics/splits. The canonical scaffold may provide parsing, contract verification, exclusive result creation, and an explicit `run_experiment(config)` interface, but its default implementation must raise `experiment implementation missing` and can never emit `evidence_eligible: true`.

- [ ] **Step 4: Add explicit self-test report registration**

Add CLI syntax:

```text
researchclaw-codex experiment register-self-test PROJECT \
  --report experiment/self_test_report.json --confirm-self-test --json
```

The handler validates without spawning code, atomically records the report artifact and bounded event, and leaves the project at the execution approval gate. Catch stable `ValueError` categories and return exit code 2 without traceback.

- [ ] **Step 5: Gate approval on current self-test evidence**

Before Stage 12 approval, require the package contract, package files, fixture, report, and environment fingerprint to match. A changed package or fixture invalidates the report and returns `experiment_self_test_required`.

- [ ] **Step 6: Verify and commit**

```bash
pytest -q tests/codex_native/test_computational_package.py tests/codex_native/test_approval.py tests/codex_native/test_cli.py -k 'self_test or generic or execution'
git diff --check
git add researchclaw/core/computational_package.py researchclaw/core/experiment_package_contract.py researchclaw/core/approval.py researchclaw/codex/cli.py tests/codex_native/test_computational_package.py tests/codex_native/test_approval.py tests/codex_native/test_cli.py
git commit -m "fix(codex): prohibit generic research evidence"
```

---

### Task 3: Bind a real executable and environment fingerprint

**Files:**
- Create: `researchclaw/core/execution_environment.py`
- Create: `tests/codex_native/test_execution_environment.py`
- Modify: `researchclaw/core/research_execution.py`
- Modify: `tests/codex_native/test_research_execution.py`

**Interfaces:**
- Produces frozen `ExecutionEnvironment(interpreter: str, python_implementation: str, python_version: str, platform: str, machine: str, dependencies: Mapping[str, str], fingerprint: str)`.
- Produces `inspect_execution_environment(interpreter: Path, required_distributions: tuple[str, ...]) -> ExecutionEnvironment`.
- `ExecutionPreparationStatus` replaces `command: str` with `argv: tuple[str, ...]` and `environment_fingerprint: str`.

- [ ] **Step 1: Write a no-alias RED test**

```python
def test_preparation_returns_verified_absolute_interpreter_without_path_shim(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    status = prepare_research_execution(project)
    assert Path(status.argv[0]).is_absolute()
    assert Path(status.argv[0]).samefile(Path(sys.executable))
    completed = subprocess.run(status.argv, cwd=project.root, check=False)
    assert completed.returncode == 0
```

The test must not modify `PATH`, create a `python` symlink, or replace `argv[0]`.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/codex_native/test_execution_environment.py tests/codex_native/test_research_execution.py -k absolute_interpreter`

Expected: the string command or `python` alias assertion fails.

- [ ] **Step 3: Implement environment inspection**

Resolve and open the interpreter as a regular executable. Require it to match the interpreter under which Stage 10 self-test evidence was registered. Use `importlib.metadata.version()` for the closed required-distribution list; missing distributions raise `execution_environment_unavailable`. Canonicalize implementation, full version, platform, machine, interpreter identity, and sorted dependency versions to compute SHA-256.

- [ ] **Step 4: Bind argv and environment in the execution contract**

Store JSON `argv` as an array. Reject shell metacharacter interpretation by never using `shell=True` and never rendering the array as the authoritative contract. Keep a quoted display string only in CLI presentation. Preparation fails with `execution_environment_changed` when the registered self-test environment differs.

- [ ] **Step 5: Verify and commit**

```bash
pytest -q tests/codex_native/test_execution_environment.py tests/codex_native/test_research_execution.py -k 'environment or argv or prepare'
git diff --check
git add researchclaw/core/execution_environment.py researchclaw/core/research_execution.py tests/codex_native/test_execution_environment.py tests/codex_native/test_research_execution.py
git commit -m "feat(codex): bind verified execution environment"
```

---

### Task 4: Implement the project-local content-addressed evidence store

**Files:**
- Create: `researchclaw/core/evidence_store.py`
- Create: `tests/codex_native/test_evidence_store.py`
- Modify: `researchclaw/core/execution_gate.py`

**Interfaces:**
- Produces `EvidenceSource(role: str, path: str, expected_sha256: str, expected_size: int)`.
- Produces `EvidenceObject(sha256: str, size: int, path: str)`.
- Produces `EvidenceCapacity(required_new_bytes: int, available_bytes: int, reusable_bytes: int)`.
- Produces `EvidenceGcPlan(objects: tuple[EvidenceObject, ...], temporary_paths: tuple[str, ...], total_bytes: int, confirmation_token: str)`.
- Produces `EvidenceStore.preflight(sources: tuple[EvidenceSource, ...]) -> EvidenceCapacity`.
- Produces `EvidenceStore.publish(source: EvidenceSource) -> EvidenceObject`.
- Produces `EvidenceStore.write_manifest(registration_id: str, payload: Mapping[str, object]) -> ArtifactRef`.
- Produces `EvidenceStore.plan_gc() -> EvidenceGcPlan` and `EvidenceStore.collect(plan: EvidenceGcPlan, confirm_token: str) -> tuple[EvidenceObject, ...]`.
- Evidence root is `.researchclaw/evidence`; objects are `.researchclaw/evidence/objects/<sha256>`.

- [ ] **Step 1: Write streaming/deduplication RED tests**

```python
def test_publish_streams_and_reuses_identical_object(tmp_path):
    store = EvidenceStore(tmp_path / "project")
    source = tmp_path / "project/data/input.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"research input")
    first = store.publish(source)
    second = store.publish(source)
    assert first == second
    assert len(tuple((store.objects_root).iterdir())) == 1
```

Add tests for symlink/FIFO/directory rejection, exclusive object creation, hash mismatch, interrupted temporary copy, 32 MiB bounded-memory streaming, same-hash reuse, and a mocked insufficient `shutil.disk_usage` preflight.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/codex_native/test_evidence_store.py`

Expected: collection fails because `EvidenceStore` does not exist.

- [ ] **Step 3: Implement secure object publication**

Reuse the no-symlink `openat` descriptor boundary from `execution_gate.py`. Stream fixed-size chunks into a same-filesystem temporary file while hashing, fsync, verify source descriptor identity has not changed, then publish with exclusive rename/link semantics. If the object exists, open and stream-verify it before reuse. Never modify an object in place.

- [ ] **Step 4: Implement capacity and manifest primitives**

`preflight` sums only objects not already verified in the store and requires `available_bytes >= required_new_bytes + max(16 MiB, required_new_bytes // 20)`. Manifests are closed, bounded to 1 MiB, canonical JSON, exclusively created, fsynced, and named by registration ID.

- [ ] **Step 5: Implement dry-run garbage collection**

`plan_gc()` streams all manifests, returns only unreferenced published objects and unreferenced inactive temporary files, and includes total bytes plus a SHA-256 confirmation token. `collect()` requires that token, holds `project_transaction`, recomputes the plan, deletes only exact unchanged targets, fsyncs directories, and returns bounded identities for the caller's event.

- [ ] **Step 6: Verify and commit**

```bash
pytest -q tests/codex_native/test_evidence_store.py
git diff --check
git add researchclaw/core/evidence_store.py researchclaw/core/execution_gate.py tests/codex_native/test_evidence_store.py
git commit -m "feat(codex): add immutable evidence object store"
```

---

### Task 5: Register immutable evidence as one recoverable transaction

**Files:**
- Create: `researchclaw/core/evidence_registration.py`
- Create: `tests/codex_native/test_evidence_registration.py`
- Modify: `researchclaw/core/research_execution.py`
- Modify: `tests/codex_native/test_research_execution.py`

**Interfaces:**
- Produces `EVIDENCE_PENDING_PATH = ".researchclaw/evidence/pending-registration.json"`.
- Produces frozen `EvidenceRegistrationStatus(registration_id, manifest_path, result_object_sha256, current_stage, next_action)`.
- Produces `register_immutable_research_evidence(project: ResearchProject, validated_result: ValidatedResearchResult) -> EvidenceRegistrationStatus`.
- Produces `recover_pending_evidence_registration(project) -> EvidenceRegistrationStatus | None`.

- [ ] **Step 1: Write the immutable-source RED test**

```python
def test_registered_stage_thirteen_uses_immutable_objects_after_source_changes(tmp_path):
    project, result = build_valid_execution_result(tmp_path / "project")
    status = register_research_result(project, str(result.relative_to(project.root)))
    manifest_before = load_evidence_manifest(project.root, status.manifest_path)
    (project.root / "data/input.csv").write_text("changed", encoding="utf-8")
    result.unlink()
    handoff = build_handoff(ResearchProject.open(project.root))
    assert handoff.current_stage == 13
    assert load_evidence_manifest(project.root, status.manifest_path) == manifest_before
```

Add an adversarial hook that mutates a source immediately after strict result validation; the registered object must contain the pre-mutation validated descriptor bytes or registration must compensate to Stage 12. It must never register the mutated bytes under the old identity.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/codex_native/test_evidence_registration.py`

Expected: mutable result/input grounding fails because no evidence manifest exists.

- [ ] **Step 3: Define the bounded pending journal**

The journal stores registration ID, canonical Stage 12 prior-state identity, target-state identity, complete source identities, intended object identities, manifest identity, event identity, phase, and abort intent. Cap it at 256 KiB before write. Do not embed complete state JSON twice; store hashes plus the minimal reconstruction fields.

- [ ] **Step 4: Implement ordered registration**

Under `project_transaction(allow_pending=True)`: strict-validate; persist pending; preflight; publish source descriptors; verify copied identities; write manifest; save Stage 13 state referencing manifest/result object; append event; verify manifest/state/event; clear pending. `research_execution.register_research_result` delegates to this function and no longer treats mutable `experiment/results.json` as the Stage 13 grounding artifact.

- [ ] **Step 5: Implement phase-aware recovery and compensation**

Recovery verifies immutable objects and identities instead of rerunning scientific calculations. Before manifest publication, compensate to canonical Stage 12 and retain safe unreferenced objects for GC. After a valid manifest exists, finish state/event publication idempotently. Any manifest/object mismatch durably records abort intent and never promotes Stage 13.

- [ ] **Step 6: Add durability-boundary tests**

Parameterize faults after pending, each object publication, manifest publication, state save, partial event write, complete event write, and pending clear. For each boundary, reopen the project twice and assert identical final outcome, no duplicate event, no mutable-file grounding, and a recoverable or cleared journal.

- [ ] **Step 7: Verify and commit**

```bash
pytest -q tests/codex_native/test_evidence_registration.py tests/codex_native/test_research_execution.py
git diff --check
git add researchclaw/core/evidence_registration.py researchclaw/core/research_execution.py tests/codex_native/test_evidence_registration.py tests/codex_native/test_research_execution.py
git commit -m "feat(codex): register immutable research evidence"
```

---

### Task 6: Add explicit quarantine and actionable Stage 12 recovery

**Files:**
- Modify: `researchclaw/core/evidence_store.py`
- Modify: `researchclaw/core/handoff.py`
- Modify: `researchclaw/core/models.py`
- Modify: `researchclaw/codex/cli.py`
- Modify: `tests/codex_native/test_evidence_store.py`
- Modify: `tests/codex_native/test_handoff.py`
- Modify: `tests/codex_native/test_cli.py`

**Interfaces:**
- Produces frozen `QuarantinedResult(original_path: str, quarantine_path: str, sha256: str, size: int, reason: str)`.
- Produces `quarantine_unregistered_result(project: ResearchProject, reason: str, confirm: bool) -> QuarantinedResult`.
- Adds next actions `quarantine_result`, `validate_experiment_package`, and `audit_legacy_evidence`.

- [ ] **Step 1: Write complete-chain RED tests**

Create a Stage 13 fixture with an invalid mutable result and assert this complete chain succeeds:

```text
build_handoff -> quarantine_result
execution quarantine-result --confirm
build_handoff -> prepare_run
prepare-run -> exact argv
external execution -> new result
register-result -> immutable manifest -> Stage 13
```

Add a Stage 12 stale-contract test asserting it remains Stage 12, removes only the stale contract ArtifactRef, returns `prepare_run`, and never rewinds to Stage 5 or advertises `validate_stage`.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/codex_native/test_handoff.py tests/codex_native/test_cli.py -k 'quarantine or stale_contract_complete_chain'`

Expected: quarantine action is unknown and stale Stage 12 contract rewinds incorrectly.

- [ ] **Step 3: Implement confirmed quarantine**

Reject registered evidence objects and any result referenced by a valid manifest. Hash the regular no-symlink source, move it to `.researchclaw/evidence/quarantine/results/<UTC>-<sha256>.json`, fsync both directories, and append a bounded event with original path, hash, reason category, and quarantine path. Never delete or overwrite a quarantine target.

- [ ] **Step 4: Classify Stage 12 controls before generic normalization**

In `_normalize_durable_project_locked`, inspect execution contract, mutable result, package contract/self-test, and approval before `_first_invalid_artifact_stage`. Route only to implemented Stage 12 actions. A package/self-test failure returns to Stage 10 validation; a legacy Stage 13 manifest absence returns `audit_legacy_evidence` without fabricating a manifest.

- [ ] **Step 5: Add CLI commands**

Add:

```text
researchclaw-codex execution quarantine-result PROJECT --reason CATEGORY --confirm --json
researchclaw-codex evidence gc PROJECT --dry-run --json
researchclaw-codex evidence gc PROJECT --confirm-token TOKEN --json
researchclaw-codex evidence audit PROJECT --json
```

All mutation commands hold the common project transaction and normalize stable errors to exit code 2 without traceback.

- [ ] **Step 6: Verify and commit**

```bash
pytest -q tests/codex_native/test_evidence_store.py tests/codex_native/test_handoff.py tests/codex_native/test_cli.py
git diff --check
git add researchclaw/core/evidence_store.py researchclaw/core/handoff.py researchclaw/core/models.py researchclaw/codex/cli.py tests/codex_native/test_evidence_store.py tests/codex_native/test_handoff.py tests/codex_native/test_cli.py
git commit -m "feat(codex): add safe stage twelve recovery"
```

---

### Task 7: Migrate public contracts and reject legacy evidence

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `skills/researchclaw/SKILL.md`
- Modify: `skills/researchclaw/references/computational-package.md`
- Modify: `skills/researchclaw/references/resource-planning.md`
- Modify: `skills/researchclaw/references/approval-policy.md`
- Modify: `tests/codex_native/test_public_docs.py`
- Modify: `tests/codex_native/test_stage12_final_fix_wave.py`

**Interfaces:**
- Documents the explicit self-test -> approval -> prepare -> execute -> immutable register flow.
- Defines legacy contracts/results as audit-only and non-registerable.

- [ ] **Step 1: Write documentation-contract RED tests**

Require public docs to mention the absolute interpreter argv, explicit self-test registration, immutable manifest, quarantine confirmation, and legacy audit. Assert no public example contains `python experiment/code/main.py`, claims that Stage 12 computes metrics, or instructs manual evidence-object deletion.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/codex_native/test_public_docs.py`

Expected: old literal command and mutable-result guidance violate the new assertions.

- [ ] **Step 3: Update the user workflow**

Document commands in their actual order, distinguish display strings from authoritative argv arrays, explain disk preflight/deduplication, and state that the user must review execution approval. Include recovery tables for environment drift, existing result, stale contract, insufficient disk, interrupted registration, and legacy Stage 13 evidence.

- [ ] **Step 4: Replace obsolete final-fix regressions**

Remove the test-only `python` shim and the generic byte-count success expectation. Preserve every still-valid lock, bounded-read, preparation-journal, and pending-cap regression. Add known-answer exact-value and immutable-source grounding assertions.

- [ ] **Step 5: Verify and commit**

```bash
pytest -q tests/codex_native/test_public_docs.py tests/codex_native/test_stage12_final_fix_wave.py
git diff --check
git add README.md AGENTS.md skills/researchclaw tests/codex_native/test_public_docs.py tests/codex_native/test_stage12_final_fix_wave.py
git commit -m "docs(codex): publish trustworthy execution workflow"
```

---

### Task 8: Add performance, adversarial integration, and release gates

**Files:**
- Create: `tests/codex_native/test_stage12_trustworthy_evidence_integration.py`
- Create: `tests/performance/test_evidence_store_benchmark.py`
- Create: `scripts/verify_stage12_evidence.sh`
- Modify: `pyproject.toml`

**Interfaces:**
- Adds pytest marker `large_evidence` for the opt-in 1 GiB benchmark.
- Adds a release-blocking exact-argv known-answer integration test.

- [ ] **Step 1: Write the exact external execution integration test**

Build a disposable approved project, run the registered self-test and full execution using the exact returned argv without changing `PATH`, verify the known MAE is `0.5`, register evidence, mutate/delete mutable sources, and prove Stage 13 still reads the immutable manifest/objects. Audit filesystem hashes at each step so execution changes only `experiment/results.json` and registration changes only declared `.researchclaw` state/evidence and event paths.

- [ ] **Step 2: Add adversarial race probes**

Use deterministic hooks to mutate each input, code file, config, environment binding, contract, and result: before validation, after validation, during object copy, after manifest publication, and after state publication. Assert either the exact validated bytes are in immutable objects or the project remains/recoverably returns to Stage 12; mismatched bytes never reach Stage 13.

- [ ] **Step 3: Add normal-CI streaming assertions**

Stream a 32 MiB input and use `tracemalloc` to assert Python peak allocation remains below 8 MiB above baseline during identity/copy operations. Verify JSON caps before decode/write and stream the public registration-event helper so it cannot call `read_all()`.

- [ ] **Step 4: Add the opt-in 1 GiB benchmark**

Mark it `@pytest.mark.large_evidence`. Generate deterministic data without retaining it in memory, report MiB/s, peak memory, first-publication time, reused-object time, and deduplicated bytes. The benchmark is informational but must fail on identity mismatch, unbounded memory above 32 MiB over baseline, or loss of deduplication.

- [ ] **Step 5: Run focused and full verification**

Create `scripts/verify_stage12_evidence.sh` with `set -eu` and the following
repository-root commands, then execute that script:

```bash
pytest -q tests/codex_native/test_stage12_trustworthy_evidence_integration.py
pytest -q tests/codex_native
pytest -q tests/performance/test_evidence_store_benchmark.py -m large_evidence
python -m compileall -q researchclaw tests/codex_native
ruff check researchclaw tests/codex_native
git diff --check
```

Expected: every command exits 0; the exact metric is `0.5`; no test injects an interpreter alias; full registration remains grounded after mutable source removal.

- [ ] **Step 6: Request independent whole-branch review**

Generate a review package from the pre-plan implementation base through HEAD. Require the reviewer to reproduce the exact argv flow, metric calculation, post-validation mutation probes, quarantine chain, stale-contract recovery, disk preflight, immutable grounding, and legacy audit. Any Critical or Important finding blocks publication regardless of green unit tests.

- [ ] **Step 7: Commit release-gate coverage**

```bash
git add tests/codex_native/test_stage12_trustworthy_evidence_integration.py tests/performance/test_evidence_store_benchmark.py scripts/verify_stage12_evidence.sh pyproject.toml
git commit -m "test(codex): gate trustworthy stage twelve evidence"
```

Do not push or merge. Apply `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`, and ask for explicit publication approval.
