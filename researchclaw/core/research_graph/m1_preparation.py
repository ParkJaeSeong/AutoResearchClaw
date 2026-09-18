"""Immutable preparation declarations and typed source-backed preparation checks.

Original B5a drafts retain their exact bytes and confer no readiness.
"""
from copy import deepcopy

from . import store
from .contracts import _REF
from .councils import _record_ref, _valid
from .external_evidence import _authored, _make, _resolve_record, evidence_records
from .issues import _Inputs, _require
from .m1_external_inputs import external_evidence, uses_external
from .m1_nodes import current_node
from .m1_preparation_verification import validation_scope

COLLECTION = 'm1_preparations'
OPERATION = 'm1.preparation.register'
EVENT = 'm1_preparation_registered'
CATEGORIES = ('design_analysis', 'data_lineage', 'material', 'manufacturing',
              'measurement', 'repetition', 'resources_permissions')
_ITEM = dict(status=('enum', ('missing', 'verified', 'not_applicable')), reason='text',
             owner_id='uuid', verification_refs=('array', _REF))
_PAYLOAD = dict(review_ref=_REF, decision_refs=dict(design=_REF, data_lineage=_REF),
    items={category: _ITEM for category in CATEGORIES}, previous_ref=('nullable', _REF),
    revision_reason=('nullable', 'text'), producer_id='text')


@validation_scope
def _check(snapshot, payload):
    _require(_valid(_PAYLOAD, payload), 'preparation_payload_invalid')
    inputs = _Inputs(snapshot)
    try:
        review, ref = current_node(inputs, 'review')
        _require(ref == payload['review_ref'] and uses_external(review), 'preparation_review_invalid')
        external_evidence(snapshot, review)
        latest = {r['atlas_qa_id']: r for r in evidence_records(snapshot)}
        for decision_ref in payload['decision_refs'].values():
            decision = _resolve_record(inputs, decision_ref, 'external_decisions', 'preparation_decision_invalid', current=True)
            _authored(inputs, 'external_decisions', decision, 'external_decision_recorded')
            _require(decision_ref == _record_ref(inputs, 'external_decisions', decision), 'preparation_decision_invalid')
            for candidate in inputs.state.get('external_decisions', {}).values():
                _authored(inputs, 'external_decisions', candidate, 'external_decision_recorded')
                prior = candidate['prior_ref']
                if prior is not None:
                    predecessor = _resolve_record(inputs, prior, 'external_decisions', 'preparation_decision_invalid', current=True)
                    _require(predecessor != decision, 'preparation_decision_superseded')
            source_review = _resolve_record(inputs, decision['review_ref'], 'external_reviews', 'preparation_decision_invalid', current=True)
            _authored(inputs, 'external_reviews', source_review, 'external_review_recorded')
            evidence = _resolve_record(inputs, source_review['evidence_ref'], 'external_evidence', 'preparation_decision_invalid', current=True)
            _require(latest.get(evidence['atlas_qa_id']) == evidence, 'preparation_decision_qa_updated')
        checked_records = None
        for category, item in payload['items'].items():
            owner = inputs.assignment(item['owner_id'])
            _require(owner['role'] == 'owner' and owner['milestone'] == 'M1', 'preparation_owner_invalid')
            if item['status'] == 'verified' or item['verification_refs']:
                from .m1_preparation_verification import check_item, typed_records, EVIDENCE, VERIFICATIONS
                _require(item['status'] != 'missing', 'preparation_missing_has_verification')
                if checked_records is None:
                    checked_records = (typed_records(snapshot, EVIDENCE), typed_records(snapshot, VERIFICATIONS))
                check_item(snapshot, payload, category, item, checked_records)
    except ValueError as error:
        if str(error).startswith('preparation_'):
            raise
        raise ValueError('preparation_inputs_invalid') from error


def _previous(inputs, payload, records):
    previous = payload['previous_ref']
    if previous is None:
        _require(payload['revision_reason'] is None and not records, 'preparation_previous_required')
        return
    _require(payload['revision_reason'] is not None, 'preparation_previous_reason_required')
    record = _resolve_record(inputs, previous, COLLECTION, 'preparation_previous_invalid', current=True)
    _require(record in records and previous == _record_ref(inputs, COLLECTION, record)
             and not any(r['previous_ref'] == previous for r in records), 'preparation_previous_invalid')


