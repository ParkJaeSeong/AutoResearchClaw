import hashlib
import json

import pytest

from researchclaw.core.research_execution import prepare_research_execution
from tests.codex_native.helpers import build_approved_stage_twelve_project


def test_prepare_run_writes_bound_contract_without_executing_project_code(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    marker = project.root / "project-code-executed"

    status = prepare_research_execution(project)

    contract_path = project.root / "experiment/execution_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert status.readiness == "ready_for_explicit_execution"
    assert status.approval_eligible is False
    assert status.command == contract["command"]
    assert status.result_path == "experiment/results.json"
    assert status.contract_sha256 == hashlib.sha256(contract_path.read_bytes()).hexdigest()
    assert contract["project_id"] == project.state.project_id
    assert contract["prohibitions"]["researchclaw_managed_execution"] is False
    assert not marker.exists()


@pytest.mark.parametrize(
    "relative_path",
    (
        "experiment/design.json",
        "experiment/package_manifest.json",
        "experiment/code/config.json",
        "experiment/resources.json",
        "experiment/code/main.py",
        "data/input.csv",
    ),
)
def test_prepare_run_rejects_changed_approved_or_required_content(
    tmp_path, relative_path
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract_path = project.root / "experiment/execution_contract.json"
    contract_before = contract_path.read_bytes()
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    changed_path = project.root / relative_path
    changed_path.write_bytes(changed_path.read_bytes() + b"\nchanged")

    with pytest.raises(
        ValueError,
        match="execution_(approval_invalid|prerequisites_changed)",
    ):
        prepare_research_execution(project)

    assert contract_path.read_bytes() == contract_before
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


def test_prepare_run_reuses_the_identical_current_contract(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")

    first = prepare_research_execution(project)
    contract_path = project.root / "experiment/execution_contract.json"
    first_bytes = contract_path.read_bytes()
    second = prepare_research_execution(project)

    assert contract_path.read_bytes() == first_bytes
    assert second.contract_sha256 == first.contract_sha256
    assert second.to_dict() == first.to_dict()
