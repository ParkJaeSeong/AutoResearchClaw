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
import math
import os
from pathlib import Path
import re

from .analysis_report import render_analysis_report
from .models import ArtifactRef, StageStatus
from .paths import resolve_project_artifact
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
ANALYSIS_REBUTTALS_PATH = "analysis/rebuttals.json"
ANALYSIS_RESULT_PATH = "analysis/results.json"
ANALYSIS_REPORT_PATH = "analysis/report.md"
_SCHEMA_VERSION = 1
_STAGE_ID = 14
_PHASE = "awaiting_independent_assessments"
_REQUIRED_ROLES = ("domain", "methodology", "critical_reproducibility")
_VERDICTS = frozenset({"supported", "refuted", "inconclusive"})
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
    stage_is_valid = project.state.current_stage == _STAGE_ID or (
        project.state.current_stage >= _STAGE_ID + 1
        and _STAGE_ID in project.state.completed_stages
    )
    if not stage_is_valid or 13 not in project.state.completed_stages:
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
    if current.state.current_stage != _STAGE_ID:
        return _validate_packet(current)
    destination = resolve_project_artifact(current.root, ANALYSIS_PACKET_PATH)
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
    """Return dynamic registration status without mutating the canonical packet."""
    current = ResearchProject.open_readonly(project.root)
    _build_packet(current)
    if ANALYSIS_PACKET_PATH not in current.state.artifacts:
        return {
            "schema_version": _SCHEMA_VERSION,
            "project_id": current.state.project_id,
            "stage_id": _STAGE_ID,
            "current_stage": current.state.current_stage,
            "phase": "awaiting_preparation",
            "next_action": "prepare_analysis",
            "registered_roles": [],
            "evidence_packet": None,
        }
    packet = _validate_packet(current)
    return _analysis_registration_status(current, packet)


def _submission_path(project: ResearchProject, value: str | Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    try:
        return resolve_project_artifact(project.root, str(candidate))
    except ValueError as error:
        raise ValueError("analysis_submission_path_invalid") from error


def _read_submission(
    project: ResearchProject, value: str | Path
) -> tuple[dict[str, object], bytes]:
    try:
        return _read_bounded_json(_submission_path(project, value))
    except ValueError as error:
        raise ValueError("analysis_submission_invalid") from error


def _record_reference(path: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(path, hashlib.sha256(payload).hexdigest(), len(payload))


def _read_record(
    project: ResearchProject, path: str
) -> tuple[dict[str, object], bytes] | None:
    destination = resolve_project_artifact(project.root, path)
    if not os.path.lexists(destination):
        if path in project.state.artifacts:
            raise ValueError("analysis_integrity_failure")
        return None
    try:
        payload, raw = _read_bounded_json(destination)
    except ValueError as error:
        raise ValueError("analysis_integrity_failure") from error
    if project.state.artifacts.get(path) != _record_reference(path, raw):
        raise ValueError("analysis_integrity_failure")
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
        _, raw = _read_bounded_json(destination)
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
            _, existing = _read_bounded_json(destination)
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
    paths = {ANALYSIS_PACKET_PATH}

    def collect(value: object) -> None:
        if isinstance(value, Mapping):
            path = value.get("path")
            digest = value.get("sha256")
            size = value.get("size")
            if (
                isinstance(path, str)
                and isinstance(digest, str)
                and _SHA256.fullmatch(digest) is not None
                and isinstance(size, int)
                and not isinstance(size, bool)
            ):
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
        value, "analysis_evidence_reference_invalid", require_nonempty=True
    )
    if len(refs) != len(set(refs)) or not set(refs).issubset(_evidence_paths(packet)):
        raise ValueError("analysis_evidence_reference_invalid")
    return refs


def _submission_base(
    payload: Mapping[str, object],
    project: ResearchProject,
    packet_ref: ArtifactRef,
    extra_fields: set[str],
) -> str:
    required = {
        "schema_version",
        "project_id",
        "evidence_packet_sha256",
        "producer",
    } | extra_fields
    if (
        set(payload) != required
        or payload.get("schema_version") != _SCHEMA_VERSION
        or isinstance(payload.get("schema_version"), bool)
    ):
        raise ValueError("analysis_submission_schema_invalid")
    if (
        payload.get("project_id") != project.state.project_id
        or payload.get("evidence_packet_sha256") != packet_ref.sha256
    ):
        raise ValueError("analysis_submission_binding_invalid")
    return _nonempty_text(payload.get("producer"), "analysis_producer_invalid")


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
        {"role", "claims", "limitations", "questions"},
    )
    role = payload.get("role")
    if role not in _REQUIRED_ROLES:
        raise ValueError("analysis_role_invalid")
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("analysis_review_schema_invalid")
    for claim in claims:
        if not isinstance(claim, Mapping) or set(claim) != {"text", "evidence_refs"}:
            raise ValueError("analysis_review_schema_invalid")
        _nonempty_text(claim.get("text"), "analysis_review_schema_invalid")
        _evidence_refs(claim.get("evidence_refs"), packet)
    _text_list(
        payload.get("limitations"),
        "analysis_review_schema_invalid",
        require_nonempty=True,
    )
    _text_list(payload.get("questions"), "analysis_review_schema_invalid")
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
    for role in _REQUIRED_ROLES:
        path = f"analysis/reviews/{role}.json"
        if path == ignore_unregistered_path and path not in project.state.artifacts:
            continue
        record = _read_record(project, path)
        if record is None:
            continue
        parsed_role, producer = _parse_review(
            record[0], project=project, packet=packet, packet_ref=packet_ref
        )
        if parsed_role != role or producer in producers:
            raise ValueError("analysis_integrity_failure")
        producers.add(producer)
        records[role] = (record[0], record[1], producer)
    return records


