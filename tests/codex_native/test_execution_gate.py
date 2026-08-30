import hashlib
import importlib
import json
import shlex
from dataclasses import replace

import pytest

from researchclaw.core import execution_gate
from researchclaw.core.models import ArtifactRef, StageStatus
from researchclaw.core.project import ResearchProject
from tests.codex_native.helpers import (
    build_stage_twelve_project,
    write_runnable_development_fixture,
)


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _recheck(project):
    module = importlib.import_module("researchclaw.core.execution_gate")
    return module.recheck_execution_readiness(project)


def _write_development_fixture(project):
    data_path = project.root / "experiment/dev_data/cells.dev.csv"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"dataset_id,condition_id,cell_id,cycle_index,cycle_life_cycles\nSYNTH_A,G01,C01,1,500\n"
    data_path.write_bytes(payload)
    manifest_path = project.root / "experiment/input_manifest.dev.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_type": "synthetic_development_input",
                "evidence_eligible": False,
                "datasets": [{"dataset_id": "SYNTH_A"}],
                "cell_records": {
                    "path": "experiment/dev_data/cells.dev.csv",
                    "row_count": 1,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
                "features": {
                    "path": "experiment/dev_data/cells.dev.csv",
                    "row_count": 1,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
                "labels": {"path": "experiment/dev_data/cells.dev.csv"},
                "groups": {"independent_group_key": "condition_id"},
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


@pytest.fixture
def stage_12_missing_project(tmp_path):
    return build_stage_twelve_project(
        tmp_path / "missing",
        readiness="needs_input",
    )


@pytest.fixture
def stage_12_ready_project(tmp_path):
    return build_stage_twelve_project(tmp_path / "ready")[0]


def test_recheck_only_refreshes_declared_observation_facts(stage_12_missing_project):
    project, declared_input = stage_12_missing_project
    declared_input.parent.mkdir(parents=True)
    declared_input.write_bytes(b"ready")
    resources = project.root / "experiment/resources.json"
    before = _load_json(resources)

    status = _recheck(project)

    after = _load_json(resources)
    assert status.readiness == "ready_for_execution"
    assert status.approval_eligible is True
    assert status.unmet_prerequisites == ()
    assert status.resource_plan_sha256 == hashlib.sha256(resources.read_bytes()).hexdigest()
    assert after["inputs"][0] == {
        "path": "data/input.csv",
        "required": True,
        "exists": True,
        "is_regular_file": True,
        "size_bytes": 5,
        "sha256": hashlib.sha256(b"ready").hexdigest(),
        "license_status": "confirmed",
        "preparation_note": "Provide data/input.csv before execution.",
    }
    for immutable_field in (
        "project_id",
        "bindings",
        "saved_hardware_profile",
        "tasks",
        "budget",
        "deferred_command",
        "result_path",
        "prohibitions",
    ):
        assert after[immutable_field] == before[immutable_field]

    reopened = ResearchProject.open(project.root)
    artifact = reopened.state.artifacts["experiment/resources.json"]
    assert artifact.sha256 == status.resource_plan_sha256
    assert artifact.size == resources.stat().st_size
    assert reopened.state.status is StageStatus.AWAITING_APPROVAL
    assert reopened.state.next_action == "approve_experiment_execution"
    events = [json.loads(line) for line in (project.root / "evaluation/events.jsonl").read_text().splitlines()]
    assert events[-1]["type"] == "execution_readiness_rechecked"


def test_stage_twelve_hashes_reopen_state_after_recheck(stage_12_missing_project):
    project, declared_input = stage_12_missing_project
    declared_input.parent.mkdir(parents=True)
    declared_input.write_bytes(b"ready")
    status = _recheck(project)
    module = importlib.import_module("researchclaw.core.execution_gate")

    hashes = module.stage_twelve_artifact_hashes(project)

    assert hashes["experiment/resources.json"] == status.resource_plan_sha256


def test_development_recheck_validates_fixture_without_mutating_execution_gate(
    stage_12_missing_project,
):
    project, _declared_input = stage_12_missing_project
    manifest_path = _write_development_fixture(project)
    resources = project.root / "experiment/resources.json"
    resources_before = resources.read_bytes()
    state_before = (project.root / ".researchclaw/state.json").read_bytes()
    module = importlib.import_module("researchclaw.core.execution_gate")

    status = module.recheck_development_input(
        project,
        "experiment/input_manifest.dev.json",
    )

    assert status.readiness == "ready_for_development"
    assert status.approval_eligible is False
    assert status.unmet_prerequisites == ()
    assert status.input_manifest_path == "experiment/input_manifest.dev.json"
    assert status.input_manifest_sha256 == hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    assert resources.read_bytes() == resources_before
    assert (project.root / ".researchclaw/state.json").read_bytes() == state_before
    events = [
        json.loads(line)
        for line in (project.root / "evaluation/events.jsonl").read_text().splitlines()
    ]
    assert events[-1]["type"] == "development_input_rechecked"


def test_validate_development_input_returns_verified_rows(stage_12_missing_project):
    project, _ = stage_12_missing_project
    manifest = write_runnable_development_fixture(project)
    event_path = project.root / "evaluation/events.jsonl"
    events_before = event_path.read_bytes()
    status, validated = execution_gate.validate_development_input(
        project, "experiment/input_manifest.dev.json", record_event=False
    )
    assert status.readiness == "ready_for_development"
    assert validated.manifest_sha256 == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert len(validated.cell_rows) == 8
    assert len(validated.feature_rows) == 16
    assert event_path.read_bytes() == events_before


def test_validated_development_input_is_deeply_immutable(stage_12_missing_project):
    project, _ = stage_12_missing_project
    write_runnable_development_fixture(project)

    _status, validated = execution_gate.validate_development_input(
        project, "experiment/input_manifest.dev.json", record_event=False
    )

    with pytest.raises(TypeError):
        validated.manifest["evidence_eligible"] = True
    with pytest.raises(TypeError):
        validated.manifest["labels"]["field"] = "changed_label"
    with pytest.raises(TypeError):
        validated.cell_rows[0]["cycle_life_cycles"] = "999999"
    with pytest.raises(TypeError):
        validated.feature_rows[0]["capacity_ah"] = "999999"


@pytest.mark.parametrize(
    ("declared_datasets", "expected_message"),
    [
        ([{"dataset_id": "DECLARED_ONLY"}], "unexpected row dataset"),
        (
            [{"dataset_id": "SYNTH_DEV"}, {"dataset_id": "MISSING_ROWS"}],
            "declared dataset has no rows",
        ),
        (
            [{"dataset_id": "SYNTH_DEV"}, {"dataset_id": "SYNTH_DEV"}],
            "dataset_id is duplicated",
        ),
    ],
    ids=("unexpected-row-dataset", "missing-declared-dataset", "duplicate-declaration"),
)
def test_development_dataset_declarations_exactly_match_row_datasets(
    stage_12_missing_project, declared_datasets, expected_message
):
    project, _ = stage_12_missing_project
    manifest_path = write_runnable_development_fixture(project)
    manifest = _load_json(manifest_path)
    manifest["datasets"] = declared_datasets
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=expected_message):
        execution_gate.validate_development_input(
            project, "experiment/input_manifest.dev.json", record_event=False
        )


def test_development_csv_hash_and_rows_come_from_one_byte_snapshot(
    stage_12_missing_project, monkeypatch
):
    project, _ = stage_12_missing_project
    write_runnable_development_fixture(project)
    cells_path = project.root / "experiment/dev_data/cells.dev.csv"
    original_bytes = cells_path.read_bytes()
    original_digest = hashlib.sha256(original_bytes).hexdigest()
    replacement = original_bytes.replace(b",train,2,5\n", b",train,2,500\n")
    real_sha256 = hashlib.sha256
    swapped = False

    class SwappingDigest:
        def __init__(self, payload=b""):
            self._delegate = real_sha256(payload)

        def update(self, payload):
            self._delegate.update(payload)

        def hexdigest(self):
            nonlocal swapped
            digest = self._delegate.hexdigest()
            if digest == original_digest and not swapped:
                cells_path.write_bytes(replacement)
                swapped = True
            return digest

    monkeypatch.setattr(execution_gate.hashlib, "sha256", SwappingDigest)

    _status, validated = execution_gate.validate_development_input(
        project, "experiment/input_manifest.dev.json", record_event=False
    )

    assert swapped is True
    assert validated.cell_rows[0]["cycle_life_cycles"] == "5"


def test_development_manifest_hash_and_parse_share_one_byte_snapshot(
    stage_12_missing_project, monkeypatch
):
    project, _ = stage_12_missing_project
    manifest_path = write_runnable_development_fixture(project)
    original_manifest = manifest_path.read_bytes()
    original_manifest_digest = hashlib.sha256(original_manifest).hexdigest()
    replacement = json.loads(original_manifest)
    replacement["datasets"] = [{"dataset_id": "REPLACED"}]
    replacement_bytes = (json.dumps(replacement) + "\n").encode()
    cells_path = project.root / "experiment/dev_data/cells.dev.csv"
    cells_digest = hashlib.sha256(cells_path.read_bytes()).hexdigest()
    real_sha256 = hashlib.sha256
    swapped = False

    class SwappingDigest:
        def __init__(self, payload=b""):
            self._delegate = real_sha256(payload)

        def update(self, payload):
            self._delegate.update(payload)

        def hexdigest(self):
            nonlocal swapped
            digest = self._delegate.hexdigest()
            if digest == cells_digest and not swapped:
                manifest_path.write_bytes(replacement_bytes)
                swapped = True
            return digest

    monkeypatch.setattr(execution_gate.hashlib, "sha256", SwappingDigest)

    _status, validated = execution_gate.validate_development_input(
        project, "experiment/input_manifest.dev.json", record_event=False
    )

    assert swapped is True
    assert validated.manifest_sha256 == original_manifest_digest
    assert validated.manifest["datasets"][0]["dataset_id"] == "SYNTH_DEV"


def test_development_csv_rejects_rows_with_mismatched_feature_columns(
    stage_12_missing_project,
):
    project, _ = stage_12_missing_project
    manifest_path = write_runnable_development_fixture(project)
    features_path = project.root / "experiment/dev_data/features.dev.csv"
    lines = features_path.read_text(encoding="utf-8").splitlines()
    lines[1] += ",unexpected-value"
    features_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = _load_json(manifest_path)
    manifest["features"]["sha256"] = hashlib.sha256(
        features_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="consistent named columns"):
        execution_gate.validate_development_input(
            project, "experiment/input_manifest.dev.json", record_event=False
        )


def test_development_validation_rejects_stale_lineage_without_rewriting_state(
    stage_12_missing_project,
):
    project, _ = stage_12_missing_project
    write_runnable_development_fixture(project)
    state_path = project.root / ".researchclaw/state.json"
    approval_paths = sorted((project.root / "approvals").glob("*.json"))
    state_before = state_path.read_bytes()
    approvals_before = {path: path.read_bytes() for path in approval_paths}
    main_path = project.root / "experiment/code/main.py"
    main_path.write_bytes(main_path.read_bytes() + b"\n# stale lineage\n")

    with pytest.raises(ValueError, match="durable project lineage is stale"):
        execution_gate.validate_development_input(
            project, "experiment/input_manifest.dev.json", record_event=False
        )

    assert state_path.read_bytes() == state_before
    assert {path: path.read_bytes() for path in approval_paths} == approvals_before


def test_development_validation_at_wrong_stage_never_migrates_durable_state(tmp_path):
    project = ResearchProject.create(
        tmp_path / "project", topic="Durable boundary", profile="materials_ai"
    )
    state_path = project.root / ".researchclaw/state.json"
    state = _load_json(state_path)
    state["stage_10_snapshot"] = {"status": "legacy_missing", "entries": []}
    state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
    state_before = state_path.read_bytes()

    with pytest.raises(ValueError, match="Stage 12"):
        execution_gate.validate_development_input(
            project, "experiment/input_manifest.dev.json", record_event=False
        )

    assert state_path.read_bytes() == state_before


def test_development_recheck_rejects_project_escape(stage_12_missing_project):
    project, _declared_input = stage_12_missing_project
    module = importlib.import_module("researchclaw.core.execution_gate")

    with pytest.raises(ValueError, match="project-relative"):
        module.recheck_development_input(project, "../outside.json")


def test_development_recheck_rejects_feature_cutoff_violation(
    stage_12_missing_project,
):
    project, _declared_input = stage_12_missing_project
    manifest_path = _write_development_fixture(project)
    manifest = _load_json(manifest_path)
    cells = project.root / "experiment/dev_data/cells.dev.csv"
    cells.write_text(
        "dataset_id,condition_id,cell_id,split_role,feature_cutoff_cycle,cycle_life_cycles\n"
        "SYNTH_A,G01,C01,train,10,500\n",
        encoding="utf-8",
    )
    features = project.root / "experiment/dev_data/features.dev.csv"
    features.write_text(
        "dataset_id,condition_id,cell_id,cycle_index,capacity_ah\n"
        "SYNTH_A,G01,C01,11,2.0\n",
        encoding="utf-8",
    )
    manifest["cell_records"] = {
        "path": "experiment/dev_data/cells.dev.csv",
        "row_count": 1,
        "sha256": hashlib.sha256(cells.read_bytes()).hexdigest(),
    }
    manifest["features"] = {
        "path": "experiment/dev_data/features.dev.csv",
        "row_count": 1,
        "sha256": hashlib.sha256(features.read_bytes()).hexdigest(),
    }
    manifest["feature_cutoff"] = {
        "cutoff_field": "feature_cutoff_cycle",
        "measurement_cycle_field": "cycle_index",
    }
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    module = importlib.import_module("researchclaw.core.execution_gate")

    with pytest.raises(ValueError, match="feature cutoff"):
        module.recheck_development_input(
            project,
            "experiment/input_manifest.dev.json",
        )


def test_development_recheck_rejects_integer_equivalent_duplicate_cycles(
    stage_12_missing_project,
):
    project, _ = stage_12_missing_project
    manifest_path = write_runnable_development_fixture(project)
    features = project.root / "experiment/dev_data/features.dev.csv"
    lines = features.read_text(encoding="utf-8").splitlines()
    lines[2] = lines[2].replace(",2,", ",01,", 1)
    features.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = _load_json(manifest_path)
    manifest["features"]["sha256"] = hashlib.sha256(features.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cell-cycle is duplicated"):
        importlib.import_module("researchclaw.core.execution_gate").recheck_development_input(
            project, "experiment/input_manifest.dev.json"
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda plan: plan["inputs"].append(
            {
                "path": "data/undeclared.csv",
                "required": False,
                "exists": False,
                "is_regular_file": False,
                "size_bytes": 0,
                "sha256": None,
                "license_status": "not_required",
                "preparation_note": "Unexpected path.",
            }
        ),
        lambda plan: plan["tasks"][0].update({"priority": 99}),
        lambda plan: plan.update({"deferred_command": "python changed.py"}),
    ],
    ids=("undeclared-input", "task-change", "command-change"),
)
def test_recheck_refuses_resource_plan_changes_since_stage_eleven(
    stage_12_missing_project,
    mutation,
):
    project, _declared_input = stage_12_missing_project
    resources = project.root / "experiment/resources.json"
    changed = _load_json(resources)
    mutation(changed)
    resources.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="Stage 12"):
        _recheck(project)

    state = ResearchProject.open(project.root).state
    assert state.current_stage == 11
    assert state.status is StageStatus.NEEDS_REVISION
    assert state.next_action == "validate_stage"


