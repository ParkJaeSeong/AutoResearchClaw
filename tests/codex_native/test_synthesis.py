from researchclaw.core.project import ResearchProject
from researchclaw.core.task_packets import build_task_packet
from researchclaw.core.validation import validate_current_stage

from tests.codex_native.helpers import build_completed_knowledge_milestone_project


VALID_SYNTHESIS = """# Evidence Synthesis

## Evidence Base

The synthesis covers the approved extraction corpus [claim-1].

## Literature Matrix

| Source | Theme | Claims | Evidence |
|---|---|---|---|
| source-1 | Representation | claim-1 | abstract |

## Key Themes

### Theme 1: Structured representations

Evidence: crystal graphs encode atomic neighborhoods [claim-1].

## Convergence and Divergence

The available claim supports structured representations; no contradictory claim was extracted [claim-1].

## Knowledge Gaps

1. Empirical gap: performance evidence is absent from the extracted claim [claim-1].
2. Methodological gap: only abstract-level evidence is available [claim-1].

## SME Applicability

Inference: implementation cost and staffing requirements require separate validation [claim-1].

## Synthesis Limitations

The evidence base contains one abstract-level claim [claim-1].
"""


def test_stage_seven_packet_is_backend_neutral_and_declares_only_synthesis(tmp_path):
    project = build_completed_knowledge_milestone_project(tmp_path / "project")
    packet = build_task_packet(project)
    assert packet.stage_id == 7
    assert packet.required_inputs == (
        "knowledge/extractions.jsonl",
        "knowledge/extraction_manifest.json",
    )
    assert packet.required_outputs == ("knowledge/synthesis.md",)
    assert packet.allowed_tool_classes == ("filesystem", "research", "analysis")


def test_stage_seven_rejects_unknown_claim_reference(tmp_path):
    project = build_completed_knowledge_milestone_project(tmp_path / "project")
    synthesis = project.root / "knowledge" / "synthesis.md"
    synthesis.write_text(VALID_SYNTHESIS.replace("claim-1", "claim-999"), encoding="utf-8")
    report = validate_current_stage(project)
    assert report.valid is False
    assert any(issue.code == "unknown_claim_reference" for issue in report.issues)


def test_stage_seven_requires_two_explicit_knowledge_gaps(tmp_path):
    project = build_completed_knowledge_milestone_project(tmp_path / "project")
    synthesis = project.root / "knowledge" / "synthesis.md"
    synthesis.write_text(
        VALID_SYNTHESIS.replace(
            "2. Methodological gap: only abstract-level evidence is available [claim-1].\n",
            "",
        ),
        encoding="utf-8",
    )
    report = validate_current_stage(project)
    assert report.valid is False
    assert any(issue.code == "insufficient_knowledge_gaps" for issue in report.issues)


def test_stage_seven_literature_matrix_must_cover_every_extracted_source(tmp_path):
    project = build_completed_knowledge_milestone_project(tmp_path / "project")
    synthesis = project.root / "knowledge" / "synthesis.md"
    synthesis.write_text(VALID_SYNTHESIS, encoding="utf-8")
    extractions = project.root / "knowledge" / "extractions.jsonl"
    extractions.write_text(
        extractions.read_text(encoding="utf-8")
        + '{"claim_id":"claim-2","source_id":"source-2","claim":"Second.","evidence_summary":"Second.","evidence_level":"full_text","locator":"Results","source_url":"https://example.org/2","applicability":["test"],"limitations":["test"]}\n',
        encoding="utf-8",
    )
    # Use the pure validator to isolate matrix coverage behavior.
    from researchclaw.core.synthesis import validate_synthesis

    issues = validate_synthesis(extractions.read_text(encoding="utf-8"), VALID_SYNTHESIS)
    assert any(issue.code == "missing_source_coverage" for issue in issues)


def test_valid_stage_seven_advances_to_stage_eight_without_model_calls(tmp_path):
    project = build_completed_knowledge_milestone_project(tmp_path / "project")
    synthesis = project.root / "knowledge" / "synthesis.md"
    synthesis.write_text(VALID_SYNTHESIS, encoding="utf-8")
    report = validate_current_stage(project)
    reopened = ResearchProject.open(project.root)
    assert report.valid is True
    assert report.recommended_action == "report_synthesis_milestone_only"
    assert reopened.state.current_stage == 8
    assert reopened.state.completed_stages == (1, 2, 3, 4, 5, 6, 7)
    assert reopened.state.next_action == "report_synthesis_milestone_only"
