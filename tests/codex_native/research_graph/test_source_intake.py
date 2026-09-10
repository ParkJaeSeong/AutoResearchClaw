"""Source acquisition is durable without granting research readiness."""
import base64
from copy import deepcopy
from uuid import uuid4

import pytest

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.views import build_view


def capture(data=b'saved source'):
    return dict(source_key='doi:10.example/source', source_version='v1',
                access_url='https://example.org/source', access_status='full_text',
                filename='source.pdf', reading_scope='Only section 2 read',
                limitations=['Measurement units unresolved'], producer_id='coordinator',
                sha256=store._hash(data), content_base64=base64.b64encode(data).decode())


def apply(root, rows, command_id=None, expected=None):
    return commands.apply_command(root, operation='m1.source.capture', payload={'captures': rows},
        expected_head=expected or store.read_head(root)['id'], command_id=command_id or str(uuid4()))


def test_capture_without_stage_prerequisites_preserves_policy_and_bytes(tmp_path):
    before=commands.init_project(tmp_path, topic='Intake test', content_origin='synthetic')
    result=apply(tmp_path,[capture()])
    assert {k:v for k,v in result['state'].items() if k != 'source_captures'} == before['state']
    row=next(iter(result['state']['source_captures'].values()))
    assert store._read_file(store._store_path(tmp_path)/'objects'/row['sha256']) == b'saved source'
    view=build_view(tmp_path)
    assert len(view['source_captures']) == 1
    assert view['source_captures'][0]['usage_status'] == 'unassessed'
    assert not view['approvals'] and not view['handoffs']
    assert all(n['status'] == 'not_started' for n in view['nodes'])
    assert build_view(tmp_path,head_id=before['id'])['source_captures'] == []


def test_retry_deduplicates_but_revised_reading_scope_preserves_history(tmp_path):
    original=commands.init_project(tmp_path, topic='Intake test', content_origin='synthetic')
    first=apply(tmp_path,[capture(),capture()],command_id='capture-1')
    assert len(first['state']['source_captures']) == 1
    assert apply(tmp_path,[capture(),capture()],command_id='capture-1',expected=original['id'])['id']==first['id']
    second=apply(tmp_path,[capture()])
    assert second['state']['source_captures']==first['state']['source_captures']
    revised=capture(); revised['reading_scope']='Sections 2 and 3 read'
    third=apply(tmp_path,[revised])
    assert len(third['state']['source_captures'])==2
    assert len(build_view(tmp_path,head_id=first['id'])['source_captures'])==1


@pytest.mark.parametrize('change',[
    {'sha256':'0'*64}, {'content_base64':'!not base64!'}, {'ready':True},
    {'reading_scope':''}, {'access_status':'approved'}, {'access_url':'javascript:alert(1)'},
])
def test_invalid_capture_is_atomic(tmp_path,change):
    before=commands.init_project(tmp_path,topic='Intake test',content_origin='synthetic')
    row=capture(); row.update(change)
    with pytest.raises(ValueError,match='source_capture'):
        apply(tmp_path,[capture(),row])
    assert store.read_head(tmp_path)['id']==before['id']


def test_blocking_issue_does_not_prevent_capture_or_get_resolved(tmp_path):
    from tests.codex_native.research_graph.test_m1_scope import Fixture
    f=Fixture(tmp_path); f.register(); f.council_prepare()
    f.publish(f.issue())
    before=deepcopy(f.head['state'])
    result=apply(tmp_path,[capture()])
    assert {k:v for k,v in result['state'].items() if k!='source_captures'}==before
    view=build_view(tmp_path)
    assert len(view['source_captures'])==1
    assert view['issues'][0]['status']=='open'


def test_cli_capture_and_inspect_keep_binary_out_of_public_body(tmp_path,capsys):
    import json
    from researchclaw.codex.cli import main
    root=tmp_path/'project'
    head=commands.init_project(root,topic='Intake test',content_origin='synthetic')
    row=capture(b'\x00PRIVATE BINARY BODY\xff')
    payload=tmp_path/'capture.json'; payload.write_text(json.dumps({'captures':[row]}))
    args=['research','apply',str(root),'--operation','m1.source.capture','--payload',str(payload),
          '--expected-head',head['id'],'--command-id','cli-capture','--json']
    assert main(args)==0
    first=json.loads(capsys.readouterr().out)
    assert main(args)==0 and json.loads(capsys.readouterr().out)==first
    assert main(['research','inspect',str(root),'--json'])==0
    output=capsys.readouterr().out
    assert 'PRIVATE BINARY BODY' not in output and 'content_base64' not in output
    assert len(json.loads(output)['source_captures'])==1


def test_stale_head_cannot_register_new_capture(tmp_path):
    original=commands.init_project(tmp_path,topic='Intake test',content_origin='synthetic')
    current=apply(tmp_path,[capture()])
    with pytest.raises(ValueError,match='head_conflict'):
        apply(tmp_path,[capture(b'changed')],expected=original['id'])
    assert store.read_head(tmp_path)['id']==current['id']


def test_changed_file_and_same_source_keep_both_immutable_versions(tmp_path):
    commands.init_project(tmp_path,topic='Intake test',content_origin='synthetic')
    first=apply(tmp_path,[capture()])
    latest=apply(tmp_path,[capture(b'new file version')])
    assert len(latest['state']['source_captures'])==2
    assert len(build_view(tmp_path,head_id=first['id'])['source_captures'])==1


def test_generic_state_import_cannot_forge_native_capture(tmp_path):
    commands.init_project(tmp_path,topic='Intake test',content_origin='synthetic')
    native=apply(tmp_path,[capture()])
    other=tmp_path/'other'
    original=commands.init_project(other,topic='Other',content_origin='synthetic')
    row=deepcopy(next(iter(native['state']['source_captures'].values())))
    row['project_id']=original['state']['project_id']
    store.commit_record(other,expected_head=original['id'],command_id='import',
        state={**original['state'],'source_captures':{row['id']:row}},
        event={**store._VERSION,'type':'imported','payload':{}},
        objects={row['id']:store._canonical(row)})
    with pytest.raises(ValueError,match='source_capture_native_invalid'):
        build_view(other)
