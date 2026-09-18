"""Validate knowledge-job responses without conflating answer and update status."""
import hashlib
import json

VERSION='atlas-knowledge-update/1.0'


def _hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _envelope(body,instance,job):
    if body.get('ok') is not True or body.get('contract_version')!=VERSION or body.get('atlas_instance_id')!=instance or body.get('job_id')!=job:
        raise ValueError('knowledge_response_identity')


def validate_job(body,instance,job,request,consumer):
    _envelope(body,instance,job)
    canonical={k:v for k,v in request.items() if k!='request_key'}
    canonical['input_refs']=sorted(canonical['input_refs'],key=lambda r:r['page_id'])
    receipt=body['receipt']
    if (receipt.get('consumer_id')!=consumer or receipt.get('operation')!='ask_and_update'
        or receipt.get('request_key')!=request['request_key'] or receipt.get('request_sha256')!=_hash(canonical)):
        raise ValueError('knowledge_receipt_mismatch')
    returned={k:v for k,v in body['payload'].items() if k!='request_key'}
    returned['input_refs']=sorted(returned['input_refs'],key=lambda r:r['page_id'])
    if returned!=canonical or body['payload']['request_key']!=request['request_key']:
        raise ValueError('knowledge_request_mismatch')
    if type(body.get('revision')) is not int or body['revision']<1:raise ValueError('knowledge_revision_invalid')
    refs={}
    for ref in body['stage_results']:
        if ref.get('schema_version')!=1 or ref.get('atlas_instance_id')!=instance or ref.get('job_id')!=job:
            raise ValueError('knowledge_stage_identity')
        key=(ref['stage'],ref['attempt'])
        if key in refs:raise ValueError('knowledge_stage_duplicate')
        refs[key]=ref
    for stage in ('answer','knowledge'):
        result=body[stage].get('result')
        if result is None:continue
        record=result['record']
        if result['sha256']!=_hash(record):raise ValueError('knowledge_result_hash')
        ref=refs.get((stage,record['attempt']))
        if not ref or ref['sha256']!=result['sha256']:raise ValueError('knowledge_result_reference')
        if record.get('schema_version')!=1 or record.get('atlas_instance_id')!=instance or record.get('job_id')!=job or record.get('stage')!=stage:
            raise ValueError('knowledge_stage_identity')
    if body['answer']['status']=='ready' and body['answer'].get('result') is None:
        raise ValueError('knowledge_answer_missing')
    return body


def validate_resume(body,instance,job,expected_revision):
    _envelope(body,instance,job)
    receipt=body['resume_receipt']
    if (receipt.get('expected_revision')!=expected_revision or receipt.get('stage') not in ('package','knowledge')
        or type(receipt.get('attempt')) is not int or receipt['attempt']<1
        or type(receipt.get('accepted_revision')) is not int or receipt['accepted_revision']<=expected_revision
        or type(body.get('replayed')) is not bool):
        raise ValueError('knowledge_resume_mismatch')
    return receipt
