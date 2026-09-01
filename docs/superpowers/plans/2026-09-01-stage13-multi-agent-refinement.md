# Stage 13 Multi-Agent Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an explicitly invoked Stage 13 workflow in which a three-agent council deliberates over immutable Stage 12 evidence, implementation agents produce isolated candidates, and deterministic CLI primitives validate, execute, register, and finalize the council decision.

**Architecture:** Add a reusable data-only deliberation validator, then layer a Stage 13 session state machine, candidate package validation, bounded candidate execution/evidence registration, and Stage 14 handoff on top. Agent reasoning remains outside the CLI; the plugin orchestrates agents and invokes granular deterministic commands. Candidate evidence uses a separate refinement manifest namespace.

**Tech Stack:** Python 3.11+, frozen dataclasses, JSON validated in Python, SHA-256 bindings, existing `ResearchProject` transactions and `EvidenceStore`, `argparse`, `pytest`, Codex plugin Markdown.

**Spec:** `docs/superpowers/specs/2026-09-01-stage13-multi-agent-refinement-design.md`

## Global Constraints

- No LLM API client or API key requirement.
- The coordinator has no vote; an implementation agent cannot vote on its candidate.
- Council roles are `domain`, `methodology`, and `critical_reproducibility`.
- Initial assessments are registered before rebuttals are disclosed.
- Two matching valid final votes are required; fewer than two valid voters pauses the session.
- Code validates evidence, authority, budgets, and procedure but never determines scientific merit from a fixed score threshold.
- Stage 12 evidence remains immutable; candidates stay below `refinement/candidates/<candidate-id>/`.
- Candidate evidence uses `.researchclaw/evidence/refinement-manifests/`, never the baseline manifest namespace.
- The first release supports computational experiments only.
- Research execution occurs only inside the user-authorized session envelope.
- Every persistent JSON record is schema version `1` and binds project, session, producer, artifacts, and UTC creation time.
- Every task follows RED → GREEN → REFACTOR and ends with a focused commit.

---

## File Structure

- Create `researchclaw/core/deliberation.py`: data-only council record and quorum validation.
- Create `researchclaw/core/refinement.py`: session, evidence packet, deliberation, candidates, final selection, and status.
- Create `researchclaw/core/refinement_execution.py`: candidate self-test/run contracts, envelope accounting, and result registration.
- Modify `models.py`, `contracts.py`, `handoff.py`, and `codex/cli.py` for Stage 13 state and commands.
- Modify the ResearchClaw skill and references for one-command agent orchestration.
- Add focused tests plus one synthetic multi-agent E2E test under `tests/codex_native/`.

### Task 1: Reusable Deliberation Contracts

**Files:**
- Create: `researchclaw/core/deliberation.py`
- Create: `tests/codex_native/test_deliberation.py`

**Interfaces:**
- Produces: `CouncilRole`, `Assessment`, `Rebuttal`, `FinalVote`, `CouncilDecision`.
- Produces: `parse_assessment(payload, *, expected_binding, expected_role) -> Assessment`.
- Produces: `parse_rebuttal(payload, *, expected_binding, expected_role) -> Rebuttal`.
- Produces: `decide_council(*, assessments, rebuttals, final_votes) -> CouncilDecision`.

- [ ] **Step 1: Write failing role and binding tests**

```python
def test_assessment_requires_expected_role_and_binding():
    payload = valid_assessment(role="domain", evidence_sha256="a" * 64)
    assert parse_assessment(
        payload, expected_binding="a" * 64, expected_role=CouncilRole.DOMAIN
    ).role is CouncilRole.DOMAIN
    with pytest.raises(ValueError, match="deliberation_binding_invalid"):
        parse_assessment(payload, expected_binding="b" * 64, expected_role=CouncilRole.DOMAIN)

def test_implementation_role_cannot_vote():
    with pytest.raises(ValueError, match="deliberation_role_invalid"):
        parse_assessment(
            valid_assessment(role="implementation", evidence_sha256="a" * 64),
            expected_binding="a" * 64,
            expected_role=CouncilRole.DOMAIN,
        )
```

