# Stage 15 Research Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register a short, evidence-bound agent deliberation that records PROCEED, REFINE, PIVOT, or unresolved direction without running further research.

**Architecture:** Add a focused research-decision coordinator module and a separate deterministic report renderer. Reuse existing project transactions, safe bounded evidence access and the Stage 14 registration patterns; expose verified historical analysis without widening its write authority. Dedicated CLI registration drives the boundary, while the skill orchestrates real independent agents.

**Tech Stack:** Python 3.11+, existing ResearchProject/ArtifactRef persistence, argparse, pytest; no runtime dependencies or external model APIs added. Use an ephemeral pytest-xdist environment for whole-suite verification.

**Spec:** `docs/superpowers/specs/2026-09-06-stage15-research-decision-design.md` (approved, commit `922840d`).

## Global Constraints

- 연구적 판단은 Codex 에이전트들이 협의하며, 로컬 CLI는 근거 연결·등록 순서·기록 무결성과 상태를 관리한다.
- 외부 LLM API나 별도 모델 프로세스는 추가하지 않는다.
- 이번 구현은 결정과 후속 요청의 등록까지다.
- 14단계의 패킷·보고서·검토·결과는 수정하거나 다시 등록하지 않는다.
- 연구 결정 값은 proceed/refine/pivot이며 협의 미완료는 decision=null과 disposition=unresolved로 표현한다. null을 proceed로 해석하지 않는다.
- 이 버전에서 정식 종합은 한 번만 등록하며 자동 재논의·기록 교체는 없다.
- REFINE/PIVOT/미합의 기록 이후의 재개·재논의 실행을 제공하지 않는다.
- 16단계는 아직 미구현이며 논문 개요를 생성하지 않는다.
- Do not broaden generic `SUPPORTED_STAGE_IDS` (currently 1–11). Preserve immutable packet bytes and historical evidence.
- No main merge, installation, GitHub push or live-project advancement is incidental to implementation; report these separately when requested.

---

## File map and contracts

| File | Responsibility |
|---|---|
| `researchclaw/core/research_decision.py` (new) | Packet verification, record schemas, ordered registration and Stage 15 status |
| `researchclaw/core/decision_report.py` (new) | Deterministic Markdown from validated decision and original records |
| `researchclaw/core/result_analysis.py` | Narrow completed-analysis read API; no new Stage 14 write permissions |
| `researchclaw/codex/cli.py` | Dedicated `decision` commands and stable errors |
| `researchclaw/core/{contracts,handoff,project,task_packets}.py` | Explicit Stage 15/16 routing and generic-bypass prevention |
| `skills/researchclaw/references/research-decision.md` (new) | Actual independent-role protocol, complete schemas and staging paths |
| `skills/researchclaw/{SKILL.md,references/stages.md,references/result-analysis.md}` | Current capability boundaries and historical/current state distinction |
| `README.md` | Replace stale Stage 14 waiting-only statement; describe Stage 15 decision-only scope |
| `tests/codex_native/test_research_decision.py` (new) | Lifecycle, safety, recovery and real CLI tests |
| `tests/codex_native/{test_result_analysis,test_handoff,test_contracts}.py` | Historical verification and boundary regressions |

Public functions in `research_decision.py` return `dict[str, object]`:

```python
def prepare_research_decision(project: ResearchProject) -> dict[str, object]: ...
def research_decision_status(project: ResearchProject) -> dict[str, object]: ...
def register_decision_review(project: ResearchProject, submission_path: str | Path) -> dict[str, object]: ...
def register_decision_rebuttals(project: ResearchProject, submission_path: str | Path) -> dict[str, object]: ...
def register_decision_result(project: ResearchProject, submission_path: str | Path) -> dict[str, object]: ...
```

These ellipses denote signatures, not implementation steps. Concrete algorithm and test steps follow.

### Durable paths and statuses

```python
DECISION_PACKET_PATH = "analysis/research-decision/evidence_packet.json"
DECISION_REBUTTALS_PATH = "analysis/research-decision/rebuttals.json"
DECISION_RESULT_PATH = "analysis/decision.json"
DECISION_REPORT_PATH = "analysis/decision.md"
ROLES = ("domain", "methodology", "critical_reproducibility")
# reviews/{role}.json and submissions/{role}.json live under analysis/research-decision/.
# The two other submissions are submissions/rebuttals.json and submissions/result.json.
```

