import hashlib
import json
from pathlib import Path

from researchclaw.codex.cli import main
from researchclaw.core.approval import approve_current_gate
from researchclaw.core.computational_package import canonical_computational_scaffold
from researchclaw.core.project import ResearchProject
from researchclaw.core.resource_planning import (
    hardware_drift_warnings,
    observe_local_hardware,
)
from researchclaw.core.validation import validate_current_stage


def valid_resource_plan(project, observation, *, readiness="ready_for_execution"):
    """Return the smallest structurally valid Stage-11 resource plan."""
    return {
        "schema_version": 1,
        "project_id": project.state.project_id,
        "bindings": {},
        "saved_hardware_profile": {},
        "hardware_observation": observation.to_dict(),
        "inputs": [],
        "tasks": [
            {
                "task_id": "run_experiment",
                "kind": "experiment",
                "depends_on": [],
                "priority": 1,
                "cpu_count": 1,
                "memory_bytes": 1,
                "gpu_count": 0,
                "temporary_disk_bytes": 1,
                "estimated_duration_seconds": 1,
            }
        ],
        "budget": {
            "max_parallel_tasks": 1,
            "peak_cpu_count": 1,
            "peak_memory_bytes": 1,
            "peak_gpu_count": 0,
            "peak_temporary_disk_bytes": 1,
            "total_estimated_duration_seconds": 1,
        },
        "deferred_command": "python experiment/code/main.py --config experiment/code/config.json",
        "result_path": "experiment/results.json",
        "prohibitions": {
            "network_access": False,
            "downloads": False,
            "package_installation": False,
            "external_llm_calls": False,
            "nested_agent_processes": False,
            "generated_code_execution": False,
        },
        "warnings": [],
        "unmet_prerequisites": [],
        "readiness": readiness,
    }


