import json
from pathlib import Path
from copy import deepcopy
import pytest
from researchclaw.codex.knowledge_protocol import validate_job,validate_resume
from researchclaw.codex.knowledge_package import collect_artifact,validate_manifest

D=json.loads((Path(__file__).parents[1]/'fixtures/atlas-knowledge-protocol-v1/protocol.json').read_text())
C=D['captures'];INSTANCE=C['info']['body']['atlas_instance_id'];JOB=C['submit']['body']['job_id'];REQUEST=C['submit']['request']


def test_real_http_fixture_preserves_answer_across_partial_and_resume():
    partial=validate_job(C['partial']['body'],INSTANCE,JOB,REQUEST,'synthetic-pilot')
    final=validate_job(C['persisted']['body'],INSTANCE,JOB,REQUEST,'synthetic-pilot')
    assert partial['answer']['result']==final['answer']['result']
    assert partial['knowledge']['status']=='partial'
    assert final['knowledge']['status']=='persisted'
    assert validate_resume(C['resume']['body'],INSTANCE,JOB,4)==validate_resume(C['resume-replay']['body'],INSTANCE,JOB,4)


def test_all_stage_and_input_artifacts_match():
    body=validate_job(C['persisted']['body'],INSTANCE,JOB,REQUEST,'synthetic-pilot')
    ref=body['answer']['result']['record']['package_ref']
    raw=collect_artifact([C['manifest']['body']],ref)
    manifest=validate_manifest(raw,ref,INSTANCE,JOB)
    for artifact in manifest['artifacts']+body['stage_results']:
        data=collect_artifact(D['artifacts'][artifact['artifact_id']],artifact)
        if 'stage' in artifact:
            record=json.loads(data)
            assert record['stage']==artifact['stage']
            assert record['attempt']==artifact['attempt']
            assert record['job_id']==JOB


@pytest.mark.parametrize('field,value',[('atlas_instance_id','other'),('job_id','other')])
def test_wrong_identity_rejected(field,value):
    body=deepcopy(C['persisted']['body']);body[field]=value
    with pytest.raises(ValueError):validate_job(body,INSTANCE,JOB,REQUEST,'synthetic-pilot')


def test_tampered_result_and_receipt_rejected():
    body=deepcopy(C['partial']['body']);body['answer']['result']['record']['qa_ref']['qa_id']='other'
    with pytest.raises(ValueError):validate_job(body,INSTANCE,JOB,REQUEST,'synthetic-pilot')
    body=deepcopy(C['partial']['body']);body['receipt']['consumer_id']='other'
    with pytest.raises(ValueError):validate_job(body,INSTANCE,JOB,REQUEST,'synthetic-pilot')


def test_replay_conflict_and_range_capture_semantics():
    replay=validate_job(C['submit-replay']['body'],INSTANCE,JOB,REQUEST,'synthetic-pilot')
    assert replay['job_id']==JOB
    assert C['conflict']['status_code']==409
    assert C['invalid-range']['status_code']==400
    assert C['past-eof']['status_code']==416
    eof=C['eof']['body']
    assert eof['data']=='' and eof['eof'] is True and eof['next_offset'] is None
    for chunks in D['artifacts'].values():
        for chunk in chunks:
            assert chunk['atlas_instance_id']==INSTANCE
            assert chunk['contract_version']=='atlas-knowledge-update/1.0'


def test_resume_for_other_revision_rejected():
    with pytest.raises(ValueError):validate_resume(C['resume']['body'],INSTANCE,JOB,999)
