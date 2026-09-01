from dataclasses import replace
import json

import pytest

import researchclaw.core.refinement as refinement
from researchclaw.core.models import ArtifactRef
from researchclaw.core.project import ResearchProject
from researchclaw.core.refinement import (
    load_refinement_session,
    prepare_refinement_session,
    register_refinement_assessment,
    register_refinement_decision,
    register_refinement_rebuttals,
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


def test_load_session_reports_baseline_unavailable_when_session_files_are_absent(tmp_path):
    project = build_stage_thirteen_project(tmp_path / "project")

    with pytest.raises(ValueError, match="refinement_baseline_unavailable"):
        load_refinement_session(project)


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


def prepared_refinement_project(path):
    project = build_stage_thirteen_project(path)
    prepare_refinement_session(project, valid_envelope())
    return project


def _submission_base(project, *, producer):
    status = load_refinement_session(project)
    packet = project.root / status.evidence_packet_path
    return {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "session_id": status.session_id,
        "producer": producer,
        "created_at": "2026-09-01T00:00:00+00:00",
        "artifacts": [
            {
                "path": status.evidence_packet_path,
                "sha256": status.evidence_packet_sha256,
                "size": packet.stat().st_size,
            }
        ],
    }


def valid_assessment_record(project, *, role):
    return {
        **_submission_base(project, producer=f"{role}-agent"),
        "role": role,
        "assessment": {
            "schema_version": 1,
            "role": role,
            "evidence_packet_sha256": load_refinement_session(project).evidence_packet_sha256,
            "recommendation": "refine",
            "rationale": ["The evidence supports a bounded refinement."],
            "evidence_refs": ["refinement/evidence_packet.json"],
            "unresolved_questions": [],
        },
    }


def valid_rebuttals_record(
    project, *, roles=("domain", "methodology", "critical_reproducibility")
):
    base = _submission_base(project, producer="coordinator")
    return {
        **base,
        "assessment_hashes": {
            role: refinement._sha256(
                next(
                    candidate.read_bytes()
                    for candidate in (
                        project.root / f"refinement/deliberations/round-001/{role}_retry.json",
                        project.root / f"refinement/deliberations/round-001/{role}_review.json",
                    )
                    if candidate.exists()
                )
            )
            for role in roles
        },
        "rebuttals": [
            {
                "schema_version": 1,
                "role": role,
                "evidence_packet_sha256": load_refinement_session(project).evidence_packet_sha256,
                "challenges": ["Address the stated uncertainty."],
                "responses": ["The uncertainty remains recorded."],
                "evidence_refs": ["refinement/evidence_packet.json"],
            }
            for role in roles
        ],
    }


def write_record(project, name, payload):
    path = project.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return path


def register_one_assessment(project, *, role):
    return register_refinement_assessment(
        project,
        write_record(project, f"submissions/{role}.json", valid_assessment_record(project, role=role)),
    )


def write_valid_rebuttals(project, **kwargs):
    return write_record(project, "submissions/rebuttals.json", valid_rebuttals_record(project, **kwargs))


def register_all_assessments(project):
    for role in ("domain", "methodology", "critical_reproducibility"):
        register_one_assessment(project, role=role)


def valid_decision_record(
    project,
    *,
    roles=("domain", "methodology", "critical_reproducibility"),
    votes=("refine", "refine", "retain_baseline"),
):
    status = load_refinement_session(project)
    supporting = [
        role
        for role, vote in zip(roles, votes)
        if vote == "refine"
    ]
    dissenting = [
        role
        for role, vote in zip(roles, votes)
        if vote != "refine"
    ]
    return {
        **_submission_base(project, producer="coordinator"),
        "assessment_hashes": {
            role: refinement._sha256(
                next(
                    candidate.read_bytes()
                    for candidate in (
                        project.root / f"refinement/deliberations/round-001/{role}_retry.json",
                        project.root / f"refinement/deliberations/round-001/{role}_review.json",
                    )
                    if candidate.exists()
                )
            )
            for role in roles
        },
        "rebuttals_sha256": refinement._sha256(
            (project.root / "refinement/deliberations/round-001/rebuttals.json").read_bytes()
        ),
        "final_votes": [
            {
                "role": role,
                "producer": f"{role}-agent",
                "evidence_packet_sha256": status.evidence_packet_sha256,
                "decision": vote,
                "rationale": ["Final position after rebuttal."],
                "evidence_refs": ["refinement/evidence_packet.json"],
            }
            for role, vote in zip(roles, votes)
        ],
        "quorum": 2,
        "supporting_roles": supporting,
        "dissenting_roles": dissenting,
        "rationale": ["Two council members support the bounded refinement."],
        "evidence_refs": ["refinement/evidence_packet.json"],
        "action": "refine",
        "candidate_id": None,
        "change_request": {
            "paths": ["refinement/candidates/candidate-001/code/model.py"]
        },
    }


def write_valid_decision(project, **kwargs):
    return write_record(
        project, "submissions/decision.json", valid_decision_record(project, **kwargs)
    )


def failed_assessment_record(project, *, role, producer, retry_of=None):
    payload = {
        **_submission_base(project, producer=producer),
        "role": role,
        "failure": "The assigned agent did not produce a valid assessment.",
    }
    if retry_of is not None:
        payload["retry"] = {"failed_producer": retry_of}
    return payload


def test_rebuttal_requires_all_initial_assessments(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_one_assessment(project, role="domain")

    with pytest.raises(ValueError, match="refinement_disclosure_order_invalid"):
        register_refinement_rebuttals(
            project, write_record(project, "submissions/rebuttals.json", {})
        )


def test_assessments_are_exclusive_and_rebuttals_bind_the_initial_records(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    first = register_one_assessment(project, role="domain")
    assert first.phase == "awaiting_independent_assessments"
    assert register_one_assessment(project, role="domain") == first

    changed = valid_assessment_record(project, role="domain")
    changed["producer"] = "different-domain-agent"
    with pytest.raises(ValueError, match="refinement_assessment_conflict"):
        register_refinement_assessment(
            project, write_record(project, "submissions/domain-changed.json", changed)
        )

    register_all_assessments(project)
    status = register_refinement_rebuttals(project, write_valid_rebuttals(project))
    assert status.phase == "awaiting_final_votes"
    assert status.next_action == "register_refinement_final_votes"
    assert ResearchProject.open(project.root).state.next_action == "register_refinement_final_votes"


def test_decision_carries_final_votes_and_derives_the_next_action(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))

    status = register_refinement_decision(project, write_valid_decision(project))

    assert status.phase == "awaiting_candidate"
    assert status.next_action == "register_refinement_candidate"
    assert load_refinement_session(project) == status


def test_one_recorded_failed_retry_authorizes_exactly_one_vacancy(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    initial_failure = failed_assessment_record(
        project, role="critical_reproducibility", producer="critical-agent-a"
    )
    register_refinement_assessment(
        project, write_record(project, "submissions/critical-failure.json", initial_failure)
    )
    retry_failure = failed_assessment_record(
        project,
        role="critical_reproducibility",
        producer="critical-agent-b",
        retry_of="critical-agent-a",
    )
    register_refinement_assessment(
        project, write_record(project, "submissions/critical-retry.json", retry_failure)
    )
    assert (
        project.root
        / "refinement/deliberations/round-001/critical_reproducibility_vacancy.json"
    ).is_file()

    register_one_assessment(project, role="domain")
    register_one_assessment(project, role="methodology")
    status = register_refinement_rebuttals(
        project, write_valid_rebuttals(project, roles=("domain", "methodology"))
    )
    assert status.phase == "awaiting_final_votes"
    status = register_refinement_decision(
        project,
        write_valid_decision(
            project, roles=("domain", "methodology"), votes=("refine", "refine")
        ),
    )
    assert status.phase == "awaiting_candidate"


def test_decision_rejects_partial_votes_without_persisting_a_record(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    partial = valid_decision_record(project)
    partial["final_votes"] = partial["final_votes"][:1]

    with pytest.raises(ValueError, match="refinement_decision_invalid"):
        register_refinement_decision(
            project, write_record(project, "submissions/partial-decision.json", partial)
        )
    assert not (project.root / "refinement/deliberations/round-001/decision.json").exists()


def test_implementation_producer_cannot_register_a_council_assessment(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    payload = valid_assessment_record(project, role="domain")
    payload["producer"] = "implementation-agent"

    with pytest.raises(ValueError, match="refinement_assessment_producer_invalid"):
        register_refinement_assessment(
            project, write_record(project, "submissions/implementation.json", payload)
        )


def test_disguised_coordinator_cannot_register_a_council_assessment(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    payload = valid_assessment_record(project, role="domain")
    payload["producer"] = "CoOrDiNaToR-agent"

    with pytest.raises(ValueError, match="refinement_assessment_producer_invalid"):
        register_refinement_assessment(
            project, write_record(project, "submissions/disguised-coordinator.json", payload)
        )


def test_council_roles_cannot_share_an_active_assessment_producer(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_one_assessment(project, role="domain")
    payload = valid_assessment_record(project, role="methodology")
    payload["producer"] = "domain-agent"

    with pytest.raises(ValueError, match="refinement_assessment_producer_duplicate"):
        register_refinement_assessment(
            project, write_record(project, "submissions/shared-producer.json", payload)
        )


def test_final_vote_producer_must_match_its_active_assessment(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(project)
    decision["final_votes"][0]["producer"] = "methodology-agent"

    with pytest.raises(ValueError, match="refinement_final_vote_producer_invalid"):
        register_refinement_decision(
            project, write_record(project, "submissions/mismatched-vote-producer.json", decision)
        )


def test_second_failed_retry_is_durable_and_pauses_without_a_second_vacancy(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    for role in ("critical_reproducibility", "methodology"):
        initial = failed_assessment_record(project, role=role, producer=f"{role}-agent-a")
        register_refinement_assessment(
            project, write_record(project, f"submissions/{role}-failure.json", initial)
        )
        retry = failed_assessment_record(
            project,
            role=role,
            producer=f"{role}-agent-b",
            retry_of=f"{role}-agent-a",
        )
        if role == "critical_reproducibility":
            register_refinement_assessment(
                project, write_record(project, f"submissions/{role}-retry.json", retry)
            )
        else:
            status = register_refinement_assessment(
                project, write_record(project, f"submissions/{role}-retry.json", retry)
            )

    assert status.phase == "paused_insufficient_voters"
    assert (project.root / "refinement/deliberations/round-001/methodology_retry.json").is_file()
    assert not (project.root / "refinement/deliberations/round-001/methodology_vacancy.json").exists()


def test_assessment_recovers_exact_orphaned_file_state_and_rejects_changed_bytes(
    tmp_path, monkeypatch
):
    project = prepared_refinement_project(tmp_path / "project")
    original = refinement._record_state_ref

    def interrupt_after_assessment(project_arg, relative_path, payload, *, next_action):
        if relative_path.endswith("domain_review.json"):
            raise RuntimeError("assessment-state interruption")
        return original(project_arg, relative_path, payload, next_action=next_action)

    monkeypatch.setattr(refinement, "_record_state_ref", interrupt_after_assessment)
    original_payload = valid_assessment_record(project, role="domain")
    original_path = write_record(project, "submissions/domain-orphan.json", original_payload)
    with pytest.raises(RuntimeError, match="assessment-state interruption"):
        register_refinement_assessment(project, original_path)

    monkeypatch.setattr(refinement, "_record_state_ref", original)
    changed = {**original_payload}
    changed["producer"] = "different-domain-agent"
    with pytest.raises(ValueError, match="refinement_assessment_conflict"):
        register_refinement_assessment(
            project, write_record(project, "submissions/domain-changed-orphan.json", changed)
        )
    assert (
        register_refinement_assessment(project, original_path).phase
        == "awaiting_independent_assessments"
    )


def test_request_discriminating_run_accepts_an_envelope_contained_change_request(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(project)
    decision["final_votes"] = [
        {**vote, "decision": "request_discriminating_run"}
        for vote in decision["final_votes"]
    ]
    decision["supporting_roles"] = ["domain", "methodology", "critical_reproducibility"]
    decision["dissenting_roles"] = []
    decision["action"] = "request_discriminating_run"

    status = register_refinement_decision(
        project, write_record(project, "submissions/discriminating-run.json", decision)
    )

    assert status.next_action == "register_refinement_candidate"


def test_submission_schema_version_rejects_bool(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    payload = valid_assessment_record(project, role="domain")
    payload["schema_version"] = True

    with pytest.raises(ValueError, match="refinement_submission_schema_invalid"):
        register_refinement_assessment(
            project, write_record(project, "submissions/bool-schema.json", payload)
        )
