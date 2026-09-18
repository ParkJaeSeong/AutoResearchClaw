"""Atomic lifecycle plans, using only verified snapshot objects and frozen inputs."""
import json
from copy import deepcopy
from datetime import datetime, timezone
from . import store
from .execution_contracts import ROLES, PHASES, validate_contract, check_input, check_output


def _check(payload, required, optional=()):
    if type(payload) is not dict or not set(required)<=set(payload) or set(payload)-set(required)-set(optional):
        raise ValueError('execution_payload_invalid')
    for key in ('work_id','attempt_id','previous_attempt_id','reason'):
        if key in payload and (not isinstance(payload[key],str) or not payload[key].strip() or len(payload[key])>1000):
            raise ValueError('execution_payload_invalid')
    if 'generation' in payload and (type(payload['generation']) is not int or payload['generation']<1):
        raise ValueError('execution_generation_invalid')


def _object(snapshot,payload,name,objects):
    if (name in payload)==(name+'_ref' in payload):raise ValueError('execution_object_required')
    if name in payload:
        value=deepcopy(payload[name]);raw=store._canonical(value);digest=store._hash(raw);objects[digest]=raw
    else:
        digest=payload[name+'_ref'];raw=snapshot.get('_issue_context',{}).get('objects',{}).get(digest)
        if not store._is_digest(digest) or raw is None or store._hash(raw)!=digest:raise ValueError('execution_object_missing')
        value=json.loads(raw)
    return value,digest


def _policy(snapshot):return store._hash(store._canonical(snapshot['state'].get('work_execution_policy',{})))


def _event(kind,actor='',payload=None):
    return {'type':kind,'actor':actor,'payload':deepcopy(payload or {}),'timestamp':datetime.now(timezone.utc).isoformat()}


def _plan(rows,work,event,objects):
    return {'state_patch':{'execution_work':rows},'event':{**store._VERSION,'type':'execution_'+event['type'],'payload':{'work_id':work['work_id'],'attempt_id':work['current_attempt_id'],**deepcopy(event)}},'object_inputs':objects}


def _new(snapshot,payload,objects):
    contract,cref=_object(snapshot,payload,'contract',objects);validate_contract(contract)
    packet,iref=_object(snapshot,payload,'input',objects)
    assignment,aref=_object(snapshot,payload,'assignment',objects)
    if assignment!={'roles':ROLES}:raise ValueError('execution_assignment_invalid')
    policy=_policy(snapshot)
    if payload.get('policy_revision',policy)!=policy:raise ValueError('execution_policy_stale')
    declared=snapshot['state'].get('work_execution_policy',{})
    if declared and (declared.get('status')!='active' or declared.get('milestone')!='M1'):raise ValueError('execution_not_active')
    report=check_input(contract,packet)
    return dict(attempt_id=payload['attempt_id'],generation=payload['generation'],contract=contract,contract_ref=cref,input=packet,input_ref=iref,input_revision=iref,assignment=assignment,assignment_revision=aref,policy_revision=policy,status='running' if report['status']=='pass' else 'blocked',input_report=report,output_report=None,result=None,result_ref=None,events=[],submissions={},return_from=payload.get('previous_attempt_id'))


def begin(snapshot,payload):
    _check(payload,('work_id','attempt_id','generation'),('contract','contract_ref','input','input_ref','assignment','assignment_ref','policy_revision'))
    rows=deepcopy(snapshot['state'].get('execution_work',{}))
    if payload['work_id'] in rows or payload['generation']!=1:raise ValueError('execution_work_exists')
    objects={};attempt=_new(snapshot,payload,objects)
    work=dict(work_id=payload['work_id'],step_id=attempt['contract']['step_id'],purpose=attempt['contract']['purpose'],current_attempt_id=attempt['attempt_id'],generation=1,status=attempt['status'],attempts={attempt['attempt_id']:attempt})
    event=_event('begun',payload={'status':attempt['status']});attempt['events'].append(event);rows[work['work_id']]=work
    return _plan(rows,work,event,objects)


def _current(snapshot,payload):
    rows=deepcopy(snapshot['state'].get('execution_work',{}));work=rows.get(payload['work_id'])
    if not work:raise ValueError('execution_work_missing')
    if work['current_attempt_id']!=payload['attempt_id'] or work['generation']!=payload['generation']:raise ValueError('execution_generation_stale')
    return rows,work,work['attempts'][payload['attempt_id']]


def _barrier(attempt,role,phase):
    if role=='coordinator':
        if phase!='final' or any(set(attempt['submissions'].get(p,{}))<set(ROLES[:3]) for p in PHASES):raise ValueError('execution_phase_barrier')
    elif phase!='initial':
        prev=PHASES[PHASES.index(phase)-1]
        if not set(ROLES[:3])<=set(attempt['submissions'].get(prev,{})):raise ValueError('execution_phase_barrier')


