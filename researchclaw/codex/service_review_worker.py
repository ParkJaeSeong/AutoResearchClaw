"""Resume an explicitly bound review delivery, without scientific adoption."""
import fcntl
import json
import os
import tempfile
from copy import deepcopy

from researchclaw.core.research_graph import store


def _save(path,value):
    data=store._canonical(value)
    fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def run_delivery(inbox,delivery_id,read_context,reviewer,*,publish=None):
    """read_context supplies authoritative current work state; reviewer uses host signature.

    This resumes a single designated role/round, not a whole council or milestone.
    """
    with inbox._db() as db:
        row=db.execute('SELECT body FROM deliveries WHERE id=?',(delivery_id,)).fetchone()
    if row is None:raise ValueError('inbox_delivery_unknown')
    delivery=json.loads(row[0])
    if store._hash(store._canonical(delivery['result_ref']))!=delivery['result_sha256']:
        raise ValueError('review_input_hash_mismatch')
    base=store._checked_path(inbox.path.parent/'reviews'/delivery_id)
    base.mkdir(parents=True,exist_ok=True)
    with (base/'run.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('review_busy') from None
        if publish is not None and (base/'result.json').exists():
            result=json.loads((base/'result.json').read_text())
            original=json.loads((base/'intent.json').read_text())['context']
            publish(delivery_id,original,result)
            inbox.acknowledge(delivery_id,delivery['recipient'])
            return result
        context=deepcopy(read_context())
        recipient=delivery['recipient']
        if not context.get('active') or context.get('recipient')!=recipient:
            return dict(state='not_applicable',delivery_id=delivery_id)
        if delivery['stage']!='answer' or delivery['result_ref'].get('answer_state')!='stored':
            return dict(state='needs_input',delivery_id=delivery_id)
        result_path=base/'result.json'
        if result_path.exists():
            result=json.loads(result_path.read_text())
            if result['context_sha256']!=store._hash(store._canonical(context)):
                return dict(state='superseded',delivery_id=delivery_id)
            inbox.acknowledge(delivery_id,recipient)
            return result
        raw_path=base/'review.json'
        context_hash=store._hash(store._canonical(context))
        intent_path=base/'intent.json'
        if intent_path.exists():
            intent=json.loads(intent_path.read_text())
            if intent['context_sha256']!=context_hash:
                return dict(state='superseded',delivery_id=delivery_id)
            if not raw_path.exists():raise ValueError('review_attempt_requires_inspection')
        else:
            if recipient['round_id'] not in ('initial','response','final'):
                raise ValueError('review_round_unsupported')
            if recipient['role_id'] not in ('domain','methodology','critical','coordinator'):
                raise ValueError('review_role_unsupported')
            if not isinstance(context.get('materials'),dict) or not isinstance(context.get('packet'),dict):
                raise ValueError('review_context_required')
            if recipient['round_id']=='initial' and any(context['packet'].get(k) for k in ('disclosed_initials','disclosed_responses','disclosed_finals')):
                raise ValueError('review_independent_input_required')
            _save(intent_path,dict(context_sha256=context_hash,context=context,delivery=delivery))
        if not raw_path.exists():
            materials=dict(context['materials'],service_result=delivery['result_ref'])
            raw=reviewer(recipient['role_id'],recipient['round_id'],context['packet'],materials,base)
            _save(raw_path,raw)
        raw=json.loads(raw_path.read_text())
        # A late answer is preserved, but never acknowledges a newer/stopped work.
        if store._hash(store._canonical(read_context()))!=context_hash:
            return dict(state='superseded',delivery_id=delivery_id)
        result=dict(state='review_complete',delivery_id=delivery_id,context_sha256=context_hash,
                    review=raw,research_adoption=False)
        _save(result_path,result)
        if publish is not None:publish(delivery_id,context,result)
        inbox.acknowledge(delivery_id,recipient)
        return result


def main():
    import argparse
    from pathlib import Path
    from .service_inbox import ServiceInbox
    from .atlas_reviewer import host_reviewer
    parser=argparse.ArgumentParser(description='Resume one explicitly bound Atlas answer review')
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--delivery-id',required=True)
    parser.add_argument('--context',type=Path,required=True)
    parser.add_argument('--host',required=True)
    args=parser.parse_args()
    root=store._checked_path(args.root.resolve())
    project=store.read_head(root)['state']['project_id']
    inbox=ServiceInbox(root,project)
    with inbox._db() as db:
        row=db.execute('SELECT body FROM deliveries WHERE id=?',(args.delivery_id,)).fetchone()
    if row is None:raise ValueError('inbox_delivery_unknown')
    delivery=json.loads(row[0]);ref=delivery['result_ref']
    if ref.get('project_id')!=project:raise ValueError('inbox_project_mismatch')
    from .service_work_binding import WorkBinding
    def binding():
        context=json.loads(args.context.read_text())
        digest=ref['qa_ref']['sha256']
        import re
        if not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('review_input_hash_mismatch')
        raw=store._checked_path(root/'.atlas-link'/'objects'/digest).read_bytes()
        if store._hash(raw)!=digest:raise ValueError('review_input_hash_mismatch')
        context['materials']=dict(context['materials'],atlas_qa_raw=raw.decode('utf-8'),
                                  source_reading='QA only; source originals not provided by this runner')
        return WorkBinding(root,context['recipient'],context['materials'],context['packet'])
    def read_context():return binding().read()
    def publish(identity,context,result):return binding().publish(identity,context,result)
    result=run_delivery(inbox,args.delivery_id,read_context,host_reviewer(args.host),publish=publish)
    print(json.dumps(dict(state=result['state'],delivery_id=args.delivery_id),ensure_ascii=False))


if __name__=='__main__':main()
