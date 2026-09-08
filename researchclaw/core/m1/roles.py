"""Pure per-node responsibilities for the M1 research graph."""

from copy import deepcopy

from .contracts import NODE_IDS, SCHEMA_VERSION, WORKFLOW_VERSION


_NODE_WORK = {
    "scope": {
        "title": "Research scope",
        "purpose": "Separate the user's objective, constraints, assumptions, and non-goals.",
        "inputs": ["user research objective", "declared constraints and profile"],
        "outputs": ["scope/goal.md", "scope/constraints.json"],
        "focus": "the objective, constraints, assumptions, and non-goals",
    },
    "questions": {
        "title": "Research questions",
        "purpose": "Turn the agreed scope into answerable questions without inventing requirements.",
        "inputs": ["scope/goal.md", "scope/constraints.json"],
        "outputs": ["scope/questions.json"],
        "focus": "the causal questions, confounders, and boundaries",
    },
    "search": {
        "title": "Search strategy",
        "purpose": "Define a reproducible search for supporting and opposing evidence.",
        "inputs": ["scope/questions.json"],
        "outputs": ["literature/search_plan.yaml"],
        "focus": "the search vocabulary, sources, coverage, and likely search bias",
    },
    "collect": {
        "title": "Source collection",
        "purpose": "Collect traceable source candidates and record their access level.",
        "inputs": ["literature/search_plan.yaml"],
        "outputs": ["literature/candidates.jsonl", "literature/search_log.jsonl"],
        "focus": "source identity, provenance, access level, and collection omissions",
    },
    "screen": {
        "title": "Literature screening",
        "purpose": "Apply the declared criteria and expose inclusion, exclusion, and uncertainty.",
        "inputs": ["literature/candidates.jsonl", "scope/questions.json"],
        "outputs": ["literature/shortlist.jsonl", "literature/screening_decisions.jsonl"],
        "focus": "inclusion criteria, exclusion reasons, and selection bias",
    },
    "extract": {
        "title": "Evidence extraction",
        "purpose": "Link claims, observations, conditions, and limitations to source locations.",
        "inputs": ["literature/shortlist.jsonl", "current corpus approval"],
        "outputs": ["knowledge/extractions.jsonl", "knowledge/extraction_manifest.json"],
        "focus": "source observations, author interpretation, locators, and missing conditions",
    },
    "synthesize": {
        "title": "Evidence synthesis",
        "purpose": "Preserve agreements, conflicts, evidence gaps, and unresolved questions.",
        "inputs": ["knowledge/extractions.jsonl", "knowledge/extraction_manifest.json"],
        "outputs": ["knowledge/synthesis.json", "knowledge/synthesis.md"],
        "focus": "agreements, conflicts, competing explanations, gaps, and limitations",
    },
    "hypothesize": {
        "title": "Hypothesis authoring",
        "purpose": "Draft evidence-linked hypotheses with predictions, falsification conditions, and alternatives.",
        "inputs": ["knowledge/synthesis.json", "extraction version bound by synthesis",
                   "prior registered hypothesis revisions when present"],
        "outputs": ["hypotheses/hypotheses.json", "hypotheses/hypotheses.md"],
        "focus": "the candidate claim, predicted observation, falsification condition, and alternatives",
    },
    "review": {
        "title": "Independent review",
        "purpose": "Independently test hypotheses against evidence, alternatives, and unresolved blockers.",
        "inputs": ["current hypothesis revisions", "current evidence and synthesis binding"],
        "outputs": ["review/positions.json", "review/decision.json"],
        "focus": "contribution, distinguishable observations, falsification, alternatives, and reproducibility",
    },
    "handoff": {
        "title": "M1 handoff",
        "purpose": "Package the reviewed direction, evidence, dissent, limits, and open M2 questions.",
        "inputs": ["review decision", "selected hypothesis revisions", "current evidence binding"],
        "outputs": ["handoff/manifest.json", "handoff/report.md"],
        "focus": "the selected direction, dissent, limitations, and open design questions",
    },
}

_PERSONAS = {
    "author": "Produces the node draft from declared inputs and records uncertainty instead of approving it.",
    "domain": "Judges research meaning, context, contribution, and competing directions.",
    "methodology": "Judges comparability, testability, inference limits, and discriminating observations.",
    "critical_reproducibility": "Checks provenance, contradictory evidence, selection bias, alternatives, and reproducibility.",
    "coordinator": "Organizes issues, positions, dissent, and next actions without voting or speaking for reviewers.",
}

