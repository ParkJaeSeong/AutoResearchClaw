"""Reviewed M1 question-only relief; unresolved issues still block review/handoff.

Only native, unanimous three-role councils can activate a proposal. This changes
preparation routing, never issue status, corpus approval or execution authority.
"""
from copy import deepcopy
from uuid import UUID, uuid5
from . import store
from .issues import _Inputs, _require
from .issue_impacts import impact_records, current_impact_ids, _event_id
from .councils import _submissions, _session, _phase, _record_ref

_QUESTION = dict(kind='node', milestone='M1', target_id='questions')
_HOLDS = [dict(kind='node', milestone='M1', target_id='review'),
          dict(kind='handoff', milestone='M1', target_id='M2')]


def _id(record):
    return str(uuid5(UUID(record['project_id']), store._hash(store._canonical({k:v for k,v in record.items() if k!='id'}))))


def _native(inputs, collection, record, event_type, key):
    first = next(old for _, old in inputs.history if record['id'] in old['state'].get(collection, {}))
    event = first['events'][-1]
    _require(first['state'][collection][record['id']] == record and event['type']==event_type
             and event['payload'].get(key)==record['id'], 'scope_native_required')
    return first


def _build_proposal(snapshot, payload):
    inputs = _Inputs(snapshot)
    _require(type(payload) is dict and set(payload)=={'impact_refs','producer_id','rationale'}
             and type(payload['impact_refs']) is list and bool(payload['impact_refs'])
             and all(type(payload[k]) is str and payload[k].strip() for k in ('producer_id','rationale')),
             'scope_proposal_invalid')
    impacts = impact_records(snapshot); current = current_impact_ids(snapshot, impacts)
    changes, seen = [], set()
    for ref in payload['impact_refs']:
        impact = inputs.reference(ref, 'issue_impacts')
        _require(impact['id'] in current, 'scope_impact_stale')
        issue = inputs.reference(impact['issue_ref'], 'issues', 'Issue')
        _require(issue['id'] not in seen and _QUESTION in issue['blocking_scope'], 'scope_question_target_required')
        seen.add(issue['id'])
        replacement = [s for s in issue['blocking_scope'] if s!=_QUESTION]
        replacement.extend(s for s in _HOLDS if s not in replacement)
        changes.append(dict(issue_ref=impact['issue_ref'], impact_ref=ref,
            issue_event_id=_event_id(inputs.state,issue['id']), original_scopes=issue['blocking_scope'],
            replacement_scopes=replacement))
    record = {**store._VERSION, 'project_id':inputs.project, 'producer_id':payload['producer_id'],
        'rationale':payload['rationale'], 'questions_revision':inputs.state.get('m1_node_heads',{}).get('questions'),
        'changes':changes, 'preserved_conditions':['Issues remain unresolved','No corpus approval or experiment permission',
        'Unresolved issues block M1 review and M1-to-M2 handoff']}
    record['id'] = _id(record)
    return record


def propose_scope(snapshot, payload):
    record = _build_proposal(snapshot, payload)
    records = snapshot['state'].get('issue_scope_proposals',{})
    _require(record['id'] not in records, 'scope_proposal_exists')
    return dict(state_patch={'issue_scope_proposals':{**records,record['id']:record}},
        object_inputs={record['id']:store._canonical(record)},
        event={**store._VERSION,'type':'issue_scope_proposed','payload':{'proposal_id':record['id']}})


def _proposal(inputs, ref):
    record = inputs.reference(ref,'issue_scope_proposals')
    _require(record['id']==_id(record), 'scope_proposal_invalid')
    first = _native(inputs,'issue_scope_proposals',record,'issue_scope_proposed','proposal_id')
    # Reconstruct at the original immutable input context, not today's state.
    index = next(i for i,(_,old) in enumerate(inputs.history) if old is first)
    _require(index>0,'scope_native_required')
    prior_head,prior = inputs.history[index-1]
    snapshot = {**store._receipt(prior_head,prior), '_issue_context':{
        'history':inputs.history[:index], 'objects':inputs.objects}}
    expected = _build_proposal(snapshot,dict(impact_refs=[r['impact_ref'] for r in record['changes']],
        producer_id=record['producer_id'],rationale=record['rationale']))
    _require(record==expected,'scope_proposal_invalid')
    return record


