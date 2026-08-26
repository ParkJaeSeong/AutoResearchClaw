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
                '{"title":"Crystal graph networks","doi":"10.1000/test",'
                '"decision":"include","reason":"directly relevant"}\n'
            ),
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
