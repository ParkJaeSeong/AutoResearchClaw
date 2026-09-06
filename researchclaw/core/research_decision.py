"""Prepare immutable, evidence-bound inputs for Stage 15 research decisions.

This module verifies historical Stage 14 evidence and publishes its canonical
decision packet. It does not make scientific decisions or execute follow-up.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import hashlib

from .models import ArtifactRef
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


@project_mutation
def prepare_research_decision(project: ResearchProject) -> dict[str, object]:
    """Create or exactly replay the canonical Stage 15 evidence packet."""
    current = ResearchProject.open_readonly(project.root)
    if current.state.current_stage != _STAGE_ID or 14 not in current.state.completed_stages:
        raise ValueError("decision_stage_invalid")
    history = validate_completed_analysis(current)
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
    if _canonical_json(_build_packet(validate_completed_analysis(current))) != packet_bytes:
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
    if current.state.current_stage < _STAGE_ID or 14 not in current.state.completed_stages:
        raise ValueError("decision_stage_invalid")
    if (
        current.state.current_stage != _STAGE_ID
        and DECISION_PACKET_PATH not in current.state.artifacts
    ):
        raise ValueError("decision_stage_invalid")
    history = validate_completed_analysis(current)
    if DECISION_PACKET_PATH not in current.state.artifacts:
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
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": current.state.project_id,
        "stage_id": _STAGE_ID,
        "current_stage": current.state.current_stage,
        "phase": "awaiting_independent_recommendations",
        "next_action": "register_decision_review",
        "registered_roles": [],
        "evidence_packet": packet,
    }
