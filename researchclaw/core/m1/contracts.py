"""Pure, versioned topology for the M1 research graph."""

from copy import deepcopy


SCHEMA_VERSION = 1
WORKFLOW_VERSION = "m1-graph-v1"

NODE_IDS = (
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

RETURN_TARGETS = {
    "scope": ("scope",),
    "questions": ("scope", "questions"),
    "search": ("questions", "search"),
    "collect": ("search", "collect"),
    "screen": ("search", "collect", "screen"),
    "extract": ("screen", "extract"),
    "synthesize": ("search", "collect", "screen", "extract", "synthesize"),
    "hypothesize": ("synthesize", "hypothesize"),
    "review": NODE_IDS[:8],
    "handoff": ("review",),
}

_NODE_TITLES = {
    "scope": "Research scope",
    "questions": "Research questions",
    "search": "Search strategy",
    "collect": "Source collection",
    "screen": "Literature screening",
    "extract": "Evidence extraction",
    "synthesize": "Evidence synthesis",
    "hypothesize": "Hypothesis authoring",
    "review": "Independent review",
    "handoff": "M1 handoff",
}

_GRAPH = {
    "schema_version": SCHEMA_VERSION,
    "workflow_version": WORKFLOW_VERSION,
    "nodes": [
        {"id": node_id, "title": _NODE_TITLES[node_id]}
        for node_id in NODE_IDS
    ],
    "forward_path": list(NODE_IDS),
    "edges": [
        {"from": source, "to": target, "kind": "forward"}
        for source, target in zip(NODE_IDS, NODE_IDS[1:])
    ]
    + [
        {"from": source, "to": target, "kind": "return"}
        for source in NODE_IDS
        for target in RETURN_TARGETS[source]
    ],
    "return_targets": {
        node_id: list(RETURN_TARGETS[node_id]) for node_id in NODE_IDS
    },
    "policy": {
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
    },
}


def describe_graph() -> dict[str, object]:
    """Return an isolated description of the fixed M1 topology and policy."""
    return deepcopy(_GRAPH)


def allowed_return_targets(node_id: str) -> tuple[str, ...]:
    """Return the closed set of nodes to which ``node_id`` may return."""
    if node_id not in NODE_IDS:
        raise ValueError("m1_node_unknown")
    return RETURN_TARGETS[node_id]
