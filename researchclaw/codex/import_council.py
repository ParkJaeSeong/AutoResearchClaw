"""Project-local review experiment using the audited host reviewer; no adoption."""
import fcntl
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .atlas_council import _saved

ROLES=('domain','methodology','critical')


def run_import_council(queue,task_id,base,reviewer, *, on_event=None):
    emit=on_event or (lambda event: None)
    task=queue.get(task_id)
    if task['status']!='input_ready':raise ValueError('review_input_not_ready')
    materials=queue.materials(task_id)
    context=task['context']
    materials.update({k:context[k] for k in ('personas','milestone_purpose') if k in context})
    if context.get('purpose'):materials['review_scope']=context['purpose']
    base=Path(base);base.mkdir(parents=True,exist_ok=True)
    with (base/'run.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('review_busy') from None
        binding={'task_id':task_id,'packet_sha256':task['packet_sha256']}
        if _saved(base/'binding.json',lambda:binding)!=binding:raise ValueError('review_binding_changed')
        if on_event is None and (base/'result.json').exists():return json.loads((base/'result.json').read_text())
        rounds={}
        for phase in ('initial','response','final'):
            packet={'disclosed_initials':rounds.get('initial',[]) if phase!='initial' else [],
                    'disclosed_responses':rounds.get('response',[]) if phase=='final' else []}
            def invoke(role):
                run=base/(phase+'-'+role);run.mkdir(exist_ok=True)
                emit(dict(kind='role_started',role=role,phase=phase))
                result=_saved(run/'verified.json',lambda:reviewer(role,phase,packet,materials,run))
                emit(dict(kind='role_submitted',role=role,phase=phase,result=result))
                return dict(role=role,**result)
            with ThreadPoolExecutor(max_workers=3) as pool:rounds[phase]=list(pool.map(invoke,ROLES))
            _saved(base/(phase+'.json'),lambda:rounds[phase])
            emit(dict(kind='phase_ready',phase=phase))
        run=base/'coordinator';run.mkdir(exist_ok=True)
        packet={'disclosed_initials':rounds['initial'],'disclosed_responses':rounds['response'],'disclosed_finals':rounds['final'],
                'instruction':'세 전문가 결론의 일치·이견과 출처 한계를 구분하고, 제한된 근거 사용과 보완 제안을 정리한다. 가설 채택·수집 실행·M1 완료는 하지 않는다.'}
        emit(dict(kind='role_started',role='coordinator',phase='final'))
        coordinator=_saved(run/'verified.json',lambda:reviewer('coordinator','final',packet,materials,run))
        emit(dict(kind='role_submitted',role='coordinator',phase='final',result=coordinator))
        result={'stage':'review_complete',**binding,'rounds':rounds,'coordinator':coordinator,'research_adoption':False}
        return _saved(base/'result.json',lambda:result)
