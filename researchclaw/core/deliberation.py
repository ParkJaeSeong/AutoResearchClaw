"""Closed, evidence-bound records for reusable council deliberation.

This module deliberately validates procedure and authority only.  It never
evaluates the scientific merit of a council member's recommendation or vote.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
import re

from .paths import validate_relative_path


_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FINAL_DECISIONS = frozenset(
    {
        "refine",
        "select_candidate",
        "retain_baseline",
        "request_discriminating_run",
        "inconclusive",
    }
)


class CouncilRole(str, Enum):
    """The only roles permitted to assess, rebut, or vote in a council."""

    DOMAIN = "domain"
    METHODOLOGY = "methodology"
    CRITICAL_REPRODUCIBILITY = "critical_reproducibility"


@dataclass(frozen=True)
class Assessment:
    role: CouncilRole
    evidence_packet_sha256: str
    recommendation: str
    rationale: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    unresolved_questions: tuple[str, ...]


@dataclass(frozen=True)
class Rebuttal:
    role: CouncilRole
    evidence_packet_sha256: str
    challenges: tuple[str, ...]
    responses: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class FinalVote:
    role: CouncilRole
    evidence_packet_sha256: str
    decision: str
    rationale: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CouncilDecision:
    decision: str
    supporting_roles: tuple[str, ...]
    dissenting_roles: tuple[str, ...]
    final_votes: tuple[FinalVote, ...]


def _error(kind: str) -> ValueError:
    return ValueError(f"deliberation_{kind}_invalid")


def _require_closed_mapping(payload: object, required_keys: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(payload, Mapping) or set(payload) != required_keys:
        raise _error("schema")
    if payload.get("schema_version") != _SCHEMA_VERSION or isinstance(
        payload.get("schema_version"), bool
    ):
        raise _error("schema")
    return payload


def _role(value: object) -> CouncilRole:
    if isinstance(value, CouncilRole):
        return value
    if not isinstance(value, str):
        raise _error("role")
    try:
        return CouncilRole(value)
    except ValueError as error:
        raise _error("role") from error


def _binding(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise _error("binding")
    return value


def _text(value: object, *, kind: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(kind)
    return value


def _texts(value: object, *, allow_empty: bool, kind: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or (not value and not allow_empty):
        raise _error(kind)
    return tuple(_text(item, kind=kind) for item in value)


def _evidence_refs(value: object) -> tuple[str, ...]:
    references = _texts(value, allow_empty=True, kind="evidence")
    try:
        return tuple(validate_relative_path(reference, kind="evidence") for reference in references)
    except ValueError as error:
        raise _error("evidence") from error


def _expected_role(value: object) -> CouncilRole:
    return _role(value)


def parse_assessment(
    payload: object, *, expected_binding: str, expected_role: CouncilRole
) -> Assessment:
    """Parse one initial council assessment against its assigned authority."""
    record = _require_closed_mapping(
        payload,
        frozenset(
            {
                "schema_version",
                "role",
                "evidence_packet_sha256",
                "recommendation",
                "rationale",
                "evidence_refs",
                "unresolved_questions",
            }
        ),
    )
    role = _role(record["role"])
    if role is not _expected_role(expected_role):
        raise _error("role")
    binding = _binding(record["evidence_packet_sha256"])
    if binding != _binding(expected_binding):
        raise _error("binding")
    return Assessment(
        role=role,
        evidence_packet_sha256=binding,
        recommendation=_text(record["recommendation"], kind="schema"),
        rationale=_texts(record["rationale"], allow_empty=False, kind="schema"),
        evidence_refs=_evidence_refs(record["evidence_refs"]),
        unresolved_questions=_texts(
            record["unresolved_questions"], allow_empty=True, kind="schema"
        ),
    )


def parse_rebuttal(
    payload: object, *, expected_binding: str, expected_role: CouncilRole
) -> Rebuttal:
    """Parse one council rebuttal against its assigned authority."""
    record = _require_closed_mapping(
        payload,
        frozenset(
            {
                "schema_version",
                "role",
                "evidence_packet_sha256",
                "challenges",
                "responses",
                "evidence_refs",
            }
        ),
    )
    role = _role(record["role"])
    if role is not _expected_role(expected_role):
        raise _error("role")
    binding = _binding(record["evidence_packet_sha256"])
    if binding != _binding(expected_binding):
        raise _error("binding")
    return Rebuttal(
        role=role,
        evidence_packet_sha256=binding,
        challenges=_texts(record["challenges"], allow_empty=False, kind="schema"),
        responses=_texts(record["responses"], allow_empty=False, kind="schema"),
        evidence_refs=_evidence_refs(record["evidence_refs"]),
    )


def _unique_roles(records: Iterable[object], expected_type: type[object]) -> dict[CouncilRole, object]:
    by_role: dict[CouncilRole, object] = {}
    for record in records:
        if not isinstance(record, expected_type):
            raise _error("schema")
        role = _role(getattr(record, "role"))
        if role in by_role:
            raise _error("role")
        by_role[role] = record
    return by_role


def _validate_assessment(record: Assessment) -> None:
    _binding(record.evidence_packet_sha256)
    _text(record.recommendation, kind="schema")
    _texts(record.rationale, allow_empty=False, kind="schema")
    _evidence_refs(record.evidence_refs)
    _texts(record.unresolved_questions, allow_empty=True, kind="schema")


def _validate_rebuttal(record: Rebuttal) -> None:
    _binding(record.evidence_packet_sha256)
    _texts(record.challenges, allow_empty=False, kind="schema")
    _texts(record.responses, allow_empty=False, kind="schema")
    _evidence_refs(record.evidence_refs)


def _validate_vote(record: FinalVote) -> None:
    _binding(record.evidence_packet_sha256)
    if record.decision not in _FINAL_DECISIONS:
        raise _error("vote")
    _texts(record.rationale, allow_empty=True, kind="schema")
    _evidence_refs(record.evidence_refs)


def _vacancies(vacant_roles: Iterable[CouncilRole | str]) -> frozenset[CouncilRole]:
    try:
        roles = tuple(_role(role) for role in vacant_roles)
    except TypeError as error:
        raise _error("role") from error
    if len(roles) > 1 or len(set(roles)) != len(roles):
        raise _error("role")
    return frozenset(roles)


def _require_exact_prior_roles(
    records: Mapping[CouncilRole, object], required_roles: frozenset[CouncilRole]
) -> None:
    if set(records) != required_roles:
        raise _error("sequence")


def decide_council(
    *,
    assessments: Iterable[Assessment],
    rebuttals: Iterable[Rebuttal],
    final_votes: Iterable[FinalVote],
    vacant_roles: Iterable[CouncilRole | str] = (),
) -> CouncilDecision:
    """Validate deliberation sequence and return a quorum-backed final decision.

    A caller may declare one vacancy only after its durable retry/vacancy record
    has been verified by the owning workflow.  This data-only module does not
    create or persist that record.
    """
    vacancies = _vacancies(vacant_roles)
    required_roles = frozenset(CouncilRole) - vacancies
    assessment_records = _unique_roles(assessments, Assessment)
    _require_exact_prior_roles(assessment_records, required_roles)
    common_binding = next(iter(assessment_records.values())).evidence_packet_sha256
    for record in assessment_records.values():
        _validate_assessment(record)  # type: ignore[arg-type]
        if record.evidence_packet_sha256 != common_binding:
            raise _error("binding")

    rebuttal_records = _unique_roles(rebuttals, Rebuttal)
    _require_exact_prior_roles(rebuttal_records, required_roles)
    for record in rebuttal_records.values():
        _validate_rebuttal(record)  # type: ignore[arg-type]
        if record.evidence_packet_sha256 != common_binding:
            raise _error("binding")

    vote_records = _unique_roles(final_votes, FinalVote)
    if len(vote_records) < 2 or not set(vote_records).issubset(required_roles):
        raise _error("sequence")
    for record in vote_records.values():
        _validate_vote(record)  # type: ignore[arg-type]
        if record.evidence_packet_sha256 != common_binding:
            raise _error("binding")

    counts = Counter(record.decision for record in vote_records.values())
    winning_decision, winning_count = counts.most_common(1)[0]
    if winning_count < 2:
        raise _error("vote")

    supporting_roles = tuple(
        role.value
        for role in CouncilRole
        if role in vote_records and vote_records[role].decision == winning_decision
    )
    dissenting_roles = tuple(
        role.value
        for role in CouncilRole
        if role in vote_records and vote_records[role].decision != winning_decision
    )
    ordered_votes = tuple(vote_records[role] for role in CouncilRole if role in vote_records)
    return CouncilDecision(
        decision=winning_decision,
        supporting_roles=supporting_roles,
        dissenting_roles=dissenting_roles,
        final_votes=ordered_votes,
    )


__all__ = [
    "Assessment",
    "CouncilDecision",
    "CouncilRole",
    "FinalVote",
    "Rebuttal",
    "decide_council",
    "parse_assessment",
    "parse_rebuttal",
]
