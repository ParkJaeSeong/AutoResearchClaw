import hashlib
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
    if stage_id == 10:
        project = ResearchProject.open(root)
        if project.state.stage_10_snapshot.status != "captured":
            from researchclaw.core.task_packets import prepare_task_packet

            prepare_task_packet(project)
        artifacts = _computational_package_fixture(root)
    else:
        artifacts = fixtures[stage_id]
    for relative, content in artifacts.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _computational_package_fixture(root: Path) -> dict[str, str]:
    project_id = ResearchProject.open(root).state.project_id
    design = (root / "experiment" / "design.json").read_bytes()
    design_sha256 = hashlib.sha256(design).hexdigest()
    approved_design = json.loads(design)
    input_contract = {
        "design_binding": approved_design["evidence_sources"],
        "required_paths": ["experiment/design.json"],
        "required_fields": ["schema_version", "project_id", "method"],
    }
    output_contract = {
        "design_binding": approved_design["success_criteria"],
        "result_path": "experiment/results.json",
        "required_fields": ["metrics", "split_summary", "provenance"],
    }
    seeds = {
        "design_binding": approved_design["reproducibility"],
        "values": [17],
    }
    config = {
        "schema_version": 1,
        "project_id": project_id,
        "design_sha256": design_sha256,
        "datasets": approved_design["method"]["datasets"],
        "baselines": approved_design["method"]["baselines"],
        "split_strategy": {
            "design_binding": approved_design["method"]["split_strategy"],
            "groups": ["train", "validation", "calibration", "test"],
            "isolation_key": "cell_id",
            "overlap_policy": "disjoint",
        },
        "metrics": approved_design["metrics"],
        "seeds": seeds,
        "input_contract": input_contract,
        "output_contract": output_contract,
        "traceability": {
            "datasets": "method.datasets",
            "baselines": "method.baselines",
            "split_strategy": "method.split_strategy",
            "metrics": "metrics",
            "seeds": "reproducibility",
            "input_contract": "evidence_sources",
            "output_contract": "success_criteria",
        },
    }
    code_files = {
        "experiment/code/README.md": (
            "# Computational validation package\n\n"
            "This package is hash-bound to the approved validation design. Stage 10 "
            "authored and statically validated it but did not execute the validation.\n\n"
            "Prepare every project-relative input declared by `input_contract`; no "
            "download or synthetic fallback is allowed. The entry point validates "
            "those inputs and builds the isolated split/evaluation plan.\n\n"
            "Dry-run command: `python experiment/code/main.py --config "
            "experiment/code/config.json --dry-run`\n\n"
            "Smoke command: `python -m pytest experiment/code/tests/test_smoke.py -q`\n\n"
            "Later execution must write only the declared result path with metrics, "
            "split summary, and provenance. Network, external LLM, nested-agent, and "
            "Stage-10 execution are prohibited.\n"
        ),
        "experiment/code/main.py": (
            "import argparse\n"
            "import json\n"
            "from pathlib import Path\n"
            "from typing import Any\n\n"
            "def load_config(config_path: Path) -> dict[str, Any]:\n"
            "    if config_path.is_absolute():\n"
            "        raise ValueError('config path must be project-relative')\n"
            "    with config_path.open(encoding='utf-8') as handle:\n"
            "        config = json.load(handle)\n"
            "    if not isinstance(config, dict):\n"
            "        raise ValueError('config must be an object')\n"
            "    return config\n\n"
            "def validate_inputs(config: dict[str, Any]) -> None:\n"
            "    contract = config['input_contract']\n"
            "    required_paths = contract['required_paths']\n"
            "    required_fields = contract['required_fields']\n"
            "    if not required_paths or not required_fields:\n"
            "        raise ValueError('input contract must be non-empty')\n"
            "    for raw_path in required_paths:\n"
            "        candidate = Path(raw_path)\n"
            "        if candidate.is_absolute() or '..' in candidate.parts:\n"
            "            raise ValueError('input path must be project-relative')\n"
            "        if not candidate.is_file():\n"
            "            raise FileNotFoundError(raw_path)\n\n"
            "        with candidate.open(encoding='utf-8') as handle:\n"
            "            record = json.load(handle)\n"
            "        if not isinstance(record, dict) or any(\n"
            "            field not in record for field in required_fields\n"
            "        ):\n"
            "            raise ValueError('input schema does not match contract')\n\n"
            "def build_plan(config: dict[str, Any]) -> dict[str, Any]:\n"
            "    return {\n"
            "        'split_strategy': config['split_strategy'],\n"
            "        'metrics': config['metrics'],\n"
            "        'baselines': config['baselines'],\n"
            "        'seeds': config['seeds'],\n"
            "    }\n\n"
            "def main(argv: list[str] | None = None) -> dict[str, Any]:\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument('--config', required=True)\n"
            "    parser.add_argument('--dry-run', action='store_true')\n"
            "    args = parser.parse_args(argv)\n"
            "    config = load_config(Path(args.config))\n"
            "    validate_inputs(config)\n"
            "    plan = build_plan(config)\n"
            "    if args.dry_run:\n"
            "        print(json.dumps(plan, sort_keys=True))\n"
            "        return plan\n"
            "    raise RuntimeError('execution is deferred to stage 12')\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "experiment/code/config.json": json.dumps(config, separators=(",", ":"))
        + "\n",
        "experiment/code/requirements.txt": "pytest==8.3.0\n",
        "experiment/code/tests/test_smoke.py": (
            "from pathlib import Path\n\n"
            "from experiment.code.main import build_plan, load_config, main, validate_inputs\n\n"
            "def test_smoke_contract():\n"
            "    config_path = Path('experiment/code/config.json')\n"
            "    config = load_config(config_path)\n"
            "    validate_inputs(config)\n"
            "    plan = build_plan(config)\n"
            "    dry_plan = main(['--config', str(config_path), '--dry-run'])\n"
            "    assert dry_plan == plan\n"
        ),
    }
    manifest = {
        "schema_version": 1,
        "project_id": project_id,
        "design_sha256": design_sha256,
        "validation_type": "computational",
        "files": [
            {
                "path": path,
                "role": path.rsplit("/", maxsplit=1)[-1],
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
            for path, content in code_files.items()
        ],
        "entry_point": "experiment/code/main.py",
        "config_path": "experiment/code/config.json",
        "runtime": {"python": ">=3.11"},
        "input_contract": input_contract,
        "output_contract": output_contract,
        "commands": {
            "dry_run": "python experiment/code/main.py --config experiment/code/config.json --dry-run",
            "smoke_test": "python -m pytest experiment/code/tests/test_smoke.py -q",
        },
        "prohibitions": {
            "stage_10_execution": False,
            "network_access": False,
            "external_llm_calls": 0,
            "nested_agent_processes": 0,
        },
        "reproducibility": {
            "design_sha256": design_sha256,
            "seeds": seeds["values"],
            "dependencies": "bounded",
        },
    }
    return {
        "experiment/package_manifest.json": json.dumps(manifest, separators=(",", ":"))
        + "\n",
        **code_files,
    }


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


def build_completed_validation_design_project(
    root: Path, validation_type: str = "computational"
) -> ResearchProject:
    project = build_completed_hypothesis_milestone_project(root)
    write_valid_fixture_artifacts(project.root, 9)
    design_path = project.root / "experiment" / "design.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design["validation_type"] = validation_type
    if validation_type == "computational":
        design["method"] = {
            "datasets": ["versioned public battery dataset"],
            "split_strategy": {
                "description": "cell-grouped held-out test split",
                "isolation_key": "cell_id",
            },
            "baselines": ["random row split"],
            "evaluation_protocol": "fit preprocessing on train only",
        }
    elif validation_type == "laboratory":
        design["method"] = {
            "materials": ["reference electrolyte formulation"],
            "controls": ["unmodified reference formulation"],
            "procedure": "randomized duplicate preparation and blinded measurement",
            "safety": "approved chemical hygiene and waste protocol",
        }
    design_path.write_text(json.dumps(design) + "\n", encoding="utf-8")

    report = validate_current_stage(project)
    assert report.valid is True
    approved = ResearchProject.open(project.root)
    approve_current_gate(approved, "approve", "Validation plan accepted")
    return ResearchProject.open(project.root)
