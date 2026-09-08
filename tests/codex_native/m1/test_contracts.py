import builtins

import pytest

from researchclaw.core.m1.contracts import (
    NODE_IDS,
    allowed_return_targets,
    describe_graph,
)


EXPECTED_NODE_IDS = (
    "scope",
    "questions",
    "search",
    "collect",
    "screen",
    "extract",
    "synthesize",
    "hypothesize",
    "review",
    "handoff",
)

EXPECTED_RETURN_TARGETS = {
    "scope": ("scope",),
    "questions": ("scope", "questions"),
    "search": ("questions", "search"),
    "collect": ("search", "collect"),
    "screen": ("search", "collect", "screen"),
    "extract": ("screen", "extract"),
    "synthesize": ("search", "collect", "screen", "extract", "synthesize"),
    "hypothesize": ("synthesize", "hypothesize"),
    "review": EXPECTED_NODE_IDS[:8],
    "handoff": ("review",),
}


def test_graph_has_a_closed_versioned_node_and_edge_catalog():
    graph = describe_graph()

    assert graph["schema_version"] == 1
    assert graph["workflow_version"] == "m1-graph-v1"
    assert NODE_IDS == EXPECTED_NODE_IDS
    assert tuple(node["id"] for node in graph["nodes"]) == EXPECTED_NODE_IDS
    assert all(node["title"].strip() and node["title"] != node["id"] for node in graph["nodes"])
    assert graph["forward_path"] == list(EXPECTED_NODE_IDS)
    assert graph["return_targets"] == {
        node_id: list(targets)
        for node_id, targets in EXPECTED_RETURN_TARGETS.items()
    }

    forward_edges = [
        (edge["from"], edge["to"])
        for edge in graph["edges"]
        if edge["kind"] == "forward"
    ]
    assert forward_edges == list(zip(EXPECTED_NODE_IDS, EXPECTED_NODE_IDS[1:]))
    assert all(
        edge["from"] in EXPECTED_NODE_IDS and edge["to"] in EXPECTED_NODE_IDS
        for edge in graph["edges"]
    )


def test_review_can_return_to_evidence_and_hypothesis_but_not_execution():
    targets = allowed_return_targets("review")

    assert "search" in targets
    assert "hypothesize" in targets
    assert "review" not in targets
    assert "handoff" not in targets
    assert "experiment_run" not in targets


@pytest.mark.parametrize("node_id", ["stage-12", "experiment_run", "", None, True])
def test_unknown_node_has_a_stable_contract_error(node_id):
    with pytest.raises(ValueError, match="^m1_node_unknown$"):
        allowed_return_targets(node_id)


def test_graph_records_the_provisional_m1_policy_without_granting_research_approval():
    policy = describe_graph()["policy"]

    assert policy == {
        "new_projects_only": True,
        "automatic_legacy_migration": False,
        "read_only_ui": True,
        "required_voting_roles": [
            "domain",
            "methodology",
            "critical_reproducibility",
        ],
        "coordinator_voting": False,
        "author_self_approval": False,
        "all_voting_roles_required": True,
        "blocking_issues_must_be_resolved": True,
        "proceed_recommendations": ["ready", "ready_with_limits"],
        "default_response_rounds": 1,
        "default_additional_returns": 2,
        "default_draft_revisions": 2,
        "selected_hypothesis_required_for": ["review", "handoff"],
        "defaults_are_research_approvals": False,
    }


def test_graph_description_is_file_free_and_isolated_between_calls(monkeypatch):
    original = describe_graph()

    def reject_file_access(*args, **kwargs):
        raise AssertionError("describe_graph must not open project state")

    monkeypatch.setattr(builtins, "open", reject_file_access)
    changed = describe_graph()
    changed["nodes"][0]["title"] = "mutated"
    changed["edges"].append({"from": "handoff", "to": "scope", "kind": "forward"})
    changed["return_targets"]["review"].append("experiment_run")
    changed["policy"]["coordinator_voting"] = True

    assert describe_graph() == original