| Condition | phase | next_action | current_stage | Completed Stage 15 |
|---|---|---|---:|---|
| No decision packet | awaiting_preparation | prepare_research_decision | 15 | no |
| Fewer than three reviews | awaiting_independent_recommendations | register_decision_review | 15 | no |
| Three reviews | awaiting_rebuttals | register_decision_rebuttals | 15 | no |
| Responses registered | awaiting_decision | register_decision_result | 15 | no |
| proceed | complete | unsupported_stage_16 | 16 | yes |
| refine/pivot | follow_up_required | report_research_follow_up | 15 | no |
| null/unresolved | needs_direction | request_research_direction | 15 | no |

Terminal status is read-only. No command executes the requested follow-up. Non-PROCEED status preserves `completed_stages` unchanged, while exposing that a decision/report has been registered. The main `status`/`resume` must never show a loop back to an already-registered submission.

### Record schemas (closed top-level keys, schema_version=1)

Every submission has `schema_version`, `project_id`, `evidence_packet_sha256`, `producer`. A cited statement is `{ "text": nonempty_string, "evidence_refs": nonempty_unique_list_of_packet_input_paths }`. Text arrays may be empty only where stated below; reject booleans as integers and non-finite JSON numbers, and reuse the current bounded JSON reader limit.

- **Review:** common fields plus `role`, `recommendation` (proceed/refine/pivot), `rationale` (nonempty cited statements), `claim_scope` (nonempty cited statements), `mandatory_follow_up` (cited statements, empty allowed), `optional_follow_up` (cited statements, empty allowed), `alternatives` (nonempty cited statements), `questions` (strings, empty allowed). Review producers are distinct. Recommendations of refine/pivot require at least one mandatory follow-up; no metric threshold controls any recommendation.
- **Rebuttals:** common fields plus `review_hashes` (exact role→registered digest map), `responses` (exactly three). Each response has `role`, the original `producer`, `review_sha256`, `challenges` (nonempty strings), `responses` (nonempty cited statements), `final_recommendation` (proceed/refine/pivot/null). The coordinator producer differs from all reviewers. This is one round of actual role responses, not new coordinator-authored votes.
- **Result:** common fields plus `review_hashes`, `rebuttals_sha256`, `decision`, `disposition` (agreed/unresolved), `rationale`, `claim_scope`, `limitations`, `mandatory_follow_up`, `optional_follow_up`, `unresolved_issues` (all cited statement arrays; rationale/scope/limitations nonempty), `disagreements` (array of `{role,text,evidence_refs}`), `recommended_stage` (13 for refine, 8 for pivot, null for proceed/unresolved). Result producer must match the rebuttal coordinator.
- For a non-null result, require `disposition=agreed` and verify it does not contradict any role's recorded final recommendation. This checks claimed consent; never compute or fill in the decision by majority, score or retry count. Null requires `disposition=unresolved`, null target and nonempty `unresolved_issues`; it is always a stop, never a fallback PROCEED. Refine/pivot require mandatory follow-up. Proceed may have mandatory writing/disclosure tasks, but no auto-execution authority.
- Agent rationale differences remain in original reviews/responses even when the direction agrees. Do not attempt to algorithmically extract semantic disagreement or prove scientific adequacy. The report includes the original records as well as the coordinator's summary.

## Task 1: Verified Stage 14 history and decision packet

**Files:** Create `researchclaw/core/research_decision.py`, `tests/codex_native/test_research_decision.py`; modify `result_analysis.py`, `cli.py`, and `test_result_analysis.py` at their functions listed below.

**Interfaces:**
- Consumes existing `ResearchProject.open_readonly`, `ArtifactRef`, `resolve_project_artifact`, `project_mutation`, and refinement `_canonical_json`, `_secure_snapshot`, `_read_bounded_json`, `_write_exclusive`.
- Produces `validate_completed_analysis(project: ResearchProject) -> dict[str, object]` in `result_analysis.py`: `{ "evidence_packet": verified_packet, "references": list_of_ArtifactRef_dicts }`. References cover the packet, result, report, three reviews and rebuttals. Validation covers all their contents and all transitive registered packet inputs.
- Produces `prepare_research_decision` and `research_decision_status` signatures above. Packet schema: version, project_id, stage_id=15, inputs `{analysis_records: references, research_evidence: stage14_packet["inputs"]}`, roles, allowed_outputs, execution_allowed=false. Do not embed a mutable lifecycle phase in packet bytes.

