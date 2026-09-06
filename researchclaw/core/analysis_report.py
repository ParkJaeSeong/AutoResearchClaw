"""Deterministic Markdown rendering for validated Stage 14 analysis."""

from __future__ import annotations

from collections.abc import Mapping


def _lines(values: object) -> list[str]:
    return [str(value) for value in values] if isinstance(values, list) else []


def _link(reference: str) -> str:
    target = reference.removeprefix("analysis/")
    if target == reference:
        target = f"../{reference}"
    return f"[{reference}](<{target}>)"


def _evidence(values: object) -> str:
    if not isinstance(values, list):
        return ""
    return ", ".join(_link(str(value)) for value in values)


def _bullet_section(output: list[str], heading: str, values: object) -> None:
    output.extend((f"## {heading}", ""))
    output.extend(f"- {value}" for value in _lines(values))
    output.append("")


def _metric_source_label(metric: Mapping[str, object], packet: Mapping[str, object]) -> str:
    inputs = packet.get("inputs")
    if not isinstance(inputs, Mapping):
        return "Observed result"
    baseline = inputs.get("baseline_result")
    selected = inputs.get("selected_result")
    if not isinstance(baseline, Mapping) or not isinstance(selected, Mapping):
        return "Observed result"
    baseline_path = baseline.get("path")
    selected_path = selected.get("path")
    references = metric.get("evidence_refs")
    if not isinstance(references, list):
        return "Observed result"
    if baseline_path in references:
        return "Baseline result"
    if selected_path in references and selected_path != baseline_path:
        return "Selected candidate"
    return "Observed result"


def render_analysis_report(payload: dict) -> str:
    """Render a stable report from already validated structured records."""
    result_value = payload.get("analysis_result", payload)
    if not isinstance(result_value, Mapping):
        raise ValueError("analysis_report_payload_invalid")
    packet = payload.get("evidence_packet", {})
    if not isinstance(packet, Mapping):
        packet = {}

    output = [
        "# Result Analysis",
        "",
        f"Project: `{result_value.get('project_id', '')}`",
        "",
        "Evidence packet: " + _link("analysis/evidence_packet.json"),
        "",
    ]
    _bullet_section(output, "Scope", result_value.get("scope"))

    output.extend(("## Observed metrics", ""))
    for metric in result_value.get("observed_metrics", []):
        if isinstance(metric, Mapping):
            output.append(
                f"- {_metric_source_label(metric, packet)} — "
                f"`{metric.get('name')}`: {metric.get('value')} "
                f"{metric.get('unit')} — evidence: {_evidence(metric.get('evidence_refs'))}"
            )
    output.append("")

    output.extend(("## Hypothesis assessments", ""))
    for assessment in result_value.get("hypothesis_assessments", []):
        if isinstance(assessment, Mapping):
            output.extend(
                (
                    f"### {assessment.get('hypothesis_id')}: {assessment.get('verdict')}",
                    "",
                    str(assessment.get("explanation", "")),
                    "",
                    f"Evidence: {_evidence(assessment.get('evidence_refs'))}",
                    "",
                )
            )

    _bullet_section(output, "Explanations", result_value.get("explanations"))
    _bullet_section(output, "Alternative explanations", result_value.get("alternatives"))
    _bullet_section(output, "Uncertainty", result_value.get("uncertainty"))
    _bullet_section(output, "Limitations", result_value.get("limitations"))
    _bullet_section(output, "Agreement", result_value.get("agreement"))

    reviews = payload.get("reviews")
    if isinstance(reviews, list):
        output.extend(("## Independent review record", ""))
        for review in reviews:
            if not isinstance(review, Mapping):
                continue
            output.extend(
                (
                    f"### {review.get('role')} — `{review.get('producer')}`",
                    "",
                )
            )
            for claim in review.get("claims", []):
                if isinstance(claim, Mapping):
                    output.append(
                        f"- {claim.get('text')} — evidence: "
                        f"{_evidence(claim.get('evidence_refs'))}"
                    )
            for limitation in _lines(review.get("limitations")):
                output.append(f"- Limitation: {limitation}")
            output.append("")

    rebuttals = payload.get("rebuttals")
    if isinstance(rebuttals, Mapping):
        output.extend(("## Challenge responses", ""))
        for response in rebuttals.get("responses", []):
            if not isinstance(response, Mapping):
                continue
            output.append(
                f"### {response.get('role')} — `{response.get('producer')}`"
            )
            output.append("")
            for challenge in _lines(response.get("challenges")):
                output.append(f"- Challenge: {challenge}")
            for answer in _lines(response.get("responses")):
                output.append(f"- Response: {answer}")
            output.append(f"- Evidence: {_evidence(response.get('evidence_refs'))}")
            output.append("")

    output.extend(("## Unresolved disagreements", ""))
    for disagreement in result_value.get("disagreements", []):
        if isinstance(disagreement, Mapping):
            output.append(
                f"- **{disagreement.get('role')}**: {disagreement.get('text')} "
                f"— evidence: {_evidence(disagreement.get('evidence_refs'))}"
            )
    output.append("")

    context = packet.get("selection_context")
    if isinstance(context, Mapping):
        output.extend(("## Preserved Stage 13 context", ""))
        dissent = context.get("dissenting_roles")
        if isinstance(dissent, list) and dissent:
            output.append("Dissenting roles: " + ", ".join(f"`{role}`" for role in dissent))
            output.append("")
        for limitation in _lines(context.get("limitations")):
            output.append(f"- {limitation}")
        output.append("")

    return "\n".join(output)
