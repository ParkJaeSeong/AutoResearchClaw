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
    write_refinement_candidate,
)


def valid_envelope() -> dict[str, object]:
    return {
        "schema_version": 1,
        "producer": "user",
        "authority": {
            "coordinator": "coordinator-agent",
            "implementation": "implementation-agent",
            "council": {
                "domain": "domain-agent",
                "methodology": "methodology-agent",
                "critical_reproducibility": "critical_reproducibility-agent",
            },
        },
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


def test_prepare_session_persists_a_closed_distinct_authority_roster(tmp_path):
    project = build_stage_thirteen_project(tmp_path / "project")
    prepare_refinement_session(project, valid_envelope())

    session = json.loads((project.root / "refinement/session.json").read_text())
    assert session["envelope"]["authority"] == valid_envelope()["authority"]

    duplicate = valid_envelope()
    duplicate["authority"]["implementation"] = "domain-agent"
    other = build_stage_thirteen_project(tmp_path / "other")
    with pytest.raises(ValueError, match="refinement_authority_invalid"):
        prepare_refinement_session(other, duplicate)


def test_prepare_session_rejects_legacy_result(tmp_path):
    with pytest.raises(ValueError, match="refinement_baseline_unavailable"):
        prepare_refinement_session(
            build_ungrounded_stage_thirteen_project(tmp_path / "project"),
            valid_envelope(),
        )


def test_load_session_reports_baseline_unavailable_when_session_files_are_absent(
    tmp_path
):
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


def _packet_artifact(project):
    status = load_refinement_session(project)
    packet = project.root / status.evidence_packet_path
    return {
        "path": status.evidence_packet_path,
        "sha256": status.evidence_packet_sha256,
        "size": packet.stat().st_size,
    }


def _latest_round_id(project):
    root = project.root / "refinement/deliberations"
    rounds = sorted(path.name for path in root.iterdir()) if root.exists() else []
    return rounds[-1] if rounds else "round-001"


def _round_artifacts(project):
    binding = (
        project.root
        / "refinement/deliberations"
        / _latest_round_id(project)
        / "round.json"
    )
    if binding.exists():
        return json.loads(binding.read_text())["evaluated_artifacts"]
    return [_packet_artifact(project)]


def _submission_base(project, *, producer, artifacts=None):
    status = load_refinement_session(project)
    return {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "session_id": status.session_id,
        "producer": producer,
        "created_at": "2026-09-01T00:00:00+00:00",
        "artifacts": _round_artifacts(project) if artifacts is None else artifacts,
    }


def valid_assessment_record(project, *, role, artifacts=None):
    return {
        **_submission_base(project, producer=f"{role}-agent", artifacts=artifacts),
        "role": role,
        "assessment": {
            "schema_version": 1,
            "role": role,
            "evidence_packet_sha256": load_refinement_session(
                project
            ).evidence_packet_sha256,
            "recommendation": "refine",
            "rationale": ["The evidence supports a bounded refinement."],
            "evidence_refs": ["refinement/evidence_packet.json"],
            "unresolved_questions": [],
        },
    }


def valid_rebuttals_record(
    project,
    *,
    roles=("domain", "methodology", "critical_reproducibility"),
    producers=None,
):
    producers = producers or {role: f"{role}-agent" for role in roles}
    base = _submission_base(project, producer="coordinator-agent")
    return {
        **base,
        "assessment_hashes": {
            role: refinement._sha256(
                next(
                    candidate.read_bytes()
                    for candidate in (
                        project.root
                        / f"refinement/deliberations/{_latest_round_id(project)}/{role}_retry.json",
                        project.root
                        / f"refinement/deliberations/{_latest_round_id(project)}/{role}_review.json",
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
                "producer": producers[role],
                "evidence_packet_sha256": load_refinement_session(
                    project
                ).evidence_packet_sha256,
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
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return path


def register_one_assessment(project, *, role, artifacts=None):
    return register_refinement_assessment(
        project,
        write_record(
            project,
            f"submissions/{role}.json",
            valid_assessment_record(project, role=role, artifacts=artifacts),
        ),
    )


def write_valid_rebuttals(project, **kwargs):
    return write_record(
        project, "submissions/rebuttals.json", valid_rebuttals_record(project, **kwargs)
    )


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
    supporting = [role for role, vote in zip(roles, votes) if vote == "refine"]
    dissenting = [role for role, vote in zip(roles, votes) if vote != "refine"]
    return {
        **_submission_base(project, producer="coordinator-agent"),
        "assessment_hashes": {
            role: refinement._sha256(
                next(
                    candidate.read_bytes()
                    for candidate in (
                        project.root
                        / f"refinement/deliberations/{_latest_round_id(project)}/{role}_retry.json",
                        project.root
                        / f"refinement/deliberations/{_latest_round_id(project)}/{role}_review.json",
                    )
                    if candidate.exists()
                )
            )
            for role in roles
        },
        "rebuttals_sha256": refinement._sha256(
            (
                project.root
                / f"refinement/deliberations/{_latest_round_id(project)}/rebuttals.json"
            ).read_bytes()
        ),
        "final_votes": [
            {
                "role": role,
                "producer": f"{role}-agent",
                "evidence_packet_sha256": status.evidence_packet_sha256,
                "decision": vote,
                "rationale": ["Final position after rebuttal."],
                "evidence_refs": ["refinement/evidence_packet.json"],
                **(
                    {
                        "change_request": {
                            "paths": [
                                "refinement/candidates/candidate-001/code/model.py"
                            ]
                        }
                    }
                    if vote in {"refine", "request_discriminating_run"}
                    else {}
                ),
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


def register_future_candidate_result(project, *, candidate_id="candidate-001"):
    relative_path = f"refinement/candidates/{candidate_id}/results.json"
    path = project.root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"schema_version": 1, "candidate_id": candidate_id, "metric": 0.25},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path.write_bytes(payload)
    current = ResearchProject.open(project.root)
    reference = ArtifactRef(relative_path, refinement._sha256(payload), len(payload))
    current.persist_state(
        replace(
            current.state,
            artifacts={**current.state.artifacts, relative_path: reference},
        )
    )
    return {"path": relative_path, "sha256": reference.sha256, "size": reference.size}


def failed_assessment_record(project, *, role, producer, retry_of=None):
    payload = {
        **_submission_base(project, producer=producer),
        "role": role,
        "failure": "The assigned agent did not produce a valid assessment.",
    }
    if retry_of is not None:
        payload["retry"] = {
            "failed_producer": retry_of,
            "replacement_producer": producer,
            "authorized_by": "coordinator-agent",
        }
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
    assert (
        ResearchProject.open(project.root).state.next_action
        == "register_refinement_final_votes"
    )


def test_round_one_durably_binds_the_exact_baseline_packet_identity(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_one_assessment(project, role="domain")

    binding_path = project.root / "refinement/deliberations/round-001/round.json"
    binding = json.loads(binding_path.read_text())
    assert binding["round_id"] == "round-001"
    assert binding["previous_round_id"] is None
    assert binding["evaluated_artifacts"] == [_packet_artifact(project)]


def test_completed_round_allocates_round_two_only_for_new_registered_candidate_evidence(
    tmp_path,
):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(project, write_valid_decision(project))
    round_one = (
        project.root / "refinement/deliberations/round-001/domain_review.json"
    ).read_bytes()
    candidate = register_future_candidate_result(project)
    evaluated = [_packet_artifact(project), candidate]

    status = register_one_assessment(project, role="domain", artifacts=evaluated)

    assert status.phase == "awaiting_independent_assessments"
    assert (
        project.root / "refinement/deliberations/round-002/domain_review.json"
    ).is_file()
    binding = json.loads(
        (project.root / "refinement/deliberations/round-002/round.json").read_text()
    )
    assert binding["previous_round_id"] == "round-001"
    assert binding["evaluated_artifacts"] == evaluated
    assert (
        project.root / "refinement/deliberations/round-001/domain_review.json"
    ).read_bytes() == round_one


def test_rejected_first_retry_does_not_poison_new_round_binding(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(project, write_valid_decision(project))
    first_candidate = register_future_candidate_result(
        project, candidate_id="candidate-001"
    )
    retry = valid_assessment_record(
        project,
        role="domain",
        artifacts=[_packet_artifact(project), first_candidate],
    )
    retry["producer"] = "domain-retry-agent"
    retry["retry"] = {
        "failed_producer": "domain-agent",
        "replacement_producer": "domain-retry-agent",
        "authorized_by": "coordinator-agent",
    }
    before = ResearchProject.open(project.root).state

    with pytest.raises(ValueError, match="refinement_retry_order_invalid"):
        register_refinement_assessment(
            project,
            write_record(project, "submissions/first-record-retry.json", retry),
        )

    round_two = project.root / "refinement/deliberations/round-002"
    assert not round_two.exists()
    assert ResearchProject.open(project.root).state == before

    second_candidate = register_future_candidate_result(
        project, candidate_id="candidate-002"
    )
    evaluated = [_packet_artifact(project), second_candidate]
    status = register_one_assessment(project, role="domain", artifacts=evaluated)

    assert status.phase == "awaiting_independent_assessments"
    binding = json.loads((round_two / "round.json").read_text())
    assert binding["evaluated_artifacts"] == evaluated


def test_round_binding_detects_evaluated_candidate_result_byte_drift(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(project, write_valid_decision(project))
    candidate = register_future_candidate_result(project)
    register_one_assessment(
        project,
        role="domain",
        artifacts=[_packet_artifact(project), candidate],
    )
    candidate_path = project.root / candidate["path"]
    candidate_path.write_bytes(candidate_path.read_bytes().replace(b"0.25", b"9.99"))

    with pytest.raises(ValueError, match="refinement_integrity_failure"):
        load_refinement_session(project)


def test_later_round_requires_an_intact_completed_predecessor(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(project, write_valid_decision(project))
    candidate = register_future_candidate_result(project)
    register_one_assessment(
        project,
        role="domain",
        artifacts=[_packet_artifact(project), candidate],
    )
    prior_decision = "refinement/deliberations/round-001/decision.json"
    current = ResearchProject.open(project.root)
    artifacts = dict(current.state.artifacts)
    artifacts.pop(prior_decision)
    current.persist_state(replace(current.state, artifacts=artifacts))
    (project.root / prior_decision).unlink()

    with pytest.raises(ValueError, match="refinement_integrity_failure"):
        load_refinement_session(project)


def test_new_round_rejects_fabricated_or_non_evidence_artifact_bindings(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(project, write_valid_decision(project))
    fabricated = {
        "path": "refinement/candidates/candidate-001/results.json",
        "sha256": "a" * 64,
        "size": 1,
    }
    payload = valid_assessment_record(
        project,
        role="domain",
        artifacts=[_packet_artifact(project), fabricated],
    )

    with pytest.raises(ValueError, match="refinement_round_binding_invalid"):
        register_refinement_assessment(
            project, write_record(project, "submissions/fabricated-round.json", payload)
        )

    unrelated_path = "refinement/notes.json"
    unrelated = project.root / unrelated_path
    unrelated.write_text('{"note":"not evaluated evidence"}', encoding="utf-8")
    raw = unrelated.read_bytes()
    current = ResearchProject.open(project.root)
    reference = ArtifactRef(unrelated_path, refinement._sha256(raw), len(raw))
    current.persist_state(
        replace(
            current.state,
            artifacts={**current.state.artifacts, unrelated_path: reference},
        )
    )
    payload["artifacts"] = [
        _packet_artifact(project),
        {"path": reference.path, "sha256": reference.sha256, "size": reference.size},
    ]
    with pytest.raises(ValueError, match="refinement_round_binding_invalid"):
        register_refinement_assessment(
            project,
            write_record(project, "submissions/non-evidence-round.json", payload),
        )


def test_new_round_rejects_reusing_the_completed_evidence_set(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(project, write_valid_decision(project))
    payload = valid_assessment_record(project, role="domain")
    payload["assessment"]["recommendation"] = "different assessment"

    with pytest.raises(ValueError, match="refinement_assessment_conflict"):
        register_refinement_assessment(
            project, write_record(project, "submissions/ungrounded-round.json", payload)
        )


def test_assessment_evidence_refs_must_belong_to_the_round_evidence_set(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    payload = valid_assessment_record(project, role="domain")
    payload["assessment"]["evidence_refs"] = ["refinement/fabricated.json"]

    with pytest.raises(ValueError, match="refinement_evidence_ref_invalid"):
        register_refinement_assessment(
            project,
            write_record(project, "submissions/fabricated-evidence.json", payload),
        )
    assert not (
        project.root / "refinement/deliberations/round-001/domain_review.json"
    ).exists()


def test_rebuttal_evidence_refs_must_belong_to_the_round_evidence_set(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    rebuttals = valid_rebuttals_record(project)
    rebuttals["rebuttals"][0]["evidence_refs"] = ["refinement/fabricated.json"]

    with pytest.raises(ValueError, match="refinement_evidence_ref_invalid"):
        register_refinement_rebuttals(
            project,
            write_record(
                project, "submissions/fabricated-rebuttal-ref.json", rebuttals
            ),
        )


def test_vote_and_decision_evidence_refs_belong_to_the_round_evidence_set(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(project)
    decision["final_votes"][0]["evidence_refs"] = ["refinement/fabricated.json"]

    with pytest.raises(ValueError, match="refinement_evidence_ref_invalid"):
        register_refinement_decision(
            project,
            write_record(project, "submissions/fabricated-vote-ref.json", decision),
        )

    decision = valid_decision_record(project)
    decision["evidence_refs"] = ["refinement/fabricated.json"]
    with pytest.raises(ValueError, match="refinement_evidence_ref_invalid"):
        register_refinement_decision(
            project,
            write_record(project, "submissions/fabricated-decision-ref.json", decision),
        )


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
        project,
        role="critical_reproducibility",
        producer="critical_reproducibility-agent",
    )
    register_refinement_assessment(
        project,
        write_record(project, "submissions/critical-failure.json", initial_failure),
    )
    retry_failure = failed_assessment_record(
        project,
        role="critical_reproducibility",
        producer="critical-retry-agent",
        retry_of="critical_reproducibility-agent",
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
    assert not (
        project.root / "refinement/deliberations/round-001/decision.json"
    ).exists()


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
            project,
            write_record(project, "submissions/disguised-coordinator.json", payload),
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


def test_assessment_producer_must_match_the_prepared_role_roster(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    payload = valid_assessment_record(project, role="domain")
    payload["producer"] = "arbitrary-reviewer"

    with pytest.raises(ValueError, match="refinement_assessment_producer_invalid"):
        register_refinement_assessment(
            project,
            write_record(project, "submissions/arbitrary-reviewer.json", payload),
        )


def test_rebuttal_producers_match_active_role_authority(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    rebuttals = valid_rebuttals_record(project)
    rebuttals["rebuttals"][0]["producer"] = "methodology-agent"

    with pytest.raises(ValueError, match="refinement_rebuttal_producer_invalid"):
        register_refinement_rebuttals(
            project,
            write_record(project, "submissions/rebuttal-takeover.json", rebuttals),
        )


def test_rebuttal_envelope_requires_the_prepared_coordinator(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    rebuttals = valid_rebuttals_record(project)
    rebuttals["producer"] = "someone-else"

    with pytest.raises(ValueError, match="refinement_coordinator_producer_invalid"):
        register_refinement_rebuttals(
            project,
            write_record(project, "submissions/not-coordinator.json", rebuttals),
        )


def test_successful_retry_durably_updates_active_rebuttal_authority(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    initial = failed_assessment_record(project, role="domain", producer="domain-agent")
    register_refinement_assessment(
        project, write_record(project, "submissions/domain-failure.json", initial)
    )
    retry = valid_assessment_record(project, role="domain")
    retry["producer"] = "domain-retry-agent"
    retry["retry"] = {
        "failed_producer": "domain-agent",
        "replacement_producer": "domain-retry-agent",
        "authorized_by": "coordinator-agent",
    }
    register_refinement_assessment(
        project,
        write_record(project, "submissions/domain-successful-retry.json", retry),
    )
    register_one_assessment(project, role="methodology")
    register_one_assessment(project, role="critical_reproducibility")
    rebuttals = valid_rebuttals_record(
        project,
        producers={
            "domain": "domain-retry-agent",
            "methodology": "methodology-agent",
            "critical_reproducibility": "critical_reproducibility-agent",
        },
    )

    status = register_refinement_rebuttals(
        project, write_record(project, "submissions/retry-rebuttals.json", rebuttals)
    )

    assert status.phase == "awaiting_final_votes"


def test_final_vote_producer_must_match_its_active_assessment(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(project)
    decision["final_votes"][0]["producer"] = "methodology-agent"

    with pytest.raises(ValueError, match="refinement_final_vote_producer_invalid"):
        register_refinement_decision(
            project,
            write_record(
                project, "submissions/mismatched-vote-producer.json", decision
            ),
        )


def test_second_failed_retry_is_durable_and_pauses_without_a_second_vacancy(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    for role in ("critical_reproducibility", "methodology"):
        initial = failed_assessment_record(project, role=role, producer=f"{role}-agent")
        register_refinement_assessment(
            project, write_record(project, f"submissions/{role}-failure.json", initial)
        )
        retry = failed_assessment_record(
            project,
            role=role,
            producer=f"{role}-agent-b",
            retry_of=f"{role}-agent",
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
    assert (
        project.root / "refinement/deliberations/round-001/methodology_retry.json"
    ).is_file()
    assert not (
        project.root / "refinement/deliberations/round-001/methodology_vacancy.json"
    ).exists()


def test_retry_replacement_requires_a_durable_coordinator_authority_update(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    initial = failed_assessment_record(project, role="domain", producer="domain-agent")
    register_refinement_assessment(
        project, write_record(project, "submissions/domain-failure.json", initial)
    )
    retry = failed_assessment_record(
        project,
        role="domain",
        producer="domain-retry-agent",
        retry_of="domain-agent",
    )
    retry["retry"]["authorized_by"] = "arbitrary-coordinator"

    with pytest.raises(ValueError, match="refinement_retry_authority_invalid"):
        register_refinement_assessment(
            project, write_record(project, "submissions/domain-takeover.json", retry)
        )


def test_vacancy_recovers_exact_generated_orphan_and_rejects_altered_bytes(
    tmp_path, monkeypatch
):
    project = prepared_refinement_project(tmp_path / "project")
    initial = failed_assessment_record(
        project,
        role="critical_reproducibility",
        producer="critical_reproducibility-agent",
    )
    register_refinement_assessment(
        project, write_record(project, "submissions/critical-failure.json", initial)
    )
    retry = failed_assessment_record(
        project,
        role="critical_reproducibility",
        producer="critical-retry-agent",
        retry_of="critical_reproducibility-agent",
    )
    retry_path = write_record(project, "submissions/critical-retry.json", retry)
    original_record_state = refinement._record_state_ref

    def interrupt_after_vacancy_file(
        project_arg, relative_path, payload, *, next_action
    ):
        if relative_path.endswith("_vacancy.json"):
            raise RuntimeError("vacancy-state interruption")
        return original_record_state(
            project_arg, relative_path, payload, next_action=next_action
        )

    monkeypatch.setattr(refinement, "_record_state_ref", interrupt_after_vacancy_file)
    with pytest.raises(RuntimeError, match="vacancy-state interruption"):
        register_refinement_assessment(project, retry_path)

    vacancy = (
        project.root
        / "refinement/deliberations/round-001/critical_reproducibility_vacancy.json"
    )
    exact = vacancy.read_bytes()
    monkeypatch.setattr(refinement, "_record_state_ref", original_record_state)
    vacancy.write_bytes(exact + b" ")
    with pytest.raises(ValueError, match="refinement_integrity_failure"):
        register_refinement_assessment(project, retry_path)

    vacancy.write_bytes(exact)
    status = register_refinement_assessment(project, retry_path)
    assert status.phase == "awaiting_independent_assessments"
    assert ResearchProject.open(project.root).state.artifacts[
        "refinement/deliberations/round-001/critical_reproducibility_vacancy.json"
    ].sha256 == refinement._sha256(exact)


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
    original_path = write_record(
        project, "submissions/domain-orphan.json", original_payload
    )
    with pytest.raises(RuntimeError, match="assessment-state interruption"):
        register_refinement_assessment(project, original_path)

    monkeypatch.setattr(refinement, "_record_state_ref", original)
    changed = {**original_payload}
    changed["producer"] = "different-domain-agent"
    with pytest.raises(ValueError, match="refinement_assessment_conflict"):
        register_refinement_assessment(
            project,
            write_record(project, "submissions/domain-changed-orphan.json", changed),
        )
    assert (
        register_refinement_assessment(project, original_path).phase
        == "awaiting_independent_assessments"
    )


def test_request_discriminating_run_accepts_an_envelope_contained_change_request(
    tmp_path
):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(project)
    decision["final_votes"] = [
        {
            **vote,
            "decision": "request_discriminating_run",
            "change_request": decision["change_request"],
        }
        for vote in decision["final_votes"]
    ]
    decision["supporting_roles"] = ["domain", "methodology", "critical_reproducibility"]
    decision["dissenting_roles"] = []
    decision["action"] = "request_discriminating_run"

    status = register_refinement_decision(
        project, write_record(project, "submissions/discriminating-run.json", decision)
    )

    assert status.next_action == "register_refinement_candidate"


@pytest.mark.parametrize("change_request", [None, {}, {"paths": []}])
def test_change_seeking_decision_requires_a_substantive_change_request(
    tmp_path, change_request
):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(project)
    decision["change_request"] = change_request

    with pytest.raises(ValueError, match="refinement_change_request_invalid"):
        register_refinement_decision(
            project,
            write_record(project, "submissions/empty-change-request.json", decision),
        )


def test_change_request_must_be_approved_by_each_supporting_vote(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(project)
    decision["final_votes"][0]["change_request"] = {
        "paths": ["refinement/candidates/candidate-001/tests/test_model.py"]
    }

    with pytest.raises(ValueError, match="refinement_change_request_invalid"):
        register_refinement_decision(
            project,
            write_record(project, "submissions/unapproved-change.json", decision),
        )


def test_non_change_decision_contains_no_change_request(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(
        project,
        votes=("retain_baseline", "retain_baseline", "retain_baseline"),
    )
    decision["action"] = "retain_baseline"
    decision["supporting_roles"] = [
        "domain",
        "methodology",
        "critical_reproducibility",
    ]
    decision["dissenting_roles"] = []
    del decision["change_request"]

    status = register_refinement_decision(
        project, write_record(project, "submissions/retain-baseline.json", decision)
    )

    assert status.phase == "awaiting_finalization"


@pytest.mark.parametrize("rationale", [[], [""], ["valid", 3]])
def test_decision_rationale_is_a_nonempty_list_of_nonempty_strings(tmp_path, rationale):
    project = prepared_refinement_project(tmp_path / "project")
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    decision = valid_decision_record(project)
    decision["rationale"] = rationale

    with pytest.raises(ValueError, match="refinement_decision_schema_invalid"):
        register_refinement_decision(
            project, write_record(project, "submissions/bad-rationale.json", decision)
        )


def test_submission_schema_version_rejects_bool(tmp_path):
    project = prepared_refinement_project(tmp_path / "project")
    payload = valid_assessment_record(project, role="domain")
    payload["schema_version"] = True

    with pytest.raises(ValueError, match="refinement_submission_schema_invalid"):
        register_refinement_assessment(
            project, write_record(project, "submissions/bool-schema.json", payload)
        )


def refinement_project_with_refine_decision(path):
    project = prepared_refinement_project(path)
    register_all_assessments(project)
    register_refinement_rebuttals(project, write_valid_rebuttals(project))
    register_refinement_decision(project, write_valid_decision(project))
    return ResearchProject.open(project.root)


def test_candidate_must_bind_council_change_request(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    manifest = write_refinement_candidate(project, decision_sha256="0" * 64)

    with pytest.raises(ValueError, match="refinement_candidate_binding_invalid"):
        refinement.register_refinement_candidate(project, manifest)


def test_candidate_cannot_bind_outside_candidate_root(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    manifest = write_refinement_candidate(
        project, files=["../../experiment/results.json"]
    )

    with pytest.raises(ValueError, match="refinement_candidate_path_invalid"):
        refinement.register_refinement_candidate(project, manifest)


def _rewrite_candidate_manifest(path, mutate):
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def test_candidate_registration_publishes_one_closed_immutable_identity(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    baseline_before = immutable_stage_twelve_snapshot(project)
    manifest = write_refinement_candidate(project)

    status = refinement.register_refinement_candidate(project, manifest)

    reopened = ResearchProject.open(project.root)
    assert status.candidate_id == "candidate-001"
    assert status.entry_point == "code/model.py"
    assert status.next_action == "prepare_refinement_run"
    assert reopened.state.next_action == "prepare_refinement_run"
    assert (
        reopened.state.artifacts[status.manifest_path].sha256 == status.manifest_sha256
    )
    assert {reference.path for reference in status.files} < set(
        reopened.state.artifacts
    )
    assert immutable_stage_twelve_snapshot(reopened) == baseline_before


def test_candidate_registration_is_byte_identically_idempotent(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    manifest = write_refinement_candidate(project)
    first = refinement.register_refinement_candidate(project, manifest)

    second = refinement.register_refinement_candidate(
        ResearchProject.open(project.root), manifest
    )

    assert second == first


def test_candidate_manifest_is_closed_before_any_state_is_published(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    unknown = manifest.parent.parent / "tests/undeclared.json"
    unknown.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="refinement_candidate_manifest_open"):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


def test_candidate_requires_the_distinct_implementation_producer(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    _rewrite_candidate_manifest(
        manifest, lambda payload: payload.__setitem__("producer", "domain-agent")
    )

    with pytest.raises(ValueError, match="refinement_candidate_producer_invalid"):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


def test_candidate_rejects_symlink_components_before_publication(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    code = manifest.parent.parent / "code"
    target = manifest.parent.parent / "real-code"
    code.rename(target)
    code.symlink_to(target, target_is_directory=True)

    with pytest.raises(
        ValueError,
        match="refinement_candidate_(path|identity)_invalid|refinement_candidate_identity_changed",
    ):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


def test_candidate_replacement_during_package_validation_is_rejected(
    tmp_path, monkeypatch
):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    source = manifest.parent.parent / "code/model.py"
    original_validator = refinement.validate_experiment_package_contract_at

    def replace_after_validation(*args, **kwargs):
        result = original_validator(*args, **kwargs)
        source.write_bytes(source.read_bytes() + b"\n# replaced\n")
        return result

    monkeypatch.setattr(
        refinement, "validate_experiment_package_contract_at", replace_after_validation
    )
    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


def test_candidate_retarget_during_package_validation_is_rejected(
    tmp_path, monkeypatch
):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    code = manifest.parent.parent / "code"
    target = manifest.parent.parent / "retargeted-code"
    original_validator = refinement.validate_experiment_package_contract_at

    def retarget_after_validation(*args, **kwargs):
        result = original_validator(*args, **kwargs)
        code.rename(target)
        code.symlink_to(target, target_is_directory=True)
        return result

    monkeypatch.setattr(
        refinement, "validate_experiment_package_contract_at", retarget_after_validation
    )
    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


def test_candidate_aba_restore_during_package_validation_is_rejected(
    tmp_path, monkeypatch
):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    source = manifest.parent.parent / "code/model.py"
    original = source.read_bytes()
    original_validator = refinement.validate_experiment_package_contract_at

    def restore_after_validation(*args, **kwargs):
        result = original_validator(*args, **kwargs)
        source.write_bytes(b"replacement")
        source.write_bytes(original)
        return result

    monkeypatch.setattr(
        refinement, "validate_experiment_package_contract_at", restore_after_validation
    )
    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


def test_candidate_baseline_aba_during_package_validation_is_rejected(
    tmp_path, monkeypatch
):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    evidence_manifest = next(
        path
        for path in project.state.artifacts
        if path.startswith(".researchclaw/evidence/manifests/")
    )
    evidence = json.loads(
        (project.root / evidence_manifest).read_text(encoding="utf-8")
    )
    baseline_object = project.root / evidence["objects"][0]["object_path"]
    original = baseline_object.read_bytes()
    original_validator = refinement.validate_experiment_package_contract_at

    def restore_baseline_after_validation(*args, **kwargs):
        result = original_validator(*args, **kwargs)
        baseline_object.write_bytes(b"replacement")
        baseline_object.write_bytes(original)
        return result

    monkeypatch.setattr(
        refinement,
        "validate_experiment_package_contract_at",
        restore_baseline_after_validation,
    )
    with pytest.raises(ValueError, match="refinement_candidate_baseline_changed"):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


@pytest.mark.parametrize(
    ("target_kind", "error"),
    (
        ("candidate", "refinement_candidate_identity_changed"),
        ("manifest", "refinement_candidate_identity_changed"),
        ("baseline", "refinement_candidate_baseline_changed"),
    ),
)
def test_candidate_publication_rolls_back_when_identity_changes_before_publish(
    tmp_path, monkeypatch, target_kind, error
):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    if target_kind == "candidate":
        target = manifest.parent.parent / "code/model.py"
    elif target_kind == "manifest":
        target = manifest
    else:
        evidence_manifest = next(
            path
            for path in project.state.artifacts
            if path.startswith(".researchclaw/evidence/manifests/")
        )
        evidence = json.loads(
            (project.root / evidence_manifest).read_text(encoding="utf-8")
        )
        target = project.root / evidence["objects"][0]["object_path"]

    def mutate_then_publish(current, state):
        target.write_bytes(target.read_bytes() + b"publication race")
        current.persist_state(state)

    monkeypatch.setattr(
        refinement, "_publish_candidate_state", mutate_then_publish, raising=False
    )

    with pytest.raises(ValueError, match=error):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


def test_candidate_rejects_an_outside_project_hardlink_without_publication(tmp_path):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    before = project.state
    manifest = write_refinement_candidate(project)
    source = manifest.parent.parent / "code/model.py"
    outside = tmp_path / "outside-model.py"
    outside.hardlink_to(source)

    with pytest.raises(ValueError, match="refinement_candidate_identity_changed"):
        refinement.register_refinement_candidate(project, manifest)

    assert ResearchProject.open(project.root).state == before


def test_candidate_accepts_absolute_manifest_below_a_symlinked_external_ancestor(
    tmp_path,
):
    project = refinement_project_with_refine_decision(tmp_path / "project")
    manifest = write_refinement_candidate(project)
    alias = tmp_path / "external-alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    aliased_manifest = alias / project.root.name / manifest.relative_to(project.root)

    status = refinement.register_refinement_candidate(project, aliased_manifest)

    assert status.manifest_path == manifest.relative_to(project.root).as_posix()


def test_bounded_snapshot_rejects_oversize_before_reading_file_bytes(
    tmp_path, monkeypatch
):
    path = tmp_path / "oversize.json"
    path.write_bytes(b"x" * 17)
    reads = 0
    original_read = refinement.os.read

    def count_reads(descriptor, size):
        nonlocal reads
        reads += 1
        return original_read(descriptor, size)

    monkeypatch.setattr(refinement.os, "read", count_reads)

    with pytest.raises(ValueError, match="bounded_snapshot_rejected"):
        refinement._secure_snapshot(
            tmp_path,
            path.name,
            maximum_bytes=16,
            read_payload=True,
            error_code="bounded_snapshot_rejected",
        )

    assert reads == 0
