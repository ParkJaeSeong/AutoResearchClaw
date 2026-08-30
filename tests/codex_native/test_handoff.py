import shlex
import subprocess
import sys
import threading
from dataclasses import replace
import hashlib


from researchclaw.core.events import event_log_for
from researchclaw.core.experiment_package_contract import (
    SELF_TEST_REPORT_PATH,
    register_experiment_self_test,
    validate_experiment_package_contract,
)
from researchclaw.core.handoff import build_handoff
from researchclaw.core.project import ResearchProject
from researchclaw.core.state import StateStore
from researchclaw.core.models import ArtifactRef
from researchclaw.core.research_execution import (
    prepare_research_execution,
    register_research_result,
)
from tests.codex_native.helpers import (
    build_approved_stage_twelve_project,
    build_stage_twelve_project,
    load_execution_contract,
    write_contract_bound_research_result,
)


def test_stage_twelve_handoff_routes_through_explicit_self_test_registration(tmp_path):
    project, _declared_input = build_stage_twelve_project(
        tmp_path / "project", register_self_test=False
    )

    before = build_handoff(project)

    assert before.next_action == "register_experiment_self_test"
    assert before.approval_eligible is False
    assert shlex.split(before.next_command) == [
        "researchclaw-codex",
        "experiment",
        "register-self-test",
        str(project.root.resolve()),
        "--report",
        SELF_TEST_REPORT_PATH,
        "--confirm-self-test",
        "--json",
    ]

    package = validate_experiment_package_contract(ResearchProject.open(project.root))
    completed = subprocess.run(
        [sys.executable, "experiment/code/main.py", *package.self_test_argv],
        cwd=project.root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    register_experiment_self_test(
        ResearchProject.open(project.root), SELF_TEST_REPORT_PATH
    )

    after = build_handoff(ResearchProject.open(project.root))
    assert after.next_action == "approve_experiment_execution"
    assert after.approval_eligible is True
    assert shlex.split(after.next_command) == [
        "researchclaw-codex",
        "approve",
        str(project.root.resolve()),
        "--decision",
        "<approve|reject>",
        "--json",
    ]


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


def test_invalid_legacy_stage_thirteen_result_routes_to_confirmed_quarantine(tmp_path):
    project = _registered_stage_thirteen_project(tmp_path / "project")
    state = project.state
    legacy_artifacts = {
        path: ref
        for path, ref in state.artifacts.items()
        if not path.startswith(".researchclaw/evidence/")
    }
    StateStore(project.root / ".researchclaw").save(
        replace(state, artifacts=legacy_artifacts)
    )
    (project.root / "experiment/results.json").write_text("{}", encoding="utf-8")

    handoff = build_handoff(ResearchProject.open(project.root))

    assert handoff.current_stage == 12
    assert handoff.next_action == "quarantine_result"
    assert "quarantine-result" in handoff.next_command
    assert "--confirm" in handoff.next_command


def test_stale_stage_twelve_contract_remains_at_stage_twelve_and_prepares_again(tmp_path):
    project = build_approved_stage_twelve_project(tmp_path / "project")
    prepare_research_execution(project)
    contract = load_execution_contract(project.root)
    result_path = write_contract_bound_research_result(project, contract)
    result_bytes = result_path.read_bytes()
    state = ResearchProject.open(project.root).state
    StateStore(project.root / ".researchclaw").save(
        replace(
            state,
            artifacts={
                **state.artifacts,
                "experiment/results.json": ArtifactRef(
                    "experiment/results.json",
                    hashlib.sha256(result_bytes).hexdigest(),
                    len(result_bytes),
                ),
            },
        )
    )
    contract_path = project.root / "experiment/execution_contract.json"
    contract_path.write_text("{}", encoding="utf-8")

    handoff = build_handoff(ResearchProject.open(project.root))

    state = ResearchProject.open(project.root).state
    assert handoff.current_stage == 12
    assert handoff.next_action == "prepare_run"
    assert "experiment/execution_contract.json" not in state.artifacts
    assert "experiment/results.json" in state.artifacts
    assert "validate_stage" not in handoff.next_command


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
    assert (
        sum(
            event.type == "research_result_registered"
            for event in event_log_for(project.root).read_all()
        )
        == 1
    )
