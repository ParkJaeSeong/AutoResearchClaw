from __future__ import annotations

from dataclasses import replace

import pytest

from researchclaw.core.deliberation import (
    Assessment,
    CouncilRole,
    FinalVote,
    Rebuttal,
    decide_council,
    parse_assessment,
    parse_rebuttal,
)


_BINDING = "a" * 64


def valid_assessment(*, role: str, evidence_sha256: str = _BINDING) -> dict[str, object]:
    return {
        "schema_version": 1,
        "role": role,
        "evidence_packet_sha256": evidence_sha256,
        "recommendation": "refine",
        "rationale": ["The evidence supports a bounded refinement."],
        "evidence_refs": ["refinement/evidence_packet.json"],
        "unresolved_questions": [],
    }


def valid_rebuttal(*, role: str, evidence_sha256: str = _BINDING) -> dict[str, object]:
    return {
        "schema_version": 1,
        "role": role,
        "evidence_packet_sha256": evidence_sha256,
        "challenges": ["Address the stated uncertainty."],
        "responses": ["The uncertainty remains recorded."],
        "evidence_refs": ["refinement/evidence_packet.json"],
    }


def assessment(role: CouncilRole) -> Assessment:
    return parse_assessment(
        valid_assessment(role=role.value),
        expected_binding=_BINDING,
        expected_role=role,
    )


def rebuttal(role: CouncilRole) -> Rebuttal:
    return parse_rebuttal(
        valid_rebuttal(role=role.value),
        expected_binding=_BINDING,
        expected_role=role,
    )


def three_valid_assessments() -> tuple[Assessment, ...]:
    return tuple(assessment(role) for role in CouncilRole)


def two_valid_assessments() -> tuple[Assessment, ...]:
    return tuple(assessment(role) for role in tuple(CouncilRole)[:2])


def three_valid_rebuttals() -> tuple[Rebuttal, ...]:
    return tuple(rebuttal(role) for role in CouncilRole)


def two_valid_rebuttals() -> tuple[Rebuttal, ...]:
    return tuple(rebuttal(role) for role in tuple(CouncilRole)[:2])


def final_votes(*decisions: str) -> tuple[FinalVote, ...]:
    return tuple(
        FinalVote(
            role=role,
            evidence_packet_sha256=_BINDING,
            decision=decision,
            rationale=("Final position after rebuttal.",),
            evidence_refs=("refinement/evidence_packet.json",),
        )
        for role, decision in zip(CouncilRole, decisions)
    )


def test_assessment_requires_expected_role_and_binding():
    payload = valid_assessment(role="domain", evidence_sha256="a" * 64)
    assert parse_assessment(
        payload, expected_binding="a" * 64, expected_role=CouncilRole.DOMAIN
    ).role is CouncilRole.DOMAIN
    with pytest.raises(ValueError, match="deliberation_binding_invalid"):
        parse_assessment(
            payload, expected_binding="b" * 64, expected_role=CouncilRole.DOMAIN
        )


def test_implementation_role_cannot_vote():
    with pytest.raises(ValueError, match="deliberation_role_invalid"):
        parse_assessment(
            valid_assessment(role="implementation", evidence_sha256="a" * 64),
            expected_binding="a" * 64,
            expected_role=CouncilRole.DOMAIN,
        )


def test_parsers_require_closed_v1_records_and_project_relative_evidence_refs():
    payload = valid_assessment(role="domain")
    payload["unrecognized_authority"] = "coordinator"
    with pytest.raises(ValueError, match="deliberation_schema_invalid"):
        parse_assessment(
            payload, expected_binding=_BINDING, expected_role=CouncilRole.DOMAIN
        )

    bad_rebuttal = valid_rebuttal(role="domain")
    bad_rebuttal["evidence_refs"] = ["../outside.json"]
    with pytest.raises(ValueError, match="deliberation_evidence_invalid"):
        parse_rebuttal(
            bad_rebuttal, expected_binding=_BINDING, expected_role=CouncilRole.DOMAIN
        )


def test_two_matching_final_votes_form_decision():
    decision = decide_council(
        assessments=three_valid_assessments(),
        rebuttals=three_valid_rebuttals(),
        final_votes=final_votes("refine", "refine", "retain_baseline"),
    )
    assert decision.decision == "refine"
    assert decision.dissenting_roles == ("critical_reproducibility",)


def test_vote_before_complete_assessments_fails():
    with pytest.raises(ValueError, match="deliberation_sequence_invalid"):
        decide_council(
            assessments=two_valid_assessments(), rebuttals=(), final_votes=()
        )


def test_declared_single_vacancy_allows_the_two_remaining_voters_to_decide():
    decision = decide_council(
        assessments=two_valid_assessments(),
        rebuttals=two_valid_rebuttals(),
        final_votes=final_votes("refine", "refine"),
        vacant_roles=(CouncilRole.CRITICAL_REPRODUCIBILITY,),
    )
    assert decision.decision == "refine"
    assert decision.dissenting_roles == ()


def test_two_assessments_need_a_declared_vacancy():
    with pytest.raises(ValueError, match="deliberation_sequence_invalid"):
        decide_council(
            assessments=two_valid_assessments(),
            rebuttals=two_valid_rebuttals(),
            final_votes=final_votes("refine", "refine"),
        )


def test_council_rejects_changed_bindings_and_duplicate_final_votes():
    altered_assessment = replace(
        assessment(CouncilRole.METHODOLOGY), evidence_packet_sha256="b" * 64
    )
    with pytest.raises(ValueError, match="deliberation_binding_invalid"):
        decide_council(
            assessments=(
                assessment(CouncilRole.DOMAIN),
                altered_assessment,
                assessment(CouncilRole.CRITICAL_REPRODUCIBILITY),
            ),
            rebuttals=three_valid_rebuttals(),
            final_votes=final_votes("refine", "refine", "retain_baseline"),
        )

    altered_rebuttal = replace(
        rebuttal(CouncilRole.DOMAIN), evidence_packet_sha256="b" * 64
    )
    with pytest.raises(ValueError, match="deliberation_binding_invalid"):
        decide_council(
            assessments=three_valid_assessments(),
            rebuttals=(
                altered_rebuttal,
                rebuttal(CouncilRole.METHODOLOGY),
                rebuttal(CouncilRole.CRITICAL_REPRODUCIBILITY),
            ),
            final_votes=final_votes("refine", "refine", "retain_baseline"),
        )

    duplicate_role = replace(final_votes("refine", "refine", "retain_baseline")[1], role=CouncilRole.DOMAIN)
    with pytest.raises(ValueError, match="deliberation_role_invalid"):
        decide_council(
            assessments=three_valid_assessments(),
            rebuttals=three_valid_rebuttals(),
            final_votes=(
                final_votes("refine", "refine", "retain_baseline")[0],
                duplicate_role,
                final_votes("refine", "refine", "retain_baseline")[2],
            ),
        )


def test_council_rejects_ties_and_unsupported_final_decisions():
    with pytest.raises(ValueError, match="deliberation_vote_invalid"):
        decide_council(
            assessments=three_valid_assessments(),
            rebuttals=three_valid_rebuttals(),
            final_votes=final_votes(
                "refine", "retain_baseline", "request_discriminating_run"
            ),
        )

    with pytest.raises(ValueError, match="deliberation_vote_invalid"):
        decide_council(
            assessments=three_valid_assessments(),
            rebuttals=three_valid_rebuttals(),
            final_votes=final_votes("refine", "refine", "coordinator_override"),
        )
