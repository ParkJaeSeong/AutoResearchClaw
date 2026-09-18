"""Declared coordinator execution scope; never inferred from a model answer."""
from copy import deepcopy
from . import store


def _check(payload,fields):
    if type(payload) is not dict or set(payload)!=set(fields):raise ValueError('execution_payload_invalid')
    if any(not isinstance(v,str) or not v.strip() for k,v in payload.items() if k!='active'):
        raise ValueError('execution_payload_invalid')


def _plan(key,value,event,payload):
    return dict(state_patch={key:deepcopy(value)},event={**store._VERSION,'type':event,'payload':deepcopy(payload)},object_inputs={})


def set_policy(snapshot,payload):
    _check(payload,('milestone','status','reason'))
    if payload['milestone']!='M1' or payload['status'] not in ('active','stopped','completed'):
        raise ValueError('execution_policy_invalid')
    if payload['status']=='completed' and snapshot['state'].get('execution_work'):
        raise ValueError('execution_milestone_gate_required')
    return _plan('work_execution_policy',payload,'work_execution_policy_set',payload)


def assign(snapshot,payload):
    _check(payload,('work_id','role_id','round_id','input_revision','milestone','active'))
    state=snapshot['state'];policy=state.get('work_execution_policy',{})
    if policy.get('status')!='active':raise ValueError('execution_not_active')
    if payload['milestone']!=policy['milestone']:raise ValueError('execution_milestone_mismatch')
    episode=state.get('work_episodes',{}).get(payload['work_id'])
    if not episode or episode['conclusion'] is not None:raise ValueError('execution_work_invalid')
    if type(payload['active']) is not bool or payload['role_id'] not in ('domain','methodology','critical','coordinator') or payload['round_id'] not in ('initial','response','final'):
        raise ValueError('execution_assignment_invalid')
    rows=deepcopy(state.get('work_execution_assignments',{}));rows[payload['work_id']]=deepcopy(payload)
    return _plan('work_execution_assignments',rows,'work_execution_assigned',payload)


def followup(snapshot,payload):
    import json
    _check(payload,('id','work_id','delivery_id','action','purpose','reason'))
    if payload['action'] not in ('ask_atlas','collect_sources','review','revise_design'):
        raise ValueError('execution_followup_action_invalid')
    episode=snapshot['state'].get('work_episodes',{}).get(payload['work_id'],{})
    found=False
    for note in episode.get('notes',[]):
        if note['kind']!='output':continue
        try:record=json.loads(note['text'])
        except (ValueError,TypeError):continue
        if isinstance(record,dict) and record.get('delivery_id')==payload['delivery_id'] and isinstance(record.get('review'),dict):
            found=True
    if not found:raise ValueError('execution_review_missing')
    rows=deepcopy(snapshot['state'].get('service_followups',{}))
    if payload['id'] in rows:raise ValueError('execution_followup_exists')
    rows[payload['id']]={**deepcopy(payload),'status':'planned','execution_authorized':False}
    return _plan('service_followups',rows,'service_followup_planned',payload)


def start_followup(snapshot,payload):
    from .work_episodes import start_episode
    _check(payload,('id',))
    state=snapshot['state'];policy=state.get('work_execution_policy',{})
    if policy.get('status')!='active' or policy.get('milestone')!='M1':
        raise ValueError('execution_not_active')
    rows=deepcopy(state.get('service_followups',{}));row=rows.get(payload['id'])
    if not row:raise ValueError('execution_followup_missing')
    # Initial executor supports readonly Atlas questions only.
    if row['action']!='ask_atlas':raise ValueError('execution_action_not_supported')
    if row['status']=='started':
        return _plan('service_followups',rows,'service_followup_start_replayed',payload)
    if row['status']!='planned':raise ValueError('execution_followup_state_invalid')
    identity='service-followup-'+store._hash(store._canonical(dict(project_id=state['project_id'],id=row['id'])))
    plan=start_episode(snapshot,dict(id=identity,stage='자료 확인',title='검토에서 나온 질문을 Atlas에 확인',
        purpose=row['purpose'],depends_on=[],return_to=row['work_id'],return_reason=row['reason'],review_required=False))
    row.update(status='started',execution_authorized=True,target_work_id=identity,
               request_key=identity,milestone='M1',policy_sha256=store._hash(store._canonical(policy)))
    plan['state_patch']['service_followups']=rows
    plan['event']={**store._VERSION,'type':'service_followup_started','payload':deepcopy(payload)}
    return plan
