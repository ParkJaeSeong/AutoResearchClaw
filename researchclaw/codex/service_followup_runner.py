"""Execute one approved M1 readonly Atlas followup, reusing transport receipts."""
from researchclaw.core.research_graph import commands,store
from researchclaw.core.transactions import project_transaction


def run_followup(session,identity):
    # The bounded submit/poll is serialized with policy changes. No model wait
    # happens here; a subsequent invocation observes the same remote request.
    with project_transaction(session.root):
        snapshot=store.read_head(session.root)
        policy=snapshot['state'].get('work_execution_policy',{})
        if policy.get('status')!='active' or policy.get('milestone')!='M1':
            raise ValueError('execution_not_active')
        row=snapshot['state'].get('service_followups',{}).get(identity)
        if not row:raise ValueError('execution_followup_missing')
        if row['action']!='ask_atlas':raise ValueError('execution_action_not_supported')
        if row['status']=='planned':
            snapshot=commands.apply_command(session.root,operation='work.execution.start',payload={'id':identity},
                expected_head=snapshot['id'],command_id='start-followup:'+identity)
            row=snapshot['state']['service_followups'][identity]
        work=snapshot['state']['work_episodes'][row['target_work_id']]
        if work['conclusion'] is not None:raise ValueError('execution_work_closed')
        key=row['request_key']
        try:request=session._get(key)
        except ValueError as exc:
            if str(exc)!='atlas_request_unknown':raise
            question=(row['purpose']+'\n확인 이유: '+row['reason']+
                      '\n기존 보유 자료에서 확인하고 출처·조건·미확인을 구분해 주세요.')
            request=session.ask(key,question,identity)
        else:
            if not request.get('qa_envelope'):request=session.poll(key)
    job=request.get('job') or {}
    result=dict(followup_id=identity,work_id=row['target_work_id'],request_key=key,
                job_id=job.get('id'),atlas_status=job.get('status'))
    if job.get('status') in ('completed','partial','failed','interrupted') and job.get('detail',{}).get('qa_ref'):
        captured=session.capture(key)
        return dict(result,state='result_stored',answer_state=captured['answer_state'],qa_ref=captured['qa_ref'])
    attention=job.get('status') in ('failed','interrupted','completed','partial') or job.get('dispatch_error') or job.get('scheduled') is False
    return dict(result,state='needs_attention' if attention else 'waiting')


def main():
    import argparse,json
    from pathlib import Path
    from .atlas_client import AtlasClient
    from .atlas_session import AtlasSession
    parser=argparse.ArgumentParser(description='Run one registered readonly Atlas followup')
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--connection',required=True,type=Path)
    parser.add_argument('--followup-id',required=True)
    args=parser.parse_args()
    print(json.dumps(run_followup(AtlasSession(args.root,AtlasClient(args.connection)),args.followup_id),ensure_ascii=False))


if __name__=='__main__':main()
