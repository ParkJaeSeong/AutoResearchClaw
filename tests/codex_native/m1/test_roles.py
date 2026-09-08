import pytest

from researchclaw.core.m1.contracts import NODE_IDS
from researchclaw.core.m1.roles import describe_roles


VOTING_ROLES = {"domain", "methodology", "critical_reproducibility"}


@pytest.mark.parametrize("node_id", NODE_IDS)
def test_each_node_exposes_purpose_inputs_outputs_and_role_questions(node_id):
    contract = describe_roles(node_id)

    assert contract["schema_version"] == 1
    assert contract["workflow_version"] == "m1-graph-v1"
    assert contract["node_id"] == node_id
    assert contract["title"].strip() and contract["title"] != node_id
    assert contract["purpose"].strip()
    assert contract["inputs"] and all(value.strip() for value in contract["inputs"])
    assert contract["outputs"] and all(value.strip() for value in contract["outputs"])
    assert contract["roles"]

    combined_questions = []
    for role in contract["roles"]:
        assert role["role_id"].strip()
        assert role["persona"].strip()
        assert role["questions"] and all(question.strip() for question in role["questions"])
        assert role["permissions"]
        combined_questions.extend(role["questions"])

    question_text = " ".join(combined_questions).lower()
    assert "purpose" in question_text
    assert "evidence" in question_text
    assert "alternative" in question_text


def test_review_uses_the_three_canonical_voters_and_a_nonvoting_coordinator():
    roles = describe_roles("review")["roles"]
    voters = {
        role["role_id"]
        for role in roles
        if role["permissions"]["can_vote"]
    }

    assert voters == VOTING_ROLES
    coordinator = next(role for role in roles if role["role_id"] == "coordinator")
    assert coordinator["permissions"]["can_vote"] is False
    assert coordinator["permissions"]["can_write_other_positions"] is False
    assert coordinator["permissions"]["can_override_blocker"] is False


def test_review_questions_exercise_each_role_specialty():
    roles = {
        role["role_id"]: " ".join(role["questions"]).lower()
        for role in describe_roles("review")["roles"]
    }

    assert all(term in roles["domain"] for term in ("contribution", "evidence", "alternative"))
    assert all(term in roles["methodology"] for term in ("distinguish", "falsification", "alternative"))
    assert all(term in roles["critical_reproducibility"] for term in ("contradictory evidence", "reproducible", "alternative"))
    assert len(set(roles.values())) == 4


def test_authors_cannot_approve_or_independently_review_their_own_outputs():
    author_nodes = set()

    for node_id in NODE_IDS:
        for role in describe_roles(node_id)["roles"]:
            permissions = role["permissions"]
            if permissions["can_author"]:
                author_nodes.add(node_id)
                assert permissions["can_approve_own_output"] is False
                assert permissions["can_independently_review_own_output"] is False

    assert author_nodes == set(NODE_IDS) - {"review", "handoff"}


def test_node_role_assignments_do_not_put_every_role_on_every_node():
    assert {role["role_id"] for role in describe_roles("collect")["roles"]} == {
        "author",
        "critical_reproducibility",
    }
    assert {role["role_id"] for role in describe_roles("hypothesize")["roles"]} == {
        "author"
    }
    assert {role["role_id"] for role in describe_roles("handoff")["roles"]} == {
        "coordinator"
    }


@pytest.mark.parametrize("node_id", ["stage-8", "experiment_run", "", None, False])
def test_describe_roles_rejects_unknown_nodes(node_id):
    with pytest.raises(ValueError, match="^m1_node_unknown$"):
        describe_roles(node_id)


def test_role_description_is_deeply_isolated_between_calls():
    original = describe_roles("review")
    changed = describe_roles("review")

    changed["inputs"].append("mutated")
    changed["roles"][0]["questions"].append("mutated")
    changed["roles"][0]["permissions"]["can_vote"] = False

    assert describe_roles("review") == original