def _expected_review_hashes(
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]]
) -> dict[str, str]:
    return {
        role: hashlib.sha256(reviews[role][1]).hexdigest() for role in _REQUIRED_ROLES
    }


def _parse_rebuttals(
    payload: Mapping[str, object],
    *,
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
) -> str:
    producer = _submission_base(
        payload,
        project,
        packet_ref,
        {"review_hashes", "responses"},
    )
    reviewer_producers = {value[2] for value in reviews.values()}
    if producer in reviewer_producers:
        raise ValueError("analysis_coordinator_producer_invalid")
    hashes = payload.get("review_hashes")
    if not isinstance(hashes, Mapping) or dict(hashes) != _expected_review_hashes(reviews):
        raise ValueError("analysis_rebuttal_binding_invalid")
    responses = payload.get("responses")
    if not isinstance(responses, list) or len(responses) != len(_REQUIRED_ROLES):
        raise ValueError("analysis_rebuttal_role_invalid")
    seen: set[str] = set()
    for response in responses:
        if not isinstance(response, Mapping) or set(response) != {
            "role",
            "producer",
            "review_sha256",
            "challenges",
            "responses",
            "evidence_refs",
        }:
            raise ValueError("analysis_rebuttal_schema_invalid")
        role = response.get("role")
        if role not in reviews or role in seen:
            raise ValueError("analysis_rebuttal_role_invalid")
        seen.add(str(role))
        if response.get("producer") != reviews[str(role)][2]:
            raise ValueError("analysis_rebuttal_producer_invalid")
        if response.get("review_sha256") != hashes[role]:
            raise ValueError("analysis_rebuttal_binding_invalid")
        _text_list(
            response.get("challenges"),
            "analysis_rebuttal_schema_invalid",
            require_nonempty=True,
        )
        _text_list(
            response.get("responses"),
            "analysis_rebuttal_schema_invalid",
            require_nonempty=True,
        )
        _evidence_refs(response.get("evidence_refs"), packet)
    if seen != set(_REQUIRED_ROLES):
        raise ValueError("analysis_rebuttal_role_invalid")
    return producer


