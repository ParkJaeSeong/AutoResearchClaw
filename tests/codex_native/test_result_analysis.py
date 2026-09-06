import json
from dataclasses import replace

import pytest

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


def test_analysis_prepare_rejects_conflicting_existing_packet(tmp_path):
    project = _finalized_project(tmp_path / "project")
    packet_path = project.root / "analysis/evidence_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text('{"foreign":true}', encoding="utf-8")

    with pytest.raises(ValueError, match="analysis_packet_conflict"):
        prepare_analysis(project)


def test_analysis_status_cli_replays_verified_packet(tmp_path, capsys):
    project = _finalized_project(tmp_path / "project")
    expected = prepare_analysis(project)

    code = run_cli("analysis", "status", str(project.root), "--json")
    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert json.loads(captured.out) == expected


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
