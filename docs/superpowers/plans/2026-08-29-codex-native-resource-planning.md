# Codex-Native Stage 11 Resource Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a closed, local-only Stage 11 resource plan that truthfully determines execution readiness and stops at a hash-bound Stage 12 approval gate.

**Architecture:** A new `resource_planning` core module owns the closed JSON schema, passive hardware observation, filesystem fact collection, DAG/budget checks, and readiness evaluation. Existing task-packet and validation flows expose and persist the plan, while a small execution-gate module owns read-only rechecks and four-artifact approval binding without running experiment code.

**Tech Stack:** Python 3.11+, standard library (`dataclasses`, `hashlib`, `json`, `os`, `platform`, `shutil`), pytest, existing ResearchClaw durable-state and plugin packaging infrastructure.

**Spec:** `docs/superpowers/specs/2026-08-29-codex-native-resource-planning-design.md`

## Global Constraints

- Stage 11 reads only approved `experiment/design.json`, validated `experiment/package_manifest.json`, `experiment/code/config.json`, `scope/hardware_profile.json`, and passive local hardware facts.
- Stage 11 writes exactly `experiment/resources.json`; it never creates `experiment/results.json`.
- Do not execute generated code or smoke tests, install packages, download data, contact networks, launch Docker/subprocesses, call external LLMs, or spawn nested agents.
- The deferred command is exactly `python experiment/code/main.py --config experiment/code/config.json` and the result path is exactly `experiment/results.json`.
- `max_parallel_tasks` is exactly `1`; total duration is the task-duration sum and peak CPU, memory, GPU, and temporary disk are per-field maxima.
- A structurally valid plan may yield `ready_for_execution` or `needs_input`; malformed or dishonest plans yield `invalid_plan`.
- Both valid readiness values complete Stage 11 and move durable state to Stage 12, but only `ready_for_execution` permits explicit execution approval.
- Stage 12 execution remains unsupported and no approval operation may execute the deferred command.
- Stage 12 approval binds SHA-256 values for the Stage 9 design, Stage 10 package manifest, Stage 10 config, and Stage 11 resource plan.
- Recheck may refresh observed facts and hashes only for already-declared input paths; it may not change tasks, commands, budgets, or add paths.
- Tests must never mutate the original battery project; release verification uses a temporary copy.

---

### Task 1: Stage 11 Contract and Passive Observation Boundary

**Files:**
- Create: `researchclaw/core/resource_planning.py`
- Modify: `researchclaw/core/contracts.py`
- Modify: `researchclaw/core/task_packets.py`
- Modify: `researchclaw/core/models.py`
- Test: `tests/codex_native/test_resource_planning.py`
- Test: `tests/codex_native/test_contracts.py`
- Test: `tests/codex_native/test_task_packets.py`

**Interfaces:**
- Consumes: `ResearchProject`, `resolve_project_artifact(root, relative_path)`, and persisted `ArtifactRef` values.
- Produces: `HardwareObservation`, `HardwareObservation.to_dict() -> dict[str, object]`, `observe_local_hardware(root: Path) -> HardwareObservation`, and Stage 11 support in `build_task_packet`.

- [ ] **Step 1: Write failing contract and observation tests**

```python
def test_stage_eleven_is_supported_with_all_read_only_inputs():
    contract = get_contract(11)
    assert SUPPORTED_STAGE_MAX == 11
    assert contract.required_inputs == (
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/config.json",
        "scope/hardware_profile.json",
    )
    assert contract.required_outputs == ("experiment/resources.json",)
    assert contract.allowed_tool_classes == ("filesystem", "analysis")


def test_observe_local_hardware_reports_passive_non_negative_facts(tmp_path):
    observed = observe_local_hardware(tmp_path)
    assert observed.logical_cpu_count >= 1
    assert observed.total_memory_bytes >= 0
    assert observed.free_disk_bytes >= 0
    assert observed.platform
    assert observed.architecture
    assert observed.method == "python_stdlib_passive"
```

- [ ] **Step 2: Run the focused tests and confirm the unsupported-boundary failure**

Run: `pytest tests/codex_native/test_contracts.py tests/codex_native/test_resource_planning.py tests/codex_native/test_task_packets.py -q`

