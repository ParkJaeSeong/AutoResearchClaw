"""Prepare immutable, evidence-bound inputs for Stage 15 research decisions.

This module verifies historical Stage 14 evidence and publishes its canonical
decision packet. It does not make scientific decisions or execute follow-up.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from .decision_report import render_decision_report
from .models import ArtifactRef, StageStatus
from .paths import resolve_project_artifact
from .project import ResearchProject
from .refinement import (
    _canonical_json,
    _read_bounded_json,
    _secure_snapshot,
    _write_exclusive,
)
from .result_analysis import validate_completed_analysis
from .transactions import project_mutation

DECISION_PACKET_PATH = "analysis/research-decision/evidence_packet.json"
DECISION_REBUTTALS_PATH = "analysis/research-decision/rebuttals.json"
DECISION_RESULT_PATH = "analysis/decision.json"
DECISION_REPORT_PATH = "analysis/decision.md"
ROLES = ("domain", "methodology", "critical_reproducibility")
_SCHEMA_VERSION = 1
_STAGE_ID = 15
_RECOMMENDATIONS = frozenset({"proceed", "refine", "pivot"})


def _packet_reference(payload: bytes) -> ArtifactRef:
    return ArtifactRef(
        DECISION_PACKET_PATH, hashlib.sha256(payload).hexdigest(), len(payload)
    )


def _build_packet(history: Mapping[str, object]) -> dict[str, object]:
    stage_14_packet = history.get("evidence_packet")
    references = history.get("references")
    if not isinstance(stage_14_packet, Mapping) or not isinstance(references, list):
        raise ValueError("decision_history_invalid")
    research_evidence = stage_14_packet.get("inputs")
    if not isinstance(research_evidence, Mapping):
        raise ValueError("decision_history_invalid")
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": stage_14_packet.get("project_id"),
        "stage_id": _STAGE_ID,
        "inputs": {
            "analysis_records": references,
            "research_evidence": dict(research_evidence),
        },
        "roles": list(ROLES),
        "allowed_outputs": [
            *(f"analysis/research-decision/reviews/{role}.json" for role in ROLES),
            DECISION_REBUTTALS_PATH,
            DECISION_RESULT_PATH,
            DECISION_REPORT_PATH,
        ],
        "execution_allowed": False,
    }


def _validate_packet(
    project: ResearchProject, history: Mapping[str, object]
) -> dict[str, object]:
    expected = _build_packet(history)
    expected_bytes = _canonical_json(expected)
    reference = project.state.artifacts.get(DECISION_PACKET_PATH)
    if reference is None or reference != _packet_reference(expected_bytes):
        raise ValueError("decision_packet_unregistered")
    destination = resolve_project_artifact(project.root, DECISION_PACKET_PATH)
    try:
        actual, actual_bytes = _read_bounded_json(destination)
    except ValueError as error:
        raise ValueError("decision_packet_invalid") from error
    _secure_snapshot(
        project.root,
        DECISION_PACKET_PATH,
        expected=reference,
        maximum_bytes=reference.size,
        error_code="decision_packet_invalid",
    )
    if actual != expected or actual_bytes != expected_bytes:
        raise ValueError("decision_packet_invalid")
    return expected


def _record_reference(path: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(path, hashlib.sha256(payload).hexdigest(), len(payload))


def _submission_path(project: ResearchProject, value: str | Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    try:
        return resolve_project_artifact(project.root, str(candidate))
    except ValueError as error:
        raise ValueError("decision_submission_path_invalid") from error


def _read_submission(
    project: ResearchProject, value: str | Path
) -> tuple[dict[str, object], bytes]:
    try:
        payload, _ = _read_bounded_json(_submission_path(project, value))
        return payload, _canonical_json(payload)
    except ValueError as error:
        raise ValueError("decision_submission_invalid") from error


def _read_record(
    project: ResearchProject, path: str
) -> tuple[dict[str, object], bytes] | None:
    destination = resolve_project_artifact(project.root, path)
    if not os.path.lexists(destination):
        if path in project.state.artifacts:
            raise ValueError("decision_integrity_failure")
        return None
    try:
        payload, raw = _read_bounded_json(destination)
    except ValueError as error:
        raise ValueError("decision_integrity_failure") from error
    reference = _record_reference(path, raw)
    if project.state.artifacts.get(path) != reference:
        raise ValueError("decision_integrity_failure")
    try:
        canonical = _canonical_json(payload)
    except ValueError as error:
        raise ValueError("decision_integrity_failure") from error
    if canonical != raw:
        raise ValueError("decision_integrity_failure")
    return payload, raw


def _read_unregistered_record(
    project: ResearchProject, path: str, *, conflict: str
) -> bytes | None:
    if path in project.state.artifacts:
        return None
    destination = resolve_project_artifact(project.root, path)
    if not os.path.lexists(destination):
        return None
    try:
        payload, raw = _read_bounded_json(destination)
        if _canonical_json(payload) != raw:
            raise ValueError(conflict)
    except ValueError as error:
        raise ValueError(conflict) from error
    return raw


def _write_record(
    project: ResearchProject, path: str, payload: bytes, *, conflict: str
) -> ResearchProject:
    destination = resolve_project_artifact(project.root, path)
    try:
        _write_exclusive(destination, payload)
    except FileExistsError:
        try:
            existing_payload, existing = _read_bounded_json(destination)
            if _canonical_json(existing_payload) != existing:
                raise ValueError(conflict)
        except ValueError as error:
            raise ValueError(conflict) from error
        if existing != payload:
            raise ValueError(conflict)
    current = ResearchProject.open_readonly(project.root)
    reference = _record_reference(path, payload)
    if current.state.artifacts.get(path) not in {None, reference}:
        raise ValueError(conflict)
    if current.state.artifacts.get(path) is None:
        current.persist_state(
            replace(
                current.state,
                artifacts={**current.state.artifacts, path: reference},
            )
        )
    return ResearchProject.open_readonly(project.root)


def _nonempty_text(value: object, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(error)
    return value


def _text_list(
    value: object, error: str, *, require_nonempty: bool = False
) -> list[str]:
    if (
        not isinstance(value, list)
        or (require_nonempty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(error)
    return list(value)


def _evidence_paths(packet: Mapping[str, object]) -> frozenset[str]:
    paths: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, Mapping):
            path = value.get("path")
            if isinstance(path, str):
                paths.add(path)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(packet.get("inputs"))
    return frozenset(paths)


def _evidence_refs(value: object, packet: Mapping[str, object]) -> list[str]:
    refs = _text_list(
        value, "decision_evidence_reference_invalid", require_nonempty=True
    )
    if len(refs) != len(set(refs)) or not set(refs).issubset(_evidence_paths(packet)):
        raise ValueError("decision_evidence_reference_invalid")
    return refs


def _statements(
    value: object,
    packet: Mapping[str, object],
    error: str,
    *,
    require_nonempty: bool = False,
) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or (require_nonempty and not value):
        raise ValueError(error)
    statements: list[Mapping[str, object]] = []
    for statement in value:
        if not isinstance(statement, Mapping) or set(statement) != {
            "text",
            "evidence_refs",
        }:
            raise ValueError(error)
        _nonempty_text(statement.get("text"), error)
        _evidence_refs(statement.get("evidence_refs"), packet)
        statements.append(statement)
    return statements


def _submission_base(
    payload: Mapping[str, object],
    project: ResearchProject,
    packet_ref: ArtifactRef,
    extra_fields: set[str],
) -> str:
    expected = {
        "schema_version",
        "project_id",
        "evidence_packet_sha256",
        "producer",
    } | extra_fields
    version = payload.get("schema_version")
    if (
        set(payload) != expected
        or version != _SCHEMA_VERSION
        or isinstance(version, bool)
    ):
        raise ValueError("decision_submission_schema_invalid")
    if (
        payload.get("project_id") != project.state.project_id
        or payload.get("evidence_packet_sha256") != packet_ref.sha256
    ):
        raise ValueError("decision_submission_binding_invalid")
    return _nonempty_text(payload.get("producer"), "decision_producer_invalid")


def _parse_review(
    payload: Mapping[str, object],
    *,
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
) -> tuple[str, str]:
    producer = _submission_base(
        payload,
        project,
        packet_ref,
        {
            "role",
            "recommendation",
            "rationale",
            "claim_scope",
            "mandatory_follow_up",
            "optional_follow_up",
            "alternatives",
            "questions",
        },
    )
    role = payload.get("role")
    recommendation = payload.get("recommendation")
    if role not in ROLES:
        raise ValueError("decision_role_invalid")
    if recommendation not in _RECOMMENDATIONS:
        raise ValueError("decision_review_schema_invalid")
    _statements(
        payload.get("rationale"),
        packet,
        "decision_review_schema_invalid",
        require_nonempty=True,
    )
    _statements(
        payload.get("claim_scope"),
        packet,
        "decision_review_schema_invalid",
        require_nonempty=True,
    )
    mandatory = _statements(
        payload.get("mandatory_follow_up"), packet, "decision_review_schema_invalid"
    )
    _statements(
        payload.get("optional_follow_up"), packet, "decision_review_schema_invalid"
    )
    _statements(
        payload.get("alternatives"),
        packet,
        "decision_review_schema_invalid",
        require_nonempty=True,
    )
    _text_list(payload.get("questions"), "decision_review_schema_invalid")
    if recommendation in {"refine", "pivot"} and not mandatory:
        raise ValueError("decision_review_schema_invalid")
    return str(role), producer


def _review_records(
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
    *,
    ignore_unregistered_path: str | None = None,
) -> dict[str, tuple[dict[str, object], bytes, str]]:
    records: dict[str, tuple[dict[str, object], bytes, str]] = {}
    producers: set[str] = set()
    for role in ROLES:
        path = f"analysis/research-decision/reviews/{role}.json"
        if path == ignore_unregistered_path and path not in project.state.artifacts:
            continue
        record = _read_record(project, path)
        if record is None:
            continue
        parsed_role, producer = _parse_review(
            record[0], project=project, packet=packet, packet_ref=packet_ref
        )
        if parsed_role != role or producer in producers:
            raise ValueError("decision_integrity_failure")
        producers.add(producer)
        records[role] = (record[0], record[1], producer)
    return records


def _expected_review_hashes(
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
) -> dict[str, str]:
    return {role: hashlib.sha256(reviews[role][1]).hexdigest() for role in ROLES}


def _parse_rebuttals(
    payload: Mapping[str, object],
    *,
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
) -> str:
    producer = _submission_base(
        payload, project, packet_ref, {"review_hashes", "responses"}
    )
    reviewer_producers = {record[2] for record in reviews.values()}
    if producer in reviewer_producers:
        raise ValueError("decision_coordinator_producer_invalid")
    hashes = payload.get("review_hashes")
    if not isinstance(hashes, Mapping) or dict(hashes) != _expected_review_hashes(
        reviews
    ):
        raise ValueError("decision_rebuttal_binding_invalid")
    responses = payload.get("responses")
    if not isinstance(responses, list) or len(responses) != len(ROLES):
        raise ValueError("decision_rebuttal_role_invalid")
    seen: set[str] = set()
    for response in responses:
        if not isinstance(response, Mapping) or set(response) != {
            "role",
            "producer",
            "review_sha256",
            "challenges",
            "responses",
            "final_recommendation",
        }:
            raise ValueError("decision_rebuttal_schema_invalid")
        role = response.get("role")
        if role not in reviews or role in seen:
            raise ValueError("decision_rebuttal_role_invalid")
        role = str(role)
        seen.add(role)
        if response.get("producer") != reviews[role][2]:
            raise ValueError("decision_rebuttal_producer_invalid")
        if response.get("review_sha256") != hashes[role]:
            raise ValueError("decision_rebuttal_binding_invalid")
        _text_list(
            response.get("challenges"),
            "decision_rebuttal_schema_invalid",
            require_nonempty=True,
        )
        _statements(
            response.get("responses"),
            packet,
            "decision_rebuttal_schema_invalid",
            require_nonempty=True,
        )
        final = response.get("final_recommendation")
        if final is not None and final not in _RECOMMENDATIONS:
            raise ValueError("decision_rebuttal_schema_invalid")
    if seen != set(ROLES):
        raise ValueError("decision_rebuttal_role_invalid")
    return producer


def _registered_rebuttals(
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
) -> tuple[dict[str, object], bytes, str] | None:
    record = _read_record(project, DECISION_REBUTTALS_PATH)
    if record is None:
        return None
    if set(reviews) != set(ROLES):
        raise ValueError("decision_integrity_failure")
    producer = _parse_rebuttals(
        record[0],
        project=project,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
    )
    return record[0], record[1], producer


def _parse_result(
    payload: Mapping[str, object],
    *,
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
    rebuttals: tuple[dict[str, object], bytes, str],
) -> str:
    producer = _submission_base(
        payload,
        project,
        packet_ref,
        {
            "review_hashes",
            "rebuttals_sha256",
            "decision",
            "disposition",
            "rationale",
            "claim_scope",
            "limitations",
            "mandatory_follow_up",
            "optional_follow_up",
            "unresolved_issues",
            "disagreements",
            "recommended_stage",
        },
    )
    reviewer_producers = {record[2] for record in reviews.values()}
    if producer != rebuttals[2] or producer in reviewer_producers:
        raise ValueError("decision_coordinator_producer_invalid")
    hashes = payload.get("review_hashes")
    if not isinstance(hashes, Mapping) or dict(hashes) != _expected_review_hashes(
        reviews
    ):
        raise ValueError("decision_result_binding_invalid")
    if payload.get("rebuttals_sha256") != hashlib.sha256(rebuttals[1]).hexdigest():
        raise ValueError("decision_result_binding_invalid")

    decision = payload.get("decision")
    if decision is not None and decision not in _RECOMMENDATIONS:
        raise ValueError("decision_result_schema_invalid")
    _statements(
        payload.get("rationale"),
        packet,
        "decision_result_schema_invalid",
        require_nonempty=True,
    )
    _statements(
        payload.get("claim_scope"),
        packet,
        "decision_result_schema_invalid",
        require_nonempty=True,
    )
    _statements(
        payload.get("limitations"),
        packet,
        "decision_result_schema_invalid",
        require_nonempty=True,
    )
    mandatory = _statements(
        payload.get("mandatory_follow_up"), packet, "decision_result_schema_invalid"
    )
    _statements(
        payload.get("optional_follow_up"), packet, "decision_result_schema_invalid"
    )
    unresolved = _statements(
        payload.get("unresolved_issues"), packet, "decision_result_schema_invalid"
    )
    disagreements = payload.get("disagreements")
    if not isinstance(disagreements, list):
        raise ValueError("decision_result_schema_invalid")  # noqa: TRY004
    seen_disagreements: set[str] = set()
    for disagreement in disagreements:
        if not isinstance(disagreement, Mapping) or set(disagreement) != {
            "role",
            "text",
            "evidence_refs",
        }:
            raise ValueError("decision_result_schema_invalid")
        role = disagreement.get("role")
        if role not in ROLES or role in seen_disagreements:
            raise ValueError("decision_result_schema_invalid")
        seen_disagreements.add(str(role))
        _nonempty_text(disagreement.get("text"), "decision_result_schema_invalid")
        _evidence_refs(disagreement.get("evidence_refs"), packet)

    target = {"proceed": None, "refine": 13, "pivot": 8, None: None}[decision]
    if payload.get("recommended_stage") != target or isinstance(
        payload.get("recommended_stage"), bool
    ):
        raise ValueError("decision_result_schema_invalid")
    if decision is None:
        if payload.get("disposition") != "unresolved" or not unresolved:
            raise ValueError("decision_result_schema_invalid")
    else:
        if payload.get("disposition") != "agreed":
            raise ValueError("decision_result_schema_invalid")
        responses = rebuttals[0].get("responses")
        if not isinstance(responses, list) or any(
            not isinstance(response, Mapping)
            or response.get("final_recommendation") != decision
            for response in responses
        ):
            raise ValueError("decision_consent_invalid")
    if decision in {"refine", "pivot"} and not mandatory:
        raise ValueError("decision_result_schema_invalid")
    return producer


def _analysis_context(project: ResearchProject) -> dict[str, object]:
    path = "analysis/results.json"
    reference = project.state.artifacts.get(path)
    if reference is None:
        raise ValueError("decision_integrity_failure")
    try:
        _secure_snapshot(
            project.root,
            path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="decision_integrity_failure",
        )
        payload, raw = _read_bounded_json(resolve_project_artifact(project.root, path))
    except ValueError as error:
        raise ValueError("decision_integrity_failure") from error
    if _record_reference(path, raw) != reference:
        raise ValueError("decision_integrity_failure")
    return payload


def _source_context(project: ResearchProject) -> dict[str, object]:
    path = "analysis/evidence_packet.json"
    reference = project.state.artifacts.get(path)
    if reference is None:
        raise ValueError("decision_integrity_failure")
    try:
        _secure_snapshot(
            project.root,
            path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="decision_integrity_failure",
        )
        packet, raw = _read_bounded_json(resolve_project_artifact(project.root, path))
    except ValueError as error:
        raise ValueError("decision_integrity_failure") from error
    if _record_reference(path, raw) != reference:
        raise ValueError("decision_integrity_failure")
    context = packet.get("selection_context")
    if not isinstance(context, Mapping):
        raise ValueError("decision_integrity_failure")
    return dict(context)


def _report_payload(
    project: ResearchProject,
    result: Mapping[str, object],
    packet: Mapping[str, object],
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
    rebuttals: tuple[dict[str, object], bytes, str],
) -> dict[str, object]:
    return {
        "decision_result": dict(result),
        "evidence_packet": dict(packet),
        "reviews": [reviews[role][0] for role in ROLES],
        "rebuttals": rebuttals[0],
        "analysis_context": _analysis_context(project),
        "source_context": _source_context(project),
    }


def _registered_result(
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
    rebuttals: tuple[dict[str, object], bytes, str] | None,
) -> tuple[dict[str, object], bytes] | None:
    record = _read_record(project, DECISION_RESULT_PATH)
    if record is None:
        return None
    if rebuttals is None:
        raise ValueError("decision_integrity_failure")
    _parse_result(
        record[0],
        project=project,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
        rebuttals=rebuttals,
    )
    report_ref = project.state.artifacts.get(DECISION_REPORT_PATH)
    if report_ref is None:
        raise ValueError("decision_integrity_failure")
    expected_report = render_decision_report(
        _report_payload(project, record[0], packet, reviews, rebuttals)
    ).encode("utf-8")
    try:
        _, report = _secure_snapshot(
            project.root,
            DECISION_REPORT_PATH,
            expected=report_ref,
            maximum_bytes=report_ref.size,
            read_payload=True,
            error_code="decision_integrity_failure",
        )
    except ValueError as error:
        raise ValueError("decision_integrity_failure") from error
    if report != expected_report:
        raise ValueError("decision_integrity_failure")
    return record


def _decision_records(
    project: ResearchProject, packet: Mapping[str, object]
) -> tuple[
    ArtifactRef,
    dict[str, tuple[dict[str, object], bytes, str]],
    tuple[dict[str, object], bytes, str] | None,
    tuple[dict[str, object], bytes] | None,
]:
    packet_ref = project.state.artifacts.get(DECISION_PACKET_PATH)
    if packet_ref is None:
        raise ValueError("decision_packet_unregistered")
    reviews = _review_records(project, packet, packet_ref)
    rebuttals = _registered_rebuttals(project, packet, packet_ref, reviews)
    result = _registered_result(project, packet, packet_ref, reviews, rebuttals)
    return packet_ref, reviews, rebuttals, result


def _registration_status(
    project: ResearchProject, packet: Mapping[str, object]
) -> dict[str, object]:
    _, reviews, rebuttals, result = _decision_records(project, packet)
    decision = None
    if result is not None:
        decision = result[0].get("decision")
        if decision == "proceed":
            phase, next_action = "complete", "unsupported_stage_16"
        elif decision is None:
            phase, next_action = "needs_direction", "request_research_direction"
        else:
            phase, next_action = "follow_up_required", "report_research_follow_up"
    elif rebuttals is not None:
        phase, next_action = "awaiting_decision", "register_decision_result"
    elif len(reviews) == len(ROLES):
        phase, next_action = "awaiting_rebuttals", "register_decision_rebuttals"
    else:
        phase, next_action = (
            "awaiting_independent_recommendations",
            "register_decision_review",
        )
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project.state.project_id,
        "stage_id": _STAGE_ID,
        "current_stage": project.state.current_stage,
        "phase": phase,
        "next_action": next_action,
        "registered_roles": [role for role in ROLES if role in reviews],
        "review_hashes": {
            role: hashlib.sha256(record[1]).hexdigest()
            for role, record in reviews.items()
        },
        "rebuttals_sha256": (
            None if rebuttals is None else hashlib.sha256(rebuttals[1]).hexdigest()
        ),
        "result_sha256": (
            None if result is None else hashlib.sha256(result[1]).hexdigest()
        ),
        "decision": decision,
        "evidence_packet": dict(packet),
    }


@project_mutation
def prepare_research_decision(project: ResearchProject) -> dict[str, object]:
    """Create or exactly replay the canonical Stage 15 evidence packet."""
    current = ResearchProject.open_readonly(project.root)
    stage_valid = current.state.current_stage == _STAGE_ID or (
        current.state.current_stage == _STAGE_ID + 1
        and _STAGE_ID in current.state.completed_stages
    )
    if not stage_valid or 14 not in current.state.completed_stages:
        raise ValueError("decision_stage_invalid")
    history = validate_completed_analysis(current)
    if DECISION_PACKET_PATH in current.state.artifacts:
        packet = _validate_packet(current, history)
        research_decision_status(current)
        return packet
    if current.state.current_stage != _STAGE_ID:
        raise ValueError("decision_stage_invalid")
    packet = _build_packet(history)
    packet_bytes = _canonical_json(packet)
    packet_ref = _packet_reference(packet_bytes)
    destination = resolve_project_artifact(current.root, DECISION_PACKET_PATH)
    try:
        _write_exclusive(destination, packet_bytes)
    except FileExistsError:
        try:
            _, existing = _read_bounded_json(destination)
        except ValueError as error:
            raise ValueError("decision_packet_conflict") from error
        if existing != packet_bytes:
            raise ValueError("decision_packet_conflict")

    current = ResearchProject.open_readonly(current.root)
    if (
        _canonical_json(_build_packet(validate_completed_analysis(current)))
        != packet_bytes
    ):
        raise ValueError("decision_history_changed")
    existing_ref = current.state.artifacts.get(DECISION_PACKET_PATH)
    if existing_ref not in {None, packet_ref}:
        raise ValueError("decision_packet_conflict")
    if existing_ref is None:
        current.persist_state(
            replace(
                current.state,
                artifacts={**current.state.artifacts, DECISION_PACKET_PATH: packet_ref},
            )
        )
    current = ResearchProject.open_readonly(current.root)
    return _validate_packet(current, validate_completed_analysis(current))


def research_decision_status(project: ResearchProject) -> dict[str, object]:
    """Return verified Stage 15 preparation status without changing project state."""
    current = ResearchProject.open_readonly(project.root)
    stage_valid = current.state.current_stage == _STAGE_ID or (
        current.state.current_stage == _STAGE_ID + 1
        and _STAGE_ID in current.state.completed_stages
    )
    if not stage_valid or 14 not in current.state.completed_stages:
        raise ValueError("decision_stage_invalid")
    history = validate_completed_analysis(current)
    if DECISION_PACKET_PATH not in current.state.artifacts:
        if current.state.current_stage != _STAGE_ID:
            raise ValueError("decision_stage_invalid")
        return {
            "schema_version": _SCHEMA_VERSION,
            "project_id": current.state.project_id,
            "stage_id": _STAGE_ID,
            "current_stage": current.state.current_stage,
            "phase": "awaiting_preparation",
            "next_action": "prepare_research_decision",
            "registered_roles": [],
            "evidence_packet": None,
        }
    packet = _validate_packet(current, history)
    status = _registration_status(current, packet)
    if status["result_sha256"] is not None:
        decision = status["decision"]
        if decision == "proceed":
            valid_terminal = (
                current.state.current_stage == _STAGE_ID + 1
                and _STAGE_ID in current.state.completed_stages
                and current.state.next_action == "unsupported_stage_16"
            )
        else:
            expected_action = (
                "request_research_direction"
                if decision is None
                else "report_research_follow_up"
            )
            valid_terminal = (
                current.state.current_stage == _STAGE_ID
                and _STAGE_ID not in current.state.completed_stages
                and current.state.next_action == expected_action
            )
        if not valid_terminal:
            raise ValueError("decision_integrity_failure")
    elif current.state.current_stage != _STAGE_ID:
        raise ValueError("decision_integrity_failure")
    return status


@project_mutation
def register_decision_review(
    project: ResearchProject, submission_path: str | Path
) -> dict[str, object]:
    """Register one evidence-bound independent Stage 15 recommendation."""
    current = ResearchProject.open_readonly(project.root)
    packet = _validate_packet(current, validate_completed_analysis(current))
    packet_ref = current.state.artifacts[DECISION_PACKET_PATH]
    source, source_bytes = _read_submission(current, submission_path)
    role, producer = _parse_review(
        source, project=current, packet=packet, packet_ref=packet_ref
    )
    target = f"analysis/research-decision/reviews/{role}.json"
    orphan = _read_unregistered_record(
        current, target, conflict="decision_review_conflict"
    )
    reviews = _review_records(
        current,
        packet,
        packet_ref,
        ignore_unregistered_path=target if orphan is not None else None,
    )
    existing = reviews.get(role)
    if existing is not None:
        if source_bytes != existing[1]:
            raise ValueError("decision_review_conflict")
        return _registration_status(current, packet)
    if current.state.current_stage != _STAGE_ID:
        raise ValueError("decision_order_invalid")
    if _read_record(current, DECISION_REBUTTALS_PATH) is not None:
        raise ValueError("decision_order_invalid")
    if producer in {record[2] for record in reviews.values()}:
        raise ValueError("decision_producer_duplicate")
    if orphan is not None and orphan != source_bytes:
        raise ValueError("decision_review_conflict")
    current = _write_record(
        current, target, source_bytes, conflict="decision_review_conflict"
    )
    return _registration_status(
        current, _validate_packet(current, validate_completed_analysis(current))
    )


@project_mutation
def register_decision_rebuttals(
    project: ResearchProject, submission_path: str | Path
) -> dict[str, object]:
    """Register the single response round after all independent reviews."""
    current = ResearchProject.open_readonly(project.root)
    packet = _validate_packet(current, validate_completed_analysis(current))
    packet_ref = current.state.artifacts[DECISION_PACKET_PATH]
    reviews = _review_records(current, packet, packet_ref)
    if set(reviews) != set(ROLES):
        raise ValueError("decision_order_invalid")
    source, source_bytes = _read_submission(current, submission_path)
    _parse_rebuttals(
        source,
        project=current,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
    )
    orphan = _read_unregistered_record(
        current, DECISION_REBUTTALS_PATH, conflict="decision_rebuttal_conflict"
    )
    if orphan is not None and orphan != source_bytes:
        raise ValueError("decision_rebuttal_conflict")
    existing = (
        None
        if orphan is not None
        else _registered_rebuttals(current, packet, packet_ref, reviews)
    )
    if existing is not None:
        if source_bytes != existing[1]:
            raise ValueError("decision_rebuttal_conflict")
        return _registration_status(current, packet)
    if current.state.current_stage != _STAGE_ID:
        raise ValueError("decision_order_invalid")
    if _read_record(current, DECISION_RESULT_PATH) is not None:
        raise ValueError("decision_order_invalid")
    current = _write_record(
        current,
        DECISION_REBUTTALS_PATH,
        source_bytes,
        conflict="decision_rebuttal_conflict",
    )
    return _registration_status(
        current, _validate_packet(current, validate_completed_analysis(current))
    )


def _write_report_exclusive(project: ResearchProject, payload: bytes) -> None:
    destination = resolve_project_artifact(project.root, DECISION_REPORT_PATH)
    try:
        _write_exclusive(destination, payload)
    except FileExistsError:
        expected = _record_reference(DECISION_REPORT_PATH, payload)
        try:
            _, existing = _secure_snapshot(
                project.root,
                DECISION_REPORT_PATH,
                expected=expected,
                maximum_bytes=expected.size,
                read_payload=True,
                error_code="decision_report_conflict",
            )
        except ValueError as error:
            raise ValueError("decision_report_conflict") from error
        if existing != payload:
            raise ValueError("decision_report_conflict")


@project_mutation
def register_decision_result(
    project: ResearchProject, submission_path: str | Path
) -> dict[str, object]:
    """Publish an authored terminal decision without executing its direction."""
    current = ResearchProject.open_readonly(project.root)
    packet = _validate_packet(current, validate_completed_analysis(current))
    packet_ref = current.state.artifacts[DECISION_PACKET_PATH]
    reviews = _review_records(current, packet, packet_ref)
    rebuttals = _registered_rebuttals(current, packet, packet_ref, reviews)
    if set(reviews) != set(ROLES) or rebuttals is None:
        raise ValueError("decision_order_invalid")
    source, source_bytes = _read_submission(current, submission_path)
    _parse_result(
        source,
        project=current,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
        rebuttals=rebuttals,
    )

    result_path = resolve_project_artifact(current.root, DECISION_RESULT_PATH)
    orphan = _read_unregistered_record(
        current, DECISION_RESULT_PATH, conflict="decision_result_conflict"
    )
    if orphan is not None and orphan != source_bytes:
        raise ValueError("decision_result_conflict")
    existing = (
        None
        if orphan is not None
        else _registered_result(current, packet, packet_ref, reviews, rebuttals)
    )
    if existing is not None:
        if source_bytes != existing[1]:
            raise ValueError("decision_result_conflict")
        return _registration_status(current, packet)
    if current.state.current_stage != _STAGE_ID:
        raise ValueError("decision_order_invalid")

    report_bytes = render_decision_report(
        _report_payload(current, source, packet, reviews, rebuttals)
    ).encode("utf-8")
    if DECISION_REPORT_PATH in current.state.artifacts:
        raise ValueError("decision_result_conflict")
    report_path = resolve_project_artifact(current.root, DECISION_REPORT_PATH)
    if os.path.lexists(report_path):
        try:
            expected_report = _record_reference(DECISION_REPORT_PATH, report_bytes)
            _, existing_report = _secure_snapshot(
                current.root,
                DECISION_REPORT_PATH,
                expected=expected_report,
                maximum_bytes=expected_report.size,
                read_payload=True,
                error_code="decision_report_conflict",
            )
        except ValueError as error:
            raise ValueError("decision_report_conflict") from error
        if existing_report != report_bytes:
            raise ValueError("decision_report_conflict")

    try:
        _write_exclusive(result_path, source_bytes)
    except FileExistsError:
        try:
            existing_payload, existing_bytes = _read_bounded_json(result_path)
            if _canonical_json(existing_payload) != existing_bytes:
                raise ValueError("decision_result_conflict")
        except ValueError as error:
            raise ValueError("decision_result_conflict") from error
        if existing_bytes != source_bytes:
            raise ValueError("decision_result_conflict")
    _write_report_exclusive(current, report_bytes)

    # Re-open and revalidate every historical and deliberation binding before state.
    current = ResearchProject.open_readonly(current.root)
    packet = _validate_packet(current, validate_completed_analysis(current))
    packet_ref = current.state.artifacts[DECISION_PACKET_PATH]
    reviews = _review_records(current, packet, packet_ref)
    rebuttals = _registered_rebuttals(current, packet, packet_ref, reviews)
    if rebuttals is None:
        raise ValueError("decision_integrity_failure")
    _parse_result(
        source,
        project=current,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
        rebuttals=rebuttals,
    )
    expected_report_bytes = render_decision_report(
        _report_payload(current, source, packet, reviews, rebuttals)
    ).encode("utf-8")
    if expected_report_bytes != report_bytes:
        raise ValueError("decision_integrity_failure")
    result_ref = _record_reference(DECISION_RESULT_PATH, source_bytes)
    report_ref = _record_reference(DECISION_REPORT_PATH, report_bytes)
    for path, reference in (
        (DECISION_RESULT_PATH, result_ref),
        (DECISION_REPORT_PATH, report_ref),
    ):
        if current.state.artifacts.get(path) not in {None, reference}:
            raise ValueError("decision_result_conflict")

    registered_artifacts = {
        **current.state.artifacts,
        DECISION_RESULT_PATH: result_ref,
        DECISION_REPORT_PATH: report_ref,
    }
    if source["decision"] == "proceed":
        completed = current.state.completed_stages
        if _STAGE_ID not in completed:
            completed = (*completed, _STAGE_ID)
        updated = replace(
            current.state,
            current_stage=_STAGE_ID + 1,
            completed_stages=completed,
            status=StageStatus.READY,
            next_action="unsupported_stage_16",
            artifacts=registered_artifacts,
            last_error=None,
        )
    else:
        action = (
            "request_research_direction"
            if source["decision"] is None
            else "report_research_follow_up"
        )
        updated = replace(
            current.state,
            status=StageStatus.READY,
            next_action=action,
            artifacts=registered_artifacts,
            last_error=None,
        )
    if updated != current.state:
        current.persist_state(updated)
    complete = ResearchProject.open_readonly(current.root)
    return _registration_status(
        complete, _validate_packet(complete, validate_completed_analysis(complete))
    )
