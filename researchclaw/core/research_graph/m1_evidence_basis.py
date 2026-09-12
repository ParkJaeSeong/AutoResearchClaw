"""Question-bound external evidence, without scientific or milestone authority."""
from copy import deepcopy
import json

from . import store
from .contracts import _REF
from .councils import _valid
from .councils import _record_ref
from .external_evidence import _make, _authored, _resolve_record, evidence_records
from .issues import _Inputs, _require
from .dependencies import _node
from .m1_nodes import current_node

COLLECTION = 'm1_evidence_bases'
OPERATION = 'm1.evidence_basis.register'
EVENT = 'm1_evidence_basis_registered'
_TEXTS = ('array', 'text')
_CLAIM = dict(claim_id='text', statement='text', evidence_ref=_REF, review_ref=_REF,
    basis_kind=('enum', ('atlas_answer', 'pilot_inference')), qa_excerpt='text', rationale='text',
    intended_use='text', limitations=_TEXTS)
_PAYLOAD = dict(question_ref=_REF, question_text='text', review_refs=('array', _REF),
    claims=('array', _CLAIM), coverage=dict(covered='text', missing='text', decision_impact='text'),
    limitations=_TEXTS, previous_ref=('nullable', _REF), revision_reason=('nullable', 'text'), producer_id='text')


def _check(snapshot, payload):
    _require(_valid(_PAYLOAD, payload) and payload['claims'] and payload['review_refs'], 'evidence_basis_invalid')
    _require(len({r['claim_id'] for r in payload['claims']}) == len(payload['claims']), 'evidence_basis_claim_duplicate')
    keys = [store._canonical(r) for r in payload['review_refs']]
    _require(len(keys) == len(set(keys)), 'evidence_basis_review_duplicate')
    inputs = _Inputs(snapshot)
    try:
        question, ref = current_node(inputs, 'questions')
        _require(ref == payload['question_ref'], 'evidence_basis_question_updated')
        _require(payload['question_text'] in [r['question'] for r in question['content']['questions']],
                 'evidence_basis_question_invalid')
        latest = {r['atlas_qa_id']: r for r in evidence_records(snapshot)}
        reviews = {}
        for ref in payload['review_refs']:
            review = _resolve_record(inputs, ref, 'external_reviews', 'evidence_basis_review_invalid', current=True)
            _authored(inputs, 'external_reviews', review, 'external_review_recorded')
            _require(review['status'] in ('use', 'limited'), 'evidence_basis_use_not_allowed')
            reviews[store._canonical(ref)] = review
        for claim in payload['claims']:
            review = reviews.get(store._canonical(claim['review_ref']))
            _require(review is not None and review['evidence_ref'] == claim['evidence_ref'], 'evidence_basis_review_invalid')
            evidence = _resolve_record(inputs, claim['evidence_ref'], 'external_evidence', 'evidence_basis_evidence_invalid', current=True)
            _require(latest.get(evidence['atlas_qa_id']) == evidence, 'evidence_basis_qa_updated')
            _require(claim['intended_use'] in review['allowed_uses'], 'evidence_basis_use_not_allowed')
            _require(claim['qa_excerpt'] in evidence['qa']['answer'], 'evidence_basis_excerpt_invalid')
        _require(set(keys) == {store._canonical(c['review_ref']) for c in payload['claims']}, 'evidence_basis_unused_review')
    except ValueError as error:
        if str(error).startswith('evidence_basis_'):
            raise
        raise ValueError('evidence_basis_reference_invalid') from error


def _claim_objects(record):
    return {f"m1/evidence_basis/{record['id']}/claims/{index}":
            store._canonical(dict(project_id=record['project_id'], basis_id=record['id'], **claim))
            for index, claim in enumerate(record['claims'])}


def _previous(inputs, payload, records):
    previous = payload['previous_ref']
    if previous is None:
        _require(payload['revision_reason'] is None and not any(
            r['question_ref'] == payload['question_ref'] and r['question_text'] == payload['question_text']
            for r in records), 'evidence_basis_previous_required')
        return
    _require(payload['revision_reason'] is not None, 'evidence_basis_previous_reason_required')
    old = _resolve_record(inputs, previous, COLLECTION, 'evidence_basis_previous_invalid', current=True)
    _require(old in records and previous == _record_ref(inputs, COLLECTION, old)
             and not any(r['previous_ref'] == previous for r in records), 'evidence_basis_previous_invalid')


