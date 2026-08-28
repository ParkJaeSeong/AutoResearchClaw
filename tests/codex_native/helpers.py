import json
from pathlib import Path

from researchclaw.codex.cli import main
from researchclaw.core.approval import approve_current_gate
from researchclaw.core.project import ResearchProject
from researchclaw.core.validation import validate_current_stage


def run_cli(*args: str) -> int:
    return main(list(args))


def run_cli_json(capsys, *args: str) -> dict[str, object]:
    assert run_cli(*args) == 0
    return json.loads(capsys.readouterr().out)


def write_valid_fixture_artifacts(root: Path, stage_id: int) -> None:
    fixtures = {
        1: {
            "scope/goal.md": "# SMART Goal\n\nPredict formation energy from a public crystal dataset.\n",
            "scope/hardware_profile.json": '{"cpu":"apple","memory_gb":128}\n',
        },
        2: {
            "scope/problem_tree.md": (
                "- Which representation best predicts formation energy?\n"
                "- Which baseline establishes useful performance?\n"
                "- How should composition leakage be prevented?\n"
            ),
        },
        3: {
            "literature/search_plan.yaml": (
                "queries:\n"
                "  - crystal graph formation energy prediction\n"
                "sources:\n"
                "  - arxiv\n"
            ),
        },
        4: {
            "literature/candidates.jsonl": (
                '{"title":"Crystal graph networks","doi":"10.1000/test"}\n'
            ),
        },
        5: {
            "literature/shortlist.jsonl": (
                '{"source_id":"source-1","title":"Crystal graph networks",'
                '"doi":"10.1000/test","url":"https://example.org/test",'
                '"decision":"include","reason":"directly relevant",'
                '"source_type":"article"}\n'
            ),
        },
        6: {
            "knowledge/extractions.jsonl": (
                '{"claim_id":"claim-1","source_id":"source-1",'
                '"claim":"Crystal graphs encode atomic neighborhoods.",'
                '"evidence_summary":"The abstract describes crystals as graphs over atoms and bonds.",'
                '"evidence_level":"abstract","locator":"Abstract",'
                '"source_url":"https://example.org/test","doi":"10.1000/test",'
                '"applicability":["materials representation"],'
                '"limitations":["Evidence is limited to the abstract"]}\n'
            ),
            "knowledge/extraction_manifest.json": json.dumps(
                {
                    "schema_version": 1,
                    "project_id": ResearchProject.open(root).state.project_id,
                    "generated_at": "2026-08-27T12:00:00Z",
                    "sources": [
                        {
                            "source_id": "source-1",
                            "decision": "include",
                            "access_status": "abstract",
                            "accessed_at": "2026-08-27T11:00:00Z",
                            "access_url": "https://example.org/test",
                            "claim_count": 1,
                            "failure_reason": None,
                        }
                    ],
                    "summary": {
                        "included_sources": 1,
                        "processed_sources": 1,
                        "claim_count": 1,
                        "full_text_sources": 0,
                        "abstract_sources": 1,
                        "metadata_only_sources": 0,
                        "unavailable_sources": 0,
                    },
                },
                separators=(",", ":"),
            )
            + "\n",
        },
        7: {
            "knowledge/synthesis.md": (
                "# Evidence Synthesis\n\n"
                "## Evidence Base\n\nCorpus [claim-1].\n\n"
                "## Literature Matrix\n\n| Source | Theme | Claims |\n|---|---|---|\n| source-1 | Representation | claim-1 |\n\n"
                "## Key Themes\n\n### Theme 1\n\nEvidence [claim-1].\n\n"
                "## Convergence and Divergence\n\nNo conflict [claim-1].\n\n"
                "## Knowledge Gaps\n\n1. Empirical gap [claim-1].\n2. Method gap [claim-1].\n\n"
                "## SME Applicability\n\nInference requires validation [claim-1].\n\n"
                "## Synthesis Limitations\n\nAbstract-only evidence [claim-1].\n"
            ),
        },
        8: {
            "hypotheses/candidates.jsonl": (
                '{"hypothesis_id":"H001","rank":1,'
                '"statement":"If grouped cell splits are used, then reported lifetime-prediction error will increase because protocol leakage is removed.",'
                '"knowledge_gap_refs":["gap-1"],"claim_refs":["claim-1"],'
                '"novelty_argument":"The synthesis identifies missing empirical evidence under leakage-safe evaluation.",'
                '"rationale":"Protocol-linked observations can otherwise expose information about held-out cells.",'
                '"prediction":{"outcome":"test MAE","direction":"increase","magnitude":"at least 10%","measurement_context":"cell-grouped split versus random row split"},'
                '"falsification_condition":"Reject if grouped-split MAE increases by less than 10% on the same eligible cells.",'
                '"required_baselines":["random row split","cell-grouped split"],'
                '"feasibility":"Uses the existing dataset and split manifest without new equipment.",'
                '"confounders":["unequal chemistry distribution","small held-out groups"],'
                '"challenges_conventional_wisdom":true}\n'
                '{"hypothesis_id":"H002","rank":2,'
                '"statement":"If provenance-complete metadata are added, then cross-source lifetime-prediction calibration will improve.",'
                '"knowledge_gap_refs":["gap-2"],"claim_refs":["claim-1"],'
                '"novelty_argument":"The synthesis identifies a methodological gap in provenance-aware evaluation.",'
                '"rationale":"Source and processing differences explain otherwise unmodelled distribution shift.",'
                '"prediction":{"outcome":"prediction interval coverage error","direction":"decrease","magnitude":"at least 5 percentage points","measurement_context":"held-out source groups"},'
                '"falsification_condition":"Reject if coverage error decreases by less than 5 percentage points.",'
                '"required_baselines":["features without provenance","features with provenance"],'
                '"feasibility":"Requires metadata already described in the synthesis.",'
                '"confounders":["source-specific chemistry","incomplete metadata"],'
                '"challenges_conventional_wisdom":false}\n'
            ),
        },
        9: {
            "experiment/design.json": json.dumps(
                {
                    "schema_version": 1,
                    "project_id": ResearchProject.open(root).state.project_id,
                    "validation_type": "policy_evidence",
                    "hypothesis_ids": ["H001"],
                    "title": "Leakage-safe materials AI policy validation",
                    "objective": "Determine whether provenance requirements improve decision reliability.",
                    "validation_questions": [
                        "Do provenance-complete records reduce cross-source calibration error?"
                    ],
                    "evidence_sources": [
                        {
                            "category": "public_dataset",
                            "scope": "battery lifetime datasets with source metadata",
                            "inclusion_criteria": ["stable source identifier", "documented preprocessing"],
                            "exclusion_criteria": ["untraceable derived data"],
                            "collection_method": "reproducible registry search",
                        }
                    ],
                    "comparators": ["current practice without mandatory provenance"],
                    "metrics": [
                        {
                            "name": "coverage error",
                            "definition": "absolute nominal-minus-observed interval coverage",
                            "target": "decrease by at least 5 percentage points",
                            "direction": "decrease",
                            "unit": "percentage_points",
                        }
                    ],
                    "success_criteria": ["Coverage error decreases by at least 5 percentage points."],
                    "failure_criteria": ["Coverage error decreases by less than 5 percentage points."],
                    "bias_controls": ["blind source labels during scoring", "publish exclusion reasons"],
                    "resources": {
                        "people": ["materials domain reviewer", "data analyst"],
                        "data": ["public battery datasets"],
                        "tools": ["spreadsheet", "statistical notebook"],
                        "duration": "8 weeks",
                        "budget": "personnel time only",
                    },
                    "reproducibility": {
                        "protocol_version": "1.0",
                        "data_provenance": "source URL, access date, and file hash",
                        "analysis_plan": "pre-specified scoring and sensitivity analysis",
                        "audit_trail": "versioned decisions and reviewer records",
                    },
                    "risks": [
                        {
                            "risk": "expert selection bias",
                            "mitigation": "publish selection criteria and conduct sensitivity analysis",
                        }
                    ],
                    "method": {
                        "data_sources": ["literature", "public datasets", "official policy documents"],
                        "stakeholder_groups": ["research institutes", "SMEs", "policy planners"],
                        "candidate_selection": "predefined eligibility criteria",
                        "scoring_model": "weighted multi-criteria scoring with disclosed weights",
                        "sensitivity_analysis": "vary each weight by plus or minus 20 percent",
                        "conflict_of_interest_plan": "record affiliations and exclude conflicted self-scoring",
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n",
        },
    }
    for relative, content in fixtures[stage_id].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def complete_first_four_stages(project: ResearchProject) -> ResearchProject:
    current = project
    for stage_id in range(1, 5):
        write_valid_fixture_artifacts(current.root, stage_id)
        report = validate_current_stage(current)
        assert report.valid is True
        current = ResearchProject.open(current.root)
    return current


def build_completed_literature_gate_project(root: Path) -> ResearchProject:
    project = ResearchProject.create(root, "Formation energy", "materials_ai")
    project = complete_first_four_stages(project)
    write_valid_fixture_artifacts(project.root, 5)
    report = validate_current_stage(project)
    assert report.valid is True
    project = ResearchProject.open(project.root)
    approve_current_gate(project, "approve", "Test corpus accepted")
    return ResearchProject.open(project.root)


def build_completed_knowledge_milestone_project(root: Path) -> ResearchProject:
    project = build_completed_literature_gate_project(root)
    write_valid_fixture_artifacts(project.root, 6)
    report = validate_current_stage(project)
    assert report.valid is True
    return ResearchProject.open(project.root)


def build_completed_synthesis_milestone_project(root: Path) -> ResearchProject:
    project = build_completed_knowledge_milestone_project(root)
    write_valid_fixture_artifacts(project.root, 7)
    report = validate_current_stage(project)
    assert report.valid is True
    return ResearchProject.open(project.root)


def build_completed_hypothesis_milestone_project(root: Path) -> ResearchProject:
    project = build_completed_synthesis_milestone_project(root)
    write_valid_fixture_artifacts(project.root, 8)
    report = validate_current_stage(project)
    assert report.valid is True
    return ResearchProject.open(project.root)