- [ ] **Step 2: Run RED**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_deliberation.py -q`

Expected: import failure because `researchclaw.core.deliberation` does not exist.

- [ ] **Step 3: Implement strict parsers and closed enums**

```python
class CouncilRole(str, Enum):
    DOMAIN = "domain"
    METHODOLOGY = "methodology"
    CRITICAL_REPRODUCIBILITY = "critical_reproducibility"

@dataclass(frozen=True)
class Assessment:
    role: CouncilRole
    evidence_packet_sha256: str
    recommendation: str
    rationale: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
```

Require schema v1, expected role/binding, non-empty rationale, project-relative evidence refs, and no unknown authority fields.

- [ ] **Step 4: Write failing quorum and sequence tests**

```python
def test_two_matching_final_votes_form_decision():
    decision = decide_council(
        assessments=three_valid_assessments(),
        rebuttals=three_valid_rebuttals(),
        final_votes=final_votes("refine", "refine", "retain_baseline"),
    )
    assert decision.decision == "refine"
    assert decision.dissenting_roles == ("critical_reproducibility",)

def test_vote_before_complete_assessments_fails():
    with pytest.raises(ValueError, match="deliberation_sequence_invalid"):
        decide_council(assessments=two_valid_assessments(), rebuttals=(), final_votes=())
```

- [ ] **Step 5: Implement quorum and dissent**

Accept only `refine`, `select_candidate`, `retain_baseline`, `request_discriminating_run`, and `inconclusive`. Reject duplicate roles, altered bindings, missing prior records, and ties without two matching votes.

- [ ] **Step 6: Verify and commit**

```bash
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_deliberation.py -q
git add researchclaw/core/deliberation.py tests/codex_native/test_deliberation.py
git commit -m "feat(codex): add evidence-bound council deliberation"
```

### Task 2: Stage 13 Session and Evidence Packet

**Files:**
- Create: `researchclaw/core/refinement.py`
- Create: `tests/codex_native/test_refinement.py`
- Modify: `researchclaw/core/models.py`
- Modify: `researchclaw/core/contracts.py`
- Modify: `tests/codex_native/helpers.py`

**Interfaces:**
- Produces: `RefinementEnvelope`, `RefinementSessionStatus`.
- Produces: `prepare_refinement_session(project, envelope_payload) -> RefinementSessionStatus`.
- Produces: `load_refinement_session(project) -> RefinementSessionStatus`.
- Durable paths: `refinement/session.json`, `refinement/evidence_packet.json`.

- [ ] **Step 1: Write failing grounding and immutability tests**

```python
def test_prepare_session_requires_verified_stage_twelve_evidence(tmp_path):
    project = build_stage_thirteen_project(tmp_path / "project")
    before = immutable_stage_twelve_snapshot(project)
    status = prepare_refinement_session(project, valid_envelope())
    assert status.phase == "awaiting_independent_assessments"
    assert immutable_stage_twelve_snapshot(project) == before

def test_prepare_session_rejects_legacy_result(tmp_path):
    with pytest.raises(ValueError, match="refinement_baseline_unavailable"):
        prepare_refinement_session(
            build_ungrounded_stage_thirteen_project(tmp_path / "project"), valid_envelope()
        )
```

- [ ] **Step 2: Run RED**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement.py -q`

- [ ] **Step 3: Implement schemas and bounds**

```python
@dataclass(frozen=True)
class RefinementEnvelope:
    maximum_runs: int
    maximum_wall_seconds: int
    maximum_candidate_seconds: int
    allowed_input_paths: tuple[str, ...]
    allowed_change_roots: tuple[str, ...]

@dataclass(frozen=True)
class RefinementSessionStatus:
    session_id: str
    phase: str
    evidence_packet_path: str
    evidence_packet_sha256: str
    runs_used: int
    maximum_runs: int
    next_action: str
```

Allow 1-10 runs and positive time bounds up to seven days. Allowed inputs must equal Stage 12 inputs; change roots are candidate-local code, config, tests, and package metadata.

- [ ] **Step 4: Implement atomic idempotent preparation**