def write_runnable_development_fixture(project: ResearchProject) -> Path:
    """Write the deterministic synthetic input used by the development runner tests."""
    cells_payload = (
        "dataset_id,condition_id,cell_id,split_role,feature_cutoff_cycle,cycle_life_cycles\n"
        "SYNTH_DEV,G01,C01,train,2,5\n"
        "SYNTH_DEV,G01,C02,train,2,6\n"
        "SYNTH_DEV,G02,C03,train,2,7\n"
        "SYNTH_DEV,G03,C04,validation,2,8\n"
        "SYNTH_DEV,G04,C05,calibration,2,9\n"
        "SYNTH_DEV,G05,C06,test,2,10\n"
        "SYNTH_DEV,G06,C07,test,2,11\n"
        "SYNTH_DEV,G06,C08,test,2,12\n"
    ).encode("utf-8")
    feature_payload = (
        "dataset_id,condition_id,cell_id,cycle_index,capacity_ah,internal_resistance_mohm\n"
        "SYNTH_DEV,G01,C01,1,2.01,41.0\n"
        "SYNTH_DEV,G01,C01,2,1.99,41.5\n"
        "SYNTH_DEV,G01,C02,1,2.02,42.0\n"
        "SYNTH_DEV,G01,C02,2,2.00,42.5\n"
        "SYNTH_DEV,G02,C03,1,2.03,43.0\n"
        "SYNTH_DEV,G02,C03,2,2.01,43.5\n"
        "SYNTH_DEV,G03,C04,1,2.04,44.0\n"
        "SYNTH_DEV,G03,C04,2,2.02,44.5\n"
        "SYNTH_DEV,G04,C05,1,2.05,45.0\n"
        "SYNTH_DEV,G04,C05,2,2.03,45.5\n"
        "SYNTH_DEV,G05,C06,1,2.06,46.0\n"
        "SYNTH_DEV,G05,C06,2,2.04,46.5\n"
        "SYNTH_DEV,G06,C07,1,2.07,47.0\n"
        "SYNTH_DEV,G06,C07,2,2.05,47.5\n"
        "SYNTH_DEV,G06,C08,1,2.08,48.0\n"
        "SYNTH_DEV,G06,C08,2,2.06,48.5\n"
    ).encode("utf-8")
    data_root = project.root / "experiment" / "dev_data"
    data_root.mkdir(parents=True, exist_ok=True)
    cells_path = data_root / "cells.dev.csv"
    features_path = data_root / "features.dev.csv"
    cells_path.write_bytes(cells_payload)
    features_path.write_bytes(feature_payload)
    manifest_path = project.root / "experiment" / "input_manifest.dev.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "synthetic_development_input",
                "evidence_eligible": False,
                "datasets": [{"dataset_id": "SYNTH_DEV"}],
                "cell_records": {
                    "path": "experiment/dev_data/cells.dev.csv",
                    "row_count": 8,
                    "sha256": hashlib.sha256(cells_payload).hexdigest(),
                },
                "features": {
                    "path": "experiment/dev_data/features.dev.csv",
                    "row_count": 16,
                    "sha256": hashlib.sha256(feature_payload).hexdigest(),
                },
                "labels": {
                    "path": "experiment/dev_data/cells.dev.csv",
                    "field": "cycle_life_cycles",
                },
                "groups": {"independent_group_key": "condition_id"},
                "feature_cutoff": {
                    "cutoff_field": "feature_cutoff_cycle",
                    "measurement_cycle_field": "cycle_index",
                },
                "provenance": {
                    "license_status": "not_required_synthetic",
                    "research_evidence_use": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


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
        "experiment/code/config.json": json.dumps(config, separators=(",", ":"))
        + "\n",
        **canonical_computational_scaffold(),
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


def set_stage_ten_required_paths(root: Path, required_paths: list[str]) -> None:
    """Keep the Stage-10 config and manifest fixture hashes aligned."""
    config_path = root / "experiment/code/config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["input_contract"]["required_paths"] = required_paths
    config_payload = json.dumps(config, separators=(",", ":")) + "\n"
    config_path.write_text(config_payload, encoding="utf-8")

    manifest_path = root / "experiment/package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_contract"]["required_paths"] = required_paths
    for file_entry in manifest["files"]:
        if file_entry["path"] == "experiment/code/config.json":
            file_entry["sha256"] = hashlib.sha256(
                config_payload.encode("utf-8")
            ).hexdigest()
            break
    manifest_path.write_text(
        json.dumps(manifest, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


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


def build_stage_twelve_project(
    root: Path,
    *,
    readiness: str = "ready_for_execution",
) -> tuple[ResearchProject, Path]:
    """Build a real Stage-12 boundary with an optional missing declared input."""
    project = build_completed_validation_design_project(root)
    write_valid_fixture_artifacts(project.root, 10)
    set_stage_ten_required_paths(project.root, ["data/input.csv"])
    declared_input = project.root / "data/input.csv"
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True
    project = ResearchProject.open(project.root)
    if readiness == "ready_for_execution":
        declared_input.parent.mkdir(parents=True)
        declared_input.write_bytes(b"ready")

    plan = valid_resource_plan(
        project,
        observe_local_hardware(project.root),
        readiness=readiness,
    )
    binding_paths = {
        "design": "experiment/design.json",
        "package_manifest": "experiment/package_manifest.json",
        "config": "experiment/code/config.json",
        "hardware_profile": "scope/hardware_profile.json",
    }
    plan["bindings"] = {
        name: {
            "path": path,
            "sha256": hashlib.sha256((project.root / path).read_bytes()).hexdigest(),
        }
        for name, path in binding_paths.items()
    }
    plan["saved_hardware_profile"] = json.loads(
        (project.root / "scope/hardware_profile.json").read_text(encoding="utf-8")
    )
    plan["warnings"] = list(
        hardware_drift_warnings(
            plan["saved_hardware_profile"],
            plan["hardware_observation"],
        )
    )

    input_exists = declared_input.is_file()
    input_payload = declared_input.read_bytes() if input_exists else b""
    plan["inputs"] = [
        {
            "path": "data/input.csv",
            "required": True,
            "exists": input_exists,
            "is_regular_file": input_exists,
            "size_bytes": len(input_payload),
            "sha256": hashlib.sha256(input_payload).hexdigest()
            if input_exists
            else None,
            "license_status": "confirmed",
            "preparation_note": "Provide data/input.csv before execution.",
        }
    ]
    plan["tasks"].insert(
        0,
        {
            "task_id": "prepare_inputs",
            "kind": "preparation",
            "depends_on": [],
            "priority": 0,
            "cpu_count": 1,
            "memory_bytes": 1,
            "gpu_count": 0,
            "temporary_disk_bytes": 1,
            "estimated_duration_seconds": 1,
        },
    )
    plan["tasks"][1]["depends_on"] = ["prepare_inputs"]
    plan["budget"]["total_estimated_duration_seconds"] = 2
    if readiness == "needs_input":
        plan["unmet_prerequisites"] = [
            "Provide required input file at data/input.csv."
        ]
    elif readiness != "ready_for_execution":
        raise ValueError(f"unsupported test readiness: {readiness}")

    resources = project.root / "experiment/resources.json"
    resources.write_text(json.dumps(plan, sort_keys=True) + "\n", encoding="utf-8")
    assert validate_current_stage(project).valid is True
    return ResearchProject.open(project.root), declared_input