Expected: FAIL because Stage 11 is outside `SUPPORTED_STAGE_IDS`, required inputs are incomplete, and `observe_local_hardware` is absent.

- [ ] **Step 3: Add immutable passive-observation types and implementation**

```python
@dataclass(frozen=True)
class HardwareObservation:
    logical_cpu_count: int
    total_memory_bytes: int
    free_disk_bytes: int
    platform: str
    architecture: str
    gpu_available: bool | None
    method: str
    observed_at: str


def observe_local_hardware(root: Path) -> HardwareObservation:
    return HardwareObservation(
        logical_cpu_count=max(1, os.cpu_count() or 1),
        total_memory_bytes=_total_memory_bytes(),
        free_disk_bytes=shutil.disk_usage(root).free,
        platform=platform.system(),
        architecture=platform.machine(),
        gpu_available=None,
        method="python_stdlib_passive",
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
```

Use `os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")` when available and return `0` when the platform exposes no passive memory fact. Do not use `subprocess`, shell commands, benchmarks, imports of generated package code, or GPU probing that launches a process.

- [ ] **Step 4: Extend the contract and packet profile context**

Set `SUPPORTED_STAGE_IDS = tuple(range(1, 12))`, `SUPPORTED_STAGE_MAX = 11`, replace Stage 11 inputs with the four exact paths, and add Stage 11 acceptance criteria. In `build_task_packet`, independently verify the Stage 9 approval still matches, then add these serialized tuple values to `profile_context`:

```python
{
    "hardware_observation": (json.dumps(observation.to_dict(), sort_keys=True),),
    "deferred_command": ("python experiment/code/main.py --config experiment/code/config.json",),
    "result_path": ("experiment/results.json",),
}
```

Add `report_resource_plan_milestone_only`, `approve_experiment_execution`, and `report_missing_execution_inputs` to the state's closed `_NEXT_ACTIONS` set so later tasks can persist these exact values.

- [ ] **Step 5: Run focused tests and commit**

Run: `pytest tests/codex_native/test_contracts.py tests/codex_native/test_resource_planning.py tests/codex_native/test_task_packets.py tests/codex_native/test_state.py -q`

Expected: PASS with packet preparation performing no writes outside the existing event/state bookkeeping.

```bash
git add researchclaw/core/contracts.py researchclaw/core/models.py researchclaw/core/resource_planning.py researchclaw/core/task_packets.py tests/codex_native/test_contracts.py tests/codex_native/test_resource_planning.py tests/codex_native/test_task_packets.py
git commit -m "feat(codex): expose stage 11 resource planning"
```

### Task 2: Closed Resource Plan Parser and Structural Validation

**Files:**
- Modify: `researchclaw/core/resource_planning.py`
- Modify: `tests/codex_native/helpers.py`
- Test: `tests/codex_native/test_resource_planning.py`

**Interfaces:**
- Consumes: `HardwareObservation` from Task 1 and JSON-decoded `object` input.
- Produces: `ResourcePlan`, `ResourceTask`, `InputReadiness`, `ResourcePlanOutcome`, and `validate_resource_plan_structure(raw: object) -> ResourcePlanOutcome`.

- [ ] **Step 1: Add a canonical valid-plan fixture and failing schema tests**

```python
def valid_resource_plan(project, observation, *, readiness="ready_for_execution"):
    return {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "bindings": {},
        "saved_hardware_profile": {},
        "hardware_observation": observation.to_dict(),
        "inputs": [],
        "tasks": [{
            "task_id": "run_experiment",
            "kind": "experiment",
            "depends_on": [],
            "priority": 1,
            "cpu_count": 1,
            "memory_bytes": 1,
            "gpu_count": 0,
            "temporary_disk_bytes": 1,
            "estimated_duration_seconds": 1,
        }],
        "budget": {
            "max_parallel_tasks": 1,
            "peak_cpu_count": 1,
            "peak_memory_bytes": 1,
            "peak_gpu_count": 0,
            "peak_temporary_disk_bytes": 1,
            "total_estimated_duration_seconds": 1,
        },
        "deferred_command": "python experiment/code/main.py --config experiment/code/config.json",
        "result_path": "experiment/results.json",
        "prohibitions": {
            "network_access": False,
            "downloads": False,
            "package_installation": False,
            "external_llm_calls": False,
            "nested_agent_processes": False,
            "generated_code_execution": False,
        },
        "warnings": [],
        "unmet_prerequisites": [],
        "readiness": readiness,
    }


@pytest.mark.parametrize("mutation,code", [
    (lambda p: p.update(extra=True), "unknown_field"),
    (lambda p: p["tasks"].append(dict(p["tasks"][0])), "duplicate_task_id"),
    (lambda p: p["tasks"][0].update(depends_on=["missing"]), "missing_dependency"),
    (lambda p: p["tasks"][0].update(memory_bytes=-1), "invalid_resource_value"),
    (lambda p: p["budget"].update(max_parallel_tasks=2), "unsupported_parallelism"),
])
def test_closed_plan_rejects_structural_errors(plan, mutation, code):
    mutation(plan)
    assert code in {issue.code for issue in validate_resource_plan_structure(plan).issues}
```

