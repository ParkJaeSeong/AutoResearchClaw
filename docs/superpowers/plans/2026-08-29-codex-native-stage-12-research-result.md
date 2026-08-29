# Codex-Native Stage 12 Research Result Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit execution handoff and contract-bound research-result registration path that completes Stage 12 and advances a project to Stage 13 without ResearchClaw executing generated code.

**Architecture:** Introduce a focused `research_execution` core module with two public operations: prepare an immutable execution contract from the approved Stage 12 state, then validate and register an externally produced result. Reuse the no-symlink project-file reader, Stage 12 approval binding, artifact model, atomic persistence, and bounded event log; keep development execution separate and permanently non-promotable.

**Tech Stack:** Python 3.11+, standard-library JSON/hashlib/datetime, existing ResearchProject persistence and approval APIs, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-codex-native-stage-12-research-result-design.md`

## Global Constraints

- Never spawn `experiment/code/main.py`, a shell, or any project-provided command.
- Never install packages, download data, enable network access, call an external LLM, or start nested agents.
- Never synthesize research results from stdout, stderr, development results, or partial metrics.
- Require a current Stage 12 approval and revalidate every bound artifact and required input.
- Permit only `experiment/results.json` as the registered research result path.
- Reject `experiment/dev_results.json`, `development_only: true`, and `evidence_eligible: false`.
- Mutate durable project state only after every result check passes.
- Record only bounded identities, counts, and stable error categories in events.
- Observe RED before implementation and GREEN after each task.

## File Structure

- Create `researchclaw/core/research_execution.py`: execution-contract construction, strict result validation, and Stage 12 transition.
- Create `tests/codex_native/test_research_execution.py`: focused core tests and immutable-control assertions.
- Modify `tests/codex_native/helpers.py`: approved Stage 12 and contract-bound result fixtures.
- Modify `researchclaw/codex/cli.py` and `tests/codex_native/test_cli.py`: explicit CLI commands.
- Modify `researchclaw/core/handoff.py` and `tests/codex_native/test_handoff.py`: safe unsupported-Stage-13 handoff.
- Modify `README.md`, `skills/researchclaw/SKILL.md`, `skills/researchclaw/references/resource-planning.md`, and `tests/codex_native/test_public_docs.py`: public guidance.

---

### Task 1: Prepare an immutable explicit-execution contract

**Files:**
- Create: `researchclaw/core/research_execution.py`
- Create: `tests/codex_native/test_research_execution.py`
- Modify: `tests/codex_native/helpers.py`

**Interfaces:**
- Consumes `ResearchProject`, `load_approval_record(root, 12)`, `approval_matches_state(root, state, record)`, `stage_twelve_artifact_hashes(project)`, and the validated Stage 11 resource plan.
- Produces `EXECUTION_CONTRACT_PATH = "experiment/execution_contract.json"`.
- Produces `ExecutionPreparationStatus(readiness, approval_eligible, command, result_path, contract_path, contract_sha256)` with `to_dict()`.
- Produces `prepare_research_execution(project: ResearchProject) -> ExecutionPreparationStatus`.

- [ ] **Step 1: Add an approved Stage 12 fixture helper**

Add `build_approved_stage_twelve_project(root)` to `tests/codex_native/helpers.py`. It must use `build_stage_twelve_project`, create every declared required input, call `recheck_execution_readiness`, then call `approve_current_gate(project, "approve", "Explicit execution approved")`. Do not write an approval file directly.

```python
def build_approved_stage_twelve_project(root: Path) -> ResearchProject:
    project, declared_input = build_stage_twelve_project(
        root, readiness="ready_for_execution"
    )
    declared_input.parent.mkdir(parents=True, exist_ok=True)
    declared_input.write_bytes(b"approved research input\n")
    recheck_execution_readiness(project)
    project = ResearchProject.open(root)
    approve_current_gate(project, "approve", "Explicit execution approved")
    return ResearchProject.open(root)
