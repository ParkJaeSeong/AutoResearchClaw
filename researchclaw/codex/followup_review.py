"""Readonly followup answer -> one explicit initial review, not council adoption."""
from researchclaw.core.research_graph import commands,store
from researchclaw.core.transactions import project_transaction
from .service_followup_runner import run_followup
from .service_inbox import ServiceInbox
from .service_work_binding import WorkBinding
from .service_review_worker import run_delivery


def review_followup(session,identity,reviewer,*,role='methodology'):
    if role not in ('domain','methodology','critical'):raise ValueError('review_role_unsupported')
    observed=run_followup(session,identity)
    if observed['state']!='result_stored':return observed
    if observed['answer_state']!='stored':return dict(observed,state='needs_input')
    request=session._get(observed['request_key'])
    digest=request['qa_ref']['sha256']
    raw=store._checked_path(session.base/'objects'/digest).read_bytes()
    if store._hash(raw)!=digest:raise ValueError('review_input_hash_mismatch')
    with project_transaction(session.root):
        snapshot=store.read_head(session.root)
        policy=snapshot['state'].get('work_execution_policy',{})
        if policy.get('status')!='active' or policy.get('milestone')!='M1':raise ValueError('execution_not_active')
        followup=snapshot['state']['service_followups'][identity]
        materials=dict(purpose=followup['purpose'],reason=followup['reason'],
            previous_work_id=followup['work_id'],previous_delivery_id=followup['delivery_id'],
            question=request['question'],atlas_qa_raw=raw.decode('utf-8'),qa_ref=request['qa_ref'],
            atlas_status=request['job']['status'],supporting=request.get('supporting',[]),
            reading_scope='Atlas QA only; source/page originals are not supplied to this reviewer',
            milestone_purpose='M1 근거 검토 및 가상 설계 준비',
            output_requirement='근거의 사용 범위·미확인·보완 제안. 가설 채택과 M1 완료 판단 아님')
        revision=store._hash(store._canonical(materials))
        recipient=dict(work_id=followup['target_work_id'],role_id=role,round_id='initial',input_revision=revision)
        assignment=dict(recipient,milestone='M1',active=True)
        existing=snapshot['state'].get('work_execution_assignments',{}).get(recipient['work_id'])
        if existing is not None and existing!=assignment:raise ValueError('review_assignment_changed')
        if existing is None:
            commands.apply_command(session.root,operation='work.execution.assign',payload=assignment,
                expected_head=snapshot['id'],command_id='followup-review-assign:'+identity)
        delivery=session.queue_answer(observed['request_key'],recipient)
    binding=WorkBinding(session.root,recipient,materials,{})
    inbox=ServiceInbox(session.root,session.project_id)
    return run_delivery(inbox,delivery['id'],binding.read,reviewer,publish=binding.publish)


def main():
    import argparse,json
    from pathlib import Path
    from .atlas_client import AtlasClient
    from .atlas_session import AtlasSession
    from .atlas_reviewer import host_reviewer
    parser=argparse.ArgumentParser(description='Observe a followup and run one bound initial evidence review')
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--connection',required=True,type=Path)
    parser.add_argument('--followup-id',required=True)
    parser.add_argument('--host',required=True)
    parser.add_argument('--role',choices=('domain','methodology','critical'),default='methodology')
    args=parser.parse_args()
    result=review_followup(AtlasSession(args.root,AtlasClient(args.connection)),args.followup_id,
                           host_reviewer(args.host),role=args.role)
    print(json.dumps(dict(state=result['state'],delivery_id=result.get('delivery_id')),ensure_ascii=False))


if __name__=='__main__':main()
