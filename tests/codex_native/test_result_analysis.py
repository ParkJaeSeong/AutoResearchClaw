import json
import shlex
from dataclasses import replace

import pytest

from researchclaw.core import result_analysis
from researchclaw.core.result_analysis import analysis_status, prepare_analysis
from researchclaw.core.project import ResearchProject
from researchclaw.core.refinement import (
    finalize_refinement,
    register_refinement_rebuttals,
)
from researchclaw.core.refinement_execution import (
    prepare_refinement_run,
    register_refinement_result,
)
from tests.codex_native.helpers import run_cli
from tests.codex_native.test_refinement import (
    _packet_artifact,
    prepared_refinement_project,
    register_all_assessments,
    register_one_assessment,
    write_final_decision,
    write_valid_rebuttals,
)
from tests.codex_native.test_refinement_execution import (
    self_tested_candidate_project,
    write_refinement_result,
)


def _finalized_project(path, action="retain_baseline"):
    project = prepared_refinement_project(path)
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = write_final_decision(project, action)
    finalize_refinement(project, decision)
    return ResearchProject.open_readonly(project.root)


def _finalized_selected_project(path, candidate_value=0.125):
    project, candidate = self_tested_candidate_project(path)
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation, metric_value=candidate_value)
    registered = register_refinement_result(
        project, candidate.candidate_id, preparation.result_path
    )
    result_ref = ResearchProject.open_readonly(project.root).state.artifacts[
        registered.result_path
    ]
    evaluated = [
        _packet_artifact(project),
        {"path": result_ref.path, "sha256": result_ref.sha256, "size": result_ref.size},
    ]
    for role in ("domain", "methodology", "critical_reproducibility"):
        register_one_assessment(project, role=role, artifacts=evaluated)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    finalize_refinement(project, write_final_decision(project, "select_candidate"))
    return ResearchProject.open_readonly(project.root), candidate, result_ref


def _write_analysis_submission(project, name, payload):
    path = project.root / "submissions" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return path


def _analysis_submission_base(project, producer):
    return {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "evidence_packet_sha256": ResearchProject.open_readonly(
            project.root
        ).state.artifacts["analysis/evidence_packet.json"].sha256,
        "producer": producer,
    }


def _valid_analysis_rebuttals(project):
    selected_result = analysis_status(ResearchProject.open_readonly(project.root))[
        "evidence_packet"
    ]["inputs"]["selected_result"]["path"]
    review_hashes = {
        role: ResearchProject.open_readonly(project.root).state.artifacts[
            f"analysis/reviews/{role}.json"
        ].sha256
        for role in ("domain", "methodology", "critical_reproducibility")
        if f"analysis/reviews/{role}.json"
        in ResearchProject.open_readonly(project.root).state.artifacts
    }
    return {
        **_analysis_submission_base(project, "analysis-coordinator"),
        "review_hashes": review_hashes,
        "responses": [
            {
                "role": role,
                "producer": f"{role}-analyst",
                "review_sha256": review_hashes[role],
                "challenges": ["Explain the strongest unresolved threat."],
                "responses": [f"{role} response preserves its original limitation."],
                "evidence_refs": [selected_result],
            }
            for role in ("domain", "methodology", "critical_reproducibility")
            if role in review_hashes
        ],
    }


def _valid_analysis_review(project, role, *, producer=None):
    packet = analysis_status(ResearchProject.open_readonly(project.root))[
        "evidence_packet"
    ]
    return {
        **_analysis_submission_base(project, producer or f"{role}-analyst"),
        "role": role,
        "claims": [
            {
                "text": f"{role} found the registered metric interpretable only in scope.",
                "evidence_refs": [packet["inputs"]["selected_result"]["path"]],
            }
        ],
        "limitations": [f"{role} limitation remains unresolved."],
        "questions": [f"What would resolve the {role} limitation?"],
    }


def _register_analysis_reviews(project):
    for role in ("domain", "methodology", "critical_reproducibility"):
        result_analysis.register_analysis_review(
            project,
            _write_analysis_submission(
                project, f"analysis-{role}.json", _valid_analysis_review(project, role)
            ),
        )


