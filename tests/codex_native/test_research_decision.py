import hashlib
import json
import shlex
from dataclasses import replace

import pytest

from researchclaw.codex.cli import main as run_cli
from researchclaw.core import research_decision, result_analysis
from researchclaw.core.project import ResearchProject
from tests.codex_native.test_result_analysis import (
    _finalized_project,
    _register_analysis_rebuttals,
    _register_analysis_reviews,
    _valid_analysis_result,
    _write_analysis_submission,
)


def analyzed_project(path):
    project = _finalized_project(path)
    result_analysis.prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    result_analysis.register_analysis_result(
        project,
        _write_analysis_submission(
            project, "result.json", _valid_analysis_result(project)
        ),
    )
    return ResearchProject.open_readonly(project.root)


def write_decision_submission(project, name, payload):
    path = project.root / "analysis/research-decision/submissions" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def decision_base(project, producer):
    state = ResearchProject.open_readonly(project.root).state
    return {
        "schema_version": 1,
        "project_id": state.project_id,
        "producer": producer,
        "evidence_packet_sha256": state.artifacts[
            research_decision.DECISION_PACKET_PATH
        ].sha256,
    }


def _decision_statement(text="Synthetic engineering evidence only."):
    return {"text": text, "evidence_refs": ["analysis/results.json"]}


def review_payload(project, role, recommendation):
    statement = _decision_statement()
    mandatory = [statement] if recommendation in {"refine", "pivot"} else []
    return {
        **decision_base(project, f"decision-{role}"),
        "role": role,
        "recommendation": recommendation,
        "rationale": [statement],
        "claim_scope": [statement],
        "mandatory_follow_up": mandatory,
        "optional_follow_up": [],
        "alternatives": [statement],
        "questions": [],
    }


def register_decision_roles(project, recommendations):
    status = None
    for role in research_decision.ROLES:
        submission = write_decision_submission(
            project,
            f"{role}.json",
            review_payload(project, role, recommendations[role]),
        )
        status = research_decision.register_decision_review(project, submission)
    return status


def rebuttal_payload(project, final_recommendations):
    current = ResearchProject.open_readonly(project.root)
    review_hashes = {
        role: current.state.artifacts[
            f"analysis/research-decision/reviews/{role}.json"
        ].sha256
        for role in research_decision.ROLES
    }
    return {
        **decision_base(project, "decision-coordinator"),
        "review_hashes": review_hashes,
        "responses": [
            {
                "role": role,
                "producer": f"decision-{role}",
                "review_sha256": review_hashes[role],
                "challenges": [f"Challenge recorded for {role}."],
                "responses": [
                    _decision_statement(
                        "Unresolved issue remains in the cited analysis."
                        if len(set(final_recommendations.values())) > 1
                        else f"{role} preserves its evidence-bound direction."
                    )
                ],
                "final_recommendation": final_recommendations[role],
            }
            for role in research_decision.ROLES
        ],
    }


def result_payload(project, decision):
    current = ResearchProject.open_readonly(project.root)
    review_hashes = {
        role: current.state.artifacts[
            f"analysis/research-decision/reviews/{role}.json"
        ].sha256
        for role in research_decision.ROLES
    }
    statement = _decision_statement()
    unresolved = (
        [_decision_statement("The role responses preserve incompatible directions.")]
        if decision is None
        else []
    )
    return {
        **decision_base(project, "decision-coordinator"),
        "review_hashes": review_hashes,
        "rebuttals_sha256": current.state.artifacts[
            research_decision.DECISION_REBUTTALS_PATH
        ].sha256,
        "decision": decision,
        "disposition": "unresolved" if decision is None else "agreed",
        "rationale": [statement],
        "claim_scope": [statement],
        "limitations": [statement],
        "mandatory_follow_up": [statement] if decision in {"refine", "pivot"} else [],
        "optional_follow_up": [],
        "unresolved_issues": unresolved,
        "disagreements": (
            [
                {
                    "role": "methodology",
                    "text": "The recorded directions remain unresolved.",
                    "evidence_refs": ["analysis/results.json"],
                }
            ]
            if decision is None
            else []
        ),
        "recommended_stage": {"proceed": None, "refine": 13, "pivot": 8}.get(decision),
    }


def complete_decision(project, decision):
    research_decision.prepare_research_decision(project)
    if decision is None:
        directions = dict(
            zip(research_decision.ROLES, ("proceed", "refine", "pivot"), strict=True)
        )
    else:
        directions = {role: decision for role in research_decision.ROLES}
    register_decision_roles(project, directions)
    rebuttals = write_decision_submission(
        project, "rebuttals.json", rebuttal_payload(project, directions)
    )
    research_decision.register_decision_rebuttals(project, rebuttals)
    result = write_decision_submission(
        project, "result.json", result_payload(project, decision)
    )
    return research_decision.register_decision_result(project, result)