- [ ] **1. Add a complete Stage 14 fixture and RED preparation test.** Reuse existing test helpers; do not manually forge project state for successful preparation.

```python
from researchclaw.core import result_analysis, research_decision
from researchclaw.core.project import ResearchProject
from tests.codex_native.test_result_analysis import (
    _finalized_project, _register_analysis_reviews,
    _register_analysis_rebuttals, _valid_analysis_result,
    _write_analysis_submission,
)

def analyzed_project(path):
    project = _finalized_project(path)
    result_analysis.prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    result_analysis.register_analysis_result(
        project, _write_analysis_submission(project, "result.json", _valid_analysis_result(project))
    )
    return ResearchProject.open_readonly(project.root)

def test_decision_prepare_preserves_analysis_and_replays_exactly(tmp_path):
    project = analyzed_project(tmp_path / "project")
    report = project.root / "analysis/report.md"
    before = report.read_bytes()
    packet = research_decision.prepare_research_decision(project)
    assert packet["stage_id"] == 15
    assert packet["execution_allowed"] is False
    state = (project.root / ".researchclaw/state.json").read_bytes()
    assert research_decision.prepare_research_decision(project) == packet
    assert (project.root / ".researchclaw/state.json").read_bytes() == state
    assert report.read_bytes() == before
```

Run `/opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_research_decision.py -q`; observe the missing import/function failure before implementation.

- [ ] **2. Implement historical verification and canonical preparation.** Factor the existing completed-record verification out of `_analysis_registration_status` without changing Stage 14 packet construction or report rendering. `_selection` currently admits only stages 14/15: allow historical reads at current_stage>=15 with completed Stage 14, while every Stage 14 mutator still requires current_stage=14 for new publication. Later-stage exact retries may verify already-completed records but never create missing ones. No fake `replace(state,current_stage=14)` workaround.

Use this order for the new preparation implementation (local names below are scoped to this function):

```python
current = ResearchProject.open_readonly(project.root)
if current.state.current_stage != 15 or 14 not in current.state.completed_stages:
    raise ValueError("decision_stage_invalid")
history = validate_completed_analysis(current)
# Build the closed packet defined above from history and the literal paths/roles.
# Canonical JSON and ArtifactRef bind its exact bytes.
destination = resolve_project_artifact(current.root, DECISION_PACKET_PATH)
# Publish exclusively; an existing file must byte-match to qualify as exact replay.
# Revalidate history after publication, then register only the packet artifact.
# persist_state(replace(current.state, artifacts={**current.state.artifacts, path: ref}))
```

The implementation must fill these local operations directly using the existing helpers; it must not introduce a generic storage framework. Preflight Stage 14 integrity and safe destination before writing. Stage 16 may only replay/verify an existing complete decision, not prepare a new one. Terminal non-PROCEED preparation must not reset records or the lifecycle.

- [ ] **3. Add named safety cases and run the full affected file.** Add parametrized corruption cases for every Stage 14 record class and retained input; reject unregistered analysis, wrong stage, changed packet, conflicting file and symlinked output parent without outside writes or state changes. Test missing packet status is read-only. In `test_result_analysis.py`, add historical-read success after a real Task 2 PROCEED when available; until Task 2, test the historical helper directly against a completed analysis and rejection of incomplete records. Do not mark a future-stage transition test passed before the real registration exists.

```python
def test_decision_prepare_rejects_output_symlink(tmp_path):
    project = analyzed_project(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.root / "analysis/research-decision").symlink_to(outside, target_is_directory=True)
    before = (project.root / ".researchclaw/state.json").read_bytes()
    with pytest.raises(ValueError):
        research_decision.prepare_research_decision(project)
    assert not list(outside.iterdir())
    assert (project.root / ".researchclaw/state.json").read_bytes() == before
```