def record(snapshot,payload):
    _check(payload,('work_id','attempt_id','generation','kind','actor','payload'))
    rows,work,attempt=_current(snapshot,payload)
    kind=payload['kind'];actor=payload['actor'];data=payload['payload']
    if kind not in ('role_started','role_submitted','role_failed','heartbeat','recovery_required') or actor not in ROLES or type(data) is not dict or data.get('phase') not in PHASES:raise ValueError('execution_event_invalid')
    allowed={'phase'}|({'result'} if kind=='role_submitted' else {'reason'} if kind in ('role_failed','recovery_required') else set())
    if set(data)-allowed or (kind=='role_submitted' and type(data.get('result')) is not dict):raise ValueError('execution_event_invalid')
    if attempt['status'] not in ('running','recovery_required'):raise ValueError('execution_state_invalid')
    if attempt['policy_revision']!=_policy(snapshot):raise ValueError('execution_policy_stale')
    _barrier(attempt,actor,data['phase'])
    previous=[e for e in attempt['events'] if e['actor']==actor and e['payload'].get('phase')==data['phase']]
    if kind=='role_started' and any(e['type'] in ('role_started','role_submitted') for e in previous):raise ValueError('execution_role_already_started')
    objects={}
    if kind=='role_submitted':
        if not any(e['type']=='role_started' for e in previous):raise ValueError('execution_role_not_started')
        phase=attempt['submissions'].setdefault(data['phase'],{})
        if actor in phase:raise ValueError('execution_role_already_submitted')
        if set(data['result'])-{'rationale','recommendation','claims','unresolved'}:raise ValueError('execution_submission_invalid')
        if not isinstance(data['result'].get('rationale'),str) or not data['result']['rationale'].strip() or data['result'].get('recommendation') not in ('use','limited','hold'):raise ValueError('execution_submission_invalid')
        raw=store._canonical(data['result']);objects[store._hash(raw)]=raw
        phase[actor]=deepcopy(data['result']);attempt['status']='running'
    if kind in ('role_failed','recovery_required'):attempt['status']='recovery_required'
    event=_event(kind,actor,data);attempt['events'].append(event);work['status']=attempt['status']
    return _plan(rows,work,event,objects)


def finish(snapshot,payload):
    _check(payload,('work_id','attempt_id','generation'),('result','result_ref'))
    rows,work,attempt=_current(snapshot,payload)
    if attempt['status'] not in ('running','recovery_required'):raise ValueError('execution_state_invalid')
    objects={};result,ref=_object(snapshot,payload,'result',objects)
    report=check_output(attempt['contract'],attempt['input'],result)
    reviewed=all(set(ROLES[:3])<=set(attempt['submissions'].get(p,{})) for p in PHASES) and attempt['submissions'].get('final',{}).get('coordinator')==result
    if not reviewed:
        report={'status':'needs_work','checks':[{'check_id':'required_review','checker_version':'1','status':'needs_work','reason':'review_missing','evidence_refs':[],'affected_judgments':['source_use'],'next_action':'complete_reviews'}]}
    if attempt['policy_revision']!=_policy(snapshot):
        report={'status':'needs_work','checks':[{'check_id':'current_revision','checker_version':'1','status':'needs_work','reason':'policy_stale','evidence_refs':[],'affected_judgments':['source_use'],'next_action':'revise_attempt'}]}
    attempt.update(result=result,result_ref=ref,output_report=report,status='accepted' if report['status']=='pass' else 'needs_work');work['status']=attempt['status']
    event=_event('finished',payload={'status':attempt['status'],'result_ref':ref});attempt['events'].append(event)
    return _plan(rows,work,event,objects)


def revise(snapshot,payload):
    _check(payload,('work_id','previous_attempt_id','attempt_id','generation','reason'),('input','input_ref'))
    rows=deepcopy(snapshot['state'].get('execution_work',{}));work=rows.get(payload['work_id'])
    if not work or work['current_attempt_id']!=payload['previous_attempt_id'] or payload['generation']!=work['generation']+1 or payload['attempt_id'] in work['attempts']:raise ValueError('execution_generation_stale')
    old=work['attempts'][payload['previous_attempt_id']];objects={}
    attempt=_new(snapshot,{**payload,'contract_ref':old['contract_ref'],'assignment_ref':old['assignment_revision']},objects)
    work.update(current_attempt_id=attempt['attempt_id'],generation=attempt['generation'],status=attempt['status']);work['attempts'][attempt['attempt_id']]=attempt
    event=_event('revised',payload={'reason':payload['reason'],'return_from':payload['previous_attempt_id']});attempt['events'].append(event)
    return _plan(rows,work,event,objects)
