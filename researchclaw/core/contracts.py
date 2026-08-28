"""Stable, data-only contracts for the research workflow stages."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StageContract:
    id: int
    name: str
    objective: str
    required_inputs: tuple[str, ...]
    required_outputs: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    allowed_tool_classes: tuple[str, ...]
    requires_approval: bool = False
    max_retries: int = 1


@dataclass(frozen=True)
class Phase:
    id: int
    name: str
    stage_ids: tuple[int, ...]


FOUNDATION_STAGE_IDS = (1, 2, 3, 4, 5)
FOUNDATION_STAGE_MAX = FOUNDATION_STAGE_IDS[-1]
LITERATURE_APPROVAL_STAGE = 5
SUPPORTED_STAGE_IDS = (1, 2, 3, 4, 5, 6, 7)
SUPPORTED_STAGE_MAX = 7

_FOUNDATION_ACCEPTANCE_CRITERIA = {
    1: (
        "scope/goal.md contains a non-heading sentence",
        "scope/hardware_profile.json is a JSON object",
    ),
    2: ("scope/problem_tree.md contains at least three numbered or bullet questions",),
    3: ("literature/search_plan.yaml is a mapping with a non-empty queries list",),
    4: (
        "each literature/candidates.jsonl record has a title and DOI, arXiv ID, or URL",
    ),
    5: (
        "each literature/shortlist.jsonl record has a title, include/exclude decision, and reason",
    ),
    6: (
        "each knowledge/extractions.jsonl record has a valid claim and source evidence",
        "knowledge/extraction_manifest.json is a complete manifest for the approved shortlist",
    ),
    7: (
        "knowledge/synthesis.md contains the required evidence-synthesis sections",
        "every bracketed claim reference resolves to knowledge/extractions.jsonl",
        "knowledge/synthesis.md identifies at least two explicit knowledge gaps",
    ),
}


def _contract(stage_id: int, name: str, objective: str, inputs: tuple[str, ...], outputs: tuple[str, ...], *, approval: bool = False) -> StageContract:
    return StageContract(
        id=stage_id,
        name=name,
        objective=objective,
        required_inputs=inputs,
        required_outputs=outputs,
        acceptance_criteria=_FOUNDATION_ACCEPTANCE_CRITERIA.get(
            stage_id,
            ("all required outputs are non-empty project-relative artifacts",),
        ),
        allowed_tool_classes=("filesystem", "research", "analysis"),
        requires_approval=approval,
    )


_CONTRACT_DATA = (
    ("topic_init", "Define the research topic", (), ("scope/goal.md", "scope/hardware_profile.json")),
    ("problem_decompose", "Decompose the research problem", ("scope/goal.md", "scope/hardware_profile.json"), ("scope/problem_tree.md",)),
    ("search_strategy", "Create a reproducible search strategy", ("scope/problem_tree.md",), ("literature/search_plan.yaml",)),
    ("literature_collect", "Collect candidate literature", ("literature/search_plan.yaml",), ("literature/candidates.jsonl",)),
    ("literature_screen", "Screen and approve candidate literature", ("literature/candidates.jsonl",), ("literature/shortlist.jsonl",)),
    (
        "knowledge_extract",
        "Extract structured knowledge from the shortlist",
        ("literature/shortlist.jsonl",),
        ("knowledge/extractions.jsonl", "knowledge/extraction_manifest.json"),
    ),
    (
        "synthesis",
        "Synthesize the current evidence without an external model backend",
        ("knowledge/extractions.jsonl", "knowledge/extraction_manifest.json"),
        ("knowledge/synthesis.md",),
    ),
    ("hypothesis_gen", "Generate testable hypotheses", ("knowledge/synthesis.md",), ("hypotheses/candidates.jsonl",)),
    ("experiment_design", "Design a reproducible experiment", ("hypotheses/candidates.jsonl",), ("experiment/design.json",)),
    ("code_generation", "Generate experiment code", ("experiment/design.json",), ("experiment/code/manifest.json",)),
    ("resource_planning", "Plan compute and data resources", ("experiment/design.json",), ("experiment/resources.json",)),
    ("experiment_run", "Run the approved experiment", ("experiment/code/manifest.json", "experiment/resources.json"), ("experiment/results.json",)),
    ("iterative_refine", "Refine the experiment from results", ("experiment/results.json",), ("experiment/iterations.jsonl",)),
    ("result_analysis", "Analyze experimental results", ("experiment/results.json",), ("analysis/results.json",)),
    ("research_decision", "Make a research decision from evidence", ("analysis/results.json",), ("analysis/decision.json",)),
    ("paper_outline", "Build the paper outline", ("knowledge/synthesis.md", "analysis/decision.json"), ("paper/outline.md",)),
    ("paper_draft", "Draft the research paper", ("paper/outline.md",), ("paper/draft.md",)),
    ("peer_review", "Review the draft", ("paper/draft.md",), ("paper/review.json",)),
    ("paper_revision", "Revise the paper using review findings", ("paper/draft.md", "paper/review.json"), ("paper/revised.md",)),
    ("quality_gate", "Approve paper quality and provenance", ("paper/revised.md",), ("paper/quality_report.json",)),
    ("knowledge_archive", "Archive reusable research knowledge", ("paper/quality_report.json",), ("knowledge/archive.json",)),
    ("export_publish", "Export publication deliverables", ("paper/revised.md", "paper/quality_report.json"), ("export/publication_bundle.json",)),
    ("citation_verify", "Verify citations and references", ("export/publication_bundle.json",), ("export/citation_report.json",)),
)

STAGE_CONTRACTS: dict[int, StageContract] = {
    stage_id: _contract(stage_id, name, objective, inputs, outputs, approval=stage_id in {5, 9, 20})
    for stage_id, (name, objective, inputs, outputs) in enumerate(_CONTRACT_DATA, start=1)
}

PHASES = (
    Phase(1, "framing", (1, 2)),
    Phase(2, "literature", (3, 4, 5, 6)),
    Phase(3, "synthesis", (7, 8)),
    Phase(4, "experiment_preparation", (9, 10, 11)),
    Phase(5, "experimentation", (12, 13)),
    Phase(6, "analysis", (14, 15)),
    Phase(7, "writing", (16, 17, 18, 19)),
    Phase(8, "release", (20, 21, 22, 23)),
)


def get_contract(stage_id: int) -> StageContract:
    """Return the contract for a stage, rejecting unknown stage identifiers."""
    try:
        return STAGE_CONTRACTS[stage_id]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"unknown stage: {stage_id}") from exc


def stage_for_output(relative_path: str) -> int | None:
    """Return the stage that declares an output path, if any."""
    for stage_id, contract in STAGE_CONTRACTS.items():
        if relative_path in contract.required_outputs:
            return stage_id
    return None