def _registered_metric_sources(
    project: ResearchProject, packet: Mapping[str, object]
) -> dict[str, dict[str, tuple[object, object]]]:
    inputs = packet.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("analysis_metric_mismatch")
    sources: dict[str, dict[str, tuple[object, object]]] = {}
    for key in ("baseline_result", "selected_result"):
        try:
            reference = _artifact(inputs.get(key), error="analysis_metric_mismatch")
        except ValueError as error:
            raise ValueError("analysis_metric_mismatch") from error
        if reference.path in sources:
            continue
        result = _read_registered_json(project, reference)
        metrics = result.get("metrics")
        if not isinstance(metrics, Mapping) or not metrics:
            raise ValueError("analysis_metric_mismatch")
        parsed: dict[str, tuple[object, object]] = {}
        for metric in metrics.values():
            if not isinstance(metric, Mapping):
                raise ValueError("analysis_metric_mismatch")
            name, unit, value = metric.get("name"), metric.get("unit"), metric.get("value")
            if (
                not isinstance(name, str)
                or not name
                or name in parsed
                or not isinstance(unit, str)
                or not unit
                or not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise ValueError("analysis_metric_mismatch")
            parsed[name] = (unit, value)
        sources[reference.path] = parsed
    return sources


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
            "observed_metrics",
            "hypothesis_assessments",
            "explanations",
            "alternatives",
            "limitations",
            "scope",
            "uncertainty",
            "agreement",
            "disagreements",
        },
    )
    if producer != rebuttals[2] or producer in {value[2] for value in reviews.values()}:
        raise ValueError("analysis_coordinator_producer_invalid")
    hashes = payload.get("review_hashes")
    if not isinstance(hashes, Mapping) or dict(hashes) != _expected_review_hashes(reviews):
        raise ValueError("analysis_result_binding_invalid")
    if payload.get("rebuttals_sha256") != hashlib.sha256(rebuttals[1]).hexdigest():
        raise ValueError("analysis_result_binding_invalid")

    metric_sources = _registered_metric_sources(project, packet)
    observed = payload.get("observed_metrics")
    if not isinstance(observed, list):
        raise ValueError("analysis_metric_mismatch")
    expected_metrics = {
        (source, name): metric
        for source, metrics in metric_sources.items()
        for name, metric in metrics.items()
    }
    seen_metrics: set[tuple[str, str]] = set()
    for metric in observed:
        if not isinstance(metric, Mapping) or set(metric) != {
            "name",
            "unit",
            "value",
            "evidence_refs",
        }:
            raise ValueError("analysis_metric_mismatch")
        name = metric.get("name")
        value = metric.get("value")
        refs = _evidence_refs(metric.get("evidence_refs"), packet)
        sources = [source for source in metric_sources if source in refs]
        if (
            not isinstance(name, str)
            or len(sources) != 1
            or (sources[0], name) in seen_metrics
            or (sources[0], name) not in expected_metrics
            or metric.get("unit") != expected_metrics[(sources[0], name)][0]
            or isinstance(value, bool)
            or value != expected_metrics[(sources[0], name)][1]
        ):
            raise ValueError("analysis_metric_mismatch")
        seen_metrics.add((sources[0], name))
    if seen_metrics != set(expected_metrics):
        raise ValueError("analysis_metric_mismatch")

    assessments = payload.get("hypothesis_assessments")
    if not isinstance(assessments, list):
        raise ValueError("analysis_hypothesis_assessment_invalid")
    expected_ids = packet.get("target_hypothesis_ids")
    if not isinstance(expected_ids, list):
        raise ValueError("analysis_hypothesis_assessment_invalid")
    seen_ids: set[str] = set()
    for assessment in assessments:
        if not isinstance(assessment, Mapping) or set(assessment) != {
            "hypothesis_id",
            "verdict",
            "explanation",
            "evidence_refs",
        }:
            raise ValueError("analysis_hypothesis_assessment_invalid")
        hypothesis_id = assessment.get("hypothesis_id")
        if (
            not isinstance(hypothesis_id, str)
            or hypothesis_id in seen_ids
            or hypothesis_id not in expected_ids
            or assessment.get("verdict") not in _VERDICTS
        ):
            raise ValueError("analysis_hypothesis_assessment_invalid")
        _nonempty_text(
            assessment.get("explanation"), "analysis_hypothesis_assessment_invalid"
        )
        _evidence_refs(assessment.get("evidence_refs"), packet)
        seen_ids.add(hypothesis_id)
    if seen_ids != set(expected_ids):
        raise ValueError("analysis_hypothesis_assessment_invalid")

    for field in ("explanations", "alternatives", "limitations", "agreement"):
        _text_list(payload.get(field), "analysis_result_schema_invalid")
    _text_list(payload.get("scope"), "analysis_scope_missing", require_nonempty=True)
    _text_list(
        payload.get("uncertainty"),
        "analysis_uncertainty_missing",
        require_nonempty=True,
    )
    disagreements = payload.get("disagreements")
    if not isinstance(disagreements, list):
        raise ValueError("analysis_result_schema_invalid")
    seen_disagreements: set[str] = set()
    for disagreement in disagreements:
        if not isinstance(disagreement, Mapping) or set(disagreement) != {
            "role",
            "text",
            "evidence_refs",
        }:
            raise ValueError("analysis_result_schema_invalid")
        role = disagreement.get("role")
        if role not in _REQUIRED_ROLES or role in seen_disagreements:
            raise ValueError("analysis_result_schema_invalid")
        seen_disagreements.add(str(role))
        _nonempty_text(disagreement.get("text"), "analysis_result_schema_invalid")
        _evidence_refs(disagreement.get("evidence_refs"), packet)
    return producer


