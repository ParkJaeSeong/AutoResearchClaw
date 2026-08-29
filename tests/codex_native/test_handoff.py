import hashlib
import json
import shlex
import threading
from dataclasses import replace

import pytest

from researchclaw.core.events import event_log_for
from researchclaw.core.handoff import build_handoff
from researchclaw.core.models import ArtifactRef, StageStatus
from researchclaw.core.project import ResearchProject
from researchclaw.core.research_execution import (
    prepare_research_execution,
    register_research_result,
)
from tests.codex_native.helpers import (
    build_approved_stage_twelve_project,
    load_execution_contract,
    write_contract_bound_research_result,
)


def test_stage_thirteen_handoff_reports_the_next_unsupported_boundary(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)
    register_research_result(project, "experiment/results.json")

    handoff = build_handoff(project)

    assert handoff.current_stage == 13
    assert handoff.stage_name == "iterative_refine"
    assert handoff.status == "ready"
    assert handoff.milestone_complete is False
    assert handoff.next_action == "report_stage_thirteen_implementation_boundary"
    assert shlex.split(handoff.next_command) == [
        "researchclaw-codex",
        "status",
        str(project.root.resolve()),
        "--json",
    ]
    assert handoff.write_policy == "no_undeclared_outputs"
    assert handoff.approval_required is False
    assert handoff.approval_eligible is False
    assert handoff.execution_readiness is None
    assert handoff.unmet_prerequisites == ()
    assert "experiment/results.json" in handoff.available_artifacts


def _registered_stage_thirteen_project(root):
    project = build_approved_stage_twelve_project(root)
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)
    register_research_result(project, "experiment/results.json")
    return ResearchProject.open(project.root)


@pytest.mark.parametrize(
    ("artifact_path", "mutation"),
    (
        ("experiment/results.json", "missing"),
        ("experiment/results.json", "stale"),
        ("experiment/execution_contract.json", "missing"),
        ("experiment/execution_contract.json", "stale"),
        ("experiment/results.json", "ungrounded"),
    ),
)
def test_stage_thirteen_handoff_rewinds_missing_or_stale_registration_grounding(
    tmp_path, artifact_path, mutation
):
    project = _registered_stage_thirteen_project(tmp_path / "project")
    artifacts = dict(project.state.artifacts)
    if mutation == "missing":
        del artifacts[artifact_path]
    elif mutation == "ungrounded":
        result_path = project.root / artifact_path
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["execution_contract"]["sha256"] = "0" * 64
        result_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        result_bytes = result_path.read_bytes()
        artifacts[artifact_path] = ArtifactRef(
            path=artifact_path,
            sha256=hashlib.sha256(result_bytes).hexdigest(),
            size=len(result_bytes),
        )
    else:
        artifact = artifacts[artifact_path]
        artifacts[artifact_path] = ArtifactRef(
            path=artifact.path,
            sha256="0" * 64,
            size=artifact.size,
        )
    project.persist_state(replace(project.state, artifacts=artifacts))

    handoff = build_handoff(project)

    reopened = ResearchProject.open(project.root)
    assert handoff.current_stage == 12
    assert handoff.milestone_complete is False
    assert handoff.next_action == "validate_stage"
    assert reopened.state.current_stage == 12
    assert reopened.state.status is StageStatus.NEEDS_REVISION
    assert 12 not in reopened.state.completed_stages


def test_handoff_holds_registration_lock_through_durable_normalization(
    tmp_path, monkeypatch
):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    write_contract_bound_research_result(project, contract)
    original_open = ResearchProject.open.__func__
    handoff_opened_stage_twelve = threading.Event()
    release_handoff = threading.Event()
    registration_finished = threading.Event()
    blocked_once = False

    def controlled_open(cls, root):
        nonlocal blocked_once
        opened = original_open(cls, root)
        if (
            threading.current_thread().name == "controlled-handoff"
            and opened.state.current_stage == 12
            and not blocked_once
        ):
            blocked_once = True
            handoff_opened_stage_twelve.set()
            assert release_handoff.wait(2.0)
        return opened

    monkeypatch.setattr(ResearchProject, "open", classmethod(controlled_open))
    handoffs = []
    registrations = []
    errors = []

    def handoff():
        try:
            handoffs.append(build_handoff(project))
        except BaseException as error:
            errors.append(error)

    def register():
        try:
            registrations.append(
                register_research_result(project, "experiment/results.json")
            )
        except BaseException as error:
            errors.append(error)
        finally:
            registration_finished.set()

    handoff_thread = threading.Thread(target=handoff, name="controlled-handoff")
    registration_thread = threading.Thread(target=register)
    handoff_thread.start()
    assert handoff_opened_stage_twelve.wait(1.0)
    registration_thread.start()
    try:
        assert not registration_finished.wait(0.2)
    finally:
        release_handoff.set()
    handoff_thread.join(timeout=2.0)
    registration_thread.join(timeout=2.0)

    assert not errors
    assert len(handoffs) == 1
    assert handoffs[0].current_stage == 12
    assert len(registrations) == 1
    reopened = ResearchProject.open(project.root)
    assert reopened.state.current_stage == 13
    assert reopened.state.completed_stages.count(12) == 1
    assert sum(
        event.type == "research_result_registered"
        for event in event_log_for(project.root).read_all()
    ) == 1
