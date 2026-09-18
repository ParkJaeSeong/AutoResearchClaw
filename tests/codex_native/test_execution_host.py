import pytest
from researchclaw.codex.execution_host import validate_host_result, host_schema


def test_host_result_requires_turn_and_disallows_tool_claims(tmp_path):
    (tmp_path/'events.jsonl').write_text('{"type":"thread.started","thread_id":"t"}\n{"type":"turn.completed"}\n')
    (tmp_path/'answer.json').write_text('{"rationale":"범위 확인","recommendation":"limited"}')
    assert validate_host_result(tmp_path,'domain')['host_id']=='codex-exec:t'
    (tmp_path/'events.jsonl').write_text('{"type":"thread.started","thread_id":"t"}\n{"type":"turn.completed"}\n{"item":{"type":"command_execution"}}\n')
    with pytest.raises(ValueError,match='tool_access'):validate_host_result(tmp_path,'domain')


def test_coordinator_schema_requires_claims_and_unresolved():
    assert 'claims' in host_schema('coordinator')['required']
    assert 'claims' not in host_schema('domain')['required']