Add the `pytest` import. Run both `test_research_decision.py` and `test_result_analysis.py`, not just the newly selected node.

- [ ] **4. Wire `decision prepare ROOT --json` and `decision status ROOT --json` to these functions.** Match the existing analysis argparse and error mapping, using `decision_command` as dest. Add a public `run_cli` test (it returns an integer, JSON comes through `capsys`). Confirm the help and output are not describing an experiment runner.

```python
assert run_cli(["decision", "prepare", str(project.root), "--json"]) == 0
assert json.loads(capsys.readouterr().out)["stage_id"] == 15
```

- [ ] **5. Verify and commit.** Run the affected files, Ruff on changed Python files and `git diff --check`. Commit `feat: prepare stage 15 decision evidence`. Report exact commands, results and unresolved findings for task review.

## Task 2: Ordered deliberation, deterministic report and safe terminal results

**Files:** Extend `researchclaw/core/research_decision.py`, `researchclaw/codex/cli.py`, `tests/codex_native/test_research_decision.py`; create `researchclaw/core/decision_report.py`.

**Interfaces:**
- Consumes Task 1's preparation, historical verifier and packet paths/schema.
- Produces the three public registration functions from the file map.
- Produces `render_decision_report(payload: Mapping[str, object]) -> str`; payload contains the validated result, packet, original role records and responses. It does not read files, mutate state or create a research judgment.

- [ ] **1. Add executable fixture writers using the complete record schema.** Define `write_decision_submission(project,name,payload) -> Path`, `decision_base(project,producer) -> dict`, and `review_payload(project,role,recommendation) -> dict` in the new test file. `decision_base` reads the registered packet digest directly from state; it must not call whole decision status while testing orphan recovery. All citations in fixtures use the actual registered `analysis/results.json` input. This is an illustrative core fixture, expanded with the fields specified in the schema above:

```python
def decision_base(project, producer):
    state = ResearchProject.open_readonly(project.root).state
    return dict(schema_version=1, project_id=state.project_id, producer=producer,
                evidence_packet_sha256=state.artifacts[research_decision.DECISION_PACKET_PATH].sha256)

def write_decision_submission(project, name, payload):
    path = project.root / "analysis/research-decision/submissions" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path

def review_payload(project, role, recommendation):
    statement = {"text": "Synthetic engineering evidence only.",
                 "evidence_refs": ["analysis/results.json"]}
    return {**decision_base(project, f"decision-{role}"), "role": role,
            "recommendation": recommendation, "rationale": [statement],
            "claim_scope": [statement], "mandatory_follow_up": [statement],
            "optional_follow_up": [], "alternatives": [statement], "questions": []}
```

Add `register_decision_roles(project,recommendations)` using three real registration calls. Add `rebuttal_payload(project,final_recommendations)` using registered role hashes/producers and one response per role. Add `result_payload(project,decision)` using the same coordinator, registered rebuttal digest and all required schema fields; `disposition` is unresolved only for null, target is the literal mapping below. These helpers generate test records, not purported independent agents.

- [ ] **2. RED-test all terminal outcomes and lack of research execution.** Implement `complete_decision(project,decision)` in tests to prepare, register three independent fixture reviews, register responses, then register result. For null, responses must include differing directions and a cited unresolved issue. Baseline permissions/budgets and all previous artifact bytes must match after registration.

```python
@pytest.mark.parametrize("decision,phase,stage,target", [
    ("proceed", "complete", 16, None),
    ("refine", "follow_up_required", 15, 13),
    ("pivot", "follow_up_required", 15, 8),
    (None, "needs_direction", 15, None),
])
def test_decision_outcomes_do_not_execute_follow_up(tmp_path, decision, phase, stage, target):
    project = analyzed_project(tmp_path / "project")
    prior = {p: (project.root / p).read_bytes() for p in project.state.artifacts}
    status = complete_decision(project, decision)
    current = ResearchProject.open_readonly(project.root)
    assert status["phase"] == phase
    assert current.state.current_stage == stage
    assert (15 in current.state.completed_stages) is (decision == "proceed")
    record = json.loads((project.root / "analysis/decision.json").read_text())
    assert record["recommended_stage"] == target
    assert all((project.root / p).read_bytes() == raw for p, raw in prior.items())
    assert not (project.root / "paper/outline.md").exists()
```

