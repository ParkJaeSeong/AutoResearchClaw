import shlex

from researchclaw.core.handoff import build_handoff
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