def test_recheck_refuses_non_stage_twelve_projects(tmp_path):
    project = ResearchProject.create(tmp_path / "project", "Formation energy", "materials_ai")

    with pytest.raises(ValueError, match="Stage 12"):
        _recheck(project)


@pytest.mark.parametrize(
    ("lineage_damage", "expected_stage"),
    [
        ("tampered-package-file", 10),
        ("missing-stage-nine-approval", 9),
        ("rejected-stage-nine-approval", 9),
    ],
)
def test_public_recheck_normalizes_all_durable_lineage_before_refreshing(
    tmp_path,
    lineage_damage,
    expected_stage,
):
    project, _declared_input = build_stage_twelve_project(tmp_path / lineage_damage)
    if lineage_damage == "tampered-package-file":
        main = project.root / "experiment/code/main.py"
        main.write_bytes(main.read_bytes() + b"\n# tampered after validation\n")
    else:
        approval_path = project.root / "approvals/stage-09.json"
        if lineage_damage == "missing-stage-nine-approval":
            approval_path.unlink()
        else:
            approval = _load_json(approval_path)
            approval["decision"] = "reject"
            approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Stage 12"):
        _recheck(project)

    state = ResearchProject.open(project.root).state
    assert state.current_stage == expected_stage
    assert state.status is StageStatus.NEEDS_REVISION
    assert state.next_action == (
        "validate_experiment_package"
        if lineage_damage == "tampered-package-file"
        else "validate_stage"
    )


