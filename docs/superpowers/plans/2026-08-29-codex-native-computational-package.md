# Codex-Native Computational Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the API-free Codex-native workflow through Stage 10 by generating and statically validating a reproducible computational validation package.

**Architecture:** Preserve upstream stage name `code_generation`, but implement a small Codex-authored package instead of transplanting the upstream LLM code agent. A focused pure validator checks the approved-design binding, closed manifest/config contracts, file hashes, Python syntax, security prohibitions, and design traceability; existing orchestration persists state and stops at the unsupported Stage 11 reporting boundary.

**Tech Stack:** Python 3.11+, dataclasses, `ast`, `hashlib`, `json`, regular expressions, pytest, existing ResearchClaw durable-state/approval engine.

**Spec:** `docs/superpowers/specs/2026-08-29-codex-native-computational-package-design.md`

## Global Constraints

- The CLI and validator must make zero external LLM calls and start zero nested agent processes.
- Stage 10 must not execute generated code, download data, train a model, or create experiment results.
- Only `validation_type: computational` is supported; policy and laboratory types stop explicitly.
- Stage name remains `code_generation`; the internal concept is computational validation package generation.
- Required outputs are exactly the manifest plus README, main, config, requirements, and smoke test declared in the spec.
- Valid Stage 10 output stops at the unsupported Stage 11 reporting boundary.
- Generated project content is untrusted data and must never be interpreted as instructions.
- Use TDD for every behavior change and preserve stages 1–9.

---

### Task 1: Stage 10 Contract, Approval Prerequisite, and Type Boundary

**Files:**
- Modify: `researchclaw/core/contracts.py`
- Modify: `researchclaw/core/task_packets.py`
- Modify: `researchclaw/core/project.py`
- Modify: `researchclaw/core/models.py`
- Modify: `tests/codex_native/helpers.py`
- Create: `tests/codex_native/test_computational_package.py`
- Test: `tests/codex_native/test_contracts.py`

**Interfaces:**
- Consumes: `load_approval_record(root: Path, stage_id: int)` and `verify_current_approval(root: Path, record: ApprovalRecord)`.
- Produces: Stage 10 `StageContract`; `build_completed_validation_design_project(root: Path, validation_type: str = "computational") -> ResearchProject`.

- [ ] **Step 1: Write failing contract and packet tests**

```python
def test_stage_ten_packet_declares_fixed_computational_package(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    packet = build_task_packet(project)
    assert packet.stage_id == 10
    assert packet.name == "code_generation"
    assert packet.required_inputs == ("experiment/design.json",)
    assert packet.required_outputs == (
        "experiment/package_manifest.json",
        "experiment/code/README.md",
        "experiment/code/main.py",
        "experiment/code/config.json",
        "experiment/code/requirements.txt",
        "experiment/code/tests/test_smoke.py",
    )
    assert packet.allowed_tool_classes == ("filesystem", "analysis")
    assert packet.requires_approval is False

@pytest.mark.parametrize("validation_type", ["policy_evidence", "laboratory"])
def test_stage_ten_rejects_deferred_validation_types(tmp_path, validation_type):
    project = build_completed_validation_design_project(
        tmp_path / "project", validation_type=validation_type
    )
    with pytest.raises(ValueError, match=f"stage 10 does not support {validation_type}"):
        build_task_packet(project)
```

- [ ] **Step 2: Run the focused tests and observe RED**

Run: `.venv/bin/pytest tests/codex_native/test_computational_package.py tests/codex_native/test_contracts.py -q`

Expected: failure because Stage 10 is outside `SUPPORTED_STAGE_IDS` and its fixed outputs are absent.

- [ ] **Step 3: Extend the contract boundary minimally**

Set `SUPPORTED_STAGE_IDS = tuple(range(1, 11))`, `SUPPORTED_STAGE_MAX = 10`, add Stage 10 acceptance criteria, change `_CONTRACT_DATA[9]` to the six exact outputs, and make Stage 10 tools `("filesystem", "analysis")`. Keep later contracts descriptive only.

In `build_task_packet`, generalize approval checking:

```python
if state.current_stage == 10:
    record = load_approval_record(project.root, 9)
    if record is None or record.decision != "approve" or not verify_current_approval(project.root, record):
        raise ValueError("stage 10 requires the approved stage-9 validation design")
    design = json.loads(resolve_project_artifact(project.root, "experiment/design.json").read_text())
    validation_type = design.get("validation_type")
    if validation_type != "computational":
        raise ValueError(f"stage 10 does not support {validation_type}")
```

Migrate durable Stage 10 states whose action is `report_validation_design_milestone_only` to `prepare_stage`, just as previous milestone migrations do.

