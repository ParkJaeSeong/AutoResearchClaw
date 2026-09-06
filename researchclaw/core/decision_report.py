"""Deterministic Markdown rendering for validated Stage 15 decisions."""

from __future__ import annotations

from collections.abc import Mapping


def _link(reference: str) -> str:
    target = reference.removeprefix("analysis/")
    if target == reference:
        target = f"../{reference}"
    return f"[{reference}](<{target}>)"


def _evidence(values: object) -> str:
    if not isinstance(values, list):
        return ""
    return ", ".join(_link(str(value)) for value in values)


def _statements(output: list[str], heading: str, values: object) -> None:
    output.extend((f"## {heading}", ""))
    if isinstance(values, list):
        for statement in values:
            if isinstance(statement, Mapping):
                output.append(
                    f"- {statement.get('text', '')} — evidence: "
                    f"{_evidence(statement.get('evidence_refs'))}"
                )
    output.append("")


def _role_statements(output: list[str], label: str, values: object) -> None:
    if not isinstance(values, list):
        return
    for statement in values:
        if isinstance(statement, Mapping):
            output.append(
                f"- {label}: {statement.get('text', '')} — evidence: "
                f"{_evidence(statement.get('evidence_refs'))}"
            )


def _text_items(output: list[str], label: str, values: object) -> None:
    if isinstance(values, list):
        output.extend(f"- {label}: {value}" for value in values)


def render_decision_report(payload: Mapping[str, object]) -> str:
    """Render stable Markdown from records validated by the registration layer."""
    result = payload.get("decision_result", payload)
    packet = payload.get("evidence_packet", {})
    if not isinstance(result, Mapping) or not isinstance(packet, Mapping):
        raise ValueError("decision_report_payload_invalid")  # noqa: TRY004

    output = [
        "# Research Decision",
        "",
        f"Project: `{result.get('project_id', '')}`",
        "",
        f"Direction: `{result.get('decision')}`",
        "",
        f"Disposition: `{result.get('disposition', '')}`",
        "",
        "Evidence packet: " + _link("analysis/research-decision/evidence_packet.json"),
        "",
    ]
    _statements(output, "Scope", result.get("claim_scope"))
    _statements(output, "Rationale", result.get("rationale"))
    _statements(output, "Limitations", result.get("limitations"))
    _statements(output, "Mandatory follow-up", result.get("mandatory_follow_up"))
    _statements(output, "Optional follow-up", result.get("optional_follow_up"))
    _statements(output, "Unresolved issues", result.get("unresolved_issues"))

    output.extend(("## Disagreements", ""))
    disagreements = result.get("disagreements")
    if isinstance(disagreements, list):
        for item in disagreements:
            if isinstance(item, Mapping):
                output.append(
                    f"- **{item.get('role', '')}**: {item.get('text', '')} — evidence: "
                    f"{_evidence(item.get('evidence_refs'))}"
                )
    output.append("")

    output.extend(("## Independent role records", ""))
    reviews = payload.get("reviews")
    if isinstance(reviews, list):
        for review in reviews:
            if not isinstance(review, Mapping):
                continue
            output.extend(
                (
                    f"### {review.get('role', '')} — `{review.get('producer', '')}`",
                    "",
                    f"Original recommendation: `{review.get('recommendation', '')}`",
                    "",
                )
            )
            _role_statements(output, "Rationale", review.get("rationale"))
            _role_statements(output, "Scope", review.get("claim_scope"))
            _role_statements(
                output, "Mandatory follow-up", review.get("mandatory_follow_up")
            )
            _role_statements(
                output, "Optional follow-up", review.get("optional_follow_up")
            )
            _role_statements(output, "Alternative", review.get("alternatives"))
            _text_items(output, "Question", review.get("questions"))
            output.append("")

    output.extend(("## Actual role responses", ""))
    rebuttals = payload.get("rebuttals")
    if isinstance(rebuttals, Mapping):
        responses = rebuttals.get("responses")
        if isinstance(responses, list):
            for response in responses:
                if not isinstance(response, Mapping):
                    continue
                output.extend(
                    (
                        (
                            f"### {response.get('role', '')} — "
                            f"`{response.get('producer', '')}`"
                        ),
                        "",
                        (
                            "Final recommendation: "
                            f"`{response.get('final_recommendation')}`"
                        ),
                        "",
                    )
                )
                _text_items(output, "Challenge", response.get("challenges"))
                _role_statements(output, "Response", response.get("responses"))
                output.append("")

    output.extend(("## Preserved Stage 14 scope and limitations", ""))
    context = payload.get("analysis_context")
    if isinstance(context, Mapping):
        _text_items(output, "Scope", context.get("scope"))
        _text_items(output, "Limitation", context.get("limitations"))
    output.append("")

    output.extend(("## Preserved source context", ""))
    inputs = packet.get("inputs")
    research_evidence = (
        inputs.get("research_evidence") if isinstance(inputs, Mapping) else None
    )
    source_context = payload.get("source_context")
    if not isinstance(source_context, Mapping):
        source_context = (
            research_evidence.get("selection_context")
            if isinstance(research_evidence, Mapping)
            else None
        )
    if isinstance(source_context, Mapping):
        _text_items(output, "Source rationale", source_context.get("rationale"))
        supporting = source_context.get("supporting_roles")
        if isinstance(supporting, list) and supporting:
            output.append(
                "Supporting roles: "
                + ", ".join(f"`{role}`" for role in supporting)
            )
        dissent = source_context.get("dissenting_roles")
        if isinstance(dissent, list) and dissent:
            output.append(
                "Dissenting roles: " + ", ".join(f"`{role}`" for role in dissent)
            )
        _text_items(output, "Source limitation", source_context.get("limitations"))
        _text_items(
            output, "Stage 14 question", source_context.get("stage_14_questions")
        )
        votes = source_context.get("votes")
        if isinstance(votes, list):
            output.extend(("", "### Preserved role votes", ""))
            for vote in votes:
                if not isinstance(vote, Mapping):
                    continue
                output.extend(
                    (
                        f"#### {vote.get('role', '')} — `{vote.get('producer', '')}`",
                        "",
                        f"Recorded decision: `{vote.get('decision', '')}`",
                    )
                )
                _text_items(output, "Vote rationale", vote.get("rationale"))
                evidence_refs = vote.get("evidence_refs")
                if isinstance(evidence_refs, list):
                    output.append(f"- Evidence: {_evidence(evidence_refs)}")
                output.append("")
    output.append("")
    return "\n".join(output)
