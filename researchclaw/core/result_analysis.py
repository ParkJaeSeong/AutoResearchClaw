"""Prepare immutable, evidence-bound inputs for Stage 14 result analysis.

This module selects evidence; it does not interpret results or make scientific
decisions.  Result bytes are always resolved through retained immutable
manifests, never through a mutable compatibility pathname.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import hashlib
import json
import re

from .models import ArtifactRef
from .project import ResearchProject
from .refinement import (
    FINAL_SELECTION_PATH,
    _canonical_json,
    _read_bounded_json,
    _secure_snapshot,
    _write_exclusive,
)
from .transactions import project_mutation


ANALYSIS_PACKET_PATH = "analysis/evidence_packet.json"
_SCHEMA_VERSION = 1
_STAGE_ID = 14
_PHASE = "awaiting_independent_assessments"
_BASELINE_MANIFEST = re.compile(
    r"\.researchclaw/evidence/manifests/[0-9a-f]{32}\.json\Z"
)
_CANDIDATE_MANIFEST = re.compile(
    r"\.researchclaw/evidence/refinement-manifests/"
    r"([0-9a-f]{32})/(candidate-[0-9]{3})/run-[0-9]{3}\.json\Z"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _artifact(value: object, *, error: str = "analysis_integrity_failure") -> ArtifactRef:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size"}:
        raise ValueError(error)
    path, digest, size = value.get("path"), value.get("sha256"), value.get("size")
    if (
        not isinstance(path, str)
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
    ):
        raise ValueError(error)
    return ArtifactRef(path, digest, size)


def _artifact_payload(reference: ArtifactRef) -> dict[str, object]:
    return {
        "path": reference.path,
        "sha256": reference.sha256,
        "size": reference.size,
    }


def _registered_reference(project: ResearchProject, path: str) -> ArtifactRef:
    reference = project.state.artifacts.get(path)
    if reference is None:
        raise ValueError("analysis_input_unregistered")
    _secure_snapshot(
        project.root,
        reference.path,
        expected=reference,
        maximum_bytes=reference.size,
        error_code="analysis_input_changed",
    )
    return reference


def _read_registered_json(
    project: ResearchProject, reference: ArtifactRef
) -> dict[str, object]:
    _secure_snapshot(
        project.root,
        reference.path,
        expected=reference,
        maximum_bytes=reference.size,
        error_code="analysis_input_changed",
    )
    try:
        payload, raw = _read_bounded_json(project.root / reference.path)
    except ValueError as error:
        raise ValueError("analysis_integrity_failure") from error
    if hashlib.sha256(raw).hexdigest() != reference.sha256 or len(raw) != reference.size:
        raise ValueError("analysis_input_changed")
    return payload


def _manifest_object(
    manifest: Mapping[str, object], source_path: str
) -> tuple[ArtifactRef, str]:
    objects = manifest.get("objects")
    if not isinstance(objects, list):
        raise ValueError("analysis_manifest_invalid")
    matches: list[tuple[ArtifactRef, str]] = []
    seen_role_sources: set[tuple[str, str]] = set()
    for value in objects:
        if not isinstance(value, Mapping) or set(value) != {
            "role",
            "source_path",
            "sha256",
            "size",
            "object_path",
        }:
            raise ValueError("analysis_manifest_invalid")
        role = value.get("role")
        declared_source = value.get("source_path")
        digest = value.get("sha256")
        size = value.get("size")
        object_path = value.get("object_path")
        if (
            not isinstance(role, str)
            or not isinstance(declared_source, str)
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or object_path != f".researchclaw/evidence/objects/{digest}"
        ):
            raise ValueError("analysis_manifest_invalid")
        role_source = (role, declared_source)
        if role_source in seen_role_sources:
            raise ValueError("analysis_manifest_invalid")
        seen_role_sources.add(role_source)
        if declared_source == source_path:
            matches.append((ArtifactRef(str(object_path), digest, size), role))
    if len(matches) != 1:
        raise ValueError("analysis_manifest_invalid")
    return matches[0]


def _verified_object(project: ResearchProject, reference: ArtifactRef) -> ArtifactRef:
    _secure_snapshot(
        project.root,
        reference.path,
        expected=reference,
        maximum_bytes=reference.size,
        error_code="analysis_input_changed",
    )
    return reference


def _target_hypotheses(
    project: ResearchProject,
    design_object: ArtifactRef,
    hypotheses_reference: ArtifactRef,
) -> tuple[str, ...]:
    try:
        _, design_bytes = _secure_snapshot(
            project.root,
            design_object.path,
            expected=design_object,
            maximum_bytes=design_object.size,
            read_payload=True,
            error_code="analysis_input_changed",
        )
        _, hypotheses_bytes = _secure_snapshot(
            project.root,
            hypotheses_reference.path,
            expected=hypotheses_reference,
            maximum_bytes=hypotheses_reference.size,
            read_payload=True,
            error_code="analysis_input_changed",
        )
        design = json.loads(design_bytes.decode("utf-8"))
        hypotheses = [
            json.loads(line)
            for line in hypotheses_bytes.decode("utf-8").splitlines()
            if line.strip()
        ]
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("analysis_hypothesis_binding_invalid") from error
    ids = design.get("hypothesis_ids") if isinstance(design, Mapping) else None
    available = {
        item.get("hypothesis_id")
        for item in hypotheses
        if isinstance(item, Mapping) and isinstance(item.get("hypothesis_id"), str)
    }
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(item, str) or not item for item in ids)
        or len(ids) != len(set(ids))
        or not set(ids).issubset(available)
    ):
        raise ValueError("analysis_hypothesis_binding_invalid")
    return tuple(ids)


def _selection(project: ResearchProject) -> tuple[dict[str, object], ArtifactRef]:
    if project.state.current_stage != _STAGE_ID or 13 not in project.state.completed_stages:
        raise ValueError("analysis_stage_invalid")
    reference = project.state.artifacts.get(FINAL_SELECTION_PATH)
    if reference is None:
        raise ValueError("analysis_final_selection_missing")
    selection = _read_registered_json(project, reference)
    if (
        selection.get("schema_version") != 1
        or selection.get("project_id") != project.state.project_id
        or selection.get("action")
        not in {"select_candidate", "retain_baseline", "inconclusive"}
        or not isinstance(selection.get("session_id"), str)
    ):
        raise ValueError("analysis_final_selection_invalid")
    return selection, reference


def _build_packet(project: ResearchProject) -> dict[str, object]:
    selection, selection_ref = _selection(project)
    decision_ref = _artifact(selection.get("council_decision"))
    if project.state.artifacts.get(decision_ref.path) != decision_ref:
        raise ValueError("analysis_input_unregistered")
    _read_registered_json(project, decision_ref)

    retained_value = selection.get("retained_evidence")
    if not isinstance(retained_value, list) or not retained_value:
        raise ValueError("analysis_final_selection_invalid")
    retained = tuple(_artifact(item) for item in retained_value)
    if len({item.path for item in retained}) != len(retained):
        raise ValueError("analysis_final_selection_invalid")
    for reference in retained:
        if project.state.artifacts.get(reference.path) != reference:
            raise ValueError("analysis_input_unregistered")
        _verified_object(project, reference)

    baseline_refs = tuple(
        reference for reference in retained if _BASELINE_MANIFEST.fullmatch(reference.path)
    )
    if len(baseline_refs) != 1:
        raise ValueError("analysis_baseline_manifest_invalid")
    baseline_ref = baseline_refs[0]
    baseline = _read_registered_json(project, baseline_ref)
    if baseline.get("project_id") != project.state.project_id:
        raise ValueError("analysis_baseline_manifest_invalid")
    baseline_result, result_role = _manifest_object(baseline, "experiment/results.json")
    if result_role != "result":
        raise ValueError("analysis_baseline_manifest_invalid")
    _verified_object(project, baseline_result)

    design_object, design_role = _manifest_object(baseline, "experiment/design.json")
    if design_role != "binding:design":
        raise ValueError("analysis_design_binding_invalid")
    _verified_object(project, design_object)
    design_registered = _registered_reference(project, "experiment/design.json")
    if (design_registered.sha256, design_registered.size) != (
        design_object.sha256,
        design_object.size,
    ):
        raise ValueError("analysis_design_binding_invalid")
    hypotheses_registered = _registered_reference(
        project, "hypotheses/candidates.jsonl"
    )
    hypothesis_ids = _target_hypotheses(
        project, design_object, hypotheses_registered
    )

    action = str(selection["action"])
    selected_candidate_id = selection.get("selected_candidate_id")
    candidate_refs = tuple(
        reference
        for reference in retained
        if _CANDIDATE_MANIFEST.fullmatch(reference.path)
    )
    selected_manifest_ref: ArtifactRef | None = None
    selected_result = baseline_result
    result_source = "baseline"
    if action == "select_candidate":
        if not isinstance(selected_candidate_id, str):
            raise ValueError("analysis_selected_candidate_invalid")
        selected_result_path = (
            f"refinement/candidates/{selected_candidate_id}/results.json"
        )
        declared_results = tuple(
            reference for reference in retained if reference.path == selected_result_path
        )
        if len(declared_results) != 1:
            raise ValueError("analysis_selected_candidate_invalid")
        matches: list[tuple[ArtifactRef, ArtifactRef, Mapping[str, object]]] = []
        for manifest_ref in candidate_refs:
            match = _CANDIDATE_MANIFEST.fullmatch(manifest_ref.path)
            if match is None or match.group(1) != selection["session_id"]:
                raise ValueError("analysis_selected_candidate_invalid")
            manifest = _read_registered_json(project, manifest_ref)
            if (
                manifest.get("project_id") != project.state.project_id
                or manifest.get("session_id") != selection["session_id"]
                or manifest.get("candidate_id") != selected_candidate_id
            ):
                raise ValueError("analysis_selected_candidate_invalid")
            result_object, role = _manifest_object(manifest, selected_result_path)
            if role != "result":
                raise ValueError("analysis_selected_candidate_invalid")
            if (result_object.sha256, result_object.size) == (
                declared_results[0].sha256,
                declared_results[0].size,
            ):
                matches.append((manifest_ref, result_object, manifest))
        if len(matches) != 1:
            raise ValueError("analysis_selected_candidate_invalid")
        selected_manifest_ref, selected_result, result_manifest = matches[0]
        _verified_object(project, selected_result)
        result_source = "selected_candidate"
    else:
        if selected_candidate_id is not None or candidate_refs:
            raise ValueError("analysis_selected_candidate_invalid")
        result_manifest = baseline

    metrics = result_manifest.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError("analysis_result_metrics_invalid")
    retained_manifests = tuple(sorted((baseline_ref, *candidate_refs), key=lambda x: x.path))
    selection_context = {
        key: selection.get(key)
        for key in (
            "rationale",
            "votes",
            "supporting_roles",
            "dissenting_roles",
            "limitations",
            "stage_14_questions",
        )
    }
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project.state.project_id,
        "stage_id": _STAGE_ID,
        "phase": _PHASE,
        "selection_action": action,
        "selected_candidate_id": selected_candidate_id,
        "result_source": result_source,
        "target_hypothesis_ids": list(hypothesis_ids),
        "metrics": dict(metrics),
        "selection_context": selection_context,
        "inputs": {
            "final_selection": _artifact_payload(selection_ref),
            "council_decision": _artifact_payload(decision_ref),
            "retained_manifests": [
                _artifact_payload(reference) for reference in retained_manifests
            ],
            "retained_evidence": [
                _artifact_payload(reference)
                for reference in sorted(retained, key=lambda item: item.path)
            ],
            "baseline_result": _artifact_payload(baseline_result),
            "selected_manifest": (
                None
                if selected_manifest_ref is None
                else _artifact_payload(selected_manifest_ref)
            ),
            "selected_result": _artifact_payload(selected_result),
            "approved_design": {
                "registered": _artifact_payload(design_registered),
                "immutable_object": _artifact_payload(design_object),
            },
            "approved_hypotheses": _artifact_payload(hypotheses_registered),
        },
        "protocol": {
            "required_roles": [
                "domain",
                "methodology",
                "critical_reproducibility",
            ],
            "independent_assessments_before_disclosure": True,
            "rebuttal_rounds": 1,
            "coordinator_mode": "non_voting",
        },
        "allowed_outputs": [
            "analysis/reviews/domain.json",
            "analysis/reviews/methodology.json",
            "analysis/reviews/critical_reproducibility.json",
            "analysis/rebuttals.json",
            "analysis/results.json",
            "analysis/report.md",
        ],
        "limits": {
            "external_llm_api": False,
            "experiment_execution": False,
            "new_data_collection": False,
            "stage_15_decision": False,
        },
    }


def _packet_reference(payload: bytes) -> ArtifactRef:
    return ArtifactRef(
        ANALYSIS_PACKET_PATH, hashlib.sha256(payload).hexdigest(), len(payload)
    )


def _validate_packet(project: ResearchProject) -> dict[str, object]:
    expected = _build_packet(project)
    expected_bytes = _canonical_json(expected)
    reference = project.state.artifacts.get(ANALYSIS_PACKET_PATH)
    if reference is None or reference != _packet_reference(expected_bytes):
        raise ValueError("analysis_packet_unregistered")
    try:
        actual, actual_bytes = _read_bounded_json(project.root / ANALYSIS_PACKET_PATH)
    except ValueError as error:
        raise ValueError("analysis_packet_invalid") from error
    _secure_snapshot(
        project.root,
        ANALYSIS_PACKET_PATH,
        expected=reference,
        maximum_bytes=reference.size,
        error_code="analysis_packet_invalid",
    )
    if actual != expected or actual_bytes != expected_bytes:
        raise ValueError("analysis_packet_invalid")
    return expected


@project_mutation
def prepare_analysis(project: ResearchProject) -> dict[str, object]:
    """Create or exactly replay the canonical Stage 14 evidence packet."""
    current = ResearchProject.open_readonly(project.root)
    packet = _build_packet(current)
    packet_bytes = _canonical_json(packet)
    packet_ref = _packet_reference(packet_bytes)
    destination = current.root / ANALYSIS_PACKET_PATH
    try:
        _write_exclusive(destination, packet_bytes)
    except FileExistsError:
        try:
            _, existing = _read_bounded_json(destination)
        except ValueError as error:
            raise ValueError("analysis_packet_conflict") from error
        if existing != packet_bytes:
            raise ValueError("analysis_packet_conflict")

    # Re-read every registered input immediately before accepting the packet.
    if _canonical_json(_build_packet(ResearchProject.open_readonly(current.root))) != packet_bytes:
        raise ValueError("analysis_input_changed")
    current = ResearchProject.open_readonly(current.root)
    existing_ref = current.state.artifacts.get(ANALYSIS_PACKET_PATH)
    if existing_ref not in {None, packet_ref}:
        raise ValueError("analysis_packet_conflict")
    if existing_ref is None:
        current.persist_state(
            replace(
                current.state,
                artifacts={**current.state.artifacts, ANALYSIS_PACKET_PATH: packet_ref},
            )
        )
    return _validate_packet(ResearchProject.open_readonly(current.root))


def analysis_status(project: ResearchProject) -> dict[str, object]:
    """Return the prepared packet only after revalidating every bound input."""
    return _validate_packet(ResearchProject.open_readonly(project.root))
