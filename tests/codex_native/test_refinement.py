from dataclasses import replace

import pytest

import researchclaw.core.refinement as refinement
from researchclaw.core.models import ArtifactRef
from researchclaw.core.project import ResearchProject
from researchclaw.core.refinement import (
    load_refinement_session,
    prepare_refinement_session,
)
from tests.codex_native.helpers import (
    build_stage_thirteen_project,
    build_ungrounded_stage_thirteen_project,
    immutable_stage_twelve_snapshot,
)


def valid_envelope() -> dict[str, object]:
    return {
        "schema_version": 1,
        "producer": "user",
        "maximum_runs": 2,
        "maximum_wall_seconds": 120,
        "maximum_candidate_seconds": 60,
        "allowed_input_paths": ["data/input.csv"],
        "allowed_change_roots": [
            "refinement/candidates/candidate-001/code",
            "refinement/candidates/candidate-001/config",
            "refinement/candidates/candidate-001/tests",
            "refinement/candidates/candidate-001/package_metadata",
        ],
    }


def test_prepare_session_requires_verified_stage_twelve_evidence(tmp_path):
    project = build_stage_thirteen_project(tmp_path / "project")
    before = immutable_stage_twelve_snapshot(project)

    status = prepare_refinement_session(project, valid_envelope())

    assert status.phase == "awaiting_independent_assessments"
    assert immutable_stage_twelve_snapshot(project) == before


def test_prepare_session_rejects_legacy_result(tmp_path):
    with pytest.raises(ValueError, match="refinement_baseline_unavailable"):
        prepare_refinement_session(
            build_ungrounded_stage_thirteen_project(tmp_path / "project"),
            valid_envelope(),
        )


def test_prepare_session_is_idempotent_only_for_the_same_grounding(tmp_path):
    project = build_stage_thirteen_project(tmp_path / "project")
    initial = prepare_refinement_session(project, valid_envelope())

    assert prepare_refinement_session(project, valid_envelope()) == initial

    (project.root / "refinement/evidence_packet.json").write_text(
        '{"tampered":true}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="refinement_integrity_failure"):
        prepare_refinement_session(project, valid_envelope())


def test_prepare_session_rejects_changed_envelope_or_baseline_binding(tmp_path):
    project = build_stage_thirteen_project(tmp_path / "project")
    prepare_refinement_session(project, valid_envelope())

    changed_envelope = valid_envelope()
    changed_envelope["maximum_runs"] = 3
    with pytest.raises(ValueError, match="refinement_integrity_failure"):
        prepare_refinement_session(project, changed_envelope)

    reopened = ResearchProject.open(project.root)
    manifest_path = next(
        path
        for path in reopened.state.artifacts
        if path.startswith(".researchclaw/evidence/manifests/")
    )
    manifest = reopened.state.artifacts[manifest_path]
    reopened.persist_state(
        replace(
            reopened.state,
            artifacts={
                **reopened.state.artifacts,
                manifest_path: ArtifactRef(manifest_path, "0" * 64, manifest.size),
            },
        )
    )
    with pytest.raises(ValueError, match="refinement_integrity_failure"):
        load_refinement_session(ResearchProject.open(project.root))


def test_prepare_session_adopts_only_exact_files_after_state_interruption(
    tmp_path, monkeypatch
):
    project = build_stage_thirteen_project(tmp_path / "project")
    original = refinement._record_state_refs

    def interrupt_after_files(*_args):
        raise RuntimeError("state interrupted")

    monkeypatch.setattr(refinement, "_record_state_refs", interrupt_after_files)
    with pytest.raises(RuntimeError, match="state interrupted"):
        prepare_refinement_session(project, valid_envelope())

    monkeypatch.setattr(refinement, "_record_state_refs", original)
    status = prepare_refinement_session(project, valid_envelope())

    assert load_refinement_session(project) == status


def test_prepare_session_recovers_an_exact_packet_only_interruption(
    tmp_path, monkeypatch
):
    project = build_stage_thirteen_project(tmp_path / "project")
    original = refinement._write_exclusive

    def interrupt_after_packet(path, payload):
        original(path, payload)
        if path.name == "evidence_packet.json":
            raise RuntimeError("packet-only interruption")

    monkeypatch.setattr(refinement, "_write_exclusive", interrupt_after_packet)
    with pytest.raises(RuntimeError, match="packet-only interruption"):
        prepare_refinement_session(project, valid_envelope())

    monkeypatch.setattr(refinement, "_write_exclusive", original)
    status = prepare_refinement_session(project, valid_envelope())

    assert load_refinement_session(project) == status


def test_prepare_session_rejects_a_non_owned_packet_only_partial(tmp_path):
    project = build_stage_thirteen_project(tmp_path / "project")
    packet = project.root / "refinement/evidence_packet.json"
    packet.parent.mkdir()
    packet.write_text('{"created_at":"2026-09-01T00:00:00+00:00"}', encoding="utf-8")

    with pytest.raises(ValueError, match="refinement_integrity_failure"):
        prepare_refinement_session(project, valid_envelope())


def test_bounded_record_read_is_descriptor_backed(tmp_path, monkeypatch):
    path = tmp_path / "record.json"
    path.write_text("{}", encoding="utf-8")

    def fail_pathname_probe(*_args):
        raise AssertionError("pathname probe")

    monkeypatch.setattr(refinement.os.path, "isfile", fail_pathname_probe)

    assert refinement._read_bounded_json(path) == ({}, b"{}")
