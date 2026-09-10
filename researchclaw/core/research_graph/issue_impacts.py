"""Append-only coordinator proposals about issue impact, never gate overrides."""
from copy import deepcopy
from uuid import UUID, uuid5

from . import store
from .issues import _Inputs, _require

_TEXT = {'group_key', 'group_title', 'next_check', 'if_unresolved', 'owner_role', 'rationale', 'producer_id'}
_LIST = {'affected_sources', 'hypotheses', 'held_work', 'preparation_work'}
_FIELDS = _TEXT | _LIST | {'issue_ref'}


def _validate(inputs, row):
    _require(type(row) is dict and set(row) == _FIELDS, 'issue_impact_invalid')
    _require(all(type(row[k]) is str and row[k].strip() for k in _TEXT), 'issue_impact_invalid')
    _require(all(type(row[k]) is list and all(type(x) is str and x.strip() for x in row[k])
                 for k in _LIST), 'issue_impact_invalid')
    _require(bool(row['held_work'] or row['preparation_work']), 'issue_impact_work_required')
    return inputs.reference(row['issue_ref'], 'issues', 'Issue')


def _event_id(state, issue_id):
    events = [r for r in state.get('issue_events', []) if r['issue_id'] == issue_id]
    return events[-1]['id'] if events else None


def _identity(record):
    return str(uuid5(UUID(record['project_id']), store._hash(store._canonical({k:v for k,v in record.items() if k!='id'}))))


def record_impacts(snapshot, payload):
    inputs = _Inputs(snapshot)
    _require(type(payload) is dict and set(payload) == {'assessments'}
             and type(payload['assessments']) is list and payload['assessments'], 'issue_impact_invalid')
    records = {r['id']: deepcopy(r) for r in impact_records(snapshot)}
    objects, ids = {}, []
    for row in payload['assessments']:
        issue = _validate(inputs, row)
        record = {**store._VERSION, 'project_id': inputs.project, **deepcopy(row),
                  'assessment_kind': 'coordinator_proposal',
                  'issue_event_id': _event_id(inputs.state, issue['id']),
                  'node_versions': deepcopy(inputs.state.get('m1_node_heads', {}))}
        record['id'] = _identity(record)
        if record['id'] not in records:
            records[record['id']] = record
            objects[record['id']] = store._canonical(record)
        ids.append(record['id'])
    return dict(state_patch={'issue_impacts': records}, object_inputs=objects,
                event={**store._VERSION, 'type': 'issue_impact_recorded',
                       'payload': {'assessment_ids': list(dict.fromkeys(ids))}})


def impact_records(snapshot):
    inputs = _Inputs(snapshot)
    records = inputs.state.get('issue_impacts', {})
    _require(type(records) is dict, 'issue_impact_collection_invalid')
    for identity in records:
        record = inputs.registered('issue_impacts', identity)
        _require(set(record) == _FIELDS | set(store._VERSION) |
                 {'id','project_id','assessment_kind','issue_event_id','node_versions'}, 'issue_impact_invalid')
        _validate(inputs, {k:record[k] for k in _FIELDS})
        _require(record['id'] == _identity(record) and record['assessment_kind']=='coordinator_proposal',
                 'issue_impact_invalid')
        first = next(old for _, old in inputs.history if identity in old['state'].get('issue_impacts', {}))
        event = first['events'][-1]
        _require(first['state']['issue_impacts'][identity] == record and event['type']=='issue_impact_recorded'
                 and identity in event['payload'].get('assessment_ids', []), 'issue_impact_native_invalid')
        _require(record['node_versions'] == first['state'].get('m1_node_heads', {})
                 and record['issue_event_id'] == _event_id(first['state'],record['issue_ref']['artifact_id']),
                 'issue_impact_binding_invalid')
    # Canonical JSON sorts mapping keys; UUID order is not revision order.
    ordered, seen = [], set()
    for _, ancestor in inputs.history:
        event = ancestor['events'][-1]
        if event['type'] != 'issue_impact_recorded':
            continue
        for identity in event['payload']['assessment_ids']:
            if identity in records and identity not in seen:
                ordered.append(records[identity])
                seen.add(identity)
    return ordered


def current_impact_ids(snapshot, records):
    latest = {}
    for record in records:
        latest[record['issue_ref']['artifact_id']] = record
    return {record['id'] for issue_id, record in latest.items()
            if record['node_versions'] == snapshot['state'].get('m1_node_heads', {})
            and record['issue_event_id'] == _event_id(snapshot['state'], issue_id)}