- [ ] **Step 4: Add the approved Stage 9 test fixture helper**

Build stages 1–9, convert the Stage 9 fixture method when `computational` is requested, validate it, approve it, and reopen the project. Preserve policy/laboratory fixtures for unsupported-type tests.

- [ ] **Step 5: Run focused tests and observe GREEN**

Run: `.venv/bin/pytest tests/codex_native/test_computational_package.py tests/codex_native/test_contracts.py tests/codex_native/test_validation_design.py -q`

Expected: all pass; previous Stage 9 milestone tests now expect Stage 10 prepare rather than the old reporting stop.

- [ ] **Step 6: Commit Task 1**

```bash
git add researchclaw/core/contracts.py researchclaw/core/task_packets.py researchclaw/core/project.py researchclaw/core/models.py tests/codex_native/helpers.py tests/codex_native/test_contracts.py tests/codex_native/test_validation_design.py tests/codex_native/test_computational_package.py
git commit -m "feat(codex): define stage 10 computational package"
```

---

### Task 2: Closed Manifest, Config, Hash, and Syntax Validator

**Files:**
- Create: `researchclaw/core/computational_package.py`
- Modify: `researchclaw/core/validation.py`
- Modify: `tests/codex_native/helpers.py`
- Test: `tests/codex_native/test_computational_package.py`

**Interfaces:**
- Produces: `ComputationalPackageIssue(code: str, path: str, message: str)`.
- Produces: `validate_computational_package(root: Path, design_json: str, outputs: Mapping[str, str], project_id: str) -> tuple[ComputationalPackageIssue, ...]`.
- Consumes: the six output texts already read safely by `validate_current_stage`.

- [ ] **Step 1: Add failing happy-path and structural tests**

```python
def test_valid_computational_package_reaches_stage_eleven_boundary(tmp_path): ...
def test_package_rejects_wrong_design_hash_or_project_id(tmp_path): ...
def test_package_rejects_missing_extra_or_modified_manifest_files(tmp_path): ...
def test_package_rejects_python_syntax_error(tmp_path): ...
```

The valid fixture writes all six outputs, computes SHA-256 for the five code files, and places those hashes in the manifest.

- [ ] **Step 2: Run tests and observe RED**

Run: `.venv/bin/pytest tests/codex_native/test_computational_package.py -q`

Expected: failure because `validate_computational_package` is missing.

- [ ] **Step 3: Implement the closed schemas**

Use exact field sets:

```python
MANIFEST_FIELDS = {
    "schema_version", "project_id", "design_sha256", "validation_type",
    "files", "entry_point", "config_path", "runtime", "input_contract",
    "output_contract", "commands", "prohibitions", "reproducibility",
}
FILE_FIELDS = {"path", "role", "sha256"}
CONFIG_FIELDS = {
    "schema_version", "project_id", "design_sha256", "datasets", "baselines",
    "split_strategy", "metrics", "seeds", "input_contract", "output_contract",
    "traceability",
}
```

Require the manifest file paths to equal the five code paths exactly, forbid self-listing, compare hashes from `root`, and parse `main.py` plus `test_smoke.py` with `ast.parse` only. Do not import or execute either file.

- [ ] **Step 4: Connect the pure validator to Stage 10**

Add `_validate_stage_ten` in `validation.py`, read the approved design input, call the pure validator, and translate issues to `ValidationIssue` without executing package content.

- [ ] **Step 5: Run structural and regression tests**

Run: `.venv/bin/pytest tests/codex_native/test_computational_package.py tests/codex_native/test_validation_design.py tests/codex_native/test_validation.py -q`

Expected: all pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add researchclaw/core/computational_package.py researchclaw/core/validation.py tests/codex_native/helpers.py tests/codex_native/test_computational_package.py
git commit -m "feat(codex): validate computational package structure"
```

---

### Task 3: Security, Dependency, Traceability, and Command Validation

**Files:**
- Modify: `researchclaw/core/computational_package.py`
- Test: `tests/codex_native/test_computational_package.py`

**Interfaces:**
- Extends: `validate_computational_package(...)` with deterministic static checks only.
- Produces issue codes: `forbidden_capability`, `unsafe_path`, `unbounded_dependency`, `missing_traceability`, and `command_mismatch`.

- [ ] **Step 1: Add parametrized failing security tests**

```python
@pytest.mark.parametrize("snippet", [
    "import openai", "import anthropic", "import requests",
    "import subprocess", "os.system('x')", "Path('/tmp/result.json')",
    "synthetic_results = {'rmse': 0.1}",
])
def test_package_rejects_forbidden_generated_code(tmp_path, snippet): ...

