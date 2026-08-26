import re

import pytest

from researchclaw.core.project import ResearchProject


def test_create_project_builds_durable_layout(tmp_path):
    project = ResearchProject.create(
        tmp_path / "demo",
        topic="Predicting formation energy from crystal structures",
        profile="materials_ai",
    )

    assert project.state.current_stage == 1
    assert project.state.status.value == "ready"
    assert re.fullmatch(r"rc-[0-9a-f]{12}", project.state.project_id)
    assert (project.root / ".researchclaw" / "state.json").is_file()
    assert (project.root / "artifacts").is_dir()
    assert (project.root / "evaluation").is_dir()
    assert (project.root / "approvals").is_dir()


def test_create_rejects_existing_nonempty_directory(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    (root / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="non-empty"):
        ResearchProject.create(root, topic="Formation energy", profile="materials_ai")


def test_open_requires_durable_state_document(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()

    with pytest.raises(ValueError, match="state.json"):
        ResearchProject.open(root)