- [ ] **Step 2: Run the parser tests and confirm they fail before implementation**

Run: `pytest tests/codex_native/test_resource_planning.py -k 'closed_plan or cycle or aggregate' -q`

Expected: FAIL because the closed parser and issue codes do not exist.

- [ ] **Step 3: Implement exact closed dataclasses and issue aggregation**

```python
@dataclass(frozen=True)
class ResourcePlanOutcome:
    plan: ResourcePlan | None
    issues: tuple[ResourcePlanIssue, ...]

    @property
    def valid(self) -> bool:
        return self.plan is not None and not self.issues
```

Define required field sets for the root, binding, observation, input, task, budget, and prohibitions objects. Reject missing fields, unknown fields, booleans where integers are expected, negative quantities, duplicate input paths/task IDs, invalid readiness values, and any `max_parallel_tasks` other than `1`. All issue paths must use stable JSON-style locations such as `tasks[0].memory_bytes`.

- [ ] **Step 4: Implement DAG and deterministic aggregate checks**

Use an iterative color-map DFS or Kahn topological pass to reject self-dependencies and cycles. Compute and compare:

```python
expected_budget = {
    "max_parallel_tasks": 1,
    "peak_cpu_count": max(task.cpu_count for task in tasks),
    "peak_memory_bytes": max(task.memory_bytes for task in tasks),
    "peak_gpu_count": max(task.gpu_count for task in tasks),
    "peak_temporary_disk_bytes": max(task.temporary_disk_bytes for task in tasks),
    "total_estimated_duration_seconds": sum(task.estimated_duration_seconds for task in tasks),
}
```

Require exactly one `kind == "experiment"` task and at least one preparation/readiness task when inputs are declared. Reject command, result path, and any prohibition value that differs from the global constants.

- [ ] **Step 5: Run parser tests and commit**

Run: `pytest tests/codex_native/test_resource_planning.py -k 'closed_plan or cycle or aggregate or command or prohibition' -q`

Expected: PASS for valid DAGs and FAIL-as-data with the asserted issue codes for malformed plans.

```bash
git add researchclaw/core/resource_planning.py tests/codex_native/helpers.py tests/codex_native/test_resource_planning.py
git commit -m "feat(codex): validate closed resource plans"
```

### Task 3: Filesystem Truth, Hardware Sufficiency, and Stage Advancement

**Files:**
- Modify: `researchclaw/core/resource_planning.py`
- Modify: `researchclaw/core/validation.py`
- Modify: `researchclaw/core/project.py`
- Modify: `researchclaw/core/handoff.py`
- Test: `tests/codex_native/test_resource_planning.py`
- Test: `tests/codex_native/test_resume.py`

**Interfaces:**
- Consumes: `validate_resource_plan_structure`, current `ResearchProject`, and `ValidationIssue`.
- Produces: `validate_stage_eleven(project: ResearchProject, raw: object) -> tuple[ResourcePlan | None, tuple[ValidationIssue, ...]]` and readiness-aware Stage 12 state/handoff.

- [ ] **Step 1: Write failing semantic-validation tests**