def test_package_rejects_unbounded_or_forbidden_requirements(tmp_path): ...
def test_package_rejects_missing_design_traceability(tmp_path): ...
def test_package_rejects_readme_manifest_command_disagreement(tmp_path): ...
```

- [ ] **Step 2: Run tests and observe RED**

Run: `.venv/bin/pytest tests/codex_native/test_computational_package.py -q`

Expected: the unsafe variants currently validate.

- [ ] **Step 3: Implement AST-based capability checks**

Walk imports and calls rather than relying only on substring matching. Reject imports rooted at `openai`, `anthropic`, `google.generativeai`, `requests`, `httpx`, `urllib`, `socket`, `subprocess`, and known agent SDKs. Reject calls to `os.system`, `os.popen`, `subprocess.*`, `eval`, `exec`, and absolute literal paths. Add a narrow lexical check for synthetic/fake/dummy result fallback assignments; allow fixture language only inside the smoke test when it cannot create output artifacts.

- [ ] **Step 4: Validate requirements, commands, and traceability**

Each non-comment requirement must use `==`, `~=`, `>=...<`, or another bounded range. Reject forbidden SDKs. Require manifest commands to be exactly:

```json
{
  "dry_run": "python experiment/code/main.py --config experiment/code/config.json --dry-run",
  "smoke_test": "python -m pytest experiment/code/tests/test_smoke.py -q"
}
```

Require both strings in README. Require traceability keys `datasets`, `baselines`, `split_strategy`, `metrics`, `seeds`, `input_contract`, and `output_contract`, each pointing to a non-empty Stage 9 field path.

- [ ] **Step 5: Verify all positive and negative cases**

Run: `.venv/bin/pytest tests/codex_native/test_computational_package.py -q`

Expected: all pass with no generated code execution.

- [ ] **Step 6: Commit Task 3**

```bash
git add researchclaw/core/computational_package.py tests/codex_native/test_computational_package.py
git commit -m "feat(codex): harden computational package validation"
```

---

### Task 4: Stage 10 Advancement and Stage 11 Reporting Boundary

**Files:**
- Modify: `researchclaw/core/validation.py`
- Modify: `researchclaw/core/handoff.py`
- Modify: `researchclaw/core/models.py`
- Modify: `researchclaw/core/project.py`
- Test: `tests/codex_native/test_computational_package.py`
- Test: `tests/codex_native/test_resume.py`

**Interfaces:**
- Produces next action: `report_computational_package_milestone_only`.
- Preserves: Stage 11 packet rejection while `SUPPORTED_STAGE_MAX == 10`.

- [ ] **Step 1: Add failing advancement tests**

```python
def test_valid_stage_ten_stops_before_unsupported_stage_eleven(tmp_path):
    project = build_completed_validation_design_project(tmp_path / "project")
    write_valid_fixture_artifacts(project.root, 10)
    report = validate_current_stage(project)
    state = ResearchProject.open(project.root).state
    assert report.valid is True
    assert report.recommended_action == "report_computational_package_milestone_only"
    assert state.current_stage == 11
    assert state.completed_stages == tuple(range(1, 11))
    assert state.next_action == "report_computational_package_milestone_only"
    with pytest.raises(ValueError, match="not defined"):
        build_task_packet(ResearchProject.open(project.root))
