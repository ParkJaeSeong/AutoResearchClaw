import copy
import json
from pathlib import Path

import pytest

from researchclaw.core import agent_roles


CATALOG = Path(agent_roles.__file__).parent / "data" / "agent_roles.json"
FIELDS = {
    "schema_version",
    "stage_id",
    "protocol_version",
    "activation",
    "mode",
    "roles",
    "existing_protocol",
}
ROLE_FIELDS = {
    "role_id",
    "responsibility",
    "required_questions",
    "judgment_criteria",
    "authority_limits",
}
JUDGES = {"domain", "methodology", "critical_reproducibility", "coordinator"}


@pytest.mark.parametrize("stage", range(1, 16))
def test_stage_description_contract(stage):
    result = agent_roles.describe_stage_roles(stage)
    assert set(result) == FIELDS
    assert result["stage_id"] == stage
    assert result["schema_version"] == result["protocol_version"] == 1
    assert result["activation"] == "guidance_only"
    mode = (
        "work_and_verify"
        if stage in {4, 6, 11, 12}
        else "implementation_council"
        if stage in {10, 13}
        else "judgment_council"
    )
    expected = (
        {"worker", "verifier"}
        if mode == "work_and_verify"
        else JUDGES | {"implementation"}
        if mode == "implementation_council"
        else JUDGES
    )
    assert result["mode"] == mode
    assert {r["role_id"] for r in result["roles"]} == expected
    protocol = {
        12: "user_execution_handoff",
        13: "registered_refinement_council",
        14: "registered_analysis_council",
        15: "registered_decision_council",
    }
    assert result["existing_protocol"] == protocol.get(
        stage, "single_author_validation"
    )
    for role in result["roles"]:
        assert set(role) == ROLE_FIELDS
        assert role["responsibility"].strip()
        for key in ("required_questions", "judgment_criteria", "authority_limits"):
            assert role[key] and all(
                isinstance(s, str) and s.strip() for s in role[key]
            )


@pytest.mark.parametrize("stage", [0, 16, 23, -1, True, 7.0, "7", None])
def test_unsupported_stage(stage):
    with pytest.raises(ValueError, match="^agent_roles_stage_unsupported$"):
        agent_roles.describe_stage_roles(stage)


def test_returned_nested_data_does_not_contaminate_next_read():
    original = agent_roles.describe_stage_roles(7)
    changed = agent_roles.describe_stage_roles(7)
    changed["roles"][0]["required_questions"].append("mutation")
    changed["roles"][0]["responsibility"] = "mutation"
    assert agent_roles.describe_stage_roles(7) == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("protocol_version", 2),
        ("activation", "enforced"),
        ("mode", "automatic"),
        ("stage_id", True),
        ("existing_protocol", "registered_analysis_council"),
        ("unknown", "x"),
    ],
)
def test_invalid_stage_fields(field, value):
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw[0][field] = value
    with pytest.raises(ValueError, match="^agent_roles_catalog_invalid$"):
        agent_roles._validate_catalog(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("role_id", "invented"),
        ("responsibility", " "),
        ("responsibility", None),
        ("required_questions", []),
        ("required_questions", [" "]),
        ("required_questions", "not a list"),
        ("judgment_criteria", []),
        ("judgment_criteria", [4]),
        ("authority_limits", []),
        ("unknown", "x"),
    ],
)
def test_invalid_role_fields(field, value):
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw[0]["roles"][0][field] = value
    with pytest.raises(ValueError, match="^agent_roles_catalog_invalid$"):
        agent_roles._validate_catalog(raw)


def test_duplicate_missing_and_malformed_catalog_entries():
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    duplicate_role = copy.deepcopy(raw)
    duplicate_role[0]["roles"].append(copy.deepcopy(raw[0]["roles"][0]))
    duplicate_stage = copy.deepcopy(raw)
    duplicate_stage[-1] = copy.deepcopy(raw[0])
    missing_field = copy.deepcopy(raw)
    del missing_field[0]["roles"][0]["authority_limits"]
    wrong_mode = copy.deepcopy(raw)
    wrong_mode[0]["mode"] = "work_and_verify"
    for invalid in (
        None,
        {},
        [],
        raw[:-1],
        raw + [raw[0]],
        [None] * 15,
        duplicate_role,
        duplicate_stage,
        missing_field,
        wrong_mode,
    ):
        with pytest.raises(ValueError, match="^agent_roles_catalog_invalid$"):
            agent_roles._validate_catalog(invalid)


