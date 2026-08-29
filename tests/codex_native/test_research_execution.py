import hashlib
import json
import runpy
from dataclasses import replace

import pytest

from researchclaw.core.models import ArtifactRef
from researchclaw.core.project import ResearchProject
from researchclaw.core.research_execution import (
    EXECUTION_CONTRACT_PATH,
    prepare_research_execution,
)
from tests.codex_native.helpers import build_approved_stage_twelve_project


def test_prepare_run_writes_bound_contract_without_executing_project_code(tmp_path):
    project = build_approved_stage_twelve_project(
        tmp_path / "project", include_execution_marker=True
    )
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


def test_marker_fixture_writes_only_when_project_code_is_run(tmp_path, monkeypatch):
    project = build_approved_stage_twelve_project(
        tmp_path / "project", include_execution_marker=True
    )
    marker = project.root / "project-code-executed"
    monkeypatch.chdir(project.root)

    with pytest.raises(SystemExit):
        runpy.run_path("experiment/code/main.py", run_name="__main__")

    assert marker.read_text(encoding="utf-8") == "executed"


def test_prepare_run_writes_the_exact_closed_contract_shape(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")

    prepare_research_execution(project)

    contract_path = project.root / EXECUTION_CONTRACT_PATH
    raw_contract = contract_path.read_bytes()
    contract = json.loads(raw_contract)
    assert raw_contract == json.dumps(
        contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert set(contract) == {
        "schema_version",
        "contract_id",
        "project_id",
        "created_at",
        "command",
        "result_path",
        "bindings",
        "inputs",
        "prohibitions",
        "result_template",
    }
    contract_id_payload = {
        key: contract[key]
        for key in (
            "project_id",
            "command",
            "result_path",
            "bindings",
            "inputs",
            "prohibitions",
            "result_template",
        )
    }
    assert contract["contract_id"] == hashlib.sha256(
        json.dumps(
            contract_id_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    expected_bindings = {
        name: {
            "path": path,
            "sha256": hashlib.sha256((project.root / path).read_bytes()).hexdigest(),
        }
        for name, path in {
            "design": "experiment/design.json",
            "package_manifest": "experiment/package_manifest.json",
            "config": "experiment/code/config.json",
            "resources": "experiment/resources.json",
        }.items()
    }
    manifest = json.loads(
        (project.root / "experiment/package_manifest.json").read_text(encoding="utf-8")
    )
    expected_bindings["package_files"] = sorted(
        [
            {"path": entry["path"], "sha256": entry["sha256"]}
            for entry in manifest["files"]
        ],
        key=lambda entry: entry["path"],
    )
    assert contract["bindings"] == expected_bindings
    input_bytes = (project.root / "data/input.csv").read_bytes()
    assert contract["inputs"] == [
        {
            "path": "data/input.csv",
            "size_bytes": len(input_bytes),
            "sha256": hashlib.sha256(input_bytes).hexdigest(),
            "license_status": "confirmed",
        }
    ]


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
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    approval_before = (project.root / "approvals/stage-12.json").read_bytes()
    second = prepare_research_execution(project)

    assert contract_path.read_bytes() == first_bytes
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    assert (project.root / "approvals/stage-12.json").read_bytes() == approval_before
    assert second.contract_sha256 == first.contract_sha256
    assert second.to_dict() == first.to_dict()


@pytest.mark.parametrize(
    "tamper",
    (
        lambda payload: payload.replace(b'"created_at":', b'"created_at" :', 1),
        lambda payload: payload.replace(b"{", b'{"schema_version":1,', 1),
    ),
    ids=("whitespace", "duplicate-key"),
)
def test_prepare_run_rejects_tampered_registered_contract_bytes(tmp_path, tamper):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract_path = project.root / EXECUTION_CONTRACT_PATH
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    contract_path.write_bytes(tamper(contract_path.read_bytes()))

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


def test_prepare_run_rejects_canonical_contract_with_wrong_artifact_identity(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    current = ResearchProject.open(project.root)
    current.persist_state(
        replace(
            current.state,
            artifacts={
                **current.state.artifacts,
                EXECUTION_CONTRACT_PATH: ArtifactRef(
                    path=EXECUTION_CONTRACT_PATH,
                    sha256="0" * 64,
                    size=0,
                ),
            },
        )
    )

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)


def test_prepare_run_rejects_canonical_created_at_tampering(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract_path = project.root / EXECUTION_CONTRACT_PATH
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["created_at"] = "2000-01-01T00:00:00+00:00"
    contract_path.write_bytes(
        json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)


def test_prepare_run_rejects_preseeded_duplicate_key_contract(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    contract_path = project.root / EXECUTION_CONTRACT_PATH
    contract_path.write_bytes(b'{"project_id":"first","project_id":"second"}')
    state_before = (project.root / ".researchclaw/state.json").read_bytes()

    with pytest.raises(ValueError, match="execution_contract_invalid"):
        prepare_research_execution(project)

    assert contract_path.read_bytes() == b'{"project_id":"first","project_id":"second"}'
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before


@pytest.mark.parametrize(
    "approval_case",
    ("missing", "rejected", "malformed", "non-current"),
)
def test_prepare_run_requires_a_current_explicit_approval(tmp_path, approval_case):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    approval_path = project.root / "approvals/stage-12.json"
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    if approval_case == "missing":
        approval_path.unlink()
    elif approval_case == "rejected":
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["decision"] = "reject"
        approval_path.write_text(json.dumps(approval), encoding="utf-8")
    elif approval_case == "malformed":
        approval_path.write_text("not-json", encoding="utf-8")
    else:
        (project.root / "experiment/design.json").write_bytes(b"changed")

    with pytest.raises(ValueError, match="execution_approval_invalid"):
        prepare_research_execution(project)

    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