def _register_analysis_rebuttals(project):
    payload = _valid_analysis_rebuttals(project)
    path = _write_analysis_submission(project, "analysis-rebuttals.json", payload)
    return result_analysis.register_analysis_rebuttals(project, path), path


def _valid_analysis_result(project, *, uncertainty=None):
    current = ResearchProject.open_readonly(project.root)
    packet = analysis_status(current)["evidence_packet"]
    review_hashes = {
        role: current.state.artifacts[f"analysis/reviews/{role}.json"].sha256
        for role in ("domain", "methodology", "critical_reproducibility")
    }
    metric = packet["metrics"]["primary"]
    result_ref = packet["inputs"]["selected_result"]["path"]
    return {
        **_analysis_submission_base(project, "analysis-coordinator"),
        "review_hashes": review_hashes,
        "rebuttals_sha256": current.state.artifacts[
            "analysis/rebuttals.json"
        ].sha256,
        "observed_metrics": [
            {
                "name": metric["name"],
                "unit": metric["unit"],
                "value": metric["value"],
                "evidence_refs": [result_ref],
            }
        ],
        "hypothesis_assessments": [
            {
                "hypothesis_id": hypothesis_id,
                "verdict": "inconclusive",
                "explanation": "The bounded observation does not establish generality.",
                "evidence_refs": [result_ref],
            }
            for hypothesis_id in packet["target_hypothesis_ids"]
        ],
        "explanations": ["The registered metric is reported without a new verdict."],
        "alternatives": ["The apparent effect may depend on the synthetic fixture."],
        "limitations": [
            "Noise robustness was not measured",
            *packet["selection_context"]["limitations"],
        ],
        "scope": ["Evidence comes from a noiseless synthetic line fixture only."],
        "uncertainty": uncertainty or ["No uncertainty estimate was registered."],
        "agreement": ["All roles agree that the registered metric must be preserved."],
        "disagreements": [
            {
                "role": "critical_reproducibility",
                "text": "The evidence does not establish real-world superiority.",
                "evidence_refs": [result_ref],
            }
        ],
    }


def test_analysis_rebuttals_reject_registration_before_independent_reviews(tmp_path):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    rebuttals_path = _write_analysis_submission(
        project, "analysis-rebuttals.json", _valid_analysis_rebuttals(project)
    )

    with pytest.raises(ValueError, match="analysis_order_invalid"):
        result_analysis.register_analysis_rebuttals(project, rebuttals_path)

    assert ResearchProject.open(project.root).state.current_stage == 14


def test_analysis_review_registration_rejects_duplicate_producer_and_bad_reference(
    tmp_path,
):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    first = _write_analysis_submission(
        project, "analysis-domain.json", _valid_analysis_review(project, "domain")
    )
    result_analysis.register_analysis_review(project, first)

    duplicate = _write_analysis_submission(
        project,
        "analysis-methodology.json",
        _valid_analysis_review(
            project, "methodology", producer="domain-analyst"
        ),
    )
    with pytest.raises(ValueError, match="analysis_producer_duplicate"):
        result_analysis.register_analysis_review(project, duplicate)

    bad = _valid_analysis_review(project, "methodology")
    bad["claims"][0]["evidence_refs"] = ["experiment/results.json"]
    with pytest.raises(ValueError, match="analysis_evidence_reference_invalid"):
        result_analysis.register_analysis_review(
            project,
            _write_analysis_submission(project, "analysis-methodology-bad.json", bad),
        )


