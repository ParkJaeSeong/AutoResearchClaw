"""Pure validation for provenance-linked hypothesis candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HypothesisIssue:
    code: str
    message: str


_REQUIRED_TEXT_FIELDS = (
    "hypothesis_id",
    "statement",
    "novelty_argument",
    "rationale",
    "falsification_condition",
    "feasibility",
)
_PREDICTION_FIELDS = ("outcome", "direction", "magnitude", "measurement_context")
_ALLOWED_FIELDS = frozenset(
    {
        "hypothesis_id",
        "rank",
        "statement",
        "knowledge_gap_refs",
        "claim_refs",
        "novelty_argument",
        "rationale",
        "prediction",
        "falsification_condition",
        "required_baselines",
        "feasibility",
        "confounders",
        "challenges_conventional_wisdom",
    }
)


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_text_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_non_empty_text(item) for item in value)
    )


def _known_claim_refs(synthesis: str) -> set[str]:
    return set(re.findall(r"\[([A-Za-z0-9][A-Za-z0-9._:-]*)\]", synthesis))


def _known_gap_refs(synthesis: str) -> set[str]:
    match = re.search(
        r"(?ms)^##\s+Knowledge Gaps\s*$\n(.*?)(?=^##\s+|\Z)",
        synthesis,
    )
    if match is None:
        return set()
    numbers = re.findall(r"(?m)^\s*(\d+)[.)]\s+", match.group(1))
    return {f"gap-{number}" for number in numbers}


def validate_hypotheses(synthesis: str, candidates_jsonl: str) -> tuple[HypothesisIssue, ...]:
    """Validate structure, ranking, and synthesis provenance for stage 8."""
    issues: list[HypothesisIssue] = []
    records: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(candidates_jsonl.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            issues.append(HypothesisIssue("invalid_format", f"line {line_number} must be valid JSON"))
            continue
        if not isinstance(record, dict):
            issues.append(HypothesisIssue("invalid_format", f"line {line_number} must be a JSON object"))
            continue
        records.append((line_number, record))

    if not 2 <= len(records) <= 5:
        issues.append(HypothesisIssue("invalid_hypothesis_count", "candidates must contain two to five hypotheses"))

    known_claims = _known_claim_refs(synthesis)
    known_gaps = _known_gap_refs(synthesis)
    ids: list[str] = []
    ranks: list[int] = []
    has_contrarian = False

    for line_number, record in records:
        label = f"line {line_number}"
        unknown_fields = sorted(set(record) - _ALLOWED_FIELDS)
        if unknown_fields:
            issues.append(HypothesisIssue("unknown_field", f"{label} has undeclared fields: {', '.join(unknown_fields)}"))
        missing_fields = [field for field in _REQUIRED_TEXT_FIELDS if not _non_empty_text(record.get(field))]
        if missing_fields:
            issues.append(HypothesisIssue("missing_required_field", f"{label} requires: {', '.join(missing_fields)}"))

        hypothesis_id = record.get("hypothesis_id")
        if _non_empty_text(hypothesis_id):
            ids.append(str(hypothesis_id))
        rank = record.get("rank")
        if isinstance(rank, int) and not isinstance(rank, bool) and rank > 0:
            ranks.append(rank)
        else:
            issues.append(HypothesisIssue("invalid_rank", f"{label} rank must be a positive integer"))

        claim_refs = record.get("claim_refs")
        if not _non_empty_text_list(claim_refs):
            issues.append(HypothesisIssue("missing_claim_reference", f"{label} requires claim_refs"))
        else:
            unknown = sorted(set(claim_refs) - known_claims)
            if unknown:
                issues.append(HypothesisIssue("unknown_claim_reference", f"{label} references unknown claims: {', '.join(unknown)}"))

        gap_refs = record.get("knowledge_gap_refs")
        if not _non_empty_text_list(gap_refs):
            issues.append(HypothesisIssue("missing_knowledge_gap_reference", f"{label} requires knowledge_gap_refs"))
        else:
            unknown = sorted(set(gap_refs) - known_gaps)
            if unknown:
                issues.append(HypothesisIssue("unknown_knowledge_gap_reference", f"{label} references unknown gaps: {', '.join(unknown)}"))

        prediction = record.get("prediction")
        if isinstance(prediction, dict) and set(prediction) != set(_PREDICTION_FIELDS):
            issues.append(HypothesisIssue("unknown_field", f"{label} prediction must contain only: {', '.join(_PREDICTION_FIELDS)}"))
        if not isinstance(prediction, dict) or any(
            not _non_empty_text(prediction.get(field)) for field in _PREDICTION_FIELDS
        ):
            issues.append(HypothesisIssue("incomplete_prediction", f"{label} requires outcome, direction, magnitude, and measurement_context"))
        elif (
            re.search(r"\d", prediction["magnitude"]) is None
            or re.search(r"\b(?:tbd|todo|unknown|later|placeholder)\b", prediction["magnitude"], re.IGNORECASE)
        ):
            issues.append(HypothesisIssue("non_quantified_prediction", f"{label} prediction magnitude must contain a numeric quantity or threshold"))

        if not _non_empty_text(record.get("falsification_condition")):
            issues.append(HypothesisIssue("missing_falsification_condition", f"{label} requires a falsification condition"))
        for field in ("required_baselines", "confounders"):
            if not _non_empty_text_list(record.get(field)):
                issues.append(HypothesisIssue("missing_required_field", f"{label} requires non-empty {field}"))

        challenge = record.get("challenges_conventional_wisdom")
        if not isinstance(challenge, bool):
            issues.append(HypothesisIssue("invalid_contrarian_flag", f"{label} challenges_conventional_wisdom must be boolean"))
        elif challenge:
            has_contrarian = True

    if len(ids) != len(set(ids)):
        issues.append(HypothesisIssue("duplicate_hypothesis_id", "hypothesis_id values must be unique"))
    if len(ranks) == len(records) and sorted(ranks) != list(range(1, len(records) + 1)):
        issues.append(HypothesisIssue("invalid_rank", "ranks must be unique and contiguous from 1"))
    if records and not has_contrarian:
        issues.append(HypothesisIssue("missing_contrarian_hypothesis", "at least one hypothesis must challenge conventional wisdom"))
    return tuple(issues)
