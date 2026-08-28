"""Pure validation for stage-9 hypothesis validation designs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationDesignIssue:
    code: str
    message: str


_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "project_id",
        "validation_type",
        "hypothesis_ids",
        "title",
        "objective",
        "validation_questions",
        "evidence_sources",
        "comparators",
        "metrics",
        "success_criteria",
        "failure_criteria",
        "bias_controls",
        "resources",
        "reproducibility",
        "risks",
        "method",
    }
)
_TEXT_FIELDS = ("title", "objective")
_TEXT_LIST_FIELDS = (
    "hypothesis_ids",
    "validation_questions",
    "comparators",
    "success_criteria",
    "failure_criteria",
    "bias_controls",
)
_EVIDENCE_FIELDS = frozenset(
    {"category", "scope", "inclusion_criteria", "exclusion_criteria", "collection_method"}
)
_METRIC_FIELDS = frozenset({"name", "definition", "target", "direction", "unit"})
_RESOURCE_FIELDS = frozenset({"people", "data", "tools", "duration", "budget"})
_REPRODUCIBILITY_FIELDS = frozenset(
    {"protocol_version", "data_provenance", "analysis_plan", "audit_trail"}
)
_RISK_FIELDS = frozenset({"risk", "mitigation"})
_METHOD_FIELDS = {
    "policy_evidence": frozenset(
        {
            "data_sources",
            "stakeholder_groups",
            "candidate_selection",
            "scoring_model",
            "sensitivity_analysis",
            "conflict_of_interest_plan",
        }
    ),
    "computational": frozenset(
        {"datasets", "split_strategy", "baselines", "evaluation_protocol"}
    ),
    "laboratory": frozenset({"materials", "controls", "procedure", "safety"}),
}
_METHOD_LIST_FIELDS = {
    "policy_evidence": frozenset({"data_sources", "stakeholder_groups"}),
    "computational": frozenset({"datasets", "baselines"}),
    "laboratory": frozenset({"materials", "controls"}),
}
_PLACEHOLDER = re.compile(r"\b(?:tbd|todo|unknown|later|placeholder)\b", re.IGNORECASE)
_THRESHOLD_CUE = re.compile(
    r">=|<=|>|<|=|%|"
    r"\b(?:at least|at most|no more than|no less than|more than|less than|"
    r"between|within|exactly|increase(?:d)? by|decrease(?:d)? by|top|"
    r"percent(?:age)?(?: points?)?)\b|"
    r"이상|이하|초과|미만|증가|감소|퍼센트|백분율",
    re.IGNORECASE,
)
_QUANTIFIED_VALUE = re.compile(
    r"^\s*[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
    r"(?:\s+[\wµμ°%./^·-]+(?:\s+[\wµμ°%./^·-]+)*)?\s*$"
)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_list(value: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(_text(item) for item in value)
    )


def _hypothesis_ids(candidates_jsonl: str) -> set[str]:
    identifiers: set[str] = set()
    for line in candidates_jsonl.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and _text(record.get("hypothesis_id")):
            identifiers.add(record["hypothesis_id"])
    return identifiers


def _closed_object(
    value: object,
    fields: frozenset[str],
    issues: list[ValidationDesignIssue],
    label: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != fields:
        issues.append(
            ValidationDesignIssue(
                "unknown_field",
                f"{label} must contain exactly: {', '.join(sorted(fields))}",
            )
        )
        return None
    return value


def validate_validation_design(
    candidates_jsonl: str,
    design_json: str,
    project_id: str,
) -> tuple[ValidationDesignIssue, ...]:
    """Validate one closed, provenance-linked stage-9 design."""
    issues: list[ValidationDesignIssue] = []
    try:
        design = json.loads(design_json)
    except json.JSONDecodeError:
        return (ValidationDesignIssue("invalid_format", "design must be valid JSON"),)
    if not isinstance(design, dict):
        return (ValidationDesignIssue("invalid_format", "design must be a JSON object"),)

    unknown_fields = sorted(set(design) - _TOP_LEVEL_FIELDS)
    missing_fields = sorted(_TOP_LEVEL_FIELDS - set(design))
    if unknown_fields:
        issues.append(
            ValidationDesignIssue(
                "unknown_field", f"design has undeclared fields: {', '.join(unknown_fields)}"
            )
        )
    if missing_fields:
        issues.append(
            ValidationDesignIssue(
                "missing_required_field", f"design requires: {', '.join(missing_fields)}"
            )
        )

    schema_version = design.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version != 1:
        issues.append(ValidationDesignIssue("invalid_format", "schema_version must equal 1"))
    if design.get("project_id") != project_id:
        issues.append(ValidationDesignIssue("project_mismatch", "project_id must match durable state"))
    for field in _TEXT_FIELDS:
        if not _text(design.get(field)):
            issues.append(ValidationDesignIssue("missing_required_field", f"{field} must be non-empty text"))
    for field in _TEXT_LIST_FIELDS:
        if not _text_list(design.get(field)):
            issues.append(ValidationDesignIssue("missing_required_field", f"{field} must be a non-empty text list"))

    known_hypotheses = _hypothesis_ids(candidates_jsonl)
    references = design.get("hypothesis_ids")
    if _text_list(references):
        unknown = sorted(set(references) - known_hypotheses)
        if unknown:
            issues.append(
                ValidationDesignIssue(
                    "unknown_hypothesis_reference",
                    f"design references unknown hypotheses: {', '.join(unknown)}",
                )
            )

    evidence_sources = design.get("evidence_sources")
    if not isinstance(evidence_sources, list) or not evidence_sources:
        issues.append(ValidationDesignIssue("missing_required_field", "evidence_sources must be non-empty"))
    else:
        for index, raw in enumerate(evidence_sources, start=1):
            source = _closed_object(raw, _EVIDENCE_FIELDS, issues, f"evidence_sources[{index}]")
            if source is None:
                continue
            if not all(_text(source.get(field)) for field in ("category", "scope", "collection_method")):
                issues.append(ValidationDesignIssue("invalid_evidence_source", f"evidence_sources[{index}] requires non-empty text fields"))
            if not _text_list(source.get("inclusion_criteria")) or not _text_list(
                source.get("exclusion_criteria"), allow_empty=True
            ):
                issues.append(ValidationDesignIssue("invalid_evidence_source", f"evidence_sources[{index}] has invalid criteria"))

    metrics = design.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        issues.append(ValidationDesignIssue("missing_required_field", "metrics must be non-empty"))
    else:
        for index, raw in enumerate(metrics, start=1):
            metric = _closed_object(raw, _METRIC_FIELDS, issues, f"metrics[{index}]")
            if metric is None:
                continue
            if not all(_text(metric.get(field)) for field in _METRIC_FIELDS):
                issues.append(ValidationDesignIssue("invalid_metric", f"metrics[{index}] requires non-empty text fields"))
                continue
            target = metric["target"]
            if (
                re.search(r"\d", target) is None
                or (
                    _THRESHOLD_CUE.search(target) is None
                    and _QUANTIFIED_VALUE.fullmatch(target) is None
                )
                or _PLACEHOLDER.search(target)
            ):
                issues.append(ValidationDesignIssue("non_quantified_metric", f"metrics[{index}] target must contain a numeric threshold"))

    resources = _closed_object(design.get("resources"), _RESOURCE_FIELDS, issues, "resources")
    if resources is not None and (
        not all(_text_list(resources.get(field)) for field in ("people", "data", "tools"))
        or not all(_text(resources.get(field)) for field in ("duration", "budget"))
    ):
        issues.append(ValidationDesignIssue("invalid_resources", "resources fields must be non-empty"))

    reproducibility = _closed_object(
        design.get("reproducibility"),
        _REPRODUCIBILITY_FIELDS,
        issues,
        "reproducibility",
    )
    if reproducibility is not None and not all(
        _text(reproducibility.get(field)) for field in _REPRODUCIBILITY_FIELDS
    ):
        issues.append(ValidationDesignIssue("invalid_reproducibility", "reproducibility fields must be non-empty"))

    risks = design.get("risks")
    if not isinstance(risks, list) or not risks:
        issues.append(ValidationDesignIssue("missing_required_field", "risks must be non-empty"))
    else:
        for index, raw in enumerate(risks, start=1):
            risk = _closed_object(raw, _RISK_FIELDS, issues, f"risks[{index}]")
            if risk is not None and not all(_text(risk.get(field)) for field in _RISK_FIELDS):
                issues.append(ValidationDesignIssue("invalid_risk", f"risks[{index}] requires risk and mitigation"))

    validation_type = design.get("validation_type")
    expected_method_fields = (
        _METHOD_FIELDS.get(validation_type) if isinstance(validation_type, str) else None
    )
    method = design.get("method")
    if expected_method_fields is None or not isinstance(method, dict) or set(method) != expected_method_fields:
        issues.append(ValidationDesignIssue("invalid_validation_method", "method does not match validation_type"))
    else:
        list_fields = _METHOD_LIST_FIELDS[validation_type]
        if any(not _text_list(method.get(field)) for field in list_fields) or any(
            not _text(method.get(field)) for field in expected_method_fields - list_fields
        ):
            issues.append(ValidationDesignIssue("invalid_validation_method", "method fields must be non-empty"))

    return tuple(issues)