def test_recheck_rejects_a_human_rejected_ready_plan(stage_12_ready_project):
    from researchclaw.core.approval import (
        approve_current_gate,
        load_approval_record,
    )

    approve_current_gate(stage_12_ready_project, "reject", "Do not run")
    rejected = ResearchProject.open(stage_12_ready_project.root)
    resources_before = (
        rejected.root / "experiment/resources.json"
    ).read_bytes()
    assert rejected.state.status is StageStatus.AWAITING_APPROVAL

    with pytest.raises(ValueError, match="human rejection"):
        _recheck(rejected)

    assert (rejected.root / "experiment/resources.json").read_bytes() == resources_before
    assert load_approval_record(rejected.root, 12).decision == "reject"


def test_missing_input_handoff_points_to_the_constrained_recheck(stage_12_missing_project):
    project, _declared_input = stage_12_missing_project

    handoff = project.build_handoff()

    assert shlex.split(handoff.next_command) == [
        "researchclaw-codex",
        "execution",
        "recheck",
        str(project.root.resolve()),
        "--json",
    ]


def test_recheck_refuses_a_forged_resource_artifact_reference(stage_12_missing_project):
    project, _declared_input = stage_12_missing_project
    state = ResearchProject.open(project.root).state
    artifact = state.artifacts["experiment/resources.json"]
    ResearchProject.open(project.root).persist_state(
        replace(
            state,
            artifacts={
                **state.artifacts,
                "experiment/resources.json": ArtifactRef(
                    path=artifact.path,
                    sha256="0" * 64,
                    size=artifact.size,
                ),
            },
        )
    )

    with pytest.raises(ValueError, match="Stage 12"):
        _recheck(ResearchProject.open(project.root))

    normalized = ResearchProject.open(project.root).state
    assert normalized.current_stage == 11
    assert normalized.status is StageStatus.NEEDS_REVISION
    assert normalized.next_action == "validate_stage"