```python
def test_ready_plan_advances_to_locked_stage_twelve(stage_11_project, ready_plan):
    write_json(stage_11_project.root / "experiment/resources.json", ready_plan)
    report = validate_current_stage(stage_11_project)
    state = ResearchProject.open(stage_11_project.root).state
    assert report.valid is True
    assert state.current_stage == 12
    assert state.status is StageStatus.AWAITING_APPROVAL
    assert state.next_action == "approve_experiment_execution"
    assert not (stage_11_project.root / "experiment/results.json").exists()


def test_truthful_missing_input_completes_planning_but_locks_approval(stage_11_project, missing_plan):
    write_json(stage_11_project.root / "experiment/resources.json", missing_plan)
    assert validate_current_stage(stage_11_project).valid is True
    state = ResearchProject.open(stage_11_project.root).state
    assert state.current_stage == 12
    assert state.status is StageStatus.AWAITING_APPROVAL
    assert state.next_action == "report_missing_execution_inputs"
```

Also add parameterized failures for stale design/manifest/config hashes, path traversal, symlink components, incorrect existence/type/size/hash facts, missing license status, insufficient CPU/memory/disk/GPU, pre-existing results, false ready claims, and nondeterministic or non-actionable unmet-prerequisite entries.

- [ ] **Step 2: Run semantic tests and confirm Stage 11 currently uses only generic validation**

Run: `pytest tests/codex_native/test_resource_planning.py tests/codex_native/test_resume.py -q`

Expected: FAIL because Stage 11 has no semantic validator or readiness-aware transition.

- [ ] **Step 3: Implement hash, path, input-fact, and hardware checks**

```python
def validate_stage_eleven(project: ResearchProject, raw: object) -> tuple[ResourcePlan | None, tuple[ValidationIssue, ...]]:
    outcome = validate_resource_plan_structure(raw)
    if not outcome.valid:
        return None, tuple(_as_validation_issue(issue) for issue in outcome.issues)
    plan = outcome.plan
    # Compare project_id, four exact SHA-256 bindings, saved profile bytes,
    # passive observation facts, declared input facts, hardware capacity,
    # readiness, warnings, and unmet prerequisites.
    return plan, tuple(issues)
```

Resolve every input with `resolve_project_artifact`; reject traversal and every path whose existing prefix is a symlink. Hash regular files in chunks. Treat `license_status` as exactly `confirmed`, `not_required`, or `unconfirmed`; a required input with `unconfirmed` license creates a deterministic prerequisite. Hardware drift from the saved profile is a warning, while capacity below peak plan needs is a prerequisite.

- [ ] **Step 4: Integrate Stage 11 and persist the two valid boundary states**

Dispatch `_validate_stage_eleven` from `validate_current_stage`. Extend `advance_validated_stage` so a valid Stage 11 report parses the persisted plan and sets:

```python
replace(
    state,
    current_stage=12,
    completed_stages=(*state.completed_stages, 11),
    status=StageStatus.AWAITING_APPROVAL,
    next_action=(
        "approve_experiment_execution"
        if plan.readiness == "ready_for_execution"
        else "report_missing_execution_inputs"
    ),
    artifacts={**state.artifacts, **report.artifact_refs},
    last_error=None,
)
```

Do not call `get_contract(12)` during validation and do not expose a Stage 12 task packet. Update `build_handoff` and `ResearchProject.status_dict()` to report `execution_readiness`, `unmet_prerequisites`, and `approval_eligible` from validated `resources.json`, falling back safely when the file is malformed.

- [ ] **Step 5: Run Stage 11, state, and resume tests and commit**

Run: `pytest tests/codex_native/test_resource_planning.py tests/codex_native/test_validation.py tests/codex_native/test_resume.py tests/codex_native/test_project.py -q`

Expected: PASS; both honest readiness states reach Stage 12 and `invalid_plan` remains at Stage 11 under normal retry policy.

```bash
git add researchclaw/core/resource_planning.py researchclaw/core/validation.py researchclaw/core/project.py researchclaw/core/handoff.py tests/codex_native/test_resource_planning.py tests/codex_native/test_resume.py
git commit -m "feat(codex): enforce stage 11 readiness semantics"
```

### Task 4: Stage 12 Recheck and Four-Artifact Approval Gate

**Files:**
- Create: `researchclaw/core/execution_gate.py`
- Modify: `researchclaw/core/approval.py`
- Modify: `researchclaw/codex/cli.py`
- Modify: `researchclaw/core/handoff.py`
- Test: `tests/codex_native/test_execution_gate.py`
- Test: `tests/codex_native/test_approval.py`
- Test: `tests/codex_native/test_cli.py`

