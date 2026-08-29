from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from researchclaw.core.filesystem_baseline import FilesystemEntry
from researchclaw.core.models import ProjectState, StageStatus, StageTenSnapshot
from researchclaw.core.state import StateStore


def test_state_round_trip_is_independent_of_conversation(tmp_path):
    store = StateStore(tmp_path)
    original = ProjectState.new("rc-test", "Materials property prediction", "materials_ai")
    store.save(original)

    loaded = StateStore(tmp_path).load()

    assert loaded == original
    assert loaded.schema_version == 1
    assert loaded.current_stage == 1
    assert loaded.status is StageStatus.READY


def test_state_round_trips_typed_stage_ten_snapshot(tmp_path):
    store = StateStore(tmp_path)
    original = replace(
        ProjectState.new("rc-test", "Topic", "materials_ai"),
        stage_10_snapshot=StageTenSnapshot(
            "captured",
            (
                FilesystemEntry("data", "directory", None),
                FilesystemEntry("data/current.csv", "symlink", "b" * 64),
                FilesystemEntry("data/input.csv", "regular_file", "a" * 64),
            ),
        ),
    )
    store.save(original)

    assert store.load() == original


@pytest.mark.parametrize(
    "next_action",
    (
        "report_foundation_milestone_only",
        "report_knowledge_milestone_only",
        "report_resource_plan_milestone_only",
        "approve_experiment_execution",
        "report_missing_execution_inputs",
    ),
)
def test_state_load_accepts_declared_milestone_actions(tmp_path, next_action):
    store = StateStore(tmp_path)
    data = ProjectState.new("rc-test", "Topic", "materials_ai").to_dict()
    data.update(
        current_stage=6,
        completed_stages=[1, 2, 3, 4, 5],
        next_action=next_action,
    )
    store.path.write_text(json.dumps(data), encoding="utf-8")

    assert store.load().next_action == next_action


def test_state_save_replaces_existing_document_atomically(tmp_path):
    store = StateStore(tmp_path)
    state = ProjectState.new("rc-test", "Topic", "materials_ai")
    store.save(state)
    store.save(replace(state, current_stage=2, completed_stages=(1,)))

    loaded = store.load()

    assert loaded.current_stage == 2
    assert loaded.completed_stages == (1,)
    assert not list(tmp_path.glob("state-*.tmp"))


def test_state_save_fsyncs_file_and_parent_directory(tmp_path, monkeypatch):
    calls: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(file_descriptor: int) -> None:
        calls.append(file_descriptor)
        real_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", recording_fsync)

    StateStore(tmp_path).save(ProjectState.new("rc-test", "Topic", "materials_ai"))

    assert len(calls) >= 2


def test_state_save_cleans_temporary_file_when_replace_fails(tmp_path, monkeypatch):
    store = StateStore(tmp_path)
    original = ProjectState.new("rc-test", "Topic", "materials_ai")
    store.save(original)

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        store.save(replace(original, topic="Changed"))

    assert json.loads(store.path.read_text(encoding="utf-8"))["topic"] == "Topic"
    assert not list(tmp_path.glob("state-*.tmp"))


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda data: data.pop("project_id"), "project_id"),
        (lambda data: data.update(current_stage=True), "current_stage"),
        (lambda data: data.update(status="unknown"), "status"),
        (lambda data: data.update(completed_stages=[2, 1]), "completed_stages"),
        (lambda data: data.update(retry_counts={"1": -1}), "retry_counts"),
        (lambda data: data.update(retry_counts={"01": 1}), "retry_counts"),
        (lambda data: data.update(last_error="broken"), "last_error"),
        (lambda data: data.update(next_action="invent_action"), "next_action"),
        (lambda data: data.update(execution_policy="automatic"), "execution_policy"),
    ],
    ids=(
        "missing-field",
        "boolean-stage",
        "unknown-status",
        "unordered-completed-stages",
        "negative-retry-count",
        "noncanonical-retry-stage",
        "invalid-last-error",
        "unknown-next-action",
        "unknown-execution-policy",
    ),
)
def test_state_load_normalizes_malformed_version_one_documents(tmp_path, mutator, message):
    store = StateStore(tmp_path)
    data = ProjectState.new("rc-test", "Topic", "materials_ai").to_dict()
    mutator(data)
    store.path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        store.load()


@pytest.mark.parametrize(
    "artifact",
    [
        {"path": "../outside.md", "sha256": "0" * 64, "size": 1},
        {"path": "/tmp/outside.md", "sha256": "0" * 64, "size": 1},
        {"path": "scope/goal.md", "sha256": "not-a-hash", "size": 1},
        {"path": "scope/goal.md", "sha256": "0" * 64, "size": -1},
    ],
    ids=("traversal", "absolute", "malformed-hash", "negative-size"),
)
def test_state_load_rejects_malformed_artifact_references(tmp_path, artifact):
    store = StateStore(tmp_path)
    data = ProjectState.new("rc-test", "Topic", "materials_ai").to_dict()
    data["artifacts"] = {artifact["path"]: artifact}
    store.path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact"):
        store.load()


@pytest.mark.parametrize(
    "snapshot",
    [
        {"status": "refreshed", "entries": []},
        {
            "status": "captured",
            "entries": [
                {"path": "../outside", "kind": "directory", "sha256": None}
            ],
        },
        {
            "status": "captured",
            "entries": [
                {"path": "data", "kind": "directory", "sha256": "0" * 64}
            ],
        },
        {
            "status": "captured",
            "entries": [
                {"path": "data/input.csv", "kind": "regular_file", "sha256": None}
            ],
        },
    ],
    ids=("status", "traversal", "directory-hash", "missing-file-hash"),
)
def test_state_load_rejects_malformed_stage_ten_snapshot(tmp_path, snapshot):
    store = StateStore(tmp_path)
    data = ProjectState.new("rc-test", "Topic", "materials_ai").to_dict()
    data["stage_10_snapshot"] = snapshot
    store.path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="snapshot"):
        store.load()
