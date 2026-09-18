"""Read-only lifecycle projection from exactly the requested graph revision."""
from copy import deepcopy
import re
from .execution_contracts import ROLES


def _safe(value):
    if isinstance(value,str):
        # Defense in depth for known credential labels and local paths in prose.
        # This is deliberately not a claim to detect arbitrary secrets.
        value=re.sub(r"(?<![A-Za-z0-9:/])(?:/[A-Za-z0-9_.~-]+)+[^\s\"<>]*", '[local path]', value)
        value=re.sub(r"[A-Za-z]:\\[^\s\"<>]+", '[local path]', value)
        return re.sub(r"(?i)(?:bearer\s+\S+|[\"']?(?:api[_-]?key|token|password|secret)[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+))", '[redacted]', value)
    if isinstance(value,list):return [_safe(v) for v in value]
    if isinstance(value,dict):return {k:_safe(v) for k,v in value.items() if k not in ('token','api_key','password','secret','path','run_dir')}
    return value


def public_execution(snapshot):
    rows=[]
    order={event['payload']['work_id']:i for i,event in enumerate(snapshot.get('events',[]),1) if event['type']=='execution_begun'}
    works=sorted(snapshot['state'].get('execution_work',{}).values(), key=lambda w:order.get(w['work_id'],0))
    for work in works:
        sequence=order.get(work['work_id'],0)
        row={k:deepcopy(work[k]) for k in ('work_id','step_id','purpose','status','current_attempt_id','generation')}
        if snapshot['state'].get('work_execution_policy',{}).get('status')=='stopped' and row['status'] in ('running','recovery_required'):
            row['status']='paused'
        row.update(title=work['purpose'],sequence=sequence,attempts=[],current_action='',observation_status='unknown')
        for attempt in sorted(work['attempts'].values(),key=lambda a:a['generation']):
            disclosed=set(ROLES[:3])<=set(attempt['submissions'].get('initial',{}))
            public={k:deepcopy(attempt[k]) for k in ('attempt_id','generation','status','return_from')}
            public.update(submissions={p:deepcopy(values) for p,values in attempt['submissions'].items() if p!='initial' or disclosed},events=[],checks=[],result=deepcopy(attempt['result']))
            for report in (attempt.get('input_report'),attempt.get('output_report')):
                if report:public['checks'].extend(deepcopy(report['checks']))
            for index,event in enumerate(attempt['events']):
                item=deepcopy(event);item['id']=f"{attempt['attempt_id']}:{index}";item['event_id']=item['id']
                data=item['payload'];data['role']=item['actor']
                if item['type']=='role_submitted':
                    visible=data.get('phase')!='initial' or disclosed
                    data['published']=visible
                    result=data.pop('result',{})
                    if visible:data['rationale']=result.get('rationale','');data['recommendation']=result.get('recommendation','')
                public['events'].append(item)
            if attempt['attempt_id']==work['current_attempt_id']:
                last=attempt['events'][-1] if attempt['events'] else {}
                row['last_observed_at']=last.get('timestamp')
                row['observation_status']='inspection_required' if attempt['status']=='recovery_required' else 'unknown'
                failed=next((c for c in reversed(public['checks']) if c['status']!='pass'),{})
                row['next_action']=failed.get('next_action','')
                row['reason']=failed.get('reason','')
            row['attempts'].append(public)
        safe=_safe(row)
        safe['redacted']=safe!=row
        rows.append(safe)
    return rows