def basis_records(snapshot):
    """Verify original registration in its historical context, never against new QA."""
    inputs = _Inputs(snapshot)
    declared = inputs.state.get(COLLECTION, {})
    _require(type(declared) is dict, 'evidence_basis_collection_invalid')
    records = []
    for index, (head, old) in enumerate(inputs.history):
        event = old['events'][-1]
        if event['type'] != EVENT:
            continue
        identity = event['payload'].get('record_id')
        record = declared.get(identity)
        _require(record is not None and old['state'].get(COLLECTION, {}).get(identity) == record,
                 'evidence_basis_native_invalid')
        _require(identity not in {r['id'] for r in records}, 'evidence_basis_native_invalid')
        payload = {k: record[k] for k in _PAYLOAD if k in record}
        expected = _make(inputs.project, dict(content_origin=inputs.state['content_origin'],
                    provenance_status='declared_only', **payload))
        _require(record == expected and index > 0, 'evidence_basis_record_invalid')
        fingerprint = store._hash(store._canonical(dict(operation=OPERATION, payload=payload)))
        _require(event['payload'] == dict(record_id=identity, _command_request=fingerprint), 'evidence_basis_native_invalid')
        previous_head, previous_commit = inputs.history[index - 1]
        historical = {**store._receipt(previous_head, previous_commit), '_issue_context':
            dict(history=inputs.history[:index], objects=inputs.objects)}
        _check(historical, payload)
        _previous(_Inputs(historical), payload, records)
        for alias, data in {identity: store._canonical(record), **_claim_objects(record)}.items():
            digest = store._hash(data)
            _require(old['object_inputs'].get(alias) == digest and inputs.objects.get(digest) == data,
                     'evidence_basis_object_invalid')
        records.append(record)
    _require(len(records) == len(declared), 'evidence_basis_native_invalid')
    return records


def register_basis(snapshot, payload):
    _check(snapshot, payload)
    inputs = _Inputs(snapshot)
    records = basis_records(snapshot)
    _previous(inputs, payload, records)
    record = _make(inputs.project, dict(content_origin=inputs.state['content_origin'],
                   provenance_status='declared_only', **deepcopy(payload)))
    return dict(state_patch={COLLECTION: {**inputs.state.get(COLLECTION, {}), record['id']: record}},
        event={**store._VERSION, 'type': EVENT, 'payload': {'record_id': record['id']}},
        object_inputs={record['id']: store._canonical(record), **_claim_objects(record)})


def basis_status(snapshot, record):
    reasons = []
    try:
        _check(snapshot, {k: record[k] for k in _PAYLOAD})
    except ValueError as error:
        reasons.append(str(error))
    return dict(current=not reasons, reason_codes=reasons)


def project_bases(snapshot, public):
    """Additive public entries; current means inputs current, not research ready."""
    inputs = _Inputs(snapshot)
    records = basis_records(snapshot)
    rows = []
    for record in records:
        entry = public.entry(COLLECTION, record)
        if entry is None:
            continue
        entry.update(basis_status(snapshot, record))
        entry['superseded'] = any(r['previous_ref'] == entry['ref'] for r in records)
        entry['claims'] = []
        for alias, data in _claim_objects(record).items():
            ref = {**entry['ref'], 'artifact_id': alias, 'sha256': store._hash(data)}
            admitted = public.admit(ref)
            if admitted is not None:
                entry['claims'].append(dict(record=json.loads(data), ref=ref, artifact_id=admitted))
        selected = {_node(r) for r in record['review_refs']}
        evidence_refs = {_node(c['evidence_ref']) for c in record['claims']}
        entry['review_candidates'] = []
        for review in inputs.state.get('external_reviews', {}).values():
            if _node(review['evidence_ref']) in evidence_refs:
                _authored(inputs, 'external_reviews', review, 'external_review_recorded')
                ref = _record_ref(inputs, 'external_reviews', review)
                if _node(ref) not in selected and public.admit(ref) is not None:
                    entry['review_candidates'].append(ref)
        rows.append(entry)
    return rows