Run these tests RED before adding registrations. Also ensure mock/spies at existing execution entrypoints fail if called, without asserting merely that a mock exists; compare durable run/evidence/approval inventory before and after.

- [ ] **3. Implement record parsing and registration.** Validate closed schemas, role set, unique producers, exact packet/review/rebuttal digests, packet-input citations, coordinator identity and order. Use Stage 14's per-record orphan handling pattern, not permissive whole-status loading while an orphan is expected. For late registration after terminal result allow exact retries only. Test false claimed consensus is rejected instead of accepting the coordinator as a single deciding authority.

The state transition is a literal application of an already-authored valid outcome:

```python
if record["decision"] == "proceed":
    updated = replace(state, current_stage=16,
                      completed_stages=(*state.completed_stages, 15),
                      status=StageStatus.READY, next_action="unsupported_stage_16",
                      artifacts=registered_artifacts, last_error=None)
else:
    action = "request_research_direction" if record["decision"] is None else "report_research_follow_up"
    updated = replace(state, status=StageStatus.READY, next_action=action,
                      artifacts=registered_artifacts, last_error=None)
```

`state` is freshly opened verified Stage 15 state; `registered_artifacts` is its artifact map plus result/report references after successful safe publication and revalidation. Exact retries do not append Stage 15 twice or save state again. No rollback function is called and no budget fields change.

- [ ] **4. Implement report generation and recovery tests.** Render direction, scope, rationale, mandatory/optional follow-up, unresolved issues, original recommendations and all actual responses. Use project-relative links adjusted from `analysis/decision.md`; do not emit links to the same packet as a substitute for source citations. Render Stage 14 scope/limitations and source context separately so coordinator summaries cannot erase them.

```python
report = (project.root / "analysis/decision.md").read_text()
assert "Synthetic engineering evidence only." in report
assert "independent" in report.lower()  # heading describing the preserved role record
for role in research_decision.ROLES:
    assert f"decision-{role}" in report
```

Keep content-preservation assertions on deliberately authored sentinel text, not source-code strings. Inject a single `persist_state` failure after each review, rebuttal and result/report publication. Verify status rejects unregistered partial records; identical retry adopts valid bytes; conflicting retry rejects without replacing them; incomplete report publication never advances state. Prepare conflict fixture payloads before injecting the interruption. Add invalid paths, tampered historical inputs, duplicate producer, early rebuttal/result, result/response direction mismatch, and deterministic report-tamper cases. Run the complete new test file after all fixture edits.

- [ ] **5. Expose register-review/register-rebuttals/register-result with `--submission PATH --json`.** Public CLI tests exercise all five decision commands and exact retries, including errors with nonzero exits. Run Stage 14 and Stage 15 test files plus Ruff/diff-check. Commit `feat: register agent research decisions`; provide reviewer the outcome and recovery coverage, not just a test count.

## Task 3: Handoff, agent instructions and acceptance

**Files:** Modify `researchclaw/core/{contracts,handoff,project,task_packets,result_analysis}.py`, `skills/researchclaw/SKILL.md`, `skills/researchclaw/references/{stages,result-analysis}.md`, `README.md`; create `skills/researchclaw/references/research-decision.md`; extend `test_research_decision.py`, `test_handoff.py`, `test_contracts.py`, `test_result_analysis.py`.

**Interfaces:**
- Consumes Task 2 `research_decision_status` and the terminal table above.
- Produces `status`/`resume` commands that route only to explicit Stage 15 commands or read-only terminal checks. Stage 16 reports `unsupported_stage_16`; `analysis status` reports completed analysis without suggesting it is a fresh Stage 14 task.

- [ ] **1. RED-test routing using genuine registered outcomes.** Use `run_cli` + `capsys`; check the four terminal cases and every intermediate registration phase. `analysis status` after PROCEED must still verify the complete Stage 14 evidence and detect tampering. Generic stage preparation/validation must reject both Stage 15 and Stage 16.