**Interfaces:**
- Consumes: validated Stage 11 `ResourcePlan`, current filesystem facts, and `ApprovalRecord` persistence.
- Produces: `ExecutionGateStatus`, `recheck_execution_readiness(project: ResearchProject) -> ExecutionGateStatus`, `stage_twelve_artifact_hashes(project: ResearchProject) -> dict[str, str]`, and CLI `execution recheck ROOT [--json]`.

- [ ] **Step 1: Write failing locked-gate, recheck, and binding tests**

```python
def test_stage_twelve_approval_refuses_needs_input(stage_12_missing_project):
    with pytest.raises(ValueError, match="execution prerequisites are not ready"):
        approve_current_gate(stage_12_missing_project, "approve", "Run it")


def test_recheck_only_refreshes_declared_input_facts(stage_12_missing_project, declared_input):
    declared_input.write_bytes(b"ready")
    before = load_json(stage_12_missing_project.root / "experiment/resources.json")
    status = recheck_execution_readiness(stage_12_missing_project)
    after = load_json(stage_12_missing_project.root / "experiment/resources.json")
    assert status.readiness == "ready_for_execution"
    assert after["tasks"] == before["tasks"]
    assert after["budget"] == before["budget"]
    assert after["deferred_command"] == before["deferred_command"]


def test_execution_approval_binds_four_artifacts(stage_12_ready_project):
    record = approve_current_gate(stage_12_ready_project, "approve", "Run it")
    assert set(record.artifact_hashes) == {
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/config.json",
        "experiment/resources.json",
    }
```

Add tests proving that recheck refuses undeclared paths and structural changes, approval performs no execution, and modifying any one of the four files invalidates `verify_current_approval`.

- [ ] **Step 2: Run gate tests and confirm current approval rejects unsupported Stage 12**

Run: `pytest tests/codex_native/test_execution_gate.py tests/codex_native/test_approval.py tests/codex_native/test_cli.py -q`

Expected: FAIL because Stage 12 is not a contract approval gate and no recheck command exists.

- [ ] **Step 3: Implement read-only observation and constrained plan refresh**

```python
@dataclass(frozen=True)
class ExecutionGateStatus:
    readiness: str
    approval_eligible: bool
    unmet_prerequisites: tuple[str, ...]
    resource_plan_sha256: str


def recheck_execution_readiness(project: ResearchProject) -> ExecutionGateStatus:
    # Require current_stage == 12 and a valid persisted Stage 11 artifact.
    # Refresh only hardware_observation, existing declared input fact fields,
    # warnings, unmet_prerequisites, readiness, and their dependent hashes.
    # Re-run the full validator before one atomic resources.json replacement.
```

Capture and compare immutable projections before writing: `project_id`, binding keys except hashes tied to refreshed declared inputs, input path/required/license/preparation fields, tasks, budget, command, result path, and prohibitions. If any differ, refuse recheck and require return to Stage 11. Update state `ArtifactRef` atomically after a successful write and emit `execution_readiness_rechecked`.

- [ ] **Step 4: Add the special Stage 12 execution approval path**

In `approve_current_gate`, branch before `get_contract(state.current_stage)` when `current_stage == 12`. Require `AWAITING_APPROVAL`, `next_action == "approve_experiment_execution"`, and fresh `ready_for_execution`. Build hashes from the four exact paths and save `approvals/stage-12.json`. For an approve decision, preserve `current_stage=12`, set status to `READY`, and set `next_action="report_resource_plan_milestone_only"`; do not mark Stage 12 complete and do not run the command. A reject decision keeps Stage 12 locked with `report_missing_execution_inputs` and records the human note.

Update `approval_matches_state` with the same special four-path set for Stage 12. Keep the generic contract-based behavior unchanged for Stages 5 and 9.

- [ ] **Step 5: Add CLI routing and run gate regression tests**

Add:

```python
execution = subcommands.add_parser("execution", help="inspect the Stage 12 execution gate")
execution_commands = execution.add_subparsers(dest="execution_command", required=True)
recheck = execution_commands.add_parser("recheck", help="refresh declared readiness facts")
recheck.add_argument("root", metavar="ROOT")
recheck.add_argument("--json", action="store_true", help="emit JSON")
```

