from researchclaw.core.contracts import PHASES, STAGE_CONTRACTS, get_contract


def test_all_23_stage_contracts_are_present_and_ordered():
    assert tuple(STAGE_CONTRACTS) == tuple(range(1, 24))
    assert [stage for phase in PHASES for stage in phase.stage_ids] == list(range(1, 24))


def test_literature_gate_contract_is_hash_approved():
    contract = get_contract(5)
    assert contract.name == "literature_screen"
    assert contract.requires_approval is True
    assert contract.required_outputs == ("literature/shortlist.jsonl",)
    assert "literature/candidates.jsonl" in contract.required_inputs
