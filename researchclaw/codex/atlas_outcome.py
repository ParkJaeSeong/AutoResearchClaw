"""Record a coordinator's explicit outcome against completed council evidence."""
import fcntl
import json
from researchclaw.core.research_graph import commands, store
from .atlas_client import AtlasError
from .atlas_council import _saved

FIELDS={'title','conclusion','rationale','limitations','next_action','prior_ref','next_question'}
ACTIONS={'collect_materials','followup_atlas','continue_design','hold'}


def record_outcome(session,key,outcome):
    if (type(outcome) is not dict or set(outcome)!=FIELDS
            or type(outcome.get('next_action')) is not str or outcome['next_action'] not in ACTIONS):
        raise AtlasError('atlas_outcome_invalid')
    text=lambda value:isinstance(value,str) and bool(value.strip())
    question=outcome['next_question']
    if (not all(text(outcome[k]) for k in ('title','conclusion','rationale'))
            or type(outcome['limitations']) is not list or not all(text(v) for v in outcome['limitations'])
            or (outcome['prior_ref'] is not None and type(outcome['prior_ref']) is not dict)
            or (question is not None and (type(question) is not dict
                or set(question)!={'question','missing_evidence','decision_impact','scope'}
                or not all(text(v) for v in question.values())))
            or (outcome['next_action']=='followup_atlas' and question is None)):
        raise AtlasError('atlas_outcome_invalid')
    session._get(key)
    base=store._checked_path(session.base/('council-'+store._hash(key.encode())))
    if not (base/'result.json').exists():raise AtlasError('atlas_council_incomplete')
    with (base/'run.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise AtlasError('atlas_council_busy',retryable=True) from None
        council=json.loads((base/'result.json').read_text())
        if council.get('stage')!='council_complete' or len(council.get('submission_refs',[]))!=3:
            raise AtlasError('atlas_council_incomplete')
        decision={k:outcome[k] for k in ('title','conclusion','rationale','limitations','prior_ref')}
        decision.update(review_ref=council['review_ref'],submission_refs=council['submission_refs'],producer_id='pilot-coordinator')
        input_path=base/'outcome-input.json'
        if not input_path.exists():
            # Reuse the pure domain validator before accepting an immutable input.
            from researchclaw.core.research_graph.external_evidence import record_decision
            record_decision(commands.read_policy_snapshot(session.root),decision)
        original=_saved(input_path,lambda:outcome)
        if original!=outcome:raise AtlasError('atlas_outcome_conflict')
        result_path=base/'outcome-result.json'
        if result_path.exists():
            result=json.loads(result_path.read_text())
            session._update(key,outcome=result)
            return result
        def commit(name,operation,payload):
            return _saved(base/(name+'-receipt.json'),lambda:commands.apply_command(session.root,
                operation=operation,payload=payload,expected_head=store.read_head(session.root)['id'],
                command_id='atlas-outcome:'+store._hash((key+':'+name).encode())))
        receipt=commit('decision','external.decision.record',decision)
        record_id=receipt['events'][-1]['payload']['record_id']
        record=receipt['state']['external_decisions'][record_id]
        ref=dict(project_id=session.project_id,head_id=receipt['id'],artifact_id=record_id,sha256=store._hash(store._canonical(record)))
        question_ref=None
        if outcome['next_question'] is not None:
            question=outcome['next_question']
            if type(question) is not dict or set(question)!={'question','missing_evidence','decision_impact','scope'}:
                raise AtlasError('atlas_outcome_invalid')
            receipt=commit('question','external.question.record',dict(question,decision_ref=ref,producer_id='pilot-coordinator'))
            identity=receipt['events'][-1]['payload']['record_id']
            record=receipt['state']['external_questions'][identity]
            question_ref=dict(project_id=session.project_id,head_id=receipt['id'],artifact_id=identity,sha256=store._hash(store._canonical(record)))
        result=dict(stage='outcome_recorded',decision_ref=ref,next_action=outcome['next_action'],next_question_ref=question_ref)
        _saved(result_path,lambda:result)
        session._update(key,outcome=result)
        return result