Run: `pytest tests/codex_native/test_execution_gate.py tests/codex_native/test_approval.py tests/codex_native/test_cli.py tests/codex_native/test_resume.py -q`

Expected: PASS with zero `subprocess`, network, generated-main imports, or results-file creation.

- [ ] **Step 6: Commit**

```bash
git add researchclaw/core/execution_gate.py researchclaw/core/approval.py researchclaw/core/handoff.py researchclaw/codex/cli.py tests/codex_native/test_execution_gate.py tests/codex_native/test_approval.py tests/codex_native/test_cli.py
git commit -m "feat(codex): lock stage 12 behind resource approval"
```

### Task 5: Skill Instructions and Public Boundary Documentation

**Files:**
- Create: `skills/researchclaw/references/resource-planning.md`
- Modify: `skills/researchclaw/SKILL.md`
- Modify: `skills/researchclaw/references/stages.md`
- Modify: `README.md`
- Modify: `RESEARCHCLAW_AGENTS.md`
- Modify: `tests/codex_native/test_public_docs.py`
- Modify: `tests/codex_native/test_plugin_package.py`

**Interfaces:**
- Consumes: exact CLI and schema behavior from Tasks 1–4.
- Produces: an installed-skill workflow that authors only `experiment/resources.json`, validates it, reports readiness, and stops before execution.

- [ ] **Step 1: Add failing documentation pressure tests**

```python
def test_public_docs_advertise_stage_eleven_boundary():
    for path in PUBLIC_BOUNDARY_FILES:
        text = path.read_text(encoding="utf-8")
        assert "Stages 1–11" in text or "Stages 1-11" in text
        assert "Stage 12" in text
        assert "explicit" in text.lower() and "approval" in text.lower()


def test_resource_planning_reference_contains_safety_literals():
    text = RESOURCE_REFERENCE.read_text(encoding="utf-8")
    assert "experiment/resources.json" in text
    assert "ready_for_execution" in text
    assert "needs_input" in text
    assert "python experiment/code/main.py --config experiment/code/config.json" in text
    assert "Do not execute" in text
```

- [ ] **Step 2: Run documentation tests and verify the Stage 10 text fails**

Run: `pytest tests/codex_native/test_public_docs.py tests/codex_native/test_plugin_package.py -q`

Expected: FAIL because current public and installed-skill boundaries stop at Stage 10.

- [ ] **Step 3: Write the exact Stage 11 skill workflow**

Document this command sequence:

```text
researchclaw-codex stage prepare <ROOT> --json
# Read only packet inputs and hardware_observation; author only experiment/resources.json.
researchclaw-codex stage validate <ROOT> --json
# If needs_input, ask the user to satisfy listed prerequisites, then:
researchclaw-codex execution recheck <ROOT> --json
# Stop. Never run the deferred command in Stage 11.
```

The reference must reproduce every closed root and nested field, accepted enum, aggregation rule, symlink/path restriction, exact command/result path, and deterministic distinction among valid-ready, valid-missing, and invalid-plan outcomes. Tell Codex not to install, download, access networks, call LLMs, spawn agents, or execute generated code.

- [ ] **Step 4: Update public boundary and regression assertions**

Change supported-stage claims to 1–11, explain that Stage 12 remains an approval-only unsupported execution boundary, and state that approving does not execute. Update regex assertions to compare documentation values to `SUPPORTED_STAGE_MAX == 11` instead of hard-coded 10.

- [ ] **Step 5: Run docs/package tests and commit**

Run: `pytest tests/codex_native/test_public_docs.py tests/codex_native/test_plugin_package.py -q`

Expected: PASS with the source skill and packaged plugin copies agreeing on the Stage 11 boundary.

```bash
git add README.md RESEARCHCLAW_AGENTS.md skills/researchclaw/SKILL.md skills/researchclaw/references/stages.md skills/researchclaw/references/resource-planning.md tests/codex_native/test_public_docs.py tests/codex_native/test_plugin_package.py
git commit -m "docs(codex): teach stage 11 resource planning"
```

### Task 6: Full Verification, Plugin Reinstall, and Battery-Project Copy Test