def test_analysis_review_registration_rejects_changed_packet(tmp_path):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    (project.root / "analysis/evidence_packet.json").write_text(
        '{"changed":true}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="analysis_packet_invalid"):
        result_analysis.register_analysis_review(
            project,
            _write_analysis_submission(
                project,
                "analysis-domain.json",
                {
                    "schema_version": 1,
                    "project_id": project.state.project_id,
                    "evidence_packet_sha256": "0" * 64,
                    "producer": "domain-analyst",
                    "role": "domain",
                    "claims": [],
                    "limitations": [],
                    "questions": [],
                },
            ),
        )


def test_analysis_review_recovers_exact_orphan_and_preserves_conflict_bytes(
    tmp_path, monkeypatch
):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    submission = _write_analysis_submission(
        project, "interrupted-domain.json", _valid_analysis_review(project, "domain")
    )
    target = project.root / "analysis/reviews/domain.json"
    original = ResearchProject.persist_state
    interrupted = False

    def fail_review_save_once(self, state):
        nonlocal interrupted
        if "analysis/reviews/domain.json" in state.artifacts and not interrupted:
            interrupted = True
            raise OSError("simulated review state interruption")
        return original(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", fail_review_save_once)
    with pytest.raises(OSError, match="review state interruption"):
        result_analysis.register_analysis_review(project, submission)
    orphan_bytes = target.read_bytes()
    monkeypatch.setattr(ResearchProject, "persist_state", original)
    conflicting = json.loads(submission.read_text(encoding="utf-8"))
    conflicting["claims"][0]["text"] = "Conflicting replacement claim."

    with pytest.raises(ValueError, match="analysis_review_conflict"):
        result_analysis.register_analysis_review(
            project,
            _write_analysis_submission(project, "conflicting-domain.json", conflicting),
        )
    assert target.read_bytes() == orphan_bytes

    status = result_analysis.register_analysis_review(project, submission)
    assert status["registered_roles"] == ["domain"]
    assert target.read_bytes() == orphan_bytes


def test_analysis_rebuttals_require_all_roles_and_bind_actual_producers(tmp_path):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    for role in ("domain", "methodology"):
        result_analysis.register_analysis_review(
            project,
            _write_analysis_submission(
                project, f"analysis-{role}.json", _valid_analysis_review(project, role)
            ),
        )
    incomplete = _write_analysis_submission(
        project, "analysis-rebuttals.json", _valid_analysis_rebuttals(project)
    )
    with pytest.raises(ValueError, match="analysis_order_invalid"):
        result_analysis.register_analysis_rebuttals(project, incomplete)

    role = "critical_reproducibility"
    result_analysis.register_analysis_review(
        project,
        _write_analysis_submission(
            project, f"analysis-{role}.json", _valid_analysis_review(project, role)
        ),
    )
    wrong = _valid_analysis_rebuttals(project)
    wrong["responses"][0]["producer"] = "fabricated-producer"
    with pytest.raises(ValueError, match="analysis_rebuttal_producer_invalid"):
        result_analysis.register_analysis_rebuttals(
            project,
            _write_analysis_submission(project, "analysis-rebuttals-wrong.json", wrong),
        )


def test_analysis_rebuttals_recovers_exact_orphan_and_preserves_conflict_bytes(
    tmp_path, monkeypatch
):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    _register_analysis_reviews(project)
    submission = _write_analysis_submission(
        project, "interrupted-rebuttals.json", _valid_analysis_rebuttals(project)
    )
    conflicting = _valid_analysis_rebuttals(project)
    conflicting["responses"][0]["responses"] = ["Conflicting replacement response."]
    target = project.root / "analysis/rebuttals.json"
    original = ResearchProject.persist_state
    interrupted = False

    def fail_rebuttal_save_once(self, state):
        nonlocal interrupted
        if "analysis/rebuttals.json" in state.artifacts and not interrupted:
            interrupted = True
            raise OSError("simulated rebuttal state interruption")
        return original(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", fail_rebuttal_save_once)
    with pytest.raises(OSError, match="rebuttal state interruption"):
        result_analysis.register_analysis_rebuttals(project, submission)
    orphan_bytes = target.read_bytes()
    monkeypatch.setattr(ResearchProject, "persist_state", original)
    with pytest.raises(ValueError, match="analysis_integrity_failure"):
        analysis_status(ResearchProject.open_readonly(project.root))

    with pytest.raises(ValueError, match="analysis_rebuttal_conflict"):
        result_analysis.register_analysis_rebuttals(
            project,
            _write_analysis_submission(
                project, "conflicting-rebuttals.json", conflicting
            ),
        )
    assert target.read_bytes() == orphan_bytes

    status = result_analysis.register_analysis_rebuttals(project, submission)
    assert status["phase"] == "awaiting_synthesis"
    assert target.read_bytes() == orphan_bytes


def test_analysis_result_rejects_early_synthesis_and_metric_mismatch(tmp_path):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    _register_analysis_reviews(project)
    early = {
        **_analysis_submission_base(project, "analysis-coordinator"),
        "review_hashes": {},
        "rebuttals_sha256": "0" * 64,
        "observed_metrics": [],
        "hypothesis_assessments": [],
        "explanations": [],
        "alternatives": [],
        "limitations": [],
        "scope": [],
        "uncertainty": [],
        "agreement": [],
        "disagreements": [],
    }
    with pytest.raises(ValueError, match="analysis_order_invalid"):
        result_analysis.register_analysis_result(
            project,
            _write_analysis_submission(project, "analysis-result-early.json", early),
        )

    _register_analysis_rebuttals(project)
    mismatch = _valid_analysis_result(project)
    mismatch["observed_metrics"][0]["value"] = 999
    with pytest.raises(ValueError, match="analysis_metric_mismatch"):
        result_analysis.register_analysis_result(
            project,
            _write_analysis_submission(project, "analysis-result-mismatch.json", mismatch),
        )


def test_analysis_result_requires_authored_uncertainty(tmp_path):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    missing = _valid_analysis_result(project)
    missing["uncertainty"] = []

    with pytest.raises(ValueError, match="analysis_uncertainty_missing"):
        result_analysis.register_analysis_result(
            project,
            _write_analysis_submission(project, "analysis-result.json", missing),
        )


def test_analysis_result_preserves_dissent_and_publishes_retry_safe_report(tmp_path):
    project = _finalized_project(tmp_path / "project")
    packet = prepare_analysis(project)
    packet_bytes = (project.root / "analysis/evidence_packet.json").read_bytes()
    _register_analysis_reviews(project)
    _, rebuttals_path = _register_analysis_rebuttals(project)
    submission = _write_analysis_submission(
        project, "analysis-result.json", _valid_analysis_result(project)
    )

    first = result_analysis.register_analysis_result(project, submission)
    result_bytes = (project.root / "analysis/results.json").read_bytes()
    report_bytes = (project.root / "analysis/report.md").read_bytes()
    first_state = ResearchProject.open_readonly(project.root).state
    second = result_analysis.register_analysis_result(
        ResearchProject.open_readonly(project.root), submission
    )
    replayed_review = result_analysis.register_analysis_review(
        ResearchProject.open_readonly(project.root),
        project.root / "submissions/analysis-domain.json",
    )
    replayed_rebuttals = result_analysis.register_analysis_rebuttals(
        ResearchProject.open_readonly(project.root), rebuttals_path
    )

    reopened = ResearchProject.open(project.root)
    report = report_bytes.decode("utf-8")
    assert reopened.state.current_stage == 15
    assert 14 in reopened.state.completed_stages
    assert first == second
    assert replayed_review == first
    assert replayed_rebuttals == first
    assert reopened.state == first_state
    assert (project.root / "analysis/results.json").read_bytes() == result_bytes
    assert (project.root / "analysis/report.md").read_bytes() == report_bytes
    assert (project.root / "analysis/evidence_packet.json").read_bytes() == packet_bytes
    assert analysis_status(reopened)["evidence_packet"] == packet
    assert "Noise robustness was not measured" in report
    assert "critical_reproducibility" in report
    assert "noiseless synthetic line fixture only" in report
    assert "No uncertainty estimate was registered" in report
    assert "real-world superiority" in report
    assert "critical_reproducibility response preserves its original limitation" in report


def test_analysis_result_binds_same_metric_to_baseline_and_selected_sources(tmp_path):
    project, _, _ = _finalized_selected_project(tmp_path / "project")
    packet = prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    synthesis = _valid_analysis_result(project)
    synthesis["observed_metrics"] = [
        {
            "name": "mae_cycles",
            "unit": "cycles",
            "value": 2.5,
            "evidence_refs": [packet["inputs"]["baseline_result"]["path"]],
        },
        {
            "name": "mae",
            "unit": "absolute_error",
            "value": 0.125,
            "evidence_refs": [packet["inputs"]["selected_result"]["path"]],
        },
    ]

    result_analysis.register_analysis_result(
        project,
        _write_analysis_submission(project, "selected-analysis-result.json", synthesis),
    )

    report = (project.root / "analysis/report.md").read_text(encoding="utf-8")
    assert "Baseline result — `mae_cycles`: 2.5 cycles" in report
    assert "Selected candidate — `mae`: 0.125 absolute_error" in report


def test_analysis_result_recovers_exact_publication_after_interrupted_state_save(
    tmp_path, monkeypatch
):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    submission = _write_analysis_submission(
        project, "interrupted-analysis-result.json", _valid_analysis_result(project)
    )
    original = ResearchProject.persist_state
    interrupted = False

    def fail_completion_once(self, state):
        nonlocal interrupted
        if state.current_stage == 15 and not interrupted:
            interrupted = True
            raise OSError("simulated interruption")
        return original(self, state)

    monkeypatch.setattr(ResearchProject, "persist_state", fail_completion_once)
    with pytest.raises(OSError, match="simulated interruption"):
        result_analysis.register_analysis_result(project, submission)
    monkeypatch.setattr(ResearchProject, "persist_state", original)

    status = result_analysis.register_analysis_result(project, submission)

    assert status["phase"] == "complete"
    assert ResearchProject.open_readonly(project.root).state.current_stage == 15


def test_analysis_registration_cli_completes_public_workflow(tmp_path, capsys):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    for role in ("domain", "methodology", "critical_reproducibility"):
        relative = f"submissions/cli-{role}.json"
        _write_analysis_submission(
            project, f"cli-{role}.json", _valid_analysis_review(project, role)
        )
        assert (
            run_cli(
                "analysis",
                "register-review",
                str(project.root),
                "--submission",
                relative,
                "--json",
            )
            == 0
        )
        capsys.readouterr()
    _write_analysis_submission(
        project, "cli-rebuttals.json", _valid_analysis_rebuttals(project)
    )
    assert run_cli(
        "analysis",
        "register-rebuttals",
        str(project.root),
        "--submission",
        "submissions/cli-rebuttals.json",
        "--json",
    ) == 0
    capsys.readouterr()
    _write_analysis_submission(
        project, "cli-result.json", _valid_analysis_result(project)
    )
    assert run_cli(
        "analysis",
        "register-result",
        str(project.root),
        "--submission",
        "submissions/cli-result.json",
        "--json",
    ) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["current_stage"] == 15

    assert run_cli("resume", str(project.root), "--json") == 0
    handoff = json.loads(capsys.readouterr().out)
    assert handoff["current_stage"] == 15
    assert handoff["stage_name"] == "research_decision"
    assert handoff["next_action"] == "unsupported_stage_15"
    assert handoff["write_policy"] == "read_only"
    assert shlex.split(handoff["next_command"]) == [
        "researchclaw-codex",
        "analysis",
        "status",
        str(project.root.resolve()),
        "--json",
    ]
    assert not (project.root / "analysis/decision.json").exists()

    state_before = ResearchProject.open_readonly(project.root).state
    assert run_cli("stage", "validate", str(project.root), "--json") == 2
    assert "Stage 15 research decisions are read-only and unsupported" in (
        capsys.readouterr().err
    )
    assert ResearchProject.open_readonly(project.root).state == state_before
    assert not (project.root / "analysis/decision.json").exists()


def test_analysis_prepare_cli_builds_packet_from_finalized_refinement(
    tmp_path, capsys
):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = write_final_decision(project, "retain_baseline")
    finalize_refinement(project, decision)

    code = run_cli("analysis", "prepare", str(project.root), "--json")
    captured = capsys.readouterr()

    assert code == 0, captured.err
    packet = json.loads(captured.out)
    assert packet["stage_id"] == 14
    assert packet["selection_action"] == "retain_baseline"
    assert packet["phase"] == "awaiting_independent_assessments"


def test_analysis_status_before_prepare_exposes_next_registration_action(tmp_path):
    project = _finalized_project(tmp_path / "project")

    status = analysis_status(project)

    assert status["phase"] == "awaiting_preparation"
    assert status["next_action"] == "prepare_analysis"
    assert status["current_stage"] == 14


def test_analysis_status_rejects_changed_retained_stage_thirteen_packet(tmp_path):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)

    (project.root / "refinement/evidence_packet.json").write_text(
        '{"tampered":true}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="analysis_input_changed"):
        analysis_status(ResearchProject.open_readonly(project.root))


@pytest.mark.parametrize("action", ["retain_baseline", "inconclusive"])
def test_analysis_prepare_preserves_non_candidate_selection_and_target_scope(
    tmp_path, action
):
    project = _finalized_project(tmp_path / "project", action)
    baseline_mutable = project.root / "experiment/results.json"
    baseline_mutable.write_text('{"not":"registered evidence"}', encoding="utf-8")

    packet = prepare_analysis(project)

    assert packet["selection_action"] == action
    assert packet["selected_candidate_id"] is None
    assert packet["result_source"] == "baseline"
    assert packet["target_hypothesis_ids"] == ["H001"]
    assert packet["inputs"]["selected_manifest"] is None
    assert packet["inputs"]["selected_result"] == packet["inputs"]["baseline_result"]
    assert packet["inputs"]["selected_result"]["path"].startswith(
        ".researchclaw/evidence/objects/"
    )
    assert packet["selection_context"]["dissenting_roles"] == [
        "critical_reproducibility"
    ]


def test_analysis_prepare_requires_registered_final_selection(tmp_path):
    project = _finalized_project(tmp_path / "project")
    project.persist_state(
        replace(
            project.state,
            artifacts={
                path: reference
                for path, reference in project.state.artifacts.items()
                if path != "refinement/final_selection.json"
            },
        )
    )

    with pytest.raises(ValueError, match="analysis_final_selection_missing"):
        prepare_analysis(ResearchProject.open_readonly(project.root))


@pytest.mark.parametrize(
    "target",
    [
        "final_selection",
        "council_decision",
        "baseline_manifest",
        "baseline_result",
        "approved_design",
        "approved_hypotheses",
    ],
)
def test_analysis_status_revalidates_every_packet_input(tmp_path, target):
    project = _finalized_project(tmp_path / "project")
    packet = prepare_analysis(project)
    if target == "final_selection":
        path = packet["inputs"]["final_selection"]["path"]
    elif target == "council_decision":
        path = packet["inputs"]["council_decision"]["path"]
    elif target == "baseline_manifest":
        path = packet["inputs"]["retained_manifests"][0]["path"]
    elif target == "baseline_result":
        path = packet["inputs"]["baseline_result"]["path"]
    elif target == "approved_design":
        path = packet["inputs"]["approved_design"]["registered"]["path"]
    else:
        path = packet["inputs"]["approved_hypotheses"]["path"]
    (project.root / path).write_bytes(b'{"changed":true}')

    with pytest.raises(ValueError, match="analysis_input_changed"):
        analysis_status(ResearchProject.open_readonly(project.root))


def test_analysis_prepare_exact_retry_preserves_packet_and_state(tmp_path):
    project = _finalized_project(tmp_path / "project")

    first = prepare_analysis(project)
    first_bytes = (project.root / "analysis/evidence_packet.json").read_bytes()
    first_state = ResearchProject.open_readonly(project.root).state
    second = prepare_analysis(ResearchProject.open_readonly(project.root))

    assert second == first
    assert (project.root / "analysis/evidence_packet.json").read_bytes() == first_bytes
    assert ResearchProject.open_readonly(project.root).state == first_state


def test_analysis_prepare_later_stage_exact_retry_is_verification_only(tmp_path):
    project = _finalized_project(tmp_path / "project")
    packet = prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    result_analysis.register_analysis_result(
        project,
        _write_analysis_submission(
            project, "completed-analysis.json", _valid_analysis_result(project)
        ),
    )
    packet_path = project.root / result_analysis.ANALYSIS_PACKET_PATH
    before_packet = packet_path.read_bytes()
    before_state = (project.root / ".researchclaw/state.json").read_bytes()

    assert prepare_analysis(ResearchProject.open_readonly(project.root)) == packet

    assert packet_path.read_bytes() == before_packet
    assert (project.root / ".researchclaw/state.json").read_bytes() == before_state


def test_analysis_prepare_later_stage_does_not_recreate_missing_packet(tmp_path):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    result_analysis.register_analysis_result(
        project,
        _write_analysis_submission(
            project, "completed-analysis.json", _valid_analysis_result(project)
        ),
    )
    packet_path = project.root / result_analysis.ANALYSIS_PACKET_PATH
    packet_path.unlink()
    before_state = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="analysis_packet_invalid"):
        prepare_analysis(ResearchProject.open_readonly(project.root))

    assert not packet_path.exists()
    assert (project.root / ".researchclaw/state.json").read_bytes() == before_state


def test_analysis_prepare_rejects_conflicting_existing_packet(tmp_path):
    project = _finalized_project(tmp_path / "project")
    packet_path = project.root / "analysis/evidence_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text('{"foreign":true}', encoding="utf-8")

    with pytest.raises(ValueError, match="analysis_packet_conflict"):
        prepare_analysis(project)


def test_analysis_prepare_rejects_symlinked_output_parent_without_escape_or_state_change(
    tmp_path,
):
    project = _finalized_project(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.root / "analysis").symlink_to(outside, target_is_directory=True)
    before = ResearchProject.open_readonly(project.root).state

    with pytest.raises(ValueError, match="unsafe artifact path"):
        prepare_analysis(project)

    assert not (outside / "evidence_packet.json").exists()
    assert ResearchProject.open_readonly(project.root).state == before


def test_analysis_status_cli_replays_verified_packet(tmp_path, capsys):
    project = _finalized_project(tmp_path / "project")
    expected = prepare_analysis(project)

    code = run_cli("analysis", "status", str(project.root), "--json")
    captured = capsys.readouterr()

    assert code == 0, captured.err
    payload = json.loads(captured.out)
    assert payload["evidence_packet"] == expected
    assert payload["phase"] == "awaiting_independent_assessments"
    assert payload["next_action"] == "register_analysis_review"


def test_validate_completed_analysis_reads_verified_history(tmp_path):
    project = _finalized_project(tmp_path / "project")
    packet = prepare_analysis(project)
    _register_analysis_reviews(project)
    _register_analysis_rebuttals(project)
    result_analysis.register_analysis_result(
        project,
        _write_analysis_submission(
            project, "completed-analysis.json", _valid_analysis_result(project)
        ),
    )
    current = ResearchProject.open_readonly(project.root)

    history = result_analysis.validate_completed_analysis(current)

    assert history["evidence_packet"] == packet
    assert [item["path"] for item in history["references"]] == [
        "analysis/evidence_packet.json",
        "analysis/results.json",
        "analysis/report.md",
        "analysis/reviews/domain.json",
        "analysis/reviews/methodology.json",
        "analysis/reviews/critical_reproducibility.json",
        "analysis/rebuttals.json",
    ]


def test_validate_completed_analysis_rejects_incomplete_records(tmp_path):
    project = _finalized_project(tmp_path / "project")
    prepare_analysis(project)

    with pytest.raises(ValueError, match="analysis_incomplete"):
        result_analysis.validate_completed_analysis(project)


def test_analysis_prepare_resolves_selected_candidate_from_immutable_manifest(
    tmp_path,
):
    project, candidate = self_tested_candidate_project(tmp_path / "project")
    preparation = prepare_refinement_run(project, candidate.candidate_id)
    write_refinement_result(project, preparation, metric_value=0.125)
    registered = register_refinement_result(
        project, candidate.candidate_id, preparation.result_path
    )
    result_ref = ResearchProject.open_readonly(project.root).state.artifacts[
        registered.result_path
    ]
    evaluated = [
        _packet_artifact(project),
        {
            "path": result_ref.path,
            "sha256": result_ref.sha256,
            "size": result_ref.size,
        },
    ]
    for role in ("domain", "methodology", "critical_reproducibility"):
        register_one_assessment(project, role=role, artifacts=evaluated)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = write_final_decision(project, "select_candidate")
    finalize_refinement(project, decision)
    (project.root / "experiment/results.json").write_text(
        '{"metrics":{"primary":{"name":"wrong","unit":"wrong","value":999}}}',
        encoding="utf-8",
    )

    packet = prepare_analysis(ResearchProject.open_readonly(project.root))

    selected = packet["inputs"]["selected_result"]
    assert packet["selection_action"] == "select_candidate"
    assert packet["selected_candidate_id"] == candidate.candidate_id
    assert packet["result_source"] == "selected_candidate"
    assert selected["path"] == f".researchclaw/evidence/objects/{result_ref.sha256}"
    assert selected["sha256"] == result_ref.sha256
    assert packet["inputs"]["selected_manifest"]["path"] == (
        registered.evidence_manifest_path
    )
    assert packet["metrics"]["primary"]["value"] == 0.125