def _review(inputs, proposal, ref, council_id):
    council = inputs.registered('councils',council_id)
    first = _native(inputs,'councils',council,'council_prepared','council_id')
    _require(council['milestone']=='M1' and council['node']=='issue_scope'
             and council['attempt']==proposal['id'] and set(council['required_roles'])=={'domain','methodology','critical'}
             and set(council['issue_ids'])=={r['issue_ref']['artifact_id'] for r in proposal['changes']}
             and _session(inputs,council)['input_binding']==ref, 'scope_council_binding_invalid')
    authors = [inputs.assignment(i) for i in council['author_assignment_ids']]
    reviewers = [inputs.assignment(i) for i in council['required_roles'].values()]
    _require(len(authors)==1 and authors[0]['actor_id']==proposal['producer_id']
             and authors[0]['role']=='owner' and all(r['role']=='resolver' and r['milestone']=='M1' for r in reviewers)
             and len({r['actor_id'] for r in reviewers})==3
             and authors[0]['actor_id'] not in {r['actor_id'] for r in reviewers}, 'scope_reviewer_invalid')
    records = _submissions(inputs,council)
    _require(_phase(inputs,council,records)=='complete','scope_review_required')
    for phase, submissions in records.items():
        for submission in submissions.values():
            _native(inputs,'council_submissions',submission,'council_submission_registered','submission_id')
            _require(submission['input_binding']==ref and ref in submission['evidence_refs']
                     and not submission['issue_proposals'], 'scope_review_required')
            if phase=='final':
                positions=[*submission['positions'], *(inputs.reference(r,'positions','Position') for r in submission['retained_position_refs'])]
                _require(all(p['stance']!='oppose' for p in positions), 'scope_review_required')
                _require(submission['recommendation']=='ready','scope_review_required')
    return [_record_ref(inputs,'council_submissions',r) for r in records['final'].values()]


def apply_scope(snapshot, payload):
    _require(type(payload) is dict and set(payload)=={'proposal_ref','council_id'}, 'scope_apply_invalid')
    inputs = _Inputs(snapshot); proposal = _proposal(inputs,payload['proposal_ref'])
    current = current_impact_ids(snapshot,impact_records(snapshot))
    _require(proposal['questions_revision']==inputs.state.get('m1_node_heads',{}).get('questions')
             and all(r['impact_ref']['artifact_id'] in current for r in proposal['changes']), 'scope_proposal_stale')
    finals = _review(inputs,proposal,payload['proposal_ref'],payload['council_id'])
    record = {**store._VERSION,'project_id':inputs.project,**deepcopy(payload),'final_refs':finals}
    record['id'] = _id(record)
    applied = inputs.state.get('issue_scope_changes',{})
    _require(record['id'] not in applied,'scope_change_exists')
    return dict(state_patch={'issue_scope_changes':{**applied,record['id']:record}},
        object_inputs={record['id']:store._canonical(record)},
        event={**store._VERSION,'type':'issue_scope_changed','payload':{'change_id':record['id']}})


def effective_scopes(inputs, issue):
    """Fall back to original scope after issue, impact or question revision changes."""
    if not hasattr(inputs, '_scope_results'):
        selected = {}
        for _,ancestor in inputs.history:
            event = ancestor['events'][-1]
            if event['type']!='issue_scope_changed':
                continue
            record = inputs.registered('issue_scope_changes',event['payload']['change_id'])
            _native(inputs,'issue_scope_changes',record,'issue_scope_changed','change_id')
            proposal = _proposal(inputs,record['proposal_ref'])
            _require(_review(inputs,proposal,record['proposal_ref'],record['council_id'])==record['final_refs'],
                     'scope_review_required')
            for change in proposal['changes']:
                selected[change['issue_ref']['artifact_id']] = proposal,change
        latest = {}
        if selected:
            snapshot = {**store._receipt(*inputs.history[-1]),
                '_issue_context':{'history':inputs.history,'objects':inputs.objects}}
            for impact in impact_records(snapshot):
                latest[impact['issue_ref']['artifact_id']] = impact['id']
        results, proposal_ids = {}, {}
        for issue_id,(proposal,change) in selected.items():
            if (proposal['questions_revision']==inputs.state.get('m1_node_heads',{}).get('questions')
                and change['issue_event_id']==_event_id(inputs.state,issue_id)
                and latest.get(issue_id)==change['impact_ref']['artifact_id']):
                results[issue_id] = change['replacement_scopes']
                proposal_ids[issue_id] = proposal['id']
        inputs._scope_results = results
        inputs._scope_proposal_ids = proposal_ids
    return deepcopy(inputs._scope_results.get(issue['id'],issue['blocking_scope']))