@validation_scope
def preparation_records(snapshot):
    """Replay original commands at their ancestors, preserving obsolete drafts."""
    inputs = _Inputs(snapshot)
    declared = inputs.state.get(COLLECTION, {})
    _require(type(declared) is dict, 'preparation_collection_invalid')
    records = []
    for index, (_, old) in enumerate(inputs.history):
        event = old['events'][-1]
        if event['type'] != EVENT:
            continue
        identity = event['payload'].get('record_id')
        record = declared.get(identity)
        _require(record is not None and old['state'].get(COLLECTION, {}).get(identity) == record
                 and identity not in {r['id'] for r in records}, 'preparation_native_invalid')
        payload = {key: record[key] for key in _PAYLOAD if key in record}
        expected = _make(inputs.project, dict(content_origin=inputs.state['content_origin'],
                    provenance_status='declared_only', **payload))
        _require(index > 0 and record == expected, 'preparation_record_invalid')
        fingerprint = store._hash(store._canonical(dict(operation=OPERATION, payload=payload)))
        _require(event['payload'] == dict(record_id=identity, _command_request=fingerprint), 'preparation_native_invalid')
        head, commit = inputs.history[index - 1]
        historical = {**store._receipt(head, commit), '_issue_context':
            dict(history=inputs.history[:index], objects=inputs.objects)}
        _check(historical, payload)
        _previous(_Inputs(historical), payload, records)
        data = store._canonical(record)
        digest = store._hash(data)
        _require(old['object_inputs'].get(identity) == digest and inputs.objects.get(digest) == data,
                 'preparation_object_invalid')
        records.append(record)
    _require(len(records) == len(declared), 'preparation_native_invalid')
    return records


@validation_scope
def register_preparation(snapshot, payload):
    _check(snapshot, payload)
    inputs = _Inputs(snapshot)
    records = preparation_records(snapshot)
    _previous(inputs, payload, records)
    record = _make(inputs.project, dict(content_origin=inputs.state['content_origin'],
                   provenance_status='declared_only', **deepcopy(payload)))
    return dict(state_patch={COLLECTION: {**inputs.state.get(COLLECTION, {}), record['id']: record}},
        event={**store._VERSION, 'type': EVENT, 'payload': {'record_id': record['id']}},
        object_inputs={record['id']: store._canonical(record)})


@validation_scope
def preparation_status(snapshot, record):
    supported = all(item['status'] != 'missing' and item['verification_refs'] for item in record['items'].values())
    reasons = [] if supported else ['preparation_draft_only']
    current = True
    try:
        _check(snapshot, {key: record[key] for key in _PAYLOAD})
    except ValueError as error:
        current = False
        reasons.append(str(error))
    from .m1_nodes import review_node
    try:
        review = review_node(snapshot, 'review')
    except ValueError as error:
        review = dict(ready=False, reason_codes=[str(error)])
    missing = [category for category in CATEGORIES if record['items'][category]['status'] == 'missing']
    if missing:
        reasons.append('preparation_items_missing')
    if any(item['status'] == 'not_applicable' and not item['verification_refs'] for item in record['items'].values()):
        reasons.append('preparation_verification_required')
    real = record['content_origin'] == 'real'
    if supported and not real:
        reasons.append('preparation_synthetic_evidence')
    return dict(current=current, preparation_ready=bool(current and supported and real), missing_items=missing,
                reason_codes=reasons, external_handoff_supported=True,
                review_ready=review['ready'], review_reason_codes=review['reason_codes'])


@validation_scope
def project_preparations(snapshot, public):
    from .m1_preparation_verification import typed_records, EVIDENCE, VERIFICATIONS
    typed_records(snapshot, EVIDENCE)
    typed_records(snapshot, VERIFICATIONS)
    rows = []
    records = preparation_records(snapshot)
    for record in records:
        entry = public.entry(COLLECTION, record)
        if entry is not None:
            entry.update(preparation_status(snapshot, record))
            entry['superseded'] = any(r['previous_ref'] == entry['ref'] for r in records)
            rows.append(entry)
    return rows