def _protected_inventory(project):
    return {
        path: (project.root / path).read_bytes()
        for path in project.state.artifacts
        if not path.startswith("analysis/research-decision/")
        and path
        not in {
            research_decision.DECISION_RESULT_PATH,
            research_decision.DECISION_REPORT_PATH,
        }
    }


def _file_bytes(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _assert_root_route(project, capsys, next_action, command, *, unchanged=False):
    for operation in ("status", "resume"):
        before = _file_bytes(project.root)
        assert run_cli([operation, str(project.root), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["next_action"] == next_action
        assert payload["approval_eligible"] is False
        expected = [
            "researchclaw-codex",
            "decision",
            command[0],
        ]
        expected.extend(
            [str(project.root.resolve()), *command[1:], "--json"]
        )
        assert shlex.split(payload["next_command"]) == expected
        if unchanged:
            assert _file_bytes(project.root) == before


def test_root_status_and_resume_route_every_stage_fifteen_phase(tmp_path, capsys):
    project = analyzed_project(tmp_path / "project")
    _assert_root_route(
        project, capsys, "prepare_research_decision", ["prepare"]
    )

    research_decision.prepare_research_decision(project)
    _assert_root_route(
        project,
        capsys,
        "register_decision_review",
        ["register-review", "--submission", "<PROJECT_RELATIVE_SUBMISSION_PATH>"],
    )

    directions = {role: "proceed" for role in research_decision.ROLES}
    register_decision_roles(project, directions)
    _assert_root_route(
        project,
        capsys,
        "register_decision_rebuttals",
        [
            "register-rebuttals",
            "--submission",
            "<PROJECT_RELATIVE_SUBMISSION_PATH>",
        ],
    )

    research_decision.register_decision_rebuttals(
        project,
        write_decision_submission(
            project, "rebuttals.json", rebuttal_payload(project, directions)
        ),
    )
    _assert_root_route(
        project,
        capsys,
        "register_decision_result",
        ["register-result", "--submission", "<PROJECT_RELATIVE_SUBMISSION_PATH>"],
    )


@pytest.mark.parametrize(
    "decision,next_action",
    [
        ("proceed", "unsupported_stage_16"),
        ("refine", "report_research_follow_up"),
        ("pivot", "report_research_follow_up"),
        (None, "request_research_direction"),
    ],
)
def test_root_status_and_resume_terminal_decisions_are_read_only(
    tmp_path, capsys, decision, next_action
):
    project = analyzed_project(tmp_path / "project")
    complete_decision(project, decision)

    _assert_root_route(project, capsys, next_action, ["status"], unchanged=True)


@pytest.mark.parametrize("decision", ["refine", "proceed"])
@pytest.mark.parametrize("operation", ["prepare", "validate"])
def test_generic_stage_commands_reject_stages_fifteen_and_sixteen(
    tmp_path, capsys, decision, operation
):
    project = analyzed_project(tmp_path / "project")
    complete_decision(project, decision)
    before = _file_bytes(project.root)

    assert run_cli(["stage", operation, str(project.root), "--json"]) == 2
    error = capsys.readouterr().err

    assert f"Stage {ResearchProject.open_readonly(project.root).state.current_stage}" in error
    assert _file_bytes(project.root) == before


@pytest.mark.parametrize(
    "decision,phase,stage,target",
    [
        ("proceed", "complete", 16, None),
        ("refine", "follow_up_required", 15, 13),
        ("pivot", "follow_up_required", 15, 8),
        (None, "needs_direction", 15, None),
    ],
)
def test_decision_outcomes_do_not_execute_follow_up(
    tmp_path, monkeypatch, decision, phase, stage, target
):
    project = analyzed_project(tmp_path / "project")
    prior = _protected_inventory(project)
    initial_state = project.state

    def unexpected_execution(*args, **kwargs):
        raise AssertionError("decision registration must not execute research")

    monkeypatch.setattr(
        "researchclaw.core.research_execution.prepare_research_execution",
        unexpected_execution,
    )
    monkeypatch.setattr(
        "researchclaw.core.development_execution.run_development_experiment",
        unexpected_execution,
    )
    monkeypatch.setattr(
        "researchclaw.core.refinement_execution.prepare_refinement_run",
        unexpected_execution,
    )

    status = complete_decision(project, decision)

    current = ResearchProject.open_readonly(project.root)
    assert status["phase"] == phase
    assert current.state.current_stage == stage
    assert (15 in current.state.completed_stages) is (decision == "proceed")
    record = json.loads(
        (project.root / research_decision.DECISION_RESULT_PATH).read_text()
    )
    assert record["recommended_stage"] == target
    assert _protected_inventory(current) == prior
    assert current.state.execution_policy == initial_state.execution_policy
    assert current.state.retry_counts == initial_state.retry_counts
    assert current.state.stage_10_snapshot == initial_state.stage_10_snapshot
    assert not (project.root / "paper/outline.md").exists()


def test_decision_registration_advances_only_through_ordered_records(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)

    assert research_decision.research_decision_status(project)["phase"] == (
        "awaiting_independent_recommendations"
    )
    for index, role in enumerate(research_decision.ROLES, start=1):
        status = research_decision.register_decision_review(
            project,
            write_decision_submission(
                project, f"{role}.json", review_payload(project, role, "proceed")
            ),
        )
        assert len(status["registered_roles"]) == index
    assert status["phase"] == "awaiting_rebuttals"

    rebuttals = write_decision_submission(
        project,
        "rebuttals.json",
        rebuttal_payload(
            project, {role: "proceed" for role in research_decision.ROLES}
        ),
    )
    status = research_decision.register_decision_rebuttals(project, rebuttals)
    assert status["phase"] == "awaiting_decision"
    assert status["next_action"] == "register_decision_result"


def test_decision_review_schema_binding_and_unique_producers_are_enforced(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    domain = write_decision_submission(
        project, "domain.json", review_payload(project, "domain", "proceed")
    )
    research_decision.register_decision_review(project, domain)

    duplicate = review_payload(project, "methodology", "proceed")
    duplicate["producer"] = "decision-domain"
    with pytest.raises(ValueError, match="decision_producer_duplicate"):
        research_decision.register_decision_review(
            project,
            write_decision_submission(project, "duplicate.json", duplicate),
        )

    bad_reference = review_payload(project, "methodology", "proceed")
    bad_reference["rationale"][0]["evidence_refs"] = ["paper/outline.md"]
    with pytest.raises(ValueError, match="decision_evidence_reference_invalid"):
        research_decision.register_decision_review(
            project,
            write_decision_submission(project, "bad-reference.json", bad_reference),
        )

    extra_field = review_payload(project, "methodology", "proceed")
    extra_field["score"] = 1
    with pytest.raises(ValueError, match="decision_submission_schema_invalid"):
        research_decision.register_decision_review(
            project,
            write_decision_submission(project, "extra-field.json", extra_field),
        )

    missing_follow_up = review_payload(project, "methodology", "refine")
    missing_follow_up["mandatory_follow_up"] = []
    with pytest.raises(ValueError, match="decision_review_schema_invalid"):
        research_decision.register_decision_review(
            project,
            write_decision_submission(
                project, "missing-follow-up.json", missing_follow_up
            ),
        )


def test_decision_records_are_published_as_canonical_json(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    payload = review_payload(project, "domain", "proceed")
    status = research_decision.register_decision_review(
        project, write_decision_submission(project, "domain.json", payload)
    )

    raw = (project.root / "analysis/research-decision/reviews/domain.json").read_bytes()
    assert (
        raw
        == json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )
    assert status["review_hashes"]["domain"] == hashlib.sha256(raw).hexdigest()


def test_decision_registration_rejects_changed_historical_input(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    (project.root / "analysis/results.json").write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError):
        research_decision.register_decision_review(
            project,
            write_decision_submission(
                project, "domain.json", review_payload(project, "domain", "proceed")
            ),
        )
    assert not (
        project.root / "analysis/research-decision/reviews/domain.json"
    ).exists()


def test_decision_registration_rejects_symlink_submission(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(review_payload(project, "domain", "proceed")), encoding="utf-8"
    )
    link = project.root / "analysis/research-decision/submissions/domain-link.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)

    with pytest.raises(ValueError, match="decision_submission_invalid"):
        research_decision.register_decision_review(project, link)
    assert not (
        project.root / "analysis/research-decision/reviews/domain.json"
    ).exists()


def test_decision_rejects_early_rounds_and_false_claimed_consensus(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    fake_rebuttals = {
        **decision_base(project, "decision-coordinator"),
        "review_hashes": {},
        "responses": [],
    }
    with pytest.raises(ValueError, match="decision_order_invalid"):
        research_decision.register_decision_rebuttals(
            project,
            write_decision_submission(project, "early-rebuttals.json", fake_rebuttals),
        )

    directions = dict(
        zip(research_decision.ROLES, ("proceed", "refine", "pivot"), strict=True)
    )
    register_decision_roles(project, directions)
    same_coordinator = rebuttal_payload(project, directions)
    same_coordinator["producer"] = "decision-domain"
    with pytest.raises(ValueError, match="decision_coordinator_producer_invalid"):
        research_decision.register_decision_rebuttals(
            project,
            write_decision_submission(
                project, "same-coordinator.json", same_coordinator
            ),
        )

    rebuttals = write_decision_submission(
        project, "rebuttals.json", rebuttal_payload(project, directions)
    )
    research_decision.register_decision_rebuttals(project, rebuttals)
    claimed_consensus = result_payload(project, "proceed")
    with pytest.raises(ValueError, match="decision_consent_invalid"):
        research_decision.register_decision_result(
            project,
            write_decision_submission(
                project, "false-consensus.json", claimed_consensus
            ),
        )
    assert not (project.root / research_decision.DECISION_RESULT_PATH).exists()


def test_decision_result_rejects_response_direction_and_target_mismatches(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    directions = {role: "proceed" for role in research_decision.ROLES}
    register_decision_roles(project, directions)
    research_decision.register_decision_rebuttals(
        project,
        write_decision_submission(
            project, "rebuttals.json", rebuttal_payload(project, directions)
        ),
    )

    mismatched = result_payload(project, "refine")
    with pytest.raises(ValueError, match="decision_consent_invalid"):
        research_decision.register_decision_result(
            project,
            write_decision_submission(project, "mismatched.json", mismatched),
        )
    bad_target = result_payload(project, "proceed")
    bad_target["recommended_stage"] = 13
    with pytest.raises(ValueError, match="decision_result_schema_invalid"):
        research_decision.register_decision_result(
            project,
            write_decision_submission(project, "bad-target.json", bad_target),
        )


def test_decision_report_preserves_original_records_and_stage_14_context(tmp_path):
    project = analyzed_project(tmp_path / "project")
    complete_decision(project, "proceed")

    report = (project.root / research_decision.DECISION_REPORT_PATH).read_text()
    assert "Synthetic engineering evidence only." in report
    assert "independent" in report.lower()
    for role in research_decision.ROLES:
        assert f"decision-{role}" in report
        assert f"{role} preserves its evidence-bound direction." in report
    assert "Evidence comes from a noiseless synthetic line fixture only." in report
    assert "Noise robustness was not measured" in report
    assert "Preserved Stage 14 scope and limitations" in report
    assert "Preserved source context" in report
    assert "The registered evidence supports this bounded conclusion." in report
    assert "Supporting roles: `domain`, `methodology`" in report
    assert "domain-agent" in report
    assert "Final position after rebuttal." in report
    assert "The result remains limited to the registered inputs." in report
    assert "Does the conclusion survive sensitivity analysis?" in report
    assert "[analysis/results.json](<results.json>)" in report


@pytest.mark.parametrize("decision", ["proceed", "refine", "pivot", None])
def test_terminal_decision_replays_are_exact_and_do_not_reset(tmp_path, decision):
    project = analyzed_project(tmp_path / "project")
    complete_decision(project, decision)
    before = (project.root / ".researchclaw/state.json").read_bytes()

    research_decision.prepare_research_decision(project)
    for role in research_decision.ROLES:
        research_decision.register_decision_review(
            project,
            project.root / f"analysis/research-decision/submissions/{role}.json",
        )
    research_decision.register_decision_rebuttals(
        project, project.root / "analysis/research-decision/submissions/rebuttals.json"
    )
    status = research_decision.register_decision_result(
        project, project.root / "analysis/research-decision/submissions/result.json"
    )

    assert (project.root / ".researchclaw/state.json").read_bytes() == before
    assert status["phase"] == (
        "complete"
        if decision == "proceed"
        else "needs_direction"
        if decision is None
        else "follow_up_required"
    )
    current = ResearchProject.open_readonly(project.root)
    assert (15 in current.state.completed_stages) is (decision == "proceed")


def test_terminal_status_revalidates_real_historical_analysis(tmp_path):
    project = analyzed_project(tmp_path / "project")
    complete_decision(project, "proceed")
    (project.root / "analysis/results.json").write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError):
        research_decision.research_decision_status(project)
    with pytest.raises(ValueError):
        research_decision.prepare_research_decision(project)


def test_decision_status_rejects_tampered_deterministic_report(tmp_path):
    project = analyzed_project(tmp_path / "project")
    complete_decision(project, "proceed")
    report = project.root / research_decision.DECISION_REPORT_PATH
    report.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="decision_integrity_failure"):
        research_decision.research_decision_status(project)


@pytest.mark.parametrize(
    "record_kind",
    ["packet", "review", "rebuttals", "result", "report"],
)
def test_decision_publication_verifies_bytes_before_state_commit(
    tmp_path, monkeypatch, record_kind
):
    project = analyzed_project(tmp_path / "project")
    if record_kind == "packet":
        target_path = research_decision.DECISION_PACKET_PATH

        def operation():
            return research_decision.prepare_research_decision(project)

    else:
        research_decision.prepare_research_decision(project)
        directions = {role: "proceed" for role in research_decision.ROLES}
        if record_kind == "review":
            target_path = "analysis/research-decision/reviews/domain.json"
            submission = write_decision_submission(
                project, "domain.json", review_payload(project, "domain", "proceed")
            )

            def operation():
                return research_decision.register_decision_review(project, submission)

        else:
            register_decision_roles(project, directions)
            rebuttals = write_decision_submission(
                project, "rebuttals.json", rebuttal_payload(project, directions)
            )
            if record_kind == "rebuttals":
                target_path = research_decision.DECISION_REBUTTALS_PATH

                def operation():
                    return research_decision.register_decision_rebuttals(
                        project, rebuttals
                    )

            else:
                research_decision.register_decision_rebuttals(project, rebuttals)
                result = write_decision_submission(
                    project, "result.json", result_payload(project, "proceed")
                )
                target_path = (
                    research_decision.DECISION_RESULT_PATH
                    if record_kind == "result"
                    else research_decision.DECISION_REPORT_PATH
                )

                def operation():
                    return research_decision.register_decision_result(project, result)

    before_state = ResearchProject.open_readonly(project.root).state
    before_state_bytes = (project.root / ".researchclaw/state.json").read_bytes()
    target = project.root / target_path
    conflicting_bytes = (
        b"injected report corruption\n"
        if record_kind == "report"
        else b'{"fault":"injected"}'
    )
    original_write = research_decision._write_exclusive

    def change_after_publication(destination, payload):
        original_write(destination, payload)
        if destination == target:
            destination.write_bytes(conflicting_bytes)

    monkeypatch.setattr(
        research_decision, "_write_exclusive", change_after_publication
    )
    with pytest.raises(ValueError):
        operation()
    monkeypatch.setattr(research_decision, "_write_exclusive", original_write)

    current = ResearchProject.open_readonly(project.root)
    assert current.state == before_state
    assert (project.root / ".researchclaw/state.json").read_bytes() == before_state_bytes
    assert target.read_bytes() == conflicting_bytes
    assert target_path not in current.state.artifacts
    if record_kind in {"result", "report"}:
        assert current.state.current_stage == 15
        assert 15 not in current.state.completed_stages
        assert research_decision.DECISION_RESULT_PATH not in current.state.artifacts
        assert research_decision.DECISION_REPORT_PATH not in current.state.artifacts

    with pytest.raises(ValueError):
        operation()
    assert target.read_bytes() == conflicting_bytes
    assert ResearchProject.open_readonly(project.root).state == before_state
    assert (project.root / ".researchclaw/state.json").read_bytes() == before_state_bytes


@pytest.mark.parametrize(
    ("record_kind", "field", "malformed"),
    [
        ("review", "role", []),
        ("review", "recommendation", {}),
        ("rebuttals", "role", []),
        ("rebuttals", "final_recommendation", {}),
        ("result", "decision", []),
        ("result", "disagreement_role", {}),
    ],
)
def test_decision_cli_rejects_malformed_enum_fields_without_publication(
    tmp_path, capsys, record_kind, field, malformed
):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    directions = {role: "proceed" for role in research_decision.ROLES}

    if record_kind == "review":
        payload = review_payload(project, "domain", "proceed")
        payload[field] = malformed
        name = f"malformed-review-{field}.json"
        output_paths = ["analysis/research-decision/reviews/domain.json"]
        command = "register-review"
    else:
        register_decision_roles(project, directions)
        if record_kind == "rebuttals":
            payload = rebuttal_payload(project, directions)
            payload["responses"][0][field] = malformed
            name = f"malformed-rebuttals-{field}.json"
            output_paths = [research_decision.DECISION_REBUTTALS_PATH]
            command = "register-rebuttals"
        else:
            research_decision.register_decision_rebuttals(
                project,
                write_decision_submission(
                    project, "rebuttals.json", rebuttal_payload(project, directions)
                ),
            )
            if field == "disagreement_role":
                payload = result_payload(project, None)
                payload["disagreements"][0]["role"] = malformed
            else:
                payload = result_payload(project, "proceed")
                payload[field] = malformed
            name = f"malformed-result-{field}.json"
            output_paths = [
                research_decision.DECISION_RESULT_PATH,
                research_decision.DECISION_REPORT_PATH,
            ]
            command = "register-result"

    submission = write_decision_submission(project, name, payload)
    before_state = (project.root / ".researchclaw/state.json").read_bytes()

    assert (
        run_cli(
            [
                "decision",
                command,
                str(project.root),
                "--submission",
                str(submission.relative_to(project.root)),
                "--json",
            ]
        )
        == 2
    )
    error = capsys.readouterr().err

    assert error.startswith("error: decision_")
    assert "Traceback" not in error
    assert (project.root / ".researchclaw/state.json").read_bytes() == before_state
    assert all(not (project.root / path).exists() for path in output_paths)


def test_decision_review_recovers_exact_orphan_and_preserves_conflict_bytes(
    tmp_path, monkeypatch
):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    submission = write_decision_submission(
        project, "domain.json", review_payload(project, "domain", "proceed")
    )
    conflict_payload = review_payload(project, "domain", "proceed")
    conflict_payload["rationale"] = [
        _decision_statement("Conflicting authored rationale.")
    ]
    conflict = write_decision_submission(
        project, "domain-conflict.json", conflict_payload
    )
    original = ResearchProject.persist_state
    failed = False

    def fail_once(self, state):
        nonlocal failed
        target = "analysis/research-decision/reviews/domain.json"
        if target in state.artifacts and not failed:
            failed = True
            raise OSError("simulated interruption")
        return original(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", fail_once)
    with pytest.raises(OSError, match="simulated interruption"):
        research_decision.register_decision_review(project, submission)
    monkeypatch.setattr(ResearchProject, "persist_state", original)
    target = project.root / "analysis/research-decision/reviews/domain.json"
    orphan = target.read_bytes()
    with pytest.raises(ValueError, match="decision_integrity_failure"):
        research_decision.research_decision_status(project)

    with pytest.raises(ValueError, match="decision_review_conflict"):
        research_decision.register_decision_review(project, conflict)
    assert target.read_bytes() == orphan
    status = research_decision.register_decision_review(project, submission)
    assert status["registered_roles"] == ["domain"]
    assert target.read_bytes() == orphan


def test_decision_rebuttals_recovers_exact_orphan(tmp_path, monkeypatch):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    directions = {role: "proceed" for role in research_decision.ROLES}
    register_decision_roles(project, directions)
    submission = write_decision_submission(
        project, "rebuttals.json", rebuttal_payload(project, directions)
    )
    conflict_payload = rebuttal_payload(project, directions)
    conflict_payload["responses"][0]["responses"] = [
        _decision_statement("Conflicting response bytes.")
    ]
    conflict = write_decision_submission(
        project, "rebuttals-conflict.json", conflict_payload
    )
    original = ResearchProject.persist_state
    failed = False

    def fail_once(self, state):
        nonlocal failed
        if research_decision.DECISION_REBUTTALS_PATH in state.artifacts and not failed:
            failed = True
            raise OSError("simulated interruption")
        return original(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", fail_once)
    with pytest.raises(OSError, match="simulated interruption"):
        research_decision.register_decision_rebuttals(project, submission)
    monkeypatch.setattr(ResearchProject, "persist_state", original)

    target = project.root / research_decision.DECISION_REBUTTALS_PATH
    orphan = target.read_bytes()
    with pytest.raises(ValueError, match="decision_integrity_failure"):
        research_decision.research_decision_status(project)
    with pytest.raises(ValueError, match="decision_rebuttal_conflict"):
        research_decision.register_decision_rebuttals(project, conflict)
    assert target.read_bytes() == orphan
    status = research_decision.register_decision_rebuttals(project, submission)
    assert status["phase"] == "awaiting_decision"


def test_decision_result_report_recovers_after_state_interruption(
    tmp_path, monkeypatch
):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    directions = {role: "proceed" for role in research_decision.ROLES}
    register_decision_roles(project, directions)
    research_decision.register_decision_rebuttals(
        project,
        write_decision_submission(
            project, "rebuttals.json", rebuttal_payload(project, directions)
        ),
    )
    submission = write_decision_submission(
        project, "result.json", result_payload(project, "proceed")
    )
    conflict_payload = result_payload(project, "proceed")
    conflict_payload["rationale"] = [_decision_statement("Conflicting result bytes.")]
    conflict = write_decision_submission(
        project, "result-conflict.json", conflict_payload
    )
    original = ResearchProject.persist_state
    failed = False

    def fail_once(self, state):
        nonlocal failed
        if research_decision.DECISION_RESULT_PATH in state.artifacts and not failed:
            failed = True
            raise OSError("simulated interruption")
        return original(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", fail_once)
    with pytest.raises(OSError, match="simulated interruption"):
        research_decision.register_decision_result(project, submission)
    monkeypatch.setattr(ResearchProject, "persist_state", original)

    assert (project.root / research_decision.DECISION_RESULT_PATH).is_file()
    assert (project.root / research_decision.DECISION_REPORT_PATH).is_file()
    assert ResearchProject.open_readonly(project.root).state.current_stage == 15
    with pytest.raises(ValueError, match="decision_integrity_failure"):
        research_decision.research_decision_status(project)

    result_path = project.root / research_decision.DECISION_RESULT_PATH
    report_path = project.root / research_decision.DECISION_REPORT_PATH
    result_orphan = result_path.read_bytes()
    report_orphan = report_path.read_bytes()
    with pytest.raises(ValueError, match="decision_result_conflict"):
        research_decision.register_decision_result(project, conflict)
    assert result_path.read_bytes() == result_orphan
    assert report_path.read_bytes() == report_orphan

    status = research_decision.register_decision_result(project, submission)
    assert status["phase"] == "complete"


def test_incomplete_report_publication_never_advances_state(tmp_path, monkeypatch):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    directions = {role: "proceed" for role in research_decision.ROLES}
    register_decision_roles(project, directions)
    research_decision.register_decision_rebuttals(
        project,
        write_decision_submission(
            project, "rebuttals.json", rebuttal_payload(project, directions)
        ),
    )
    submission = write_decision_submission(
        project, "result.json", result_payload(project, "proceed")
    )
    original = research_decision._write_report_exclusive
    monkeypatch.setattr(
        research_decision,
        "_write_report_exclusive",
        lambda *args: (_ for _ in ()).throw(OSError("report interruption")),
    )
    with pytest.raises(OSError, match="report interruption"):
        research_decision.register_decision_result(project, submission)
    monkeypatch.setattr(research_decision, "_write_report_exclusive", original)

    assert (project.root / research_decision.DECISION_RESULT_PATH).is_file()
    assert not (project.root / research_decision.DECISION_REPORT_PATH).exists()
    assert ResearchProject.open_readonly(project.root).state.current_stage == 15
    status = research_decision.register_decision_result(project, submission)
    assert status["phase"] == "complete"


def test_decision_cli_exposes_all_five_commands_and_nonzero_errors(tmp_path, capsys):
    project = analyzed_project(tmp_path / "project")
    assert run_cli(["decision", "prepare", str(project.root), "--json"]) == 0
    capsys.readouterr()
    directions = {role: "proceed" for role in research_decision.ROLES}
    for role in research_decision.ROLES:
        write_decision_submission(
            project, f"{role}.json", review_payload(project, role, "proceed")
        )
        assert (
            run_cli(
                [
                    "decision",
                    "register-review",
                    str(project.root),
                    "--submission",
                    f"analysis/research-decision/submissions/{role}.json",
                    "--json",
                ]
            )
            == 0
        )
        capsys.readouterr()
    write_decision_submission(
        project, "rebuttals.json", rebuttal_payload(project, directions)
    )
    assert (
        run_cli(
            [
                "decision",
                "register-rebuttals",
                str(project.root),
                "--submission",
                "analysis/research-decision/submissions/rebuttals.json",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    write_decision_submission(
        project, "result.json", result_payload(project, "proceed")
    )
    assert (
        run_cli(
            [
                "decision",
                "register-result",
                str(project.root),
                "--submission",
                "analysis/research-decision/submissions/result.json",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["phase"] == "complete"
    assert run_cli(["decision", "status", str(project.root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "complete"
    state = (project.root / ".researchclaw/state.json").read_bytes()
    assert (
        run_cli(
            [
                "decision",
                "register-review",
                str(project.root),
                "--submission",
                "analysis/research-decision/submissions/domain.json",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        run_cli(
            [
                "decision",
                "register-result",
                str(project.root),
                "--submission",
                "analysis/research-decision/submissions/result.json",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (project.root / ".researchclaw/state.json").read_bytes() == state
    assert (
        run_cli(
            [
                "decision",
                "register-result",
                str(project.root),
                "--submission",
                "../outside.json",
                "--json",
            ]
        )
        == 2
    )
    assert "error:" in capsys.readouterr().err


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


def test_decision_packet_closes_over_verified_analysis_history(tmp_path):
    project = analyzed_project(tmp_path / "project")

    packet = research_decision.prepare_research_decision(project)

    history = result_analysis.validate_completed_analysis(project)
    assert packet == {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "stage_id": 15,
        "inputs": {
            "analysis_records": history["references"],
            "research_evidence": history["evidence_packet"]["inputs"],
        },
        "roles": ["domain", "methodology", "critical_reproducibility"],
        "allowed_outputs": [
            "analysis/research-decision/reviews/domain.json",
            "analysis/research-decision/reviews/methodology.json",
            "analysis/research-decision/reviews/critical_reproducibility.json",
            "analysis/research-decision/rebuttals.json",
            "analysis/decision.json",
            "analysis/decision.md",
        ],
        "execution_allowed": False,
    }
    assert "phase" not in packet


@pytest.mark.parametrize(
    "record_path",
    [
        "analysis/evidence_packet.json",
        "analysis/results.json",
        "analysis/report.md",
        "analysis/reviews/domain.json",
        "analysis/reviews/methodology.json",
        "analysis/reviews/critical_reproducibility.json",
        "analysis/rebuttals.json",
    ],
)
def test_decision_prepare_rejects_changed_analysis_record(tmp_path, record_path):
    project = analyzed_project(tmp_path / "project")
    before = (project.root / ".researchclaw/state.json").read_bytes()
    (project.root / record_path).write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError):
        research_decision.prepare_research_decision(project)

    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


@pytest.mark.parametrize(
    "target",
    [
        "final_selection",
        "council_decision",
        "baseline_manifest",
        "retained_stage_13_packet",
        "baseline_result",
        "approved_design",
        "approved_hypotheses",
    ],
)
def test_decision_prepare_rejects_changed_retained_analysis_input(tmp_path, target):
    project = analyzed_project(tmp_path / "project")
    inputs = result_analysis.validate_completed_analysis(project)["evidence_packet"][
        "inputs"
    ]
    paths = {
        "final_selection": inputs["final_selection"]["path"],
        "council_decision": inputs["council_decision"]["path"],
        "baseline_manifest": inputs["retained_manifests"][0]["path"],
        "retained_stage_13_packet": next(
            item["path"]
            for item in inputs["retained_evidence"]
            if item["path"] == "refinement/evidence_packet.json"
        ),
        "baseline_result": inputs["baseline_result"]["path"],
        "approved_design": inputs["approved_design"]["registered"]["path"],
        "approved_hypotheses": inputs["approved_hypotheses"]["path"],
    }
    before = (project.root / ".researchclaw/state.json").read_bytes()
    (project.root / paths[target]).write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError):
        research_decision.prepare_research_decision(project)

    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_prepare_rejects_unregistered_analysis(tmp_path):
    project = analyzed_project(tmp_path / "project")
    project.persist_state(
        replace(
            project.state,
            artifacts={
                path: reference
                for path, reference in project.state.artifacts.items()
                if path != result_analysis.ANALYSIS_RESULT_PATH
            },
        )
    )
    before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError):
        research_decision.prepare_research_decision(
            ResearchProject.open_readonly(project.root)
        )

    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_prepare_rejects_wrong_stage(tmp_path):
    project = _finalized_project(tmp_path / "project")
    before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="decision_stage_invalid"):
        research_decision.prepare_research_decision(project)

    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_status_rejects_changed_packet(tmp_path):
    project = analyzed_project(tmp_path / "project")
    research_decision.prepare_research_decision(project)
    packet_path = project.root / research_decision.DECISION_PACKET_PATH
    packet_path.write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError, match="decision_packet_invalid"):
        research_decision.research_decision_status(project)


def test_decision_prepare_rejects_conflicting_existing_packet(tmp_path):
    project = analyzed_project(tmp_path / "project")
    packet_path = project.root / research_decision.DECISION_PACKET_PATH
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text('{"foreign":true}', encoding="utf-8")
    before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="decision_packet_conflict"):
        research_decision.prepare_research_decision(project)

    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_prepare_recovers_exact_packet_after_interrupted_state_save(
    tmp_path, monkeypatch
):
    project = analyzed_project(tmp_path / "project")
    original = ResearchProject.persist_state
    interrupted = False

    def fail_packet_registration_once(self, state):
        nonlocal interrupted
        if (
            research_decision.DECISION_PACKET_PATH in state.artifacts
            and not interrupted
        ):
            interrupted = True
            raise OSError("simulated interruption")
        return original(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", fail_packet_registration_once)
    with pytest.raises(OSError, match="simulated interruption"):
        research_decision.prepare_research_decision(project)
    monkeypatch.setattr(ResearchProject, "persist_state", original)

    orphan = project.root / research_decision.DECISION_PACKET_PATH
    assert orphan.is_file()
    assert (
        research_decision.DECISION_PACKET_PATH
        not in ResearchProject.open_readonly(project.root).state.artifacts
    )

    packet = research_decision.prepare_research_decision(project)

    current = ResearchProject.open_readonly(project.root)
    assert research_decision.DECISION_PACKET_PATH in current.state.artifacts
    assert json.loads(orphan.read_text(encoding="utf-8")) == packet


def test_decision_prepare_rejects_output_symlink(tmp_path):
    project = analyzed_project(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.root / "analysis/research-decision").symlink_to(
        outside, target_is_directory=True
    )
    before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="unsafe artifact path"):
        research_decision.prepare_research_decision(project)

    assert not list(outside.iterdir())
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_status_without_packet_is_read_only(tmp_path):
    project = analyzed_project(tmp_path / "project")
    before = (project.root / ".researchclaw/state.json").read_bytes()

    status = research_decision.research_decision_status(project)

    assert status["phase"] == "awaiting_preparation"
    assert status["next_action"] == "prepare_research_decision"
    assert status["evidence_packet"] is None
    assert not (project.root / research_decision.DECISION_PACKET_PATH).exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before


def test_decision_prepare_and_status_cli_use_evidence_only_language(tmp_path, capsys):
    project = analyzed_project(tmp_path / "project")

    assert run_cli(["decision", "prepare", str(project.root), "--json"]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["stage_id"] == 15
    assert packet["execution_allowed"] is False

    assert run_cli(["decision", "status", str(project.root), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["evidence_packet"] == packet
    assert status["phase"] == "awaiting_independent_recommendations"

    assert run_cli(["decision", "--help"]) == 0
    help_text = capsys.readouterr().out
    assert "evidence-bound Stage 15 research decision" in help_text
    assert "run experiment" not in help_text.lower()