Bind the Stage 9 design, Stage 10 package/files, Stage 11 resources, Stage 12 contract/result, and verified baseline manifest. Use `project_mutation`, exclusive writes, state artifact refs, and a stable session ID. Add refinement next actions to `models._NEXT_ACTIONS`.

- [ ] **Step 5: Add tamper and interruption tests**

Identical preparation returns the existing session. Changed packet, envelope, or baseline binding raises `refinement_integrity_failure`. A failure between file and state persistence may adopt only exact owned files.

- [ ] **Step 6: Verify and commit**

```bash
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement.py tests/codex_native/test_state.py tests/codex_native/test_contracts.py -q
git add researchclaw/core/refinement.py researchclaw/core/models.py researchclaw/core/contracts.py tests/codex_native/test_refinement.py tests/codex_native/helpers.py
git commit -m "feat(codex): prepare grounded refinement sessions"
```

### Task 3: Durable Assessments and Decisions

**Files:**
- Modify: `researchclaw/core/refinement.py`
- Modify: `tests/codex_native/test_refinement.py`

**Interfaces:**
- Produces: `register_refinement_assessment(project, path) -> RefinementSessionStatus`.
- Produces: `register_refinement_rebuttals(project, path) -> RefinementSessionStatus`.
- Produces: `register_refinement_decision(project, path) -> RefinementSessionStatus`.

- [ ] **Step 1: Write failing disclosure-order test**

```python
def test_rebuttal_requires_all_initial_assessments(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_one_assessment(project, role="domain")
    with pytest.raises(ValueError, match="refinement_disclosure_order_invalid"):
        register_refinement_rebuttals(project, write_valid_rebuttals(project))
```