def _registered_rebuttals(
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
) -> tuple[dict[str, object], bytes, str] | None:
    record = _read_record(project, ANALYSIS_REBUTTALS_PATH)
    if record is None:
        return None
    if set(reviews) != set(_REQUIRED_ROLES):
        raise ValueError("analysis_integrity_failure")
    producer = _parse_rebuttals(
        record[0],
        project=project,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
    )
    return record[0], record[1], producer


def _report_payload(
    result: Mapping[str, object],
    packet: Mapping[str, object],
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
    rebuttals: tuple[dict[str, object], bytes, str],
) -> dict[str, object]:
    return {
        "analysis_result": dict(result),
        "evidence_packet": dict(packet),
        "reviews": [reviews[role][0] for role in _REQUIRED_ROLES],
        "rebuttals": rebuttals[0],
    }


def _registered_result(
    project: ResearchProject,
    packet: Mapping[str, object],
    packet_ref: ArtifactRef,
    reviews: Mapping[str, tuple[dict[str, object], bytes, str]],
    rebuttals: tuple[dict[str, object], bytes, str] | None,
) -> tuple[dict[str, object], bytes] | None:
    record = _read_record(project, ANALYSIS_RESULT_PATH)
    if record is None:
        return None
    if rebuttals is None:
        raise ValueError("analysis_integrity_failure")
    _parse_result(
        record[0],
        project=project,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
        rebuttals=rebuttals,
    )
    report_ref = project.state.artifacts.get(ANALYSIS_REPORT_PATH)
    if report_ref is None:
        raise ValueError("analysis_integrity_failure")
    expected_report = render_analysis_report(
        _report_payload(record[0], packet, reviews, rebuttals)
    ).encode("utf-8")
    try:
        _, actual_report = _secure_snapshot(
            project.root,
            ANALYSIS_REPORT_PATH,
            expected=report_ref,
            maximum_bytes=report_ref.size,
            read_payload=True,
            error_code="analysis_integrity_failure",
        )
    except ValueError as error:
        raise ValueError("analysis_integrity_failure") from error
    if actual_report != expected_report:
        raise ValueError("analysis_integrity_failure")
    return record


def _analysis_registration_status(
    project: ResearchProject, packet: Mapping[str, object]
) -> dict[str, object]:
    _, reviews, rebuttals, result = _analysis_records(project, packet)
    if result is not None:
        phase, next_action = "complete", "unsupported_stage_15"
    elif rebuttals is not None:
        phase, next_action = "awaiting_synthesis", "register_analysis_result"
    elif len(reviews) == len(_REQUIRED_ROLES):
        phase, next_action = "awaiting_rebuttals", "register_analysis_rebuttals"
    else:
        phase, next_action = (
            "awaiting_independent_assessments",
            "register_analysis_review",
        )
    return {
        "schema_version": _SCHEMA_VERSION,
        "project_id": project.state.project_id,
        "stage_id": _STAGE_ID,
        "current_stage": project.state.current_stage,
        "phase": phase,
        "next_action": next_action,
        "registered_roles": [role for role in _REQUIRED_ROLES if role in reviews],
        "review_hashes": (
            _expected_review_hashes(reviews)
            if len(reviews) == len(_REQUIRED_ROLES)
            else {
                role: hashlib.sha256(value[1]).hexdigest()
                for role, value in reviews.items()
            }
        ),
        "rebuttals_sha256": (
            None if rebuttals is None else hashlib.sha256(rebuttals[1]).hexdigest()
        ),
        "result_sha256": (
            None if result is None else hashlib.sha256(result[1]).hexdigest()
        ),
        "evidence_packet": dict(packet),
    }


def _analysis_records(
    project: ResearchProject, packet: Mapping[str, object]
) -> tuple[
    ArtifactRef,
    dict[str, tuple[dict[str, object], bytes, str]],
    tuple[dict[str, object], bytes, str] | None,
    tuple[dict[str, object], bytes] | None,
]:
    packet_ref = project.state.artifacts.get(ANALYSIS_PACKET_PATH)
    if packet_ref is None:
        raise ValueError("analysis_packet_unregistered")
    reviews = _review_records(project, packet, packet_ref)
    rebuttals = _registered_rebuttals(project, packet, packet_ref, reviews)
    result = _registered_result(project, packet, packet_ref, reviews, rebuttals)
    return packet_ref, reviews, rebuttals, result


