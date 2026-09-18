from researchclaw.core.research_graph.execution_view import public_execution
from tests.codex_native.research_graph.test_execution_lifecycle import begin, record
from researchclaw.core.research_graph import commands


def test_initial_barrier_and_historical_projection(tmp_path):
    begin(tmp_path)
    record(tmp_path,'domain','initial','role_started')
    old=record(tmp_path,'domain','initial')
    view=public_execution(old)
    assert not view[0]['attempts'][0]['submissions']
    assert 'result' not in view[0]['attempts'][0]['events'][-1]['payload']
    for role in ['methodology','critical']:
        record(tmp_path,role,'initial','role_started');record(tmp_path,role,'initial')
    latest=public_execution(commands.read_policy_snapshot(tmp_path))
    assert len(latest[0]['attempts'][0]['submissions']['initial'])==3
    assert not public_execution(old)[0]['attempts'][0]['submissions']


def test_public_projection_redacts_secrets_and_paths(tmp_path):
    import json
    begin(tmp_path)
    for role in ['domain','methodology','critical']:
        record(tmp_path,role,'initial','role_started')
        record(tmp_path,role,'initial',output={'rationale':'token=abc /Users/person/file','recommendation':'hold'})
    serialized=json.dumps(public_execution(commands.read_policy_snapshot(tmp_path)))
    assert 'abc' not in serialized and '/Users/person' not in serialized


def test_work_sequence_uses_ledger_order():
    from copy import deepcopy
    from tests.codex_native.research_graph.test_execution_contracts import contract, packet
    from researchclaw.core.research_graph.execution_lifecycle import begin as begin_plan
    from researchclaw.core.research_graph import store
    snapshot={'state':{},'events':[]}
    rows={}
    for identity in ['z-last-alphabetically','a-first-alphabetically']:
        plan=begin_plan(snapshot,{'work_id':identity,'attempt_id':identity+'a','generation':1,'contract':contract(),'input':packet(),'assignment':{'roles':contract()['roles']}})
        snapshot['state'].update(plan['state_patch']);snapshot['events'].append(plan['event'])
    snapshot['state']['execution_work']=dict(sorted(snapshot['state']['execution_work'].items()))
    view=public_execution(snapshot)
    assert view[0]['work_id']=='z-last-alphabetically'


def test_embedded_json_credentials_and_arbitrary_absolute_paths(tmp_path):
    import json
    begin(tmp_path)
    for role in ['domain','methodology','critical']:
        record(tmp_path,role,'initial','role_started')
        record(tmp_path,role,'initial',output={'rationale':'{"token":"secret-value"} /opt/project/private.txt C:\\private\\file.txt','recommendation':'hold'})
    serialized=json.dumps(public_execution(commands.read_policy_snapshot(tmp_path)))
    assert 'secret-value' not in serialized and '/opt/project' not in serialized and 'private' not in serialized


def test_projection_redacts_quoted_credential_and_windows_path(tmp_path):
    import json
    begin(tmp_path)
    for role in ['domain','methodology','critical']:
        record(tmp_path,role,'initial','role_started')
        record(tmp_path,role,'initial',output={'rationale':r'Credentials {"token":"abc123"}; C:\Users\alice\secret.txt and /opt/private/data.txt','recommendation':'hold'})
    value=json.dumps(public_execution(commands.read_policy_snapshot(tmp_path)))
    assert 'abc123' not in value and 'alice' not in value and '/opt/private' not in value


def test_stopped_policy_is_not_shown_as_running(tmp_path):
    head=begin(tmp_path)
    commands.apply_command(tmp_path,operation='work.execution.policy',payload={'milestone':'M1','status':'stopped','reason':'pause'},expected_head=head['id'],command_id='stop')
    assert public_execution(commands.read_policy_snapshot(tmp_path))[0]['status']=='paused'


def test_redacted_projection_is_labelled_without_changing_saved_original(tmp_path):
    begin(tmp_path)
    for role in ['domain','methodology','critical']:
        record(tmp_path,role,'initial','role_started')
        record(tmp_path,role,'initial',output={'rationale':'token=abc123','recommendation':'hold'})
    snapshot=commands.read_policy_snapshot(tmp_path)
    assert public_execution(snapshot)[0]['redacted'] is True
    assert snapshot['state']['execution_work']['review']['attempts']['a1']['submissions']['initial']['domain']['rationale']=='token=abc123'
