from researchclaw.core.contracts import (
    LITERATURE_APPROVAL_STAGE,
    PHASES,
    STAGE_CONTRACTS,
    SUPPORTED_STAGE_IDS,
    SUPPORTED_STAGE_MAX,
    get_contract,
)


def test_supported_stage_boundary_includes_validation_design():
    assert SUPPORTED_STAGE_IDS == (1, 2, 3, 4, 5, 6, 7, 8, 9)
    assert SUPPORTED_STAGE_MAX == 9
    assert LITERATURE_APPROVAL_STAGE == 5


def test_all_23_stage_contracts_are_present_and_ordered():
    assert tuple(STAGE_CONTRACTS) == tuple(range(1, 24))
    assert [stage for phase in PHASES for stage in phase.stage_ids] == list(range(1, 24))


def test_literature_gate_contract_is_hash_approved():
    contract = get_contract(5)
    assert contract.name == "literature_screen"
    assert contract.requires_approval is True
    assert contract.required_outputs == ("literature/shortlist.jsonl",)
    assert "literature/candidates.jsonl" in contract.required_inputs


def test_stage_six_acceptance_names_the_complete_manifest_artifact():
    criteria = "\n".join(get_contract(6).acceptance_criteria)

    assert "knowledge/extraction_manifest.json" in criteria
    assert "knowledge/extractions.jsonl is a complete manifest" not in criteria


def test_foundation_contracts_are_the_resolved_packet_and_validation_source():
    expected = {
        1: ((), ("scope/goal.md", "scope/hardware_profile.json")),
        2: (("scope/goal.md", "scope/hardware_profile.json"), ("scope/problem_tree.md",)),
        3: (("scope/problem_tree.md",), ("literature/search_plan.yaml",)),
        4: (("literature/search_plan.yaml",), ("literature/candidates.jsonl",)),
        5: (("literature/candidates.jsonl",), ("literature/shortlist.jsonl",)),
    }

    for stage_id, (required_inputs, required_outputs) in expected.items():
        contract = get_contract(stage_id)
        assert contract.required_inputs == required_inputs
        assert contract.required_outputs == required_outputs
        assert contract.acceptance_criteria
        assert contract.acceptance_criteria != (
            "all required outputs exist",
            "outputs are project-relative artifacts",
        )