def validate_completed_analysis(project: ResearchProject) -> dict[str, object]:
    """Verify completed Stage 14 records and their transitive immutable inputs."""
    current = ResearchProject.open_readonly(project.root)
    if (
        current.state.current_stage < _STAGE_ID + 1
        or _STAGE_ID not in current.state.completed_stages
    ):
        raise ValueError("analysis_incomplete")
    packet = _validate_packet(current)
    _, reviews, rebuttals, result = _analysis_records(current, packet)
    if (
        set(reviews) != set(_REQUIRED_ROLES)
        or rebuttals is None
        or result is None
    ):
        raise ValueError("analysis_incomplete")
    paths = (
        ANALYSIS_PACKET_PATH,
        ANALYSIS_RESULT_PATH,
        ANALYSIS_REPORT_PATH,
        *(f"analysis/reviews/{role}.json" for role in _REQUIRED_ROLES),
        ANALYSIS_REBUTTALS_PATH,
    )
    references = []
    for path in paths:
        reference = current.state.artifacts.get(path)
        if reference is None:
            raise ValueError("analysis_incomplete")
        references.append(_artifact_payload(reference))
    return {"evidence_packet": dict(packet), "references": references}


@project_mutation
def register_analysis_review(
    project: ResearchProject, submission_path: str | Path
) -> dict[str, object]:
    """Register one evidence-bound independent role review."""
    current = ResearchProject.open_readonly(project.root)
    packet = _validate_packet(current)
    packet_ref = current.state.artifacts[ANALYSIS_PACKET_PATH]
    source, source_bytes = _read_submission(current, submission_path)
    role, producer = _parse_review(
        source, project=current, packet=packet, packet_ref=packet_ref
    )
    target = f"analysis/reviews/{role}.json"
    orphan = _read_unregistered_record(
        current, target, conflict="analysis_review_conflict"
    )
    reviews = _review_records(
        current,
        packet,
        packet_ref,
        ignore_unregistered_path=target if orphan is not None else None,
    )
    rebuttals = _read_record(current, ANALYSIS_REBUTTALS_PATH)
    existing = reviews.get(role)
    if existing is not None:
        if source_bytes != existing[1]:
            raise ValueError("analysis_review_conflict")
        return _analysis_registration_status(current, packet)
    if current.state.current_stage != _STAGE_ID:
        raise ValueError("analysis_order_invalid")
    if rebuttals is not None:
        raise ValueError("analysis_order_invalid")
    if producer in {value[2] for value in reviews.values()}:
        raise ValueError("analysis_producer_duplicate")
    if orphan is not None and orphan != source_bytes:
        raise ValueError("analysis_review_conflict")
    current = _write_record(
        current,
        target,
        source_bytes,
        conflict="analysis_review_conflict",
    )
    return _analysis_registration_status(current, _validate_packet(current))


@project_mutation
def register_analysis_rebuttals(
    project: ResearchProject, submission_path: str | Path
) -> dict[str, object]:
    """Register the response round after every independent review exists."""
    current = ResearchProject.open_readonly(project.root)
    packet = _validate_packet(current)
    packet_ref = current.state.artifacts[ANALYSIS_PACKET_PATH]
    reviews = _review_records(current, packet, packet_ref)
    if set(reviews) != set(_REQUIRED_ROLES):
        raise ValueError("analysis_order_invalid")
    source, source_bytes = _read_submission(current, submission_path)
    _parse_rebuttals(
        source,
        project=current,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
    )
    orphan = _read_unregistered_record(
        current, ANALYSIS_REBUTTALS_PATH, conflict="analysis_rebuttal_conflict"
    )
    if orphan is not None and orphan != source_bytes:
        raise ValueError("analysis_rebuttal_conflict")
    existing = (
        None
        if orphan is not None
        else _registered_rebuttals(current, packet, packet_ref, reviews)
    )
    if existing is not None:
        if source_bytes != existing[1]:
            raise ValueError("analysis_rebuttal_conflict")
        return _analysis_registration_status(current, packet)
    if current.state.current_stage != _STAGE_ID:
        raise ValueError("analysis_order_invalid")
    if _read_record(current, ANALYSIS_RESULT_PATH) is not None:
        raise ValueError("analysis_order_invalid")
    current = _write_record(
        current,
        ANALYSIS_REBUTTALS_PATH,
        source_bytes,
        conflict="analysis_rebuttal_conflict",
    )
    return _analysis_registration_status(current, _validate_packet(current))