_COUNCIL_NODES = {"scope", "questions", "search", "screen", "synthesize"}
_VERIFY_NODES = {"collect", "extract"}


def _permissions(role_id: str, *, voting: bool) -> dict[str, bool]:
    is_author = role_id == "author"
    is_reviewer = role_id in {"domain", "methodology", "critical_reproducibility"}
    return {
        "can_author": is_author,
        "can_independently_review": is_reviewer,
        "can_vote": is_reviewer and voting,
        "can_approve_own_output": False,
        "can_independently_review_own_output": False,
        "can_write_other_positions": False,
        "can_override_blocker": False,
    }


def _role(role_id: str, node_id: str, *, voting: bool = False) -> dict[str, object]:
    focus = _NODE_WORK[node_id]["focus"]
    questions = {
        "author": [
            f"Does the draft cover the stated purpose for {focus}?",
            f"Which evidence supports the draft treatment of {focus}?",
            f"Which alternative should the draft preserve for {focus}?",
        ],
        "domain": [
            f"Does {focus} address a meaningful contribution and the node purpose?",
            f"Which domain evidence supports or limits {focus}?",
            f"Which alternative research direction for {focus} remains plausible?",
        ],
        "methodology": [
            f"Is {focus} precise enough to serve the node purpose and permit falsification?",
            f"What evidence would distinguish the proposed account of {focus}?",
            f"Which alternative explanation could the current method confuse with {focus}?",
        ],
        "critical_reproducibility": [
            f"Which assumption about {focus} could defeat the node purpose?",
            f"Is the evidence for {focus} reproducible, including contradictory evidence?",
            f"Which alternative account of {focus} was not independently checked?",
        ],
        "coordinator": [
            f"Is the node purpose for {focus} clear to every assigned participant?",
            f"Is each evidence question about {focus} assigned and recorded?",
            f"Are alternatives, blockers, and dissent about {focus} preserved without override?",
        ],
    }[role_id]
    if node_id == "review":
        questions += {
            "domain": ["What contribution is supported by the bound claims, and where is its evidence limited?"],
            "methodology": ["Which predicted observation distinguishes the hypothesis, and which falsification condition rejects it?",
                            "Which unresolved measurements or designs belong in open_design_questions for M2?"],
            "critical_reproducibility": ["Which competing explanation remains plausible, and under which conditions does the hypothesis fail?"],
            "coordinator": ["Are author and reviewer assignment IDs distinct, with actual provenance checked separately?"],
        }[role_id]
    return {
        "role_id": role_id,
        "persona": f"{_PERSONAS[role_id]} At this node, focus on {focus}.",
        "questions": questions,
        "permissions": _permissions(role_id, voting=voting),
    }


def _node_roles(node_id: str) -> list[dict[str, object]]:
    if node_id in _COUNCIL_NODES:
        return [
            _role("author", node_id),
            _role("domain", node_id, voting=True),
            _role("methodology", node_id, voting=True),
            _role("critical_reproducibility", node_id, voting=True),
            _role("coordinator", node_id),
        ]
    if node_id in _VERIFY_NODES:
        return [
            _role("author", node_id),
            _role("critical_reproducibility", node_id),
        ]
    if node_id == "hypothesize":
        return [_role("author", node_id)]
    if node_id == "review":
        return [
            _role("domain", node_id, voting=True),
            _role("methodology", node_id, voting=True),
            _role("critical_reproducibility", node_id, voting=True),
            _role("coordinator", node_id),
        ]
    return [_role("coordinator", node_id)]


_ROLE_CONTRACTS = {
    node_id: {
        "schema_version": SCHEMA_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "node_id": node_id,
        "title": work["title"],
        "purpose": work["purpose"],
        "inputs": work["inputs"],
        "outputs": work["outputs"],
        "roles": _node_roles(node_id),
    }
    for node_id, work in _NODE_WORK.items()
}


def describe_roles(node_id: str) -> dict[str, object]:
    """Return an isolated role, question, I/O, and permission contract."""
    if node_id not in NODE_IDS:
        raise ValueError("m1_node_unknown")
    return deepcopy(_ROLE_CONTRACTS[node_id])
