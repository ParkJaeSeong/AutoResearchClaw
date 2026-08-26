import json
import subprocess
import sys
from dataclasses import replace

from researchclaw.core.approval import approve_current_gate
from researchclaw.core.models import ArtifactRef
from researchclaw.core.project import ResearchProject
from researchclaw.core.validation import validate_current_stage
from tests.codex_native.helpers import complete_first_four_stages, write_valid_fixture_artifacts


def _resume(root):
    result = subprocess.run(
        [sys.executable, "-m", "researchclaw.codex.cli", "resume", str(root), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


def test_resume_uses_only_project_files(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    complete_first_four_stages(project)

    payload = _resume(project.root)
    assert payload["current_stage"] == 5
    assert payload["next_command"].endswith("stage prepare")
    assert "conversation" not in json.dumps(payload).lower()


def test_resume_rehashes_persisted_artifacts_before_preparing(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    goal = project.root / "scope" / "goal.md"
    goal.write_text("# Changed\n\nDifferent goal.\n", encoding="utf-8")

    payload = _resume(project.root)

    assert payload["status"] == "needs_revision"
    assert payload["next_command"].endswith("stage validate")


def test_resume_points_an_unapproved_gate_to_approve(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    write_valid_fixture_artifacts(project.root, 5)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True

    payload = _resume(project.root)

    assert payload["status"] == "awaiting_approval"
    assert payload["next_command"].endswith("approve")


def test_resume_rejects_artifact_paths_outside_the_project(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    state = ResearchProject.open(project.root).state
    ResearchProject.open(project.root).persist_state(
        replace(
            state,
            artifacts={
                "../outside.md": ArtifactRef(
                    path="../outside.md",
                    sha256="31207a2065f46a5b948fce6fe5c13e85abaf5631e2f894b47dcd4fce14f6c57b",
                    size=7,
                )
            },
        )
    )

    payload = _resume(project.root)

    assert payload["status"] == "needs_revision"


def test_resume_rechecks_completed_gate_approval_records(tmp_path):
    project = ResearchProject.create(tmp_path / "demo", "Formation energy", "materials_ai")
    complete_first_four_stages(project)
    write_valid_fixture_artifacts(project.root, 5)
    assert validate_current_stage(ResearchProject.open(project.root)).valid is True
    approve_current_gate(ResearchProject.open(project.root), "approve", "Approved")
    approval_path = project.root / "approvals" / "stage-05.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["artifact_hashes"]["literature/shortlist.jsonl"] = "0" * 64
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    payload = _resume(project.root)

    assert payload["status"] == "needs_revision"
    assert payload["next_command"].endswith("stage validate")
