"""Deterministic validation for Codex-authored evidence synthesis."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


REQUIRED_SECTIONS = (
    "Evidence Base",
    "Literature Matrix",
    "Key Themes",
    "Convergence and Divergence",
    "Knowledge Gaps",
    "SME Applicability",
    "Synthesis Limitations",
)


@dataclass(frozen=True)
class SynthesisIssue:
    code: str
    message: str


def _corpus_ids(extractions_text: str) -> tuple[set[str], set[str], list[SynthesisIssue]]:
    identifiers: set[str] = set()
    source_ids: set[str] = set()
    issues: list[SynthesisIssue] = []
    for line_number, line in enumerate(extractions_text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            issues.append(SynthesisIssue("invalid_extraction_input", f"extraction line {line_number} is not valid JSON"))
            continue
        claim_id = record.get("claim_id") if isinstance(record, dict) else None
        if not isinstance(claim_id, str) or not claim_id.strip():
            issues.append(SynthesisIssue("invalid_extraction_input", f"extraction line {line_number} has no claim_id"))
            continue
        identifiers.add(claim_id)
        source_id = record.get("source_id")
        if isinstance(source_id, str) and source_id.strip():
            source_ids.add(source_id)
    return identifiers, source_ids, issues


def _section_body(markdown: str, heading: str) -> str:
    pattern = rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, markdown)
    return match.group(1).strip() if match else ""


def validate_synthesis(extractions_text: str, synthesis_text: str) -> tuple[SynthesisIssue, ...]:
    """Validate structure and traceability without generating any prose."""
    claim_ids, source_ids, issues = _corpus_ids(extractions_text)
    for heading in REQUIRED_SECTIONS:
        if not _section_body(synthesis_text, heading):
            issues.append(SynthesisIssue("missing_synthesis_section", f"missing or empty section: {heading}"))

    references = set(re.findall(r"\[([A-Za-z0-9][A-Za-z0-9._:-]*)\]", synthesis_text))
    for reference in sorted(references - claim_ids):
        issues.append(SynthesisIssue("unknown_claim_reference", f"unknown claim reference: {reference}"))
    if claim_ids and not references:
        issues.append(SynthesisIssue("missing_claim_references", "synthesis must cite extracted claim IDs in brackets"))

    matrix = _section_body(synthesis_text, "Literature Matrix")
    for source_id in sorted(source_ids):
        if re.search(rf"(?<![A-Za-z0-9._:-]){re.escape(source_id)}(?![A-Za-z0-9._:-])", matrix) is None:
            issues.append(SynthesisIssue("missing_source_coverage", f"Literature Matrix does not cover source: {source_id}"))

    gaps = _section_body(synthesis_text, "Knowledge Gaps")
    numbered_gaps = re.findall(r"(?m)^\s*\d+[.)]\s+\S", gaps)
    if len(numbered_gaps) < 2:
        issues.append(SynthesisIssue("insufficient_knowledge_gaps", "Knowledge Gaps must contain at least two numbered gaps"))
    return tuple(issues)
