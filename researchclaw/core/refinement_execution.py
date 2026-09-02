"""Development-only validation and registration for Stage-13 candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

from .execution_environment import inspect_execution_environment
from . import experiment_package_contract as package_contract
from .experiment_package_contract import validate_experiment_package_contract_at
from .models import ArtifactRef, ProjectState
from .project import ResearchProject
from .refinement import (
    EVIDENCE_PACKET_PATH,
    SESSION_PATH,
    CandidateStatus,
    _artifact,
    _baseline,
    _baseline_registration_snapshot,
    _canonical_json,
    _created_at,
    _read_bounded_json,
    _revalidate_refinement_candidate,
    _same_published_baseline_snapshot,
    _secure_snapshot,
    _write_exclusive,
    revalidate_refinement_candidate,
)
from .transactions import project_mutation


REFINEMENT_SELF_TEST_REGISTRATION_ROOT = ".researchclaw/refinement-self-tests"
_REPORT_LOCAL_PATH = "package_metadata/self_test_report.json"
_CONTRACT_LOCAL_PATH = "package_metadata/package_contract.json"
_MANIFEST_LOCAL_PATH = "package_metadata/package_manifest.json"
_MAX_JSON_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REPORT_KEYS = {
    "schema_version",
    "package_contract",
    "fixture",
    "environment_fingerprint",
    "package_manifest",
    "entry_point",
    "package_files",
    "metrics",
    "passed",
    "development_only",
}
_IDENTITY_KEYS = {"path", "sha256"}
_METRIC_KEYS = {"name", "actual", "expected", "tolerance"}


@dataclass(frozen=True)
class SelfTestPreparationStatus:
    """One verified candidate-rooted self-test command; it is never executed here."""

    candidate_id: str
    argv: tuple[str, ...]
    cwd: str
    environment_fingerprint: str
    candidate_manifest_sha256: str
    package_contract_sha256: str
    decision_sha256: str
    report_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": "ready_for_explicit_refinement_self_test",
            "candidate_id": self.candidate_id,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "environment_fingerprint": self.environment_fingerprint,
            "candidate_manifest_sha256": self.candidate_manifest_sha256,
            "package_contract_sha256": self.package_contract_sha256,
            "decision_sha256": self.decision_sha256,
            "report_path": self.report_path,
        }


def _candidate_root(project: ResearchProject, candidate_id: str) -> Path:
    return (
        project.root.resolve(strict=True)
        / "refinement"
        / "candidates"
        / candidate_id
    )


def prepare_refinement_self_test(
    project: ResearchProject, candidate_id: str
) -> SelfTestPreparationStatus:
    """Return a verified candidate command without executing or reserving a run."""
    current = ResearchProject.open_readonly(project.root)
    candidate = revalidate_refinement_candidate(current, candidate_id)
    root = _candidate_root(current, candidate_id)
    report_path = (
        f"refinement/candidates/{candidate_id}/package_metadata/self_test_report.json"
    )
    if os.path.lexists(current.root / report_path):
        raise ValueError("refinement_self_test_report_exists")
    baseline = _baseline(current)
    baseline_before = _baseline_registration_snapshot(current, baseline)
    result_before = _direct_baseline_result_snapshot(current)
    bound_before = _bound_candidate_snapshot(current, candidate)
    state_before = _state_file_snapshot(current)
    package = validate_experiment_package_contract_at(
        current,
        package_root=root,
        contract_path="package_metadata/package_contract.json",
    )
    environment = inspect_execution_environment(
        Path(sys.executable).resolve(strict=True), package.required_distributions
    )
    if _bound_candidate_snapshot(current, candidate) != bound_before:
        raise ValueError("refinement_candidate_identity_changed")
    if revalidate_refinement_candidate(current, candidate_id) != candidate:
        raise ValueError("refinement_candidate_identity_changed")
    repeated_package = validate_experiment_package_contract_at(
        current,
        package_root=root,
        contract_path="package_metadata/package_contract.json",
    )
    if repeated_package != package:
        raise ValueError("refinement_candidate_identity_changed")
    if (
        _bound_candidate_snapshot(current, candidate) != bound_before
        or _baseline_registration_snapshot(current, baseline) != baseline_before
        or _direct_baseline_result_snapshot(current) != result_before
        or _state_file_snapshot(current) != state_before
        or ResearchProject.open_readonly(current.root).state != current.state
    ):
        raise ValueError("refinement_candidate_identity_changed")
    return SelfTestPreparationStatus(
        candidate_id=candidate_id,
        argv=(environment.launcher, package.entry_point, *package.self_test_argv),
        cwd=str(root),
        environment_fingerprint=environment.fingerprint,
        candidate_manifest_sha256=candidate.manifest_sha256,
        package_contract_sha256=package.contract_sha256,
        decision_sha256=candidate.decision_sha256,
        report_path=report_path,
    )


def _artifact_payload(reference: ArtifactRef) -> dict[str, object]:
    return {
        "path": reference.path,
        "sha256": reference.sha256,
        "size": reference.size,
    }


def _require_closed(
    value: object, keys: set[str], *, error: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(error)
    return value


def _candidate_report_path(candidate_id: str) -> str:
    return f"refinement/candidates/{candidate_id}/{_REPORT_LOCAL_PATH}"


def _registration_path(session_id: str, candidate_id: str) -> str:
    return f"{REFINEMENT_SELF_TEST_REGISTRATION_ROOT}/{session_id}/{candidate_id}.json"


def _candidate_reference(
    candidate: CandidateStatus, local_path: str
) -> ArtifactRef:
    project_path = f"refinement/candidates/{candidate.candidate_id}/{local_path}"
    matches = tuple(
        reference for reference in candidate.files if reference.path == project_path
    )
    if len(matches) != 1:
        raise ValueError("refinement_candidate_binding_invalid")
    return matches[0]


def _identity(
    value: object, *, path: str, sha256: str, error: str
) -> None:
    identity = _require_closed(value, _IDENTITY_KEYS, error=error)
    if identity.get("path") != path or identity.get("sha256") != sha256:
        raise ValueError(error)


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and float("-inf") < float(value) < float("inf")
    )


def _validate_report_metrics(
    value: object, expected_metrics: object
) -> tuple[dict[str, object], ...]:
    if not isinstance(expected_metrics, list) or not expected_metrics:
        raise ValueError("refinement_self_test_report_invalid")
    expected: dict[str, tuple[float, float]] = {}
    for raw in expected_metrics:
        item = _require_closed(
            raw,
            {"name", "expected", "tolerance"},
            error="refinement_self_test_report_invalid",
        )
        name = item.get("name")
        expected_value = item.get("expected")
        tolerance = item.get("tolerance")
        if (
            not isinstance(name, str)
            or not name
            or name in expected
            or not _finite_number(expected_value)
            or not _finite_number(tolerance)
            or float(tolerance) < 0
        ):
            raise ValueError("refinement_self_test_report_invalid")
        expected[name] = (float(expected_value), float(tolerance))
    if not isinstance(value, list):
        raise ValueError("refinement_self_test_report_invalid")
    reported: list[dict[str, object]] = []
    names: set[str] = set()
    for raw in value:
        metric = _require_closed(
            raw, _METRIC_KEYS, error="refinement_self_test_report_invalid"
        )
        name = metric.get("name")
        if (
            not isinstance(name, str)
            or name in names
            or not all(
                _finite_number(metric.get(field))
                for field in ("actual", "expected", "tolerance")
            )
        ):
            raise ValueError("refinement_self_test_report_invalid")
        names.add(name)
        if name not in expected:
            raise ValueError("refinement_self_test_report_invalid")
        required_expected, required_tolerance = expected[name]
        if (
            float(metric["expected"]) != required_expected
            or float(metric["tolerance"]) != required_tolerance
            or abs(float(metric["actual"]) - required_expected) > required_tolerance
        ):
            raise ValueError("refinement_self_test_report_invalid")
        reported.append(dict(metric))
    if names != set(expected):
        raise ValueError("refinement_self_test_report_invalid")
    return tuple(reported)


@dataclass(frozen=True)
class _ValidatedCandidateSelfTest:
    report: ArtifactRef
    environment_fingerprint: str
    package_manifest: ArtifactRef
    entry_point: ArtifactRef
    fixture: ArtifactRef
    config: ArtifactRef
    metrics: tuple[dict[str, object], ...]


def _read_candidate_bytes(
    root: Path, local_path: str, *, maximum_bytes: int = 16 * 1024 * 1024
) -> bytes:
    try:
        return package_contract._read_candidate_package_bytes(
            root, local_path, maximum_bytes=maximum_bytes
        )
    except (OSError, ValueError) as error:
        raise ValueError("refinement_self_test_report_invalid") from error


def _validate_candidate_self_test_report(
    project: ResearchProject,
    candidate: CandidateStatus,
    package: package_contract.ValidatedExperimentPackage,
    environment_fingerprint: str,
) -> _ValidatedCandidateSelfTest:
    root = _candidate_root(project, candidate.candidate_id)
    try:
        contract, _contract_bytes = package_contract._read_json_object(
            root, _CONTRACT_LOCAL_PATH, candidate_rooted=True
        )
        package_manifest, manifest_bytes = package_contract._read_json_object(
            root, _MANIFEST_LOCAL_PATH, candidate_rooted=True
        )
        report, report_bytes = package_contract._read_json_object(
            root, _REPORT_LOCAL_PATH, candidate_rooted=True
        )
    except (OSError, ValueError) as error:
        raise ValueError("refinement_self_test_report_invalid") from error
    _require_closed(
        report, _REPORT_KEYS, error="refinement_self_test_report_invalid"
    )
    if (
        report.get("schema_version") != 1
        or isinstance(report.get("schema_version"), bool)
        or report.get("passed") is not True
        or report.get("development_only") is not True
    ):
        raise ValueError("refinement_self_test_report_invalid")
    _identity(
        report.get("package_contract"),
        path=_CONTRACT_LOCAL_PATH,
        sha256=package.contract_sha256,
        error="refinement_self_test_report_invalid",
    )
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    _identity(
        report.get("package_manifest"),
        path=_MANIFEST_LOCAL_PATH,
        sha256=manifest_sha256,
        error="refinement_self_test_report_invalid",
    )
    entry_bytes = _read_candidate_bytes(root, package.entry_point)
    entry_sha256 = hashlib.sha256(entry_bytes).hexdigest()
    _identity(
        report.get("entry_point"),
        path=package.entry_point,
        sha256=entry_sha256,
        error="refinement_self_test_report_invalid",
    )
    files = package_manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("refinement_self_test_report_invalid")
    expected_files: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for raw in files:
        if not isinstance(raw, Mapping) or set(raw) - {"path", "role", "sha256"}:
            raise ValueError("refinement_self_test_report_invalid")
        path = raw.get("path")
        digest = raw.get("sha256")
        if (
            not isinstance(path, str)
            or path in seen_paths
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or hashlib.sha256(_read_candidate_bytes(root, path)).hexdigest() != digest
        ):
            raise ValueError("refinement_self_test_report_invalid")
        seen_paths.add(path)
        expected_files.append({"path": path, "sha256": digest})
    reported_files = report.get("package_files")
    if not isinstance(reported_files, list):
        raise ValueError("refinement_self_test_report_invalid")
    normalized_reported: list[dict[str, str]] = []
    for raw in reported_files:
        identity = _require_closed(
            raw, _IDENTITY_KEYS, error="refinement_self_test_report_invalid"
        )
        path = identity.get("path")
        digest = identity.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
        ):
            raise ValueError("refinement_self_test_report_invalid")
        normalized_reported.append({"path": path, "sha256": digest})
    if normalized_reported != expected_files:
        raise ValueError("refinement_self_test_report_invalid")
    self_test = contract.get("self_test")
    if not isinstance(self_test, Mapping):
        raise ValueError("refinement_self_test_report_invalid")
    fixture_path = self_test.get("fixture_path")
    if not isinstance(fixture_path, str):
        raise ValueError("refinement_self_test_report_invalid")
    fixture_bytes = _read_candidate_bytes(root, fixture_path)
    fixture_sha256 = hashlib.sha256(fixture_bytes).hexdigest()
    _identity(
        report.get("fixture"),
        path=fixture_path,
        sha256=fixture_sha256,
        error="refinement_self_test_report_invalid",
    )
    fingerprint = report.get("environment_fingerprint")
    if fingerprint != environment_fingerprint or not isinstance(fingerprint, str):
        raise ValueError("refinement_self_test_environment_changed")
    argv = self_test.get("argv_suffix")
    if (
        not isinstance(argv, list)
        or argv.count("--config") != 1
        or argv.index("--config") + 1 >= len(argv)
        or not isinstance(argv[argv.index("--config") + 1], str)
    ):
        raise ValueError("refinement_self_test_report_invalid")
    config_path = argv[argv.index("--config") + 1]
    config_bytes = _read_candidate_bytes(root, config_path)
    metrics = _validate_report_metrics(
        report.get("metrics"), self_test.get("expected_metrics")
    )
    report_path = _candidate_report_path(candidate.candidate_id)
    report_snapshot, secure_report_bytes = _secure_snapshot(
        project.root,
        report_path,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_self_test_report_invalid",
    )
    if secure_report_bytes != report_bytes:
        raise ValueError("refinement_self_test_report_invalid")
    prefix = f"refinement/candidates/{candidate.candidate_id}/"
    return _ValidatedCandidateSelfTest(
        report=report_snapshot.reference,
        environment_fingerprint=fingerprint,
        package_manifest=ArtifactRef(
            f"{prefix}{_MANIFEST_LOCAL_PATH}", manifest_sha256, len(manifest_bytes)
        ),
        entry_point=ArtifactRef(
            f"{prefix}{package.entry_point}", entry_sha256, len(entry_bytes)
        ),
        fixture=ArtifactRef(
            f"{prefix}{fixture_path}", fixture_sha256, len(fixture_bytes)
        ),
        config=ArtifactRef(
            f"{prefix}{config_path}",
            hashlib.sha256(config_bytes).hexdigest(),
            len(config_bytes),
        ),
        metrics=metrics,
    )


def _secure_registration_directory(project: ResearchProject, session_id: str) -> Path:
    root = project.root.resolve(strict=True)
    cursor = root
    for relative in (".researchclaw", "refinement-self-tests", session_id):
        cursor /= relative
        try:
            cursor.mkdir(mode=0o700)
        except FileExistsError:
            pass
        metadata = cursor.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("refinement_self_test_registration_recovery_invalid")
    return cursor


def _registration_payload(
    *,
    project: ResearchProject,
    session_id: str,
    candidate: CandidateStatus,
    producer: str,
    created_at: str,
    candidate_manifest: ArtifactRef,
    council_decision: ArtifactRef,
    evidence_packet: ArtifactRef,
    baseline_manifest: ArtifactRef,
    package_contract_ref: ArtifactRef,
    validated: _ValidatedCandidateSelfTest,
    self_test_argv: tuple[str, ...],
) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    role_references = [
        ("candidate_manifest", candidate_manifest),
        ("council_decision", council_decision),
        ("evidence_packet", evidence_packet),
        ("baseline_manifest", baseline_manifest),
        *(("candidate_file", reference) for reference in candidate.files),
        ("self_test_report", validated.report),
    ]
    seen: set[str] = set()
    for role, reference in role_references:
        if reference.path in seen:
            continue
        seen.add(reference.path)
        artifacts.append({"role": role, **_artifact_payload(reference)})
    artifacts.sort(key=lambda item: str(item["path"]))
    return {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "session_id": session_id,
        "candidate_id": candidate.candidate_id,
        "producer": producer,
        "created_at": created_at,
        "candidate_manifest": _artifact_payload(candidate_manifest),
        "council_decision": _artifact_payload(council_decision),
        "evidence_packet": _artifact_payload(evidence_packet),
        "baseline_manifest": _artifact_payload(baseline_manifest),
        "package_contract": _artifact_payload(package_contract_ref),
        "package_manifest": _artifact_payload(validated.package_manifest),
        "candidate_files": [
            _artifact_payload(reference) for reference in candidate.files
        ],
        "entry_point": _artifact_payload(validated.entry_point),
        "fixture": _artifact_payload(validated.fixture),
        "config": _artifact_payload(validated.config),
        "self_test_report": _artifact_payload(validated.report),
        "environment_fingerprint": validated.environment_fingerprint,
        "self_test_argv": list(self_test_argv),
        "metrics": list(validated.metrics),
        "development_only": True,
        "artifacts": artifacts,
    }


def _read_registration_or_created_at(
    project: ResearchProject, relative_path: str
) -> tuple[dict[str, object] | None, bytes | None, str]:
    path = project.root / relative_path
    if not os.path.lexists(path):
        return None, None, datetime.now(timezone.utc).isoformat()
    try:
        payload, payload_bytes = _read_bounded_json(path)
        created_at = _created_at(payload.get("created_at"))
        snapshot, secure_bytes = _secure_snapshot(
            project.root,
            relative_path,
            maximum_bytes=_MAX_JSON_BYTES,
            read_payload=True,
            error_code="refinement_self_test_registration_recovery_invalid",
        )
    except (OSError, ValueError) as error:
        raise ValueError(
            "refinement_self_test_registration_recovery_invalid"
        ) from error
    if secure_bytes != payload_bytes or snapshot.reference.size != len(payload_bytes):
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    return payload, payload_bytes, created_at


def _publish_refinement_self_test_state(
    project: ResearchProject, state: ProjectState
) -> None:
    """One replaceable state-publication seam for interruption tests."""
    project.persist_state(state)


def _direct_baseline_result_snapshot(project: ResearchProject):
    return _secure_snapshot(
        project.root,
        "experiment/results.json",
        maximum_bytes=16 * 1024 * 1024,
        read_payload=True,
        error_code="refinement_candidate_baseline_changed",
    )


def _bound_candidate_snapshot(
    project: ResearchProject, candidate: CandidateStatus
):
    manifest = project.state.artifacts.get(candidate.manifest_path)
    if manifest is None:
        raise ValueError("refinement_candidate_binding_invalid")
    manifest_payload, _ = _read_bounded_json(project.root / candidate.manifest_path)
    decision = manifest_payload.get("decision")
    decision_path = decision.get("path") if isinstance(decision, Mapping) else None
    decision_reference = (
        project.state.artifacts.get(decision_path)
        if isinstance(decision_path, str)
        else None
    )
    session_reference = project.state.artifacts.get(SESSION_PATH)
    packet_reference = project.state.artifacts.get(EVIDENCE_PACKET_PATH)
    if any(
        reference is None
        for reference in (decision_reference, session_reference, packet_reference)
    ):
        raise ValueError("refinement_candidate_binding_invalid")
    references = tuple(
        dict.fromkeys(
            (
                manifest,
                *candidate.files,
                decision_reference,
                session_reference,
                packet_reference,
            )
        )
    )
    return tuple(
        _secure_snapshot(
            project.root,
            reference.path,
            expected=reference,
            maximum_bytes=reference.size,
            error_code="refinement_candidate_identity_changed",
        )[0]
        for reference in references
    )


def _state_file_snapshot(project: ResearchProject):
    return _secure_snapshot(
        project.root,
        ".researchclaw/state.json",
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_self_test_registration_recovery_invalid",
    )


@project_mutation
def register_refinement_self_test(
    project: ResearchProject, candidate_id: str, report_path: str | Path
) -> CandidateStatus:
    """Validate and durably register one candidate development self-test."""
    current = ResearchProject.open(project.root)
    expected_report_path = _candidate_report_path(candidate_id)
    supplied_report_path = Path(report_path)
    if supplied_report_path.is_absolute() or supplied_report_path.as_posix() != (
        expected_report_path
    ):
        raise ValueError("refinement_self_test_report_path_invalid")
    starting_state = current.state
    session_payload, _session_bytes = _read_bounded_json(current.root / SESSION_PATH)
    session_id = session_payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("refinement_integrity_failure")
    registration_path = _registration_path(session_id, candidate_id)
    registered_report = starting_state.artifacts.get(expected_report_path)
    registered_registration = starting_state.artifacts.get(registration_path)
    complete_registration = (
        registered_report is not None
        and registered_registration is not None
        and starting_state.next_action == "prepare_refinement_run"
    )
    if any(
        (
            registered_report is not None,
            registered_registration is not None,
            starting_state.next_action == "prepare_refinement_run",
        )
    ) and not complete_registration:
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    candidate = (
        revalidate_refinement_candidate(current, candidate_id)
        if complete_registration
        else _revalidate_refinement_candidate(
            current,
            candidate_id,
            unregistered_report_path=expected_report_path,
        )
    )
    if not complete_registration and candidate.next_action != "prepare_refinement_self_test":
        raise ValueError("refinement_self_test_registration_unavailable")
    baseline = _baseline(current)
    baseline_before = _baseline_registration_snapshot(current, baseline)
    result_before = _direct_baseline_result_snapshot(current)
    candidate_before = _bound_candidate_snapshot(current, candidate)
    state_file_before = _state_file_snapshot(current)
    report_before = _secure_snapshot(
        current.root,
        expected_report_path,
        maximum_bytes=_MAX_JSON_BYTES,
        error_code="refinement_self_test_report_invalid",
    )[0]
    package = validate_experiment_package_contract_at(
        current,
        package_root=_candidate_root(current, candidate_id),
        contract_path=_CONTRACT_LOCAL_PATH,
    )
    try:
        environment = inspect_execution_environment(
            Path(sys.executable).resolve(strict=True), package.required_distributions
        )
    except (OSError, ValueError) as error:
        raise ValueError("execution_environment_unavailable") from error
    validated = _validate_candidate_self_test_report(
        current, candidate, package, environment.fingerprint
    )
    if _bound_candidate_snapshot(current, candidate) != candidate_before:
        raise ValueError("refinement_candidate_identity_changed")
    report_after = _secure_snapshot(
        current.root,
        expected_report_path,
        expected=validated.report,
        maximum_bytes=_MAX_JSON_BYTES,
        error_code="refinement_self_test_report_invalid",
    )[0]
    if report_after != report_before:
        raise ValueError("refinement_self_test_report_invalid")
    if registered_report is not None and registered_report != validated.report:
        raise ValueError("refinement_self_test_report_changed")
    repeated_candidate = (
        revalidate_refinement_candidate(current, candidate_id)
        if complete_registration
        else _revalidate_refinement_candidate(
            current,
            candidate_id,
            unregistered_report_path=expected_report_path,
        )
    )
    if repeated_candidate != candidate:
        raise ValueError("refinement_candidate_identity_changed")
    repeated_package = validate_experiment_package_contract_at(
        current,
        package_root=_candidate_root(current, candidate_id),
        contract_path=_CONTRACT_LOCAL_PATH,
    )
    if repeated_package != package:
        raise ValueError("refinement_candidate_identity_changed")
    baseline_after_validation = _baseline_registration_snapshot(current, baseline)
    result_after_validation = _direct_baseline_result_snapshot(current)
    if (
        baseline_after_validation != baseline_before
        or result_after_validation != result_before
        or _bound_candidate_snapshot(current, candidate) != candidate_before
        or _state_file_snapshot(current) != state_file_before
        or ResearchProject.open_readonly(current.root).state != starting_state
    ):
        raise ValueError("refinement_candidate_baseline_changed")

    candidate_manifest = starting_state.artifacts.get(candidate.manifest_path)
    evidence_packet = starting_state.artifacts.get(EVIDENCE_PACKET_PATH)
    if candidate_manifest is None or evidence_packet is None:
        raise ValueError("refinement_candidate_binding_invalid")
    manifest_payload, _ = _read_bounded_json(current.root / candidate.manifest_path)
    producer = manifest_payload.get("producer")
    decision_value = manifest_payload.get("decision")
    baseline_value = manifest_payload.get("baseline_manifest")
    if not isinstance(producer, str) or not isinstance(decision_value, Mapping):
        raise ValueError("refinement_candidate_binding_invalid")
    try:
        baseline_manifest = _artifact(baseline_value)
    except ValueError as error:
        raise ValueError("refinement_candidate_binding_invalid") from error
    if starting_state.artifacts.get(baseline_manifest.path) != baseline_manifest:
        raise ValueError("refinement_candidate_binding_invalid")
    decision_path = decision_value.get("path")
    if not isinstance(decision_path, str):
        raise ValueError("refinement_candidate_binding_invalid")
    council_decision = starting_state.artifacts.get(decision_path)
    if council_decision is None or council_decision.sha256 != candidate.decision_sha256:
        raise ValueError("refinement_candidate_binding_invalid")
    package_contract_ref = _candidate_reference(candidate, _CONTRACT_LOCAL_PATH)
    if package_contract_ref.sha256 != package.contract_sha256:
        raise ValueError("refinement_candidate_binding_invalid")

    existing_payload, existing_bytes, created_at = _read_registration_or_created_at(
        current, registration_path
    )
    registration_payload = _registration_payload(
        project=current,
        session_id=session_id,
        candidate=candidate,
        producer=producer,
        created_at=created_at,
        candidate_manifest=candidate_manifest,
        council_decision=council_decision,
        evidence_packet=evidence_packet,
        baseline_manifest=baseline_manifest,
        package_contract_ref=package_contract_ref,
        validated=validated,
        self_test_argv=package.self_test_argv,
    )
    registration_bytes = _canonical_json(registration_payload)
    if len(registration_bytes) > _MAX_JSON_BYTES:
        raise ValueError("refinement_self_test_registration_recovery_invalid")
    registration_ref = ArtifactRef(
        registration_path,
        hashlib.sha256(registration_bytes).hexdigest(),
        len(registration_bytes),
    )
    if existing_payload is not None:
        if existing_bytes != registration_bytes:
            raise ValueError("refinement_self_test_registration_recovery_invalid")
    else:
        _secure_registration_directory(current, session_id)
        try:
            _write_exclusive(current.root / registration_path, registration_bytes)
        except FileExistsError as error:
            raise ValueError(
                "refinement_self_test_registration_recovery_invalid"
            ) from error
    registration_snapshot, persisted_registration_bytes = _secure_snapshot(
        current.root,
        registration_path,
        expected=registration_ref,
        maximum_bytes=_MAX_JSON_BYTES,
        read_payload=True,
        error_code="refinement_self_test_registration_recovery_invalid",
    )
    if persisted_registration_bytes != registration_bytes:
        raise ValueError("refinement_self_test_registration_recovery_invalid")

    target_state = replace(
        starting_state,
        next_action="prepare_refinement_run",
        artifacts={
            **starting_state.artifacts,
            expected_report_path: validated.report,
            registration_path: registration_ref,
        },
    )
    if complete_registration:
        if starting_state != target_state:
            raise ValueError("refinement_self_test_registration_recovery_invalid")
    else:
        if ResearchProject.open_readonly(current.root).state != starting_state:
            raise ValueError("refinement_self_test_registration_recovery_invalid")
        try:
            _publish_refinement_self_test_state(current, target_state)
        except Exception:
            rollback = ResearchProject.open(current.root)
            if rollback.state != starting_state:
                rollback.persist_state(starting_state)
            raise

    try:
        published = ResearchProject.open_readonly(current.root)
        if published.state != target_state:
            raise ValueError("refinement_self_test_registration_recovery_invalid")
        final_candidate = revalidate_refinement_candidate(published, candidate_id)
        final_registration, final_registration_bytes = _read_bounded_json(
            published.root / registration_path
        )
        final_snapshot, final_secure_bytes = _secure_snapshot(
            published.root,
            registration_path,
            expected=registration_snapshot.reference,
            maximum_bytes=_MAX_JSON_BYTES,
            read_payload=True,
            error_code="refinement_self_test_registration_recovery_invalid",
        )
        if (
            final_candidate.next_action != "prepare_refinement_run"
            or final_registration != registration_payload
            or final_registration_bytes != registration_bytes
            or final_secure_bytes != registration_bytes
            or not _same_published_baseline_snapshot(
                (registration_snapshot,), (final_snapshot,)
            )
            or not _same_published_baseline_snapshot(
                baseline_before, _baseline_registration_snapshot(published, baseline)
            )
            or _direct_baseline_result_snapshot(published) != result_before
        ):
            raise ValueError("refinement_self_test_registration_recovery_invalid")
    except Exception:
        if not complete_registration:
            rollback = ResearchProject.open(current.root)
            if rollback.state != starting_state:
                rollback.persist_state(starting_state)
        raise
    return final_candidate
