"""Immutable Atlas QA imports and their Pilot-side review records."""
import base64
import binascii
from copy import deepcopy
from uuid import UUID, uuid5

from . import store
from .atlas_format import parse_atlas_qa
from .councils import _disclosed, _record_ref, _session, _submissions
from .dependencies import _References
from .issues import _Inputs, _require

_IMPORT_FIELDS = {'content_base64', 'sha256', 'filename', 'producer_id'}
_REVIEW_FIELDS = {'evidence_ref', 'question_ref', 'status', 'allowed_uses', 'held_uses',
                  'limitations', 'rationale', 'producer_id'}
_DECISION_FIELDS = {'review_ref', 'title', 'conclusion', 'rationale', 'limitations',
                    'submission_refs', 'prior_ref', 'producer_id'}
_QUESTION_FIELDS = {'decision_ref', 'question', 'missing_evidence', 'decision_impact', 'scope', 'producer_id'}


def _text(value):
    return type(value) is str and bool(value.strip())


def _texts(value):
    return type(value) is list and all(_text(item) for item in value)


def _identity(project, body):
    return str(uuid5(UUID(project), store._hash(store._canonical(body))))


def _make(project, body):
    record = {**store._VERSION, 'project_id': project, **body}
    record['id'] = _identity(project, record)
    return record


def _native(inputs, collection, record, event_type, event_id):
    label = {'external_evidence': 'external_evidence', 'external_reviews': 'external_review',
             'external_decisions': 'external_decision', 'external_questions': 'external_question'}[collection]
    first = next((old for _, old in inputs.history if record['id'] in old['state'].get(collection, {})), None)
    _require(first is not None and first['state'][collection][record['id']] == record
             and first['events'][-1]['type'] == event_type
             and first['events'][-1]['payload'].get(event_id) == record['id'],
             label + '_native_invalid')
    _require(inputs.objects.get(store._hash(store._canonical(record))) == store._canonical(record),
             label + '_record_invalid')


def _record_ref_at(inputs, collection, record):
    return _record_ref(inputs, collection, record)


def _resolve_record(inputs, ref, collection, error, *, current=False):
    try:
        _require(type(ref) is dict and set(ref) == {'project_id', 'head_id', 'artifact_id', 'sha256'}
                 and ref['project_id'] == inputs.project and ref['head_id'] in inputs.heads, error)
        ancestor = inputs.heads[ref['head_id']]
        record = ancestor['state'].get(collection, {}).get(ref['artifact_id'])
        _require(type(record) is dict and record.get('project_id') == inputs.project
                 and store._canonical(record) == inputs.objects.get(ref['sha256']), error)
        if current:
            _require(inputs.state.get(collection, {}).get(record['id']) == record, error)
        return record
    except (KeyError, TypeError):
        raise ValueError(error) from None


def _authored(inputs, collection, record, event_type):
    keys = {'external_reviews': 'external_review', 'external_decisions': 'external_decision',
            'external_questions': 'external_question'}
    _native(inputs, collection, record, event_type, 'record_id')
    body = {key: value for key, value in record.items() if key != 'id'}
    _require(record['id'] == _identity(inputs.project, body), keys[collection] + '_record_invalid')
    return record


def evidence_records(snapshot):
    inputs = _Inputs(snapshot)
    records = inputs.state.get('external_evidence', {})
    _require(type(records) is dict, 'external_evidence_collection_invalid')
    ordered = []
    for _, old in inputs.history:
        if old['events'][-1]['type'] == 'external_evidence_imported':
            identity = old['events'][-1]['payload'].get('record_id')
            if identity in records and identity not in {item['id'] for item in ordered}:
                ordered.append(records[identity])
    _require(len(ordered) == len(records), 'external_evidence_native_invalid')
    prior_by_qa = {}
    for record in ordered:
        _native(inputs, 'external_evidence', record, 'external_evidence_imported', 'record_id')
        raw = inputs.objects.get(record.get('sha256'))
        _require(type(raw) is bytes and store._hash(raw) == record['sha256'], 'external_evidence_bytes_invalid')
        parsed = parse_atlas_qa(raw)
        expected = _evidence_record(inputs, parsed, record['filename'], record['producer_id'], record['previous_ref'], len(raw))
        _require(expected == record, 'external_evidence_record_invalid')
        previous = prior_by_qa.get(record['atlas_qa_id'])
        expected_ref = None if previous is None else _record_ref_at(inputs, 'external_evidence', previous)
        _require(record['previous_ref'] == expected_ref, 'external_evidence_version_invalid')
        prior_by_qa[record['atlas_qa_id']] = record
    return ordered


def _evidence_record(inputs, parsed, filename, producer_id, previous_ref, byte_count):
    return _make(inputs.project, dict(producer_id=producer_id, content_origin=inputs.state['content_origin'],
        provenance_status='declared_only', atlas_qa_id=parsed['id'], filename=filename,
        sha256=parsed['file_sha256'], byte_count=byte_count, previous_ref=deepcopy(previous_ref),
        qa=deepcopy(parsed)))