**Files:**
- Modify only if verification finds a specific defect: files owned by Tasks 1–5
- Test: `tests/codex_native/test_resource_planning.py`
- Test: `tests/codex_native/test_execution_gate.py`
- Verify: installed ResearchClaw plugin and temporary battery-project copy

**Interfaces:**
- Consumes: all Stage 11 code, docs, CLI, and plugin packaging from Tasks 1–5.
- Produces: recorded evidence that the source tree, packaged plugin, and live temporary-copy workflow meet the design success criteria.

- [ ] **Step 1: Run all Codex-native tests from a clean process**

Run: `pytest tests/codex_native -q`

Expected: PASS with no Stage 1–10 regression.

- [ ] **Step 2: Run the complete repository suite**

Run: `pytest -q`

Expected: PASS. If a pre-existing unrelated failure appears, record the exact test and confirm it also fails at commit `aa5651f`; do not weaken Stage 11 assertions.

- [ ] **Step 3: Run static safety searches**

Run: `rg -n "subprocess|os\.system|requests\.|urllib|pip install|docker|experiment/results\.json" researchclaw/core/resource_planning.py researchclaw/core/execution_gate.py`

Expected: only the constant result-path literal may match; no execution, network, installer, Docker, or shell API appears.

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only intentional tracked changes.

- [ ] **Step 4: Update the cachebuster and reinstall the personal-marketplace plugin**

Run:

```bash
python3 /Users/jspark/.codex/skills/.system/plugin-creator/scripts/read_marketplace_name.py
python3 /Users/jspark/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py \
  /Users/jspark/Documents/Codex/2026-08-26/new-chat/AutoResearchClaw/.worktrees/codex-native-stage11
codex plugin add autoresearchclaw-codex@personal
```

Expected: the first command prints `personal`, the cachebuster command preserves the `0.1.0` base version with one fresh `+codex.<token>` suffix, and installation succeeds. A new Codex task is required for an interactive skill test after reinstall; the remaining CLI verification in this task may continue in the current shell.

Expected: installed plugin metadata and `resource-planning.md` report support through Stage 11.

- [ ] **Step 5: Exercise a temporary battery-project copy**

Use the known local project `/Users/jspark/Documents/Codex/2026-08-29/re/work/battery_life_ai_ready_data` and create an isolated copy:

```bash
stage11_tmp_dir="$(mktemp -d)"
stage11_battery_copy="$stage11_tmp_dir/battery_life_ai_ready_data"
cp -R /Users/jspark/Documents/Codex/2026-08-29/re/work/battery_life_ai_ready_data "$stage11_battery_copy"
researchclaw-codex stage prepare "$stage11_battery_copy" --json > "$stage11_tmp_dir/stage11-packet.json"
```

Invoke the installed `$researchclaw` skill in a new Codex task with this exact instruction: `Resume Stage 11 for the project at <stage11_battery_copy>. Use only the prepared packet and declared project inputs, create only experiment/resources.json, validate it, report readiness, and stop before Stage 12 execution.` Replace `<stage11_battery_copy>` with the printed absolute path. After that task completes, run:

Verify with:

```bash
test -f "$stage11_battery_copy/experiment/resources.json"
test ! -e "$stage11_battery_copy/experiment/results.json"
researchclaw-codex status "$stage11_battery_copy" --json
researchclaw-codex resume "$stage11_battery_copy" --json
git -C /Users/jspark/Documents/Codex/2026-08-29/re/work/battery_life_ai_ready_data status --short
```

Expected: current stage 12; readiness truthfully equals `ready_for_execution` or `needs_input`; approval eligibility agrees with readiness; external-LLM and nested-agent counters remain zero; the original project's `git status --short` and artifact hashes are unchanged.

- [ ] **Step 6: Commit verification-only fixes, if any, and record the final clean state**

If Steps 1–5 required a real fix, first add a reproducing test, make the smallest correction, rerun the focused and full suites, and commit:

```bash
git add researchclaw tests skills README.md RESEARCHCLAW_AGENTS.md
git commit -m "fix(codex): close stage 11 verification gaps"
```

Finish with: `git status --short && git log --oneline -6`

Expected: clean worktree and six or fewer focused Stage 11 commits after the design/plan commits.