```

- [ ] **Step 2: Write the failing preparation test**

```python
def test_prepare_run_writes_bound_contract_without_executing_project_code(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    marker = project.root / "project-code-executed"
    status = prepare_research_execution(project)
    contract_path = project.root / "experiment/execution_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert status.readiness == "ready_for_explicit_execution"
    assert status.approval_eligible is False
    assert status.command == contract["command"]
    assert status.result_path == "experiment/results.json"
    assert status.contract_sha256 == hashlib.sha256(contract_path.read_bytes()).hexdigest()
    assert contract["project_id"] == project.state.project_id
    assert contract["prohibitions"]["researchclaw_managed_execution"] is False
    assert not marker.exists()
```

The Stage 10 fixture must already contain marker-writing code before Stage 11 validation so all hashes and approval remain valid. Preparation must not import or run that code.

- [ ] **Step 3: Run RED**

Run `pytest -q tests/codex_native/test_research_execution.py::test_prepare_run_writes_bound_contract_without_executing_project_code`.

Expected: collection fails because `researchclaw.core.research_execution` does not exist.

- [ ] **Step 4: Implement contract construction**

Create constants and the frozen status dataclass:

```python
EXECUTION_CONTRACT_PATH = "experiment/execution_contract.json"
RESEARCH_RESULT_PATH = "experiment/results.json"

@dataclass(frozen=True)
class ExecutionPreparationStatus:
    readiness: str
    approval_eligible: bool
    command: str
    result_path: str
    contract_path: str
    contract_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

Implement these private interfaces:

```python
def _load_current_stage_twelve_approval(project: ResearchProject) -> ApprovalRecord:
    """Require Stage 12, approve decision, and approval_matches_state."""

def _load_current_resource_plan(project: ResearchProject) -> dict[str, object]:
    """Reopen the Stage 11 artifact and rerun structural/hash validation."""

def _snapshot_required_inputs(
    project: ResearchProject, plan: Mapping[str, object]
) -> list[dict[str, object]]:
    """Return sorted path/size/sha256/license entries for required regular files."""

def _build_execution_contract(project: ResearchProject) -> dict[str, object]:
    """Return the closed contract with deterministic contract_id."""
```

Read required inputs and package files through `_read_project_file_snapshot`. Require the resource plan's exact `result_path` to be `experiment/results.json`. Bind design, package manifest, config, resources, and each package-manifest file SHA-256.

Compute `contract_id` from canonical JSON of project ID, command, result path, bindings, inputs, prohibitions, and result template, excluding `created_at` and `contract_id`. Serialize with `sort_keys=True`, compact separators, and `allow_nan=False`.

Write with `atomic_write_json`. Add the contract `ArtifactRef` without changing current stage, completed stages, status, next action, approvals, or Stage 10 snapshot. If an existing contract has the same deterministic ID and passes current validation, return it byte-for-byte.

- [ ] **Step 5: Add stale and idempotency tests**

Parameterize mutations of design, package manifest, config, resources, a package file, and a required input. Each must raise `execution_approval_invalid` or `execution_prerequisites_changed`, preserve any existing contract, and leave state unchanged. Add a test proving repeated preparation returns identical contract bytes and SHA-256.

- [ ] **Step 6: Verify and commit**

Run:

```bash
pytest -q tests/codex_native/test_research_execution.py -k prepare
git diff --check
```

Expected: all selected tests pass and diff check exits 0.

```bash
git add researchclaw/core/research_execution.py tests/codex_native/test_research_execution.py tests/codex_native/helpers.py
git commit -m "feat(codex): prepare explicit research execution"
```

---

### Task 2: Validate a closed, contract-bound research result

**Files:**
- Modify: `researchclaw/core/research_execution.py`
- Modify: `tests/codex_native/test_research_execution.py`
- Modify: `tests/codex_native/helpers.py`

**Interfaces:**
- Consumes the validated execution contract from Task 1.
- Produces `ValidatedResearchResult(result_path, result_sha256, payload, metric_count, input_count)`.
- Produces `validate_research_result(project: ResearchProject, result_path: str) -> ValidatedResearchResult` with no state or event mutation.
- Produces test helper `write_contract_bound_research_result(project, contract, **overrides) -> Path`.

- [ ] **Step 1: Add the canonical result fixture**

The helper must write the exact closed root keys in the spec. Use this metric/split structure and copy actual contract bindings and inputs:

```python
"metrics": {
    "primary": {"name": "mae_cycles", "value": 2.5, "unit": "cycles"}
},
"split_summary": {
    "isolation_key": "cell_id",
    "roles": {
        "train": {"cell_count": 6, "group_count": 3},
        "validation": {"cell_count": 2, "group_count": 1},
        "calibration": {"cell_count": 2, "group_count": 1},
        "test": {"cell_count": 4, "group_count": 2},
    },
    "cell_overlap_count": 0,
    "group_overlap_count": 0,
    "leakage_count": 0,
}
```

Set project ID, contract ID/SHA-256, provenance bindings/inputs, and runtime budget from actual fixture artifacts.

- [ ] **Step 2: Write the failing pure-validation test**

```python
def test_validate_research_result_accepts_exact_binding_without_mutation(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    events_before = (project.root / "evaluation/events.jsonl").read_bytes()
    validated = validate_research_result(project, "experiment/results.json")
    assert validated.result_sha256 == hashlib.sha256(result_path.read_bytes()).hexdigest()
    assert validated.metric_count == 1
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert (project.root / "evaluation/events.jsonl").read_bytes() == events_before
```

- [ ] **Step 3: Run RED**

Run `pytest -q tests/codex_native/test_research_execution.py::test_validate_research_result_accepts_exact_binding_without_mutation`.

Expected: FAIL because `validate_research_result` is absent.

- [ ] **Step 4: Implement strict result validation**

Add:

```python
@dataclass(frozen=True)
class ValidatedResearchResult:
    result_path: str
    result_sha256: str
    payload: Mapping[str, object]
    metric_count: int
    input_count: int
```

Read the contract and result using `_read_project_file_snapshot`. Decode UTF-8 with `json.loads(..., parse_constant=reject_non_finite)`. Reject extra or missing keys at every fixed-schema level. Validate in this order:

1. Exact result path; reject `dev_results.json` before reading.
2. Current approval and current contract bindings/inputs.
3. Root flags, project ID, completed status, and contract path/ID/SHA-256.
4. One or more metric records with exactly name/value/unit, finite non-boolean numeric value, and non-empty strings.
5. Required split roles, non-negative integer counts, expected isolation key, and zero overlap/leakage.
6. Provenance bindings and inputs equal to the current contract.
7. Finite non-negative elapsed time, positive integer maximum, elapsed not above maximum, maximum not above approved budget.
8. Freeze the parsed payload before returning it.

- [ ] **Step 5: Add table-driven rejection tests**

Cover extra keys, NaN, Inf, empty metrics, partial/failed status, development flag, non-evidence flag, wrong project, wrong contract ID/hash, changed provenance, negative split counts, overlap/leakage, elapsed over maximum, budget mismatch, absolute/path-escape paths, symlink, directory, and `experiment/dev_results.json`. Assert stable categories from the spec and byte-identical state, approvals, resources, contract, and result after failure.

- [ ] **Step 6: Verify and commit**

```bash
pytest -q tests/codex_native/test_research_execution.py -k 'validate or reject'
git diff --check
git add researchclaw/core/research_execution.py tests/codex_native/test_research_execution.py tests/codex_native/helpers.py
git commit -m "feat(codex): validate contract-bound research results"
```

---

### Task 3: Register the result and advance exactly to Stage 13

**Files:**
- Modify: `researchclaw/core/research_execution.py`
- Modify: `tests/codex_native/test_research_execution.py`
- Modify: `researchclaw/core/handoff.py`
- Modify: `tests/codex_native/test_handoff.py`

**Interfaces:**
- Consumes `validate_research_result(project, result_path)`.
- Produces `ResearchResultRegistrationStatus(readiness, approval_eligible, result_path, result_sha256, current_stage, next_action)` with `to_dict()`.
- Produces `register_research_result(project: ResearchProject, result_path: str) -> ResearchResultRegistrationStatus`.

- [ ] **Step 1: Write the failing transition test**

```python
def test_register_result_completes_stage_twelve(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    status = register_research_result(project, "experiment/results.json")
    reopened = ResearchProject.open(project.root)
    assert status.readiness == "research_result_registered"
    assert status.current_stage == 13
    assert reopened.state.current_stage == 13
    assert reopened.state.status == StageStatus.READY
    assert reopened.state.completed_stages.count(12) == 1
    assert reopened.state.artifacts["experiment/results.json"].sha256 == hashlib.sha256(
        result_path.read_bytes()
    ).hexdigest()
```

- [ ] **Step 2: Run RED**

Run `pytest -q tests/codex_native/test_research_execution.py::test_register_result_completes_stage_twelve`.

Expected: FAIL because registration is absent.

- [ ] **Step 3: Implement the state transition**

After pure validation, re-read result bytes and require the same SHA-256 immediately before persistence. Build an `ArtifactRef`, then persist:

```python
replace(
    state,
    current_stage=13,
    status=StageStatus.READY,
    completed_stages=(*tuple(s for s in state.completed_stages if s != 12), 12),
    next_action="prepare_stage",
    artifacts={**state.artifacts, "experiment/results.json": result_ref},
    last_error=None,
)
```

Preserve execution policy, retry counts, approvals, other artifacts, and Stage 10 snapshot. Append `research_result_registered` after persistence with only contract path/hash, result path/hash, metric count, and input count.

- [ ] **Step 4: Add race, retry, failure-event, and handoff tests**

Test a result changed between validation and persistence, duplicate registration, and each validation failure. State must remain Stage 12 on failure. Failure event keys must be a subset of `error_category`, `contract_path`, `contract_sha256`, `result_path`, and `result_sha256`.

Test `build_handoff()` at current stage 13. If it cannot represent unsupported Stage 13 safely, change only its message/state reconstruction so it reports Stage 13 as the next implementation boundary. Do not implement Stage 13 preparation or validation.

- [ ] **Step 5: Verify and commit**

```bash
pytest -q tests/codex_native/test_research_execution.py tests/codex_native/test_handoff.py
git diff --check
git add researchclaw/core/research_execution.py tests/codex_native/test_research_execution.py researchclaw/core/handoff.py tests/codex_native/test_handoff.py
git commit -m "feat(codex): complete stage twelve from registered results"
```

---

### Task 4: Expose explicit CLI commands and public guidance

**Files:**
- Modify: `researchclaw/codex/cli.py`
- Modify: `tests/codex_native/test_cli.py`
- Modify: `README.md`
- Modify: `skills/researchclaw/SKILL.md`
- Modify: `skills/researchclaw/references/resource-planning.md`
- Modify: `tests/codex_native/test_public_docs.py`

**Interfaces:**
- Produces `execution prepare-run ROOT [--json]`.
- Produces `execution register-result ROOT --result experiment/results.json --confirm-research-result [--json]`.
- Preserves existing recheck and development-execution commands.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_execution_prepare_run_cli_emits_handoff(tmp_path, capsys):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    assert main(["execution", "prepare-run", str(project.root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["readiness"] == "ready_for_explicit_execution"
    assert payload["result_path"] == "experiment/results.json"

def test_execution_register_result_cli_advances_to_thirteen(tmp_path, capsys):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    write_contract_bound_research_result(project, load_execution_contract(project.root))
    assert main([
        "execution", "register-result", str(project.root),
        "--result", "experiment/results.json",
        "--confirm-research-result", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["readiness"] == "research_result_registered"
    assert payload["current_stage"] == 13
```

Also test unapproved preparation and omission of each required registration flag. Every failure returns 2, keeps stdout empty, names the stable error or missing flag on stderr, and leaves state unchanged.

- [ ] **Step 2: Run RED**

Run `pytest -q tests/codex_native/test_cli.py -k 'prepare_run or register_result'`.

Expected: FAIL because neither command exists.

- [ ] **Step 3: Implement the CLI routes**

Open normally for `prepare-run` because it records the contract artifact. Require `--result` and `store_true, required=True` for `--confirm-research-result`; open normally because registration advances state. Route errors through the existing `OSError`/`ValueError` boundary. Keep non-JSON output `stage 12: {readiness}`.

- [ ] **Step 4: Update public guidance**

Document both exact commands and state that `prepare-run` does not execute the returned command; the user runs it in the project root; registration accepts only contract-bound `experiment/results.json`; stdout and development results are never evidence; successful registration advances to Stage 13, whose refinement remains separate.

Add public-doc tests for both command strings and the phrases `does not execute`, `development result`, and `Stage 13`.

- [ ] **Step 5: Verify and commit**

```bash
pytest -q tests/codex_native/test_cli.py -k execution
pytest -q tests/codex_native/test_public_docs.py
git diff --check
git add researchclaw/codex/cli.py tests/codex_native/test_cli.py README.md skills/researchclaw/SKILL.md skills/researchclaw/references/resource-planning.md tests/codex_native/test_public_docs.py
git commit -m "feat(codex): expose research result registration"
```

---

### Task 5: Adversarial review, integration verification, and publish

**Files:**
- Modify only files implicated by concrete review findings.
- Test: all `tests/codex_native`.

**Interfaces:**
- Verifies the complete workflow and clean Git synchronization.

- [ ] **Step 1: Review every invariant**

Inspect the final diff for: no subprocess/project import; no package/network/LLM/nested-agent action; closed finite schemas; regular project-relative files; current approval and hashes; development-result rejection; no stdout evidence; no premature state mutation; bounded events; exact Stage 12-to-13 transition.

For each defect, add a failing regression test, observe RED, apply the smallest fix, and rerun GREEN.

- [ ] **Step 2: Run the full suite fresh**

```bash
pytest -q tests/codex_native
git diff --check
```

Expected: zero failures and diff check exit 0.

- [ ] **Step 3: Run a disposable integration workflow**

Create a small approved Stage 12 fixture; do not register the user's long-running battery result first. Run:

```bash
PYTHONPATH=. /opt/homebrew/opt/python@3.11/bin/python3.11 -m researchclaw.codex.cli execution prepare-run /ABSOLUTE/FIXTURE/PROJECT --json
cd /ABSOLUTE/FIXTURE/PROJECT
python experiment/code/main.py --config experiment/code/config.json
PYTHONPATH=. /opt/homebrew/opt/python@3.11/bin/python3.11 -m researchclaw.codex.cli execution register-result /ABSOLUTE/FIXTURE/PROJECT --result experiment/results.json --confirm-research-result --json
PYTHONPATH=. /opt/homebrew/opt/python@3.11/bin/python3.11 -m researchclaw.codex.cli status /ABSOLUTE/FIXTURE/PROJECT --json
```

Expect `ready_for_explicit_execution`, the exact returned command to create only
`experiment/results.json`, `research_result_registered`, and `current_stage:
13`. Verify design, package, config, resources, approvals, inputs, contract, and
result retain pre-registration SHA-256 values; only state and append-only events
change during registration.

### Final review amendment

The release-blocking review extends the implementation with one common project
mutation transaction, strict shared result validation for initial registration,
pending recovery, and Stage-13 grounding, bounded JSON/event streaming, a
contract-preparation journal, and supported Stage-12 rewind actions. The fixed
Stage-10 non-dry entry point is the approved external runner; ResearchClaw
itself still never starts that process. Final verification must invoke the
exact returned command rather than a fixture writer and must not push or merge
the review branch.

- [ ] **Step 4: Run final verification**

```bash
pytest -q tests/codex_native
git diff --check
git status --short --branch
```

Do not claim completion or commit final fixes unless this fresh run reports zero failures.

- [ ] **Step 5: Commit review fixes and publish**

If review created changes, commit them as `fix(codex): harden research result registration`. Then:

```bash
git push origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expect no ahead/behind marker and identical local/remote commit hashes.