@pytest.mark.parametrize(
    "stage,terms",
    [
        (1, ("assumption", "success")),
        (2, ("causal", "confounding")),
        (3, ("search", "bias")),
        (4, ("identifier", "screening")),
        (5, ("exclude", "disconfirming")),
        (6, ("observation", "inference")),
        (7, ("conflict", "competing", "source count")),
        (8, ("falsifi", "rejection")),
        (9, ("leakage", "budget")),
        (10, ("fit", "predict", "static")),
        (11, ("resource", "readiness")),
        (12, ("execution", "failure")),
        (13, ("stop", "dissent")),
        (14, ("uncertainty", "interpretation")),
        (15, ("pivot", "disclosure")),
    ],
)
def test_stage_content_is_specific(stage, terms):
    text = json.dumps(agent_roles.describe_stage_roles(stage)["roles"]).lower()
    assert all(term in text for term in terms)


@pytest.mark.parametrize("stage", [1, 2, 3, 5, 7, 8, 9, 10, 13, 14, 15])
def test_coordinator_does_not_vote(stage):
    roles = agent_roles.describe_stage_roles(stage)["roles"]
    coordinator = next(r for r in roles if r["role_id"] == "coordinator")
    assert "non-voting" in " ".join(coordinator["authority_limits"]).lower()


PER_ROLE_QUESTION_TERMS = {
    1: {"domain": ("requirement", "non-goal"), "methodology": ("success", "resource"), "critical_reproducibility": ("assumption", "alternative objective"), "coordinator": ("framing", "evidence")},
    2: {"domain": ("relationship", "question"), "methodology": ("causal", "decomposition"), "critical_reproducibility": ("missing cause", "confounding"), "coordinator": ("structure", "evidence")},
    3: {"domain": ("terminology", "synonym"), "methodology": ("query", "coverage"), "critical_reproducibility": ("search bias", "publication bias"), "coordinator": ("search", "evidence")},
    4: {"worker": ("identifier", "access failure"), "verifier": ("identifier", "collection completeness")},
    5: {"domain": ("include", "borderline"), "methodology": ("methodological fit", "consistent"), "critical_reproducibility": ("disconfirming", "selection bias"), "coordinator": ("screening", "evidence")},
    6: {"worker": ("claim", "location"), "verifier": ("observation", "inference")},
    7: {"domain": ("agreement", "gap"), "methodology": ("strength", "comparab"), "critical_reproducibility": ("competing", "source count"), "coordinator": ("conflict", "evidence")},
    8: {"domain": ("value", "rationale"), "methodology": ("falsifi", "discriminating"), "critical_reproducibility": ("rejection", "competing"), "coordinator": ("candidate", "evidence")},
    9: {"domain": ("objective", "control"), "methodology": ("leakage", "metric"), "critical_reproducibility": ("failure", "budget"), "coordinator": ("design", "evidence")},
    10: {"domain": ("approved design", "code"), "methodology": ("fit", "predict"), "critical_reproducibility": ("static", "scientific"), "coordinator": ("correspondence", "evidence"), "implementation": ("authorizes", "checks")},
    11: {"worker": ("resource estimate", "input"), "verifier": ("resource", "readiness")},
    12: {"worker": ("execution", "failure"), "verifier": ("missing", "failure")},
    13: {"domain": ("improvement", "candidate"), "methodology": ("allowed change", "fair"), "critical_reproducibility": ("stop", "dissent"), "coordinator": ("refinement", "evidence"), "implementation": ("allowed change", "checks")},
    14: {"domain": ("hypothesis", "evidence"), "methodology": ("observation", "interpretation"), "critical_reproducibility": ("alternative", "uncertainty"), "coordinator": ("analysis", "evidence")},
    15: {"domain": ("proceed", "pivot"), "methodology": ("readiness", "missing evidence"), "critical_reproducibility": ("unresolved", "disclosure"), "coordinator": ("recommendation", "evidence")},
}


@pytest.mark.parametrize(
    "stage,role_id,terms",
    [
        (stage, role_id, terms)
        for stage, role_terms in PER_ROLE_QUESTION_TERMS.items()
        for role_id, terms in role_terms.items()
    ],
)
def test_each_role_questions_are_stage_specific(stage, role_id, terms):
    roles = agent_roles.describe_stage_roles(stage)["roles"]
    role = next(role for role in roles if role["role_id"] == role_id)
    assert len(role["required_questions"]) >= 2
    questions = " ".join(role["required_questions"]).lower()
    assert all(term in questions for term in terms)
