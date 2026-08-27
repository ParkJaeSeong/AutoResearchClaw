"""Deterministic, network-free validation for stage-6 knowledge artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


EVIDENCE_LEVELS = frozenset({"full_text", "abstract", "metadata_only"})
ACCESS_STATUSES = frozenset({"full_text", "abstract", "metadata_only", "unavailable"})
GENERAL_CLAIM_LIMIT = 10
EXTENDED_CLAIM_LIMIT = 15
EXTENDED_SOURCE_TYPES = frozenset(
    {
        "standard",
        "government_guidance",
        "government_framework",
    }
)
PLACEHOLDER_MARKERS = (
    "template key finding",
    "template method summary",
    "placeholder",
    "fill this in",
)
CLAIM_FIELDS = frozenset(
    {
        "claim_id",
        "source_id",
        "claim",
        "evidence_summary",
        "evidence_level",
        "locator",
        "source_url",
        "applicability",
        "limitations",
        "doi",
        "arxiv_id",
        "supporting_excerpt",
        "quantitative_details",
        "conflicts_with",
    }
)
_FORBIDDEN_PAYLOAD_FIELDS = frozenset({"full_text", "source_text"})
_EVIDENCE_CONTENT_FIELDS = (
    "claim",
    "evidence_summary",
    "locator",
    "supporting_excerpt",
    "applicability",
    "limitations",
    "conflicts_with",
    "quantitative_details",
)

_SHORTLIST_PATH = "literature/shortlist.jsonl"
_CLAIMS_PATH = "knowledge/extractions.jsonl"
_MANIFEST_PATH = "knowledge/extraction_manifest.json"


@dataclass(frozen=True)
class KnowledgeIssue:
    code: str
    path: str
    message: str


def _invalid(issues: list[KnowledgeIssue], path: str, message: str) -> None:
    issues.append(KnowledgeIssue("invalid_format", path, message))


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _strict_json_loads(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_json_constant)


def _parse_jsonl(
    text: str,
    path: str,
    issues: list[KnowledgeIssue],
    *,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not text.strip():
        if not allow_empty:
            _invalid(issues, path, "artifact must contain at least one JSON object")
        return records
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = _strict_json_loads(line)
        except (json.JSONDecodeError, ValueError):
            _invalid(issues, path, f"line {line_number} must be valid JSON")
            continue
        if not isinstance(value, dict):
            _invalid(issues, path, f"line {line_number} must be a JSON object")
            continue
        records.append(value)
    return records


def _parse_manifest(text: str, issues: list[KnowledgeIssue]) -> dict[str, Any] | None:
    if not text.strip():
        _invalid(issues, _MANIFEST_PATH, "artifact must contain a JSON object")
        return None
    try:
        value = _strict_json_loads(text)
    except (json.JSONDecodeError, ValueError):
        _invalid(issues, _MANIFEST_PATH, "artifact must be valid JSON")
        return None
    if not isinstance(value, dict):
        _invalid(issues, _MANIFEST_PATH, "artifact must be a JSON object")
        return None
    return value


def _non_empty_string(record: dict[str, Any], field: str) -> bool:
    value = record.get(field)
    return isinstance(value, str) and bool(value.strip())


def _string_list(record: dict[str, Any], field: str, *, non_empty: bool = False) -> bool:
    value = record.get(field)
    return (
        isinstance(value, list)
        and (bool(value) or not non_empty)
        and all(isinstance(member, str) and bool(member.strip()) for member in value)
    )


def _normalize_claim(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return any(marker in value.casefold() for marker in PLACEHOLDER_MARKERS)
    if isinstance(value, list):
        return any(_contains_placeholder(member) for member in value)
    if isinstance(value, dict):
        return any(_contains_placeholder(member) for member in value.values())
    return False


def _forbidden_field_paths(value: Any, prefix: str) -> tuple[str, ...]:
    paths: list[str] = []
    if isinstance(value, dict):
        for field, member in value.items():
            path = f"{prefix}.{field}"
            if isinstance(field, str) and field.casefold() in _FORBIDDEN_PAYLOAD_FIELDS:
                paths.append(path)
            paths.extend(_forbidden_field_paths(member, path))
    elif isinstance(value, list):
        for index, member in enumerate(value):
            paths.extend(_forbidden_field_paths(member, f"{prefix}[{index}]"))
    return tuple(paths)


def _is_integer(value: Any, *, minimum: int | None = None) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and (minimum is None or value >= minimum)
    )


def _is_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_shortlist(
    records: list[dict[str, Any]],
    issues: list[KnowledgeIssue],
) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for line_number, record in enumerate(records, start=1):
        for field in ("source_id", "title", "decision", "reason"):
            if not _non_empty_string(record, field):
                _invalid(
                    issues,
                    _SHORTLIST_PATH,
                    f"line {line_number} requires non-empty string {field}",
                )
        source_id = record.get("source_id")
        if isinstance(source_id, str) and source_id.strip():
            if source_id in sources:
                _invalid(
                    issues,
                    _SHORTLIST_PATH,
                    f"line {line_number} has duplicate source_id: {source_id}",
                )
            else:
                sources[source_id] = record
        if record.get("decision") not in {"include", "exclude"}:
            _invalid(issues, _SHORTLIST_PATH, f"line {line_number} has an invalid decision")
        if not any(_non_empty_string(record, field) for field in ("doi", "arxiv_id", "url")):
            _invalid(
                issues,
                _SHORTLIST_PATH,
                f"line {line_number} requires doi, arxiv_id, or url",
            )
        for field in ("doi", "arxiv_id", "url", "source_type"):
            if field in record and not _non_empty_string(record, field):
                _invalid(
                    issues,
                    _SHORTLIST_PATH,
                    f"line {line_number} field {field} must be a non-empty string",
                )
    return sources


def _identifiers_match(field: str, claim_value: str, source_value: str) -> bool:
    if field in {"doi", "arxiv_id"}:
        return claim_value.casefold() == source_value.casefold()
    return claim_value == source_value


def _validate_claims(
    records: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    issues: list[KnowledgeIssue],
) -> None:
    claim_ids: set[str] = set()
    normalized_claims: set[tuple[str, str]] = set()
    claim_counts: dict[str, int] = {}
    for line_number, record in enumerate(records, start=1):
        for field in sorted(set(record) - CLAIM_FIELDS):
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"line {line_number} has unknown claim field: {field}",
            )
        for field_path in _forbidden_field_paths(
            record.get("quantitative_details"),
            "quantitative_details",
        ):
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"line {line_number} has forbidden claim field: {field_path}",
            )
        for field in (
            "claim_id",
            "source_id",
            "claim",
            "evidence_summary",
            "evidence_level",
            "source_url",
        ):
            if not _non_empty_string(record, field):
                _invalid(
                    issues,
                    _CLAIMS_PATH,
                    f"line {line_number} requires non-empty string {field}",
                )

        claim_id = record.get("claim_id")
        if isinstance(claim_id, str) and claim_id.strip():
            if claim_id in claim_ids:
                _invalid(
                    issues,
                    _CLAIMS_PATH,
                    f"line {line_number} has duplicate claim_id: {claim_id}",
                )
            claim_ids.add(claim_id)

        evidence_level = record.get("evidence_level")
        if evidence_level not in EVIDENCE_LEVELS:
            _invalid(issues, _CLAIMS_PATH, f"line {line_number} has an invalid evidence_level")

        applicability = record.get("applicability")
        if not isinstance(applicability, list) or not applicability:
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"line {line_number} applicability must be a non-empty list",
            )
        elif not _string_list(record, "applicability"):
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"line {line_number} applicability must contain only non-empty strings",
            )
        if not _string_list(record, "limitations"):
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"line {line_number} limitations must contain only strings",
            )
        if "conflicts_with" in record and not _string_list(record, "conflicts_with"):
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"line {line_number} conflicts_with must contain only non-empty strings",
            )
        for field in ("doi", "arxiv_id", "supporting_excerpt"):
            if field in record and not _non_empty_string(record, field):
                _invalid(
                    issues,
                    _CLAIMS_PATH,
                    f"line {line_number} field {field} must be a non-empty string",
                )

        source_id = record.get("source_id")
        source = sources.get(source_id) if isinstance(source_id, str) else None
        if source is None and isinstance(source_id, str) and source_id.strip():
            _invalid(issues, _CLAIMS_PATH, f"line {line_number} has unknown source_id: {source_id}")
        elif source is not None:
            if source.get("decision") == "exclude":
                _invalid(issues, _CLAIMS_PATH, f"line {line_number} refers to an excluded source")
            for claim_field, source_field in (
                ("doi", "doi"),
                ("arxiv_id", "arxiv_id"),
                ("source_url", "url"),
            ):
                claim_value = record.get(claim_field)
                source_value = source.get(source_field)
                if (
                    isinstance(claim_value, str)
                    and isinstance(source_value, str)
                    and not _identifiers_match(source_field, claim_value, source_value)
                ):
                    _invalid(
                        issues,
                        _CLAIMS_PATH,
                        f"line {line_number} {claim_field} contradicts shortlist {source_field}",
                    )

        if not _non_empty_string(record, "locator"):
            _invalid(issues, _CLAIMS_PATH, f"line {line_number} requires an explicit locator")
        excerpt = record.get("supporting_excerpt")
        if isinstance(excerpt, str) and len(excerpt.split()) > 25:
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"line {line_number} supporting_excerpt exceeds 25 words",
            )
        if evidence_level == "metadata_only" and "quantitative_details" in record:
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"line {line_number} metadata_only claim cannot contain quantitative_details",
            )
        for field in _EVIDENCE_CONTENT_FIELDS:
            if field in record and _contains_placeholder(record[field]):
                _invalid(
                    issues,
                    _CLAIMS_PATH,
                    f"line {line_number} {field} contains a placeholder marker",
                )

        claim = record.get("claim")
        if isinstance(source_id, str) and isinstance(claim, str) and claim.strip():
            if source is not None and source.get("decision") == "include":
                claim_counts[source_id] = claim_counts.get(source_id, 0) + 1
            normalized_key = (source_id, _normalize_claim(claim))
            if normalized_key in normalized_claims:
                _invalid(
                    issues,
                    _CLAIMS_PATH,
                    f"line {line_number} has a duplicate normalized claim for source {source_id}",
                )
            normalized_claims.add(normalized_key)

    for source_id, claim_count in claim_counts.items():
        source_type = sources[source_id].get("source_type")
        limit = EXTENDED_CLAIM_LIMIT if source_type in EXTENDED_SOURCE_TYPES else GENERAL_CLAIM_LIMIT
        if claim_count > limit:
            _invalid(
                issues,
                _CLAIMS_PATH,
                f"source {source_id} has {claim_count} claims and exceeds claim limit {limit}",
            )


def _actual_claim_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        source_id = record.get("source_id")
        if isinstance(source_id, str) and source_id.strip():
            counts[source_id] = counts.get(source_id, 0) + 1
    return counts


def _all_included_sources_unavailable(
    sources: dict[str, dict[str, Any]],
    manifest: dict[str, Any] | None,
) -> bool:
    included_ids = {
        source_id for source_id, source in sources.items() if source.get("decision") == "include"
    }
    if not included_ids or manifest is None or not isinstance(manifest.get("sources"), list):
        return False
    unavailable_ids = {
        entry.get("source_id")
        for entry in manifest["sources"]
        if isinstance(entry, dict)
        and entry.get("decision") == "include"
        and entry.get("access_status") == "unavailable"
        and _is_integer(entry.get("claim_count"), minimum=0)
        and entry.get("claim_count") == 0
        and isinstance(entry.get("failure_reason"), str)
        and bool(entry["failure_reason"].strip())
    }
    return included_ids <= unavailable_ids


def _validate_manifest(
    manifest: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    claims: list[dict[str, Any]],
    project_id: str,
    issues: list[KnowledgeIssue],
) -> None:
    if not _is_integer(manifest.get("schema_version")) or manifest.get("schema_version") != 1:
        _invalid(issues, _MANIFEST_PATH, "schema_version must be integer 1")

    manifest_project_id = manifest.get("project_id")
    if not isinstance(manifest_project_id, str) or not manifest_project_id.strip():
        _invalid(issues, _MANIFEST_PATH, "project_id must be a non-empty string")
    elif manifest_project_id != project_id:
        _invalid(issues, _MANIFEST_PATH, "project_id does not match current project")

    if not _is_timestamp(manifest.get("generated_at")):
        _invalid(issues, _MANIFEST_PATH, "invalid generated_at timestamp")

    source_entries = manifest.get("sources")
    if not isinstance(source_entries, list):
        _invalid(issues, _MANIFEST_PATH, "sources must be a list")
        source_entries = []
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        _invalid(issues, _MANIFEST_PATH, "summary must be a JSON object")
        summary = {}

    included_ids = {
        source_id for source_id, source in sources.items() if source.get("decision") == "include"
    }
    claim_counts = _actual_claim_counts(claims)
    manifest_ids: set[str] = set()
    processed_ids: set[str] = set()
    status_ids: dict[str, set[str]] = {status: set() for status in ACCESS_STATUSES}

    for entry_number, entry in enumerate(source_entries, start=1):
        if not isinstance(entry, dict):
            _invalid(
                issues,
                _MANIFEST_PATH,
                f"sources entry {entry_number} must be a JSON object",
            )
            continue

        for field in (
            "source_id",
            "decision",
            "access_status",
            "accessed_at",
            "access_url",
            "claim_count",
            "failure_reason",
        ):
            if field not in entry:
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"sources entry {entry_number} requires field {field}",
                )

        source_id = entry.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            _invalid(
                issues,
                _MANIFEST_PATH,
                f"sources entry {entry_number} requires non-empty string source_id",
            )
            source_id = ""
        elif source_id in manifest_ids:
            _invalid(issues, _MANIFEST_PATH, f"manifest has duplicate source_id: {source_id}")
        else:
            manifest_ids.add(source_id)

        approved_source = sources.get(source_id)
        if source_id and approved_source is None:
            _invalid(issues, _MANIFEST_PATH, f"manifest has unknown source_id: {source_id}")
        elif approved_source is not None and approved_source.get("decision") == "exclude":
            _invalid(issues, _MANIFEST_PATH, f"manifest contains excluded source: {source_id}")

        if entry.get("decision") != "include":
            _invalid(
                issues,
                _MANIFEST_PATH,
                f"manifest source {source_id or entry_number} must have decision include",
            )

        access_status = entry.get("access_status")
        if access_status not in ACCESS_STATUSES:
            _invalid(
                issues,
                _MANIFEST_PATH,
                f"manifest source {source_id or entry_number} has an invalid access_status",
            )
        elif source_id and source_id not in status_ids[access_status]:
            status_ids[access_status].add(source_id)

        declared_count = entry.get("claim_count")
        if not _is_integer(declared_count, minimum=0):
            _invalid(
                issues,
                _MANIFEST_PATH,
                f"manifest source {source_id or entry_number} claim_count must be a non-negative integer",
            )
        elif source_id:
            actual_count = claim_counts.get(source_id, 0)
            if declared_count != actual_count:
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"manifest source {source_id} claim_count {declared_count} does not match actual count {actual_count}",
                )

        actual_count = claim_counts.get(source_id, 0)
        if access_status == "unavailable":
            failure_reason = entry.get("failure_reason")
            if actual_count != 0:
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"unavailable source {source_id} must have zero claims",
                )
            if not isinstance(failure_reason, str) or not failure_reason.strip():
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"unavailable source {source_id} requires a failure_reason",
                )
            if entry.get("accessed_at") is not None:
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"unavailable source {source_id} requires null accessed_at",
                )
            if entry.get("access_url") is not None:
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"unavailable source {source_id} requires null access_url",
                )
            if actual_count == 0 and isinstance(failure_reason, str) and failure_reason.strip():
                processed_ids.add(source_id)
        elif access_status in EVIDENCE_LEVELS:
            if actual_count == 0:
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"non-unavailable source {source_id} must have at least one claim",
                )
            if not _is_timestamp(entry.get("accessed_at")):
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"non-unavailable source {source_id} requires accessed_at with an invalid accessed_at timestamp",
                )
            access_url = entry.get("access_url")
            if not isinstance(access_url, str) or not access_url.strip():
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"non-unavailable source {source_id} requires access_url",
                )
            if entry.get("failure_reason") is not None:
                _invalid(
                    issues,
                    _MANIFEST_PATH,
                    f"non-unavailable source {source_id} requires null failure_reason",
                )
            processed_ids.add(source_id)

    for missing_id in sorted(included_ids - manifest_ids):
        _invalid(issues, _MANIFEST_PATH, f"manifest is missing included source: {missing_id}")

    expected_summary = {
        "included_sources": len(included_ids),
        "processed_sources": len(processed_ids & included_ids),
        "claim_count": len(claims),
        "full_text_sources": len(status_ids["full_text"] & included_ids),
        "abstract_sources": len(status_ids["abstract"] & included_ids),
        "metadata_only_sources": len(status_ids["metadata_only"] & included_ids),
        "unavailable_sources": len(status_ids["unavailable"] & included_ids),
    }
    for field, expected in expected_summary.items():
        actual = summary.get(field)
        if not _is_integer(actual, minimum=0):
            _invalid(
                issues,
                _MANIFEST_PATH,
                f"summary {field} must be a non-negative integer",
            )
        elif actual != expected:
            _invalid(
                issues,
                _MANIFEST_PATH,
                f"summary {field} {actual} does not match recomputed count {expected}",
            )

    included_summary = summary.get("included_sources")
    processed_summary = summary.get("processed_sources")
    if (
        _is_integer(included_summary, minimum=0)
        and _is_integer(processed_summary, minimum=0)
        and processed_summary != included_summary
    ):
        _invalid(issues, _MANIFEST_PATH, "summary processed_sources must equal included_sources")


def validate_knowledge_extraction(
    shortlist_text: str,
    claims_text: str,
    manifest_text: str,
    project_id: str,
) -> tuple[KnowledgeIssue, ...]:
    """Validate local stage-6 artifacts without performing source access."""
    issues: list[KnowledgeIssue] = []
    shortlist = _parse_jsonl(shortlist_text, _SHORTLIST_PATH, issues)
    claims = _parse_jsonl(claims_text, _CLAIMS_PATH, issues, allow_empty=True)
    manifest = _parse_manifest(manifest_text, issues)
    sources = _validate_shortlist(shortlist, issues)
    if not claims_text.strip() and not _all_included_sources_unavailable(sources, manifest):
        _invalid(issues, _CLAIMS_PATH, "artifact must contain at least one JSON object")
    _validate_claims(claims, sources, issues)
    if manifest is not None:
        _validate_manifest(manifest, sources, claims, project_id, issues)
    return tuple(issues)
