"""Explicit local Atlas observer and individual-review dispatcher. No OS autostart."""
import argparse
import hashlib
import fcntl
import json
import re
import time
from pathlib import Path

from .atlas_client import AtlasClient
from .atlas_reviewer import host_reviewer
from .document_handoff_runner import configured_adapter, cycle
from .import_council import run_import_council
from .import_review import load_queue


def dispatch(queue, context, client, reviewer, runs, run=run_import_council, publish=None):
    results=[];errors=[]
    for task in queue.reconcile(context):
        key=task['id']
        try:
            if queue.completed(key) is not None:
                if publish:publish(key,queue.completed(key))
                queue.execution(key,'review_complete')
                results.append({'task_id':key,'status':'review_complete'})
                continue
            if queue.get(key)['status']=='needs_recovery':
                results.append({'task_id':key,'status':'needs_recovery'})
                continue
            prepared=queue.prepare(key,client)
            if prepared['status']!='input_ready':raise ValueError('review_input_not_ready')
            queue.execution(key,'review_running')
            result=run(queue,key,Path(runs)/key,reviewer)
            queue.complete(key,result)
            if publish:publish(key,result)
            queue.execution(key,'review_complete')
            results.append({'task_id':key,'status':'review_complete'})
        except (ValueError,OSError,KeyError,TypeError) as exc:
            queue.execution(key,'review_failed')
            code=str(exc)
            errors.append({'task_id':key,'code':code if re.fullmatch('[a-zA-Z_]+',code) else 'review_requires_inspection'})
    return {'results':results,'errors':errors}


def require_active_work(root, work_id):
    from researchclaw.core.research_graph import store
    state=store.read_head(root)['state']
    episode=state.get('work_episodes',{}).get(work_id)
    policy=state.get('work_execution_policy',{})
    if not episode or episode['execution_status']!='running' or policy.get('status')!='active' or policy.get('milestone')!='M1':
        raise ValueError('review_work_not_active')


def publish_review(root, task_id, task, result):
    """Return immutable review text to its original episode; never adopt or finish it."""
    from researchclaw.core.research_graph import commands,store
    work=task['context']['work_id']
    if task['request'].get('work_ref')!=work:raise ValueError('review_work_mismatch')
    require_active_work(root,work)
    labels={'domain':'소재·공정 검토자','methodology':'평가 방법 검토자','critical':'반증·실행 검토자'}
    phases={'initial':'첫 의견','response':'서로의 의견 검토','final':'최종 의견'}
    notes=[]
    for phase,rows in result['rounds'].items():
        for row in rows:
            notes.append((phase+'-'+row['role'],'dialogue',labels.get(row['role'],row['role'])+' · '+phases[phase],row['answer']['rationale']))
    notes.append(('coordinator','output','조정자 · 개별 문헌 검토 결과',result['coordinator']['answer']['rationale']+'\n\n개별 문헌의 사용 범위에 대한 검토입니다. 연구 가설 채택이나 단계 완료는 아닙니다. 검토 기록: '+task_id))
    for suffix,kind,author,text in notes:
        commands.apply_command(root,operation='episode.note',payload=dict(id=work,kind=kind,author=author,text=text),
            expected_head=store.read_head(root)['id'],command_id='import-review:'+task_id+':'+suffix)


def tick(root,context,documents_connection,import_connection,a1_connection,reviewer):
    root=Path(root).resolve()
    context=dict(context)
    source=context.pop('question_source',None)
    if not isinstance(source,str) or not source:
        raise ValueError('review_question_source_required')
    question_path=(root/source).resolve()
    if not question_path.is_relative_to(root):raise ValueError('review_question_path_invalid')
    current=question_path.read_bytes()
    if hashlib.sha256(current).hexdigest()!=context.get('question_revision') or current.decode('utf-8')!=context.get('question'):
        raise ValueError('review_question_changed')
    if context.get('work_id'):require_active_work(root,context['work_id'])
    queue=load_queue(root)
    runs=root/'.document-handoff/review-runs';runs.mkdir(exist_ok=True)
    with (runs/'worker.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('review_worker_busy') from None
        adapter=configured_adapter(root,documents_connection,import_connection)
        observed=cycle(adapter)
        publish=(lambda key,result:publish_review(root,key,queue.get(key),result)) if context.get('work_id') else None
        result=dispatch(queue,context,AtlasClient(a1_connection),reviewer,runs,publish=publish)
        result['observation']=observed
        # Persist each cycle. Saved results can reconcile even after earlier ACK.
        with (runs/'observations.jsonl').open('a') as log:
            log.write(json.dumps({'at':time.time(),**result},ensure_ascii=False)+'\n')
        return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    for name in ('context','documents-connection','import-connection','a1-connection','host'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--watch',action='store_true')
    args=p.parse_args(argv)
    reviewer=host_reviewer(args.host)
    try:
        while True:
            context=json.loads(args.context.read_text())
            result=tick(args.root,context,args.documents_connection,args.import_connection,args.a1_connection,reviewer)
            print(json.dumps(result),flush=True)
            # Do not blindly retry failed model attempts on a timer.
            if result['errors'] or not result['observation']['ok']:return 1
            if not args.watch:return 0
            time.sleep(60)
    except KeyboardInterrupt:return 130


if __name__=='__main__':raise SystemExit(main())