def _write_report_exclusive(project: ResearchProject, payload: bytes) -> None:
    path = resolve_project_artifact(project.root, ANALYSIS_REPORT_PATH)
    try:
        _write_exclusive(path, payload)
    except FileExistsError:
        try:
            _, existing = _secure_snapshot(
                project.root,
                ANALYSIS_REPORT_PATH,
                expected=_record_reference(ANALYSIS_REPORT_PATH, payload),
                maximum_bytes=len(payload),
                read_payload=True,
                error_code="analysis_report_conflict",
            )
        except ValueError as error:
            raise ValueError("analysis_report_conflict") from error
        if existing != payload:
            raise ValueError("analysis_report_conflict")


@project_mutation
def register_analysis_result(
    project: ResearchProject, submission_path: str | Path
) -> dict[str, object]:
    """Validate synthesis, publish its report, and complete Stage 14."""
    current = ResearchProject.open_readonly(project.root)
    packet = _validate_packet(current)
    packet_ref = current.state.artifacts[ANALYSIS_PACKET_PATH]
    reviews = _review_records(current, packet, packet_ref)
    rebuttals = _registered_rebuttals(current, packet, packet_ref, reviews)
    if rebuttals is None:
        raise ValueError("analysis_order_invalid")
    source, source_bytes = _read_submission(current, submission_path)
    _parse_result(
        source,
        project=current,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
        rebuttals=rebuttals,
    )
    result_path = resolve_project_artifact(current.root, ANALYSIS_RESULT_PATH)
    if (
        ANALYSIS_RESULT_PATH not in current.state.artifacts
        and os.path.lexists(result_path)
    ):
        try:
            _, orphan = _read_bounded_json(result_path)
        except ValueError as error:
            raise ValueError("analysis_result_conflict") from error
        if orphan != source_bytes:
            raise ValueError("analysis_result_conflict")
        existing = None
    else:
        existing = _read_record(current, ANALYSIS_RESULT_PATH)
    if existing is not None:
        if source_bytes != existing[1]:
            raise ValueError("analysis_result_conflict")
        return _analysis_registration_status(current, packet)
    if current.state.current_stage != _STAGE_ID:
        raise ValueError("analysis_order_invalid")

    try:
        _write_exclusive(result_path, source_bytes)
    except FileExistsError:
        try:
            _, orphan = _read_bounded_json(result_path)
        except ValueError as error:
            raise ValueError("analysis_result_conflict") from error
        if orphan != source_bytes:
            raise ValueError("analysis_result_conflict")
    report_bytes = render_analysis_report(
        _report_payload(source, packet, reviews, rebuttals)
    ).encode("utf-8")
    _write_report_exclusive(current, report_bytes)

    # Revalidate all bindings after publication and before advancing the stage.
    current = ResearchProject.open_readonly(current.root)
    packet = _validate_packet(current)
    packet_ref = current.state.artifacts[ANALYSIS_PACKET_PATH]
    reviews = _review_records(current, packet, packet_ref)
    rebuttals = _registered_rebuttals(current, packet, packet_ref, reviews)
    if rebuttals is None:
        raise ValueError("analysis_integrity_failure")
    _parse_result(
        source,
        project=current,
        packet=packet,
        packet_ref=packet_ref,
        reviews=reviews,
        rebuttals=rebuttals,
    )
    result_ref = _record_reference(ANALYSIS_RESULT_PATH, source_bytes)
    report_ref = _record_reference(ANALYSIS_REPORT_PATH, report_bytes)
    for path, reference in (
        (ANALYSIS_RESULT_PATH, result_ref),
        (ANALYSIS_REPORT_PATH, report_ref),
    ):
        if current.state.artifacts.get(path) not in {None, reference}:
            raise ValueError("analysis_result_conflict")
    completed = current.state.completed_stages
    if _STAGE_ID not in completed:
        completed = (*completed, _STAGE_ID)
    current.persist_state(
        replace(
            current.state,
            current_stage=_STAGE_ID + 1,
            status=StageStatus.READY,
            completed_stages=completed,
            next_action="prepare_stage",
            artifacts={
                **current.state.artifacts,
                ANALYSIS_RESULT_PATH: result_ref,
                ANALYSIS_REPORT_PATH: report_ref,
            },
            last_error=None,
        )
    )
    complete = ResearchProject.open_readonly(current.root)
    return _analysis_registration_status(complete, _validate_packet(complete))