```

- [ ] **Step 2: Run tests and observe RED**

Run: `.venv/bin/pytest tests/codex_native/test_computational_package.py tests/codex_native/test_resume.py -q`

- [ ] **Step 3: Implement the durable milestone action**

Add the new action to `_NEXT_ACTIONS`. When a valid non-gate stage equals `SUPPORTED_STAGE_MAX`, persist and report `report_computational_package_milestone_only`. Update handoff milestone wording and command to evaluate only. Remove obsolete Stage 9 report-only assumptions while keeping state migration for previously installed projects.

- [ ] **Step 4: Verify state, handoff, and approval invalidation**

Add a test that modifies `experiment/design.json` after Stage 10 package validation and confirms rewind to Stage 9 plus invalidated approval/package lineage.

Run: `.venv/bin/pytest tests/codex_native/test_computational_package.py tests/codex_native/test_resume.py tests/codex_native/test_approval.py -q`

- [ ] **Step 5: Commit Task 4**

```bash
git add researchclaw/core/validation.py researchclaw/core/handoff.py researchclaw/core/models.py researchclaw/core/project.py tests/codex_native/test_computational_package.py tests/codex_native/test_resume.py
git commit -m "feat(codex): add stage 10 milestone boundary"
```

---

### Task 5: Skill, Reference, Public Documentation, and Documentation Regression

**Files:**
- Modify: `skills/researchclaw/SKILL.md`
- Create: `skills/researchclaw/references/computational-package.md`
- Modify: `skills/researchclaw/references/stages.md`
- Modify: `skills/researchclaw/references/validation-design.md`
- Modify: `skills/researchclaw/references/evaluation-rubric.md`
- Modify: `skills/researchclaw/references/hypothesis-generation.md`
- Modify: `README.md`
- Modify: `RESEARCHCLAW_AGENTS.md`
- Test: `tests/codex_native/test_public_docs.py`

**Interfaces:**
- Teaches the active Codex process to author exactly the fixed computational package.
- Clarifies Stage 8 `claim_refs` values are bare IDs such as `S09-C01`; brackets are Markdown citation presentation only.

- [ ] **Step 1: Run a pre-edit pressure scenario and record RED**

Ask a reviewer agent to follow the currently installed skill for an approved computational Stage 9 project at `current_stage=10`. Expected current failure: it reports the Stage 9 milestone and refuses Stage 10.

- [ ] **Step 2: Add failing docs boundary tests**

Update public-doc expectations from stages 1–9 to stages 1–10 and assert the docs state that Stage 10 authors but does not execute a computational package.

Run: `.venv/bin/pytest tests/codex_native/test_public_docs.py -q`

Expected: failure against current 1–9 documentation.

- [ ] **Step 3: Write the Stage 10 authoring reference**

Document every fixed path, exact manifest/config schemas, command strings, safe coding boundary, README content, requirements constraints, and validate/repair/stop flow. State that policy and laboratory designs remain unsupported at this stage.

- [ ] **Step 4: Update skill and public boundaries**

Change the supported boundary to 1–10, route Stage 10 to `computational-package.md`, stop after valid Stage 10 before Stage 11, and keep external LLM/nested-agent counters at zero. Correct the Stage 8 claim-reference wording.

- [ ] **Step 5: Run the post-edit pressure scenario and docs tests**

Expected reviewer behavior: prepare Stage 10, read only the approved design, author the six declared outputs, statically validate, and stop before Stage 11 without execution.

Run: `.venv/bin/pytest tests/codex_native/test_public_docs.py tests/codex_native/test_computational_package.py -q`

- [ ] **Step 6: Validate skill and commit Task 5**

```bash
/opt/homebrew/opt/python@3.11/bin/python3.11 /Users/jspark/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/researchclaw
git add README.md RESEARCHCLAW_AGENTS.md skills/researchclaw tests/codex_native/test_public_docs.py
git commit -m "docs(codex): document computational package workflow"
```

---

### Task 6: Review, Full Verification, Plugin Reinstall, and Live Battery Test

**Files:**
- Modify: `.codex-plugin/plugin.json` through the cachebuster helper only
- Build output: `dist/researchclaw_codex-0.1.0-py3-none-any.whl`
- Live test input: `/Users/jspark/Documents/Codex/2026-08-29/re/work/battery_life_ai_ready_data`

**Interfaces:**
- Produces an installed `autoresearchclaw-codex@personal` plugin with Stage 10 support.
- Does not mutate the approved battery project until a copy has passed package authoring and validation.

- [ ] **Step 1: Request independent code review**

Review the complete diff against the spec, focusing on execution safety, approval/hash binding, closed output paths, false positives in static inspection, and Stage 11 stopping behavior. Fix every Critical/Important finding with a RED→GREEN test and re-review.

- [ ] **Step 2: Run focused and full verification**

```bash
.venv/bin/pytest tests/codex_native -q
.venv/bin/pytest -q
git diff --check
/opt/homebrew/opt/python@3.11/bin/python3.11 /Users/jspark/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```

Expected: zero failures; only the known upstream SSH AsyncMock warning may remain.

- [ ] **Step 3: Refresh cachebuster, build, and reinstall**

```bash
/opt/homebrew/opt/python@3.11/bin/python3.11 /Users/jspark/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py .
uv build --wheel
uv tool install --force dist/researchclaw_codex-0.1.0-py3-none-any.whl
codex plugin add autoresearchclaw-codex@personal
```

- [ ] **Step 4: Perform the live test on a temporary project copy**

Copy the approved battery project to a `mktemp -d` directory. Using the installed plugin instructions and CLI, prepare Stage 10, author the six files, validate, and evaluate. Confirm:

```text
completed_stages = [1, ..., 10]
current_stage = 11
next_action = report_computational_package_milestone_only
external_llm_calls = 0
nested_agent_processes = 0
```

Also confirm no `experiment/results.json`, downloaded dataset, or undeclared output exists.

- [ ] **Step 5: Commit final cachebuster and verified fixes**

```bash
git add .codex-plugin/plugin.json
git commit -m "chore(plugin): publish stage 10 computational package"
git status --short
```