```python
project = analyzed_project(tmp_path / "project")
assert run_cli(["resume", str(project.root), "--json"]) == 0
assert json.loads(capsys.readouterr().out)["next_action"] == "prepare_research_decision"
complete_decision(project, "proceed")
assert run_cli(["resume", str(project.root), "--json"]) == 0
assert json.loads(capsys.readouterr().out)["next_action"] == "unsupported_stage_16"
assert result_analysis.analysis_status(ResearchProject.open_readonly(project.root))["phase"] == "complete"
```

Wrap this code in a test function importing the Task 2 test helpers. Add assertions that both status/resume leave all bytes unchanged in terminal cases and return `approval_eligible=false`; do not run a placeholder submission string returned by an intermediate handoff.

- [ ] **2. Implement boundary integration.** Extend the special post-execution boundaries in `handoff.py` and `project.py` to Stage 16; avoid generic execution readiness or completed-milestone fallthrough. Use a phase→command mapping for intermediate Stage 15, and `decision status` for its terminals and Stage 16. Add `analysis/decision.md` to Stage 15 required outputs. Preserve generic support range 1–11. Keep `analysis status` scoped to historical analysis: completed state returns `next_action=analysis_complete`, while root status/resume owns the current decision next action. Do not call decision_status from completed-analysis validation, avoiding circular recursion.

- [ ] **3. Write the consuming skill reference and update advertised boundaries.** Include every schema above and working input-path examples; never cite an unlisted packet path as evidence. Permit exactly the five submission files. Require independent Stage 15 recommendations before disclosure, one actual response round, a distinct non-voting coordinator, no forced expected outcome, and cited distinctions between required and optional follow-up. Null/no agreement stops. Explain that REFINE/PIVOT registration is not rollback authority, that no re-opening is supplied in this milestone, and that archived Stage 14 wording does not dictate current state. Do not activate this workflow from an unrelated research request.

- [ ] **4. Run source verification, then actual-agent acceptance on a disposable copy.** Run all affected tests, skill validator, Ruff and diff-check. Start one source acceptance from a fresh copy of `/Users/jspark/Downloads/researchclaw-stage14-user-test-20260906`, preserving the original. Use exactly three real Codex role assignments plus coordinator; record initial recommendations before disclosure and actual responses, with no new data/experiment/model API. Any of the valid terminal outcomes is acceptable if honestly supported. Verify original bytes, prior evidence, report/result binding and correct stop. A synthetic fixture does not certify real research judgment quality.

```bash
uv run --no-project --python /opt/homebrew/bin/python3.11 --with '.[dev]' --with pytest-xdist python -m pytest -q -n 4 tests/codex_native/test_research_decision.py tests/codex_native/test_result_analysis.py tests/codex_native/test_handoff.py tests/codex_native/test_contracts.py tests/codex_native/test_stage13_multi_agent_e2e.py
/opt/homebrew/bin/python3.11 /Users/jspark/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/researchclaw
git diff --check
```

- [ ] **5. Complete reviews and integration readiness.** Commit `feat: integrate stage 15 decision handoff`. Require task review and final feature review per the chosen execution skill; fix concrete findings in bounded passes. Before merge/deployment run the whole suite, not just selected nodes:

```bash
uv run --no-project --python /opt/homebrew/bin/python3.11 --with '.[dev]' --with pytest-xdist python -m pytest -q -n 4 --dist worksteal --maxfail=1
```

Report skipped tests and warnings separately. A serial full-suite run previously cost 30 minutes before a failure; the verified four-worker run completed in about 11 minutes on this host, not a promised duration for new work. Do not let a package cache or installed older skill stand in for source verification. Installation and GitHub publishing need the user's separate request; after installation compare actual module/skill bytes and run installed CLI from outside the repository.

## Self-review coverage

- Evidence binding, historical access and path safety: Task 1.
- Three-role direction records, consent consistency, terminal cases and publication recovery: Task 2.
- No automatic decision/execution/rollback, generic bypass, readable provenance, skill and real-role acceptance: Tasks 2–3.
- Later-stage historical validation and current handoff authority: Tasks 1 and 3.
- Deferred real-research quality evaluation: retained in scope and acceptance notes, not represented as completed.
- No runtime code has been changed by writing this plan. Execute in an isolated worktree; keep each review boundary to the three tasks above.