def import_evidence(snapshot, payload):
    _require(type(payload) is dict and set(payload) == _IMPORT_FIELDS
             and _text(payload['filename']) and _text(payload['producer_id'])
             and type(payload['sha256']) is str, 'external_evidence_import_invalid')
    try:
        data = base64.b64decode(payload['content_base64'], validate=True)
    except (ValueError, binascii.Error, TypeError):
        raise ValueError('external_evidence_bytes_invalid') from None
    _require(store._is_digest(payload['sha256']) and store._hash(data) == payload['sha256'],
             'external_evidence_hash_mismatch')
    parsed = parse_atlas_qa(data)
    inputs = _Inputs(snapshot)
    records = {r['id']: deepcopy(r) for r in evidence_records(snapshot)}
    same = [r for r in records.values() if r['atlas_qa_id'] == parsed['id']]
    existing = next((r for r in same if r['sha256'] == payload['sha256']), None)
    objects = {}
    if existing is None:
        previous = _record_ref_at(inputs, 'external_evidence', same[-1]) if same else None
        record = _evidence_record(inputs, parsed, payload['filename'], payload['producer_id'], previous, len(data))
        records[record['id']] = record
        objects[record['id']] = store._canonical(record)
        objects['external/raw/' + payload['sha256']] = data
    else:
        record = existing
    return {'state_patch': {'external_evidence': records}, 'object_inputs': objects,
            'event': {**store._VERSION, 'type': 'external_evidence_imported', 'payload': {'record_id': record['id']}}}


def _question_ref(inputs, ref):
    native_questions = [r for _, old in inputs.history for r in old['state'].get('m1_node_revisions', {}).values()
                        if r.get('node') == 'questions']
    try:
        return _resolve_record(inputs, ref, 'external_evidence', 'external_review_question_invalid')
    except ValueError:
        pass
    try:
        _References(inputs).resolve(ref)
        data = inputs.objects[ref['sha256']]
        record = next(item for item in native_questions if store._canonical(item) == data)
        from .m1_nodes import _native
        _native(inputs, 'm1_node_revisions', record, 'm1_node_registered',
                dict(node=record['node'], revision_id=record['id'], attempt=record['attempt']))
        return record
    except (ValueError, KeyError, StopIteration, TypeError):
        raise ValueError('external_review_question_invalid') from None


def record_review(snapshot, payload):
    _require(type(payload) is dict and set(payload) == _REVIEW_FIELDS
             and type(payload.get('status')) is str
             and payload['status'] in ('use', 'limited', 'hold', 'exclude')
             and _texts(payload['allowed_uses']) and _texts(payload['held_uses'])
             and _texts(payload['limitations']) and _text(payload['rationale']) and _text(payload['producer_id']),
             'external_review_invalid')
    _require(bool(payload['allowed_uses']) == (payload['status'] in ('use', 'limited'))
             and (payload['status'] not in ('hold', 'exclude') or bool(payload['held_uses'])),
             'external_review_uses_invalid')
    inputs = _Inputs(snapshot)
    valid_evidence = evidence_records(snapshot)
    evidence = _resolve_record(inputs, payload['evidence_ref'], 'external_evidence', 'external_review_evidence_invalid')
    _require(any(evidence == item for item in valid_evidence), 'external_review_evidence_invalid')
    _question_ref(inputs, payload['question_ref'])
    record = _make(inputs.project, dict(content_origin=inputs.state['content_origin'], provenance_status='declared_only',
        **deepcopy(payload)))
    records = {**inputs.state.get('external_reviews', {}), record['id']: record}
    return {'state_patch': {'external_reviews': records}, 'object_inputs': {record['id']: store._canonical(record)},
            'event': {**store._VERSION, 'type': 'external_review_recorded', 'payload': {'record_id': record['id']}}}


def record_decision(snapshot, payload):
    _require(type(payload) is dict and set(payload) == _DECISION_FIELDS
             and all(_text(payload[k]) for k in ('title', 'conclusion', 'rationale', 'producer_id'))
             and _texts(payload['limitations']) and type(payload['submission_refs']) is list
             and (payload['prior_ref'] is None or type(payload['prior_ref']) is dict), 'external_decision_invalid')
    inputs = _Inputs(snapshot)
    review = _resolve_record(inputs, payload['review_ref'], 'external_reviews', 'external_decision_review_invalid')
    _authored(inputs, 'external_reviews', review, 'external_review_recorded')
    if payload['prior_ref'] is not None:
        prior = _resolve_record(inputs, payload['prior_ref'], 'external_decisions', 'external_decision_prior_invalid')
        _authored(inputs, 'external_decisions', prior, 'external_decision_recorded')
    disclosed = {}
    for council in inputs.state.get('councils', {}).values():
        if _session(inputs, council)['input_binding'] == payload['review_ref']:
            for item in _disclosed(inputs, council, _submissions(inputs, council))['final']:
                disclosed[store._canonical(item['submission_ref'])] = item['submission']
    for ref in payload['submission_refs']:
        _require(store._canonical(ref) in disclosed, 'external_decision_submission_invalid')
    status = 'council_final' if payload['submission_refs'] else 'coordinator_only'
    record = _make(inputs.project, dict(content_origin=inputs.state['content_origin'], provenance_status='declared_only',
        review_status=status, **deepcopy(payload)))
    return {'state_patch': {'external_decisions': {**inputs.state.get('external_decisions', {}), record['id']: record}},
            'object_inputs': {record['id']: store._canonical(record)},
            'event': {**store._VERSION, 'type': 'external_decision_recorded', 'payload': {'record_id': record['id']}}}


def record_question(snapshot, payload):
    _require(type(payload) is dict and set(payload) == _QUESTION_FIELDS
             and all(_text(payload[k]) for k in _QUESTION_FIELDS - {'decision_ref'}), 'external_question_invalid')
    inputs = _Inputs(snapshot)
    decision = _resolve_record(inputs, payload['decision_ref'], 'external_decisions', 'external_question_decision_invalid')
    _authored(inputs, 'external_decisions', decision, 'external_decision_recorded')
    record = _make(inputs.project, dict(content_origin=inputs.state['content_origin'], provenance_status='declared_only',
        **deepcopy(payload)))
    return {'state_patch': {'external_questions': {**inputs.state.get('external_questions', {}), record['id']: record}},
            'object_inputs': {record['id']: store._canonical(record)},
            'event': {**store._VERSION, 'type': 'external_question_recorded', 'payload': {'record_id': record['id']}}}