- [ ] **Step 2: Run RED**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement.py -k 'assessment or rebuttal or decision' -q`

- [ ] **Step 3: Implement exclusive per-role registration**

Allocate monotonic `round-[0-9]{3}` directories and store initial records at `refinement/deliberations/<round-id>/<role>_review.json`. Re-registration is idempotent only for identical bytes. `rebuttals.json` binds all initial hashes; no final vote is accepted before it exists. A retry record names the failed producer and replacement producer. After one failed retry, record the role as vacant; two remaining voters must agree or the session pauses.

- [ ] **Step 4: Implement decision registration**

`decision.json` contains final votes, quorum, supporting/dissenting roles, rationale, evidence refs, action, and optional change request. Reject unknown candidates and changes outside the envelope. Derive next action from the vote without a coordinator override.

- [ ] **Step 5: Add retry and partial-persistence tests**

One failed role may be retried once with a new producer ID. A role cannot submit two different valid records. Recovery cannot count partial or duplicate votes.

- [ ] **Step 6: Verify and commit**

```bash
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_deliberation.py tests/codex_native/test_refinement.py -q
git add researchclaw/core/refinement.py tests/codex_native/test_refinement.py
git commit -m "feat(codex): register refinement council deliberations"
```

### Task 4: Isolated Candidate Registration

**Files:**
- Modify: `researchclaw/core/refinement.py`
- Modify: `researchclaw/core/experiment_package_contract.py`
- Modify: `tests/codex_native/test_refinement.py`
- Modify: `tests/codex_native/helpers.py`

**Interfaces:**
- Produces: `CandidateStatus`.
- Produces: `register_refinement_candidate(project, manifest_path) -> CandidateStatus`.
- Candidate root: `refinement/candidates/candidate-[0-9]{3}/`.

- [ ] **Step 1: Write failing containment and binding tests**

```python
def test_candidate_must_bind_council_change_request(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    manifest = write_candidate(project, decision_sha256="0" * 64)
    with pytest.raises(ValueError, match="refinement_candidate_binding_invalid"):
        register_refinement_candidate(project, manifest)

def test_candidate_cannot_bind_outside_candidate_root(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    with pytest.raises(ValueError, match="refinement_candidate_path_invalid"):
        register_refinement_candidate(
            project, write_candidate(project, files=["../../experiment/results.json"])
        )
```

- [ ] **Step 2: Run RED**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement.py -k candidate -q`

- [ ] **Step 3: Implement candidate manifests**

Allocate monotonic candidate IDs. Bind each regular non-symlink file, council decision, baseline package, unchanged inputs/split/metric declarations, implementation producer, and entry point. Reject unknown files, symlink components, and baseline paths.

- [ ] **Step 4: Reuse Stage 10 validation without weakening it**

Add `validate_experiment_package_contract_at(project, *, package_root: Path, contract_path: str) -> ExperimentPackageContract`, and make the existing `validate_experiment_package_contract(project)` wrapper call it for the baseline package. Candidate packages retain AST, manifest, self-test adapter, traceability, and output checks. Compare the baseline snapshot before and after validation.

- [ ] **Step 5: Add replacement and ABA tests**

Replace, retarget, and restore candidate files between validation phases. Any changed identity fails; byte-identical re-registration returns the original status.

- [ ] **Step 6: Verify and commit**

```bash
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement.py tests/codex_native/test_experiment_package_contract.py tests/codex_native/test_computational_package.py -q
git add researchclaw/core/refinement.py researchclaw/core/experiment_package_contract.py tests/codex_native/test_refinement.py tests/codex_native/helpers.py
git commit -m "feat(codex): register isolated refinement candidates"
```

### Task 5: Candidate Self-Test, Execution, and Evidence

**Files:**
- Create: `researchclaw/core/refinement_execution.py`
- Create: `tests/codex_native/test_refinement_execution.py`
- Modify: `researchclaw/core/refinement.py`

**Interfaces:**
- Produces: `prepare_refinement_self_test(project, candidate_id) -> SelfTestPreparationStatus`.
- Produces: `register_refinement_self_test(project, candidate_id, report_path) -> CandidateStatus`.
- Produces: `prepare_refinement_run(project, candidate_id) -> RefinementRunStatus`.
- Produces: `register_refinement_result(project, candidate_id, result_path) -> RefinementRunStatus`.

- [ ] **Step 1: Write failing self-test and uv launcher test**

```python
def test_candidate_self_test_uses_verified_uv_launcher(tmp_path):
    project, candidate = registered_candidate_project(tmp_path / "project")
    status = prepare_refinement_self_test(project, candidate)
    assert Path(status.argv[0]).is_absolute()
    assert status.cwd.endswith(f"refinement/candidates/{candidate}")
    assert status.environment_fingerprint
```

- [ ] **Step 2: Run RED**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement_execution.py -q`

- [ ] **Step 3: Implement self-test preparation and registration**

Reuse Stage 12 environment and report validation with candidate-relative paths. Bind candidate manifest, council decision, evidence packet, environment, and candidate files. Self-tests do not consume research-run slots.

- [ ] **Step 4: Write failing envelope and preservation tests**

```python
def test_prepare_run_rejects_exhausted_envelope(tmp_path):
    project, candidate = self_tested_candidate_project(tmp_path / "project", maximum_runs=1)
    register_one_candidate_run(project, candidate)
    with pytest.raises(ValueError, match="refinement_run_budget_exhausted"):
        prepare_refinement_run(project, candidate)

def test_candidate_result_never_replaces_baseline(tmp_path):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    before = (project.root / "experiment/results.json").read_bytes()
    run_and_register_candidate(project, candidate)
    assert (project.root / "experiment/results.json").read_bytes() == before
```

- [ ] **Step 5: Implement atomic run reservation and authoritative contract**

Bind candidate files, self-test, baseline evidence, allowed inputs, envelope, next run slot, and authoritative argv. Reserve the slot atomically. Recovery completes the owned reservation or releases it only when no result exists. Enforce maxima without interpreting metrics.

- [ ] **Step 6: Register immutable candidate evidence**

Write manifests below `.researchclaw/evidence/refinement-manifests/<session>/<candidate>/<run>.json` and objects through `EvidenceStore`. Never create another baseline manifest or change `experiment/results.json`.

- [ ] **Step 7: Verify and commit**

```bash
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement_execution.py tests/codex_native/test_execution_environment.py tests/codex_native/test_evidence_registration.py tests/codex_native/test_evidence_store.py -q
git add researchclaw/core/refinement_execution.py researchclaw/core/refinement.py tests/codex_native/test_refinement_execution.py
git commit -m "feat(codex): execute bounded refinement candidates"
```

### Task 6: Final Selection and Stage 14 Handoff

**Files:**
- Modify: `researchclaw/core/refinement.py`
- Modify: `researchclaw/core/handoff.py`
- Modify: `researchclaw/core/models.py`
- Modify: `tests/codex_native/test_refinement.py`
- Modify: `tests/codex_native/test_handoff.py`

**Interfaces:**
- Produces: `finalize_refinement(project, decision_path) -> RefinementSessionStatus`.
- Produces: Stage 14 state with `refinement/final_selection.json` and retained evidence refs.

- [ ] **Step 1: Write failing finalization tests**

```python
@pytest.mark.parametrize("decision", ["select_candidate", "retain_baseline", "inconclusive"])
def test_finalize_preserves_results_and_advances(tmp_path, decision):
    project = deliberated_refinement_project(tmp_path / "project", decision=decision)
    before = all_registered_result_hashes(project)
    status = finalize_refinement(project, write_final_decision(project, decision))
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 14
    assert reopened.state.completed_stages[-1] == 13
    assert all_registered_result_hashes(reopened) == before
    assert status.next_action == "prepare_stage"
```

- [ ] **Step 2: Run RED**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement.py tests/codex_native/test_handoff.py -k 'final or thirteen or fourteen' -q`

- [ ] **Step 3: Implement finalization**

Require a registered council decision selecting existing verified evidence. Persist rationale, votes, dissent, limitations, and Stage 14 questions. Never copy candidate files over the baseline. Mark Stage 13 complete and advance atomically.

- [ ] **Step 4: Replace unsupported Stage 13 handoff**

Map each verified session phase to its refinement action. Remove `report_stage_thirteen_implementation_boundary`. Tampered or unknown session state fails closed rather than falling back to generic `stage prepare`.

- [ ] **Step 5: Verify and commit**

```bash
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement.py tests/codex_native/test_handoff.py tests/codex_native/test_resume.py tests/codex_native/test_stage12_trustworthy_evidence_integration.py -q
git add researchclaw/core/refinement.py researchclaw/core/handoff.py researchclaw/core/models.py tests/codex_native/test_refinement.py tests/codex_native/test_handoff.py
git commit -m "feat(codex): finalize refinement into Stage 14"
```

### Task 7: Deterministic Refinement CLI

**Files:**
- Modify: `researchclaw/codex/cli.py`
- Modify: `tests/codex_native/test_cli.py`

**Interfaces:**
- Produces: `researchclaw-codex refinement <subcommand>` JSON interfaces.

- [ ] **Step 1: Write failing parser and dispatch test**

```python
def test_refinement_prepare_session_cli_is_agent_neutral(tmp_path, capsys):
    project = build_stage_thirteen_project(tmp_path / "project")
    assert main([
        "refinement", "prepare-session", str(project.root),
        "--envelope", "refinement/envelope.json", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["phase"] == "awaiting_independent_assessments"
    assert "model" not in payload and "api_key" not in payload
```

- [ ] **Step 2: Run RED**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_cli.py -k refinement -q`

- [ ] **Step 3: Add deterministic subcommands**

Add `prepare-session`, `register-assessment`, `register-deliberation`, `register-decision`, `register-candidate`, `prepare-self-test`, `register-self-test`, `prepare-run`, `register-result`, `status`, and `finalize`. Registration accepts project-relative paths. Self-test, result, and finalization require confirmation flags. No command accepts model, provider, key, prompt, or arbitrary shell arguments.

- [ ] **Step 4: Add stable error and JSON tests**

Known validation failures return exit code `2`, one `error: <code>` line on stderr, and no partial stdout. Successful payloads use `to_dict()` and sorted JSON keys.

- [ ] **Step 5: Verify and commit**

```bash
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_cli.py tests/codex_native/test_refinement.py tests/codex_native/test_refinement_execution.py -q
git add researchclaw/codex/cli.py tests/codex_native/test_cli.py
git commit -m "feat(codex): expose deterministic refinement CLI"
```

### Task 8: Plugin Orchestration and End-to-End Gate

**Files:**
- Modify: `skills/researchclaw/SKILL.md`
- Create: `skills/researchclaw/references/refinement.md`
- Modify: `skills/researchclaw/references/stages.md`
- Modify: `docs/CODEX_23_STAGE_OVERVIEW_KO.md`
- Modify: `tests/codex_native/test_public_docs.py`
- Modify: `tests/codex_native/test_plugin_package.py`
- Create: `tests/codex_native/test_stage13_multi_agent_e2e.py`

**Interfaces:**
- User entry: one explicit Stage 13 ResearchClaw request.
- Agent protocol: non-voting coordinator, three voters, and a non-voting implementation agent.
- Deterministic interface: Task 7 CLI only.

- [ ] **Step 1: Write failing public contract test**

```python
def test_refinement_workflow_requires_council_and_forbids_llm_api_calls():
    normalized = " ".join(REFINEMENT_REFERENCE.read_text().split()).lower()
    assert "coordinator has no vote" in normalized
    assert "independent assessment" in normalized
    assert "implementation agent must not vote" in normalized
    assert "must not call an llm api" in normalized
    assert "researchclaw-codex refinement" in normalized
```

- [ ] **Step 2: Run RED**

Run: `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_public_docs.py tests/codex_native/test_plugin_package.py -q`

- [ ] **Step 3: Write coordinator protocol and public docs**

Require three independent agent tasks before disclosure, one challenge/revision round, implementation-agent vote exclusion, authoritative argv execution, authority escalation on envelope exhaustion, and dissent reporting. Forbid LLM provider configuration or calls.

- [ ] **Step 4: Write synthetic multi-agent E2E**

Build a tiny Stage 13 project; register three fixture assessments, rebuttals, and a 2-1 refine decision; register and self-test a candidate; run a one-second fixture; register candidate evidence; register a 2-1 selection; finalize.

```python
assert final_project.state.current_stage == 14
assert baseline_after == baseline_before
assert candidate_manifest.startswith(".researchclaw/evidence/refinement-manifests/")
assert final_selection["dissenting_roles"] == ["critical_reproducibility"]
assert no_network_or_llm_client_was_called
```

- [ ] **Step 5: Run release verification**

```bash
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_stage13_multi_agent_e2e.py -q
/opt/homebrew/bin/python3.11 -m pytest tests/codex_native -q
/opt/homebrew/bin/python3.11 -m compileall -q researchclaw
git diff --check
```

- [ ] **Step 6: Verify installed `uv tool` after merged-result gate**

Install from merged `main`, create a temporary synthetic Stage 13 project, and run `researchclaw-codex refinement status` plus one prepare/self-test sequence. Assert the installed launcher is preserved and the fingerprint matches.

- [ ] **Step 7: Commit the release slice**

```bash
git add skills/researchclaw/SKILL.md skills/researchclaw/references/refinement.md skills/researchclaw/references/stages.md docs/CODEX_23_STAGE_OVERVIEW_KO.md tests/codex_native/test_public_docs.py tests/codex_native/test_plugin_package.py tests/codex_native/test_stage13_multi_agent_e2e.py
git commit -m "docs(codex): orchestrate multi-agent Stage 13 refinement"
```

## Final Review Checklist

- [ ] Governance and no-API rule: Tasks 1 and 8.
- [ ] Session/evidence packet and resume: Tasks 2 and 3.
- [ ] Candidate isolation: Task 4.
- [ ] Bounded execution and immutable candidate evidence: Task 5.
- [ ] Final selection and Stage 14 handoff: Task 6.
- [ ] Deterministic CLI: Task 7.
- [ ] One-command plugin orchestration and E2E: Task 8.
- [ ] Types and names used by later tasks match their producing interfaces.
- [ ] Stage 12 baseline remains under the existing single-manifest contract.
- [ ] Candidate evidence uses only the refinement manifest namespace.
- [ ] Implementation starts in a fresh isolated worktree from approved `main`.
