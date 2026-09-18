"""Captured item sources and independent declared-actor checks; no identity authentication."""
import base64
import binascii
from copy import deepcopy
from contextvars import ContextVar
from functools import wraps

from . import store
from .contracts import _REF
from .councils import _record_ref, _valid
from .external_evidence import _make, _resolve_record
from .issues import _Inputs, _require

EVIDENCE = 'm1_preparation_evidence'
VERIFICATIONS = 'm1_preparation_verifications'
CRITERIA = {
    'design_analysis': ('variables_controls', 'analysis', 'success_stop'),
    'data_lineage': ('source_version', 'transformations', 'tracking'),
    'material': ('identity', 'availability', 'conditions'),
    'manufacturing': ('process', 'equipment', 'operator'),
    'measurement': ('method_units', 'calibration', 'recording'),
    'repetition': ('replicates', 'independence', 'analysis'),
    'resources_permissions': ('authority', 'operator', 'budget', 'schedule', 'safety'),
}
_CAPTURE = dict(review_ref=_REF, decision_refs=dict(design=_REF, data_lineage=_REF),
    category=('enum', tuple(CRITERIA)), owner_id='uuid', disposition=('enum', ('verified', 'not_applicable')),
    source_kind=('enum', ('document', 'instrument_record', 'data_manifest', 'code_environment', 'permission_record')),
    source_locator='text', source_version='text', content_base64='text', sha256='text', producer_id='text')
_VERIFY = dict(evidence_ref=_REF, reviewer_id='uuid', excerpt='text', rationale='text',
               outcome=('enum', ('confirmed', 'rejected')), checks='any', producer_id='text')
_SPECS = {EVIDENCE: (_CAPTURE, 'm1.preparation.evidence.capture', 'm1_preparation_evidence_captured'),
          VERIFICATIONS: (_VERIFY, 'm1.preparation.evidence.verify', 'm1_preparation_evidence_verified')}


_REPLAY = ContextVar('preparation_validation_scope', default=None)


def validation_scope(function):
    """Share replay results only during one synchronous policy invocation."""
    @wraps(function)
    def scoped(*args, **kwargs):
        if _REPLAY.get() is not None:
            return function(*args, **kwargs)
        token = _REPLAY.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _REPLAY.reset(token)
    return scoped


def _binding(snapshot, payload):
    from .m1_preparation import CATEGORIES, _check
    memo = _REPLAY.get()
    key = ('binding', snapshot['id'], store._canonical({key: payload[key] for key in ('review_ref', 'decision_refs', 'owner_id')}))
    if memo is not None and key in memo:
        return
    _check(snapshot, dict(review_ref=payload['review_ref'], decision_refs=payload['decision_refs'],
        items={key: dict(status='missing', reason='Evidence binding check', owner_id=payload['owner_id'],
                        verification_refs=[]) for key in CATEGORIES},
        previous_ref=None, revision_reason=None, producer_id=payload['producer_id']))
    if memo is not None:
        memo[key] = True


def _capture(snapshot, payload):
    _require(_valid(_CAPTURE, payload), 'preparation_evidence_payload_invalid')
    _binding(snapshot, payload)
    inputs = _Inputs(snapshot)
    owner = inputs.assignment(payload['owner_id'])
    _require(payload['producer_id'] == owner['actor_id'], 'preparation_evidence_owner_invalid')
    try:
        raw = base64.b64decode(payload['content_base64'], validate=True)
        text = raw.decode('utf-8')
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise ValueError('preparation_evidence_bytes_invalid') from None
    _require(text.strip() and store._hash(raw) == payload['sha256'], 'preparation_evidence_bytes_invalid')
    return raw


def _verify(snapshot, payload, evidence_records=None):
    spec = {**_VERIFY, 'checks': {}}
    # Category-specific closed checklist is validated after resolving the source.
    _require(type(payload) is dict and set(payload) == set(_VERIFY)
             and _valid({k:v for k,v in spec.items() if k != 'checks'},
                        {k:v for k,v in payload.items() if k != 'checks'}), 'preparation_verification_payload_invalid')
    inputs = _Inputs(snapshot)
    records = typed_records(snapshot, EVIDENCE) if evidence_records is None else evidence_records
    evidence = _resolve_record(inputs, payload['evidence_ref'], EVIDENCE, 'preparation_evidence_ref_invalid', current=True)
    _require(evidence in records and payload['evidence_ref'] == _record_ref(inputs, EVIDENCE, evidence),
             'preparation_evidence_ref_invalid')
    binding = ('review_ref', 'decision_refs', 'category', 'owner_id')
    current = [row for row in records if all(row[key] == evidence[key] for key in binding)]
    _require(current and current[-1] == evidence, 'preparation_evidence_superseded')
    raw = _capture(snapshot, {key: evidence[key] for key in _CAPTURE})
    owner = inputs.assignment(evidence['owner_id'])
    reviewer = inputs.assignment(payload['reviewer_id'])
    _require(reviewer['role'] == 'resolver' and reviewer['milestone'] == 'M1'
             and reviewer['actor_id'] != owner['actor_id'] and payload['producer_id'] == reviewer['actor_id'],
             'preparation_verification_actor_invalid')
    text = raw.decode('utf-8')
    _require(payload['excerpt'] in text, 'preparation_verification_excerpt_invalid')
    keys = ('scope_exemption',) if evidence['disposition'] == 'not_applicable' else CRITERIA[evidence['category']]
    _require(_valid({key: dict(result=('enum', ('pass', 'fail')), excerpt='text') for key in keys}, payload['checks']),
             'preparation_verification_checks_invalid')
    _require(all(check['excerpt'] in text for check in payload['checks'].values()), 'preparation_verification_excerpt_invalid')
    _require(payload['outcome'] != 'confirmed' or all(check['result'] == 'pass' for check in payload['checks'].values()),
             'preparation_verification_outcome_invalid')
    return evidence


@validation_scope
def typed_records(snapshot, collection):
    """Recompute native commands at original ancestors, including their source bytes."""
    memo = _REPLAY.get()
    cache_key = ('records', snapshot['id'], collection)
    if cache_key in memo:
        return memo[cache_key]
    inputs = _Inputs(snapshot)
    spec, operation, event_type = _SPECS[collection]
    declared = inputs.state.get(collection, {})
    _require(type(declared) is dict, 'preparation_evidence_collection_invalid')
    records = []
    for index, (_, old) in enumerate(inputs.history):
        event = old['events'][-1]
        if event['type'] != event_type:
            continue
        identity = event['payload'].get('record_id')
        record = declared.get(identity)
        _require(index > 0 and type(record) is dict and old['state'].get(collection, {}).get(identity) == record
                 and identity not in {r['id'] for r in records}, 'preparation_evidence_native_invalid')
        payload = {key: record[key] for key in spec if key in record}
        head, ancestor = inputs.history[index - 1]
        historical = {**store._receipt(head, ancestor), '_issue_context': dict(history=inputs.history[:index], objects=inputs.objects)}
        plan = _plan(historical, payload, collection)
        expected = plan['state_patch'][collection].get(identity)
        _require(expected is not None, 'preparation_evidence_native_invalid')
        fingerprint = store._hash(store._canonical(dict(operation=operation, payload=payload)))
        _require(record == expected and event['payload'] == dict(record_id=identity, _command_request=fingerprint),
                 'preparation_evidence_native_invalid')
        for alias, data in plan['object_inputs'].items():
            digest = store._hash(data)
            _require(old['object_inputs'].get(alias) == digest and inputs.objects.get(digest) == data,
                     'preparation_evidence_object_invalid')
        records.append(record)
    _require(len(records) == len(declared), 'preparation_evidence_native_invalid')
    memo[cache_key] = records
    return records


def _plan(snapshot, payload, collection):
    raw = _capture(snapshot, payload) if collection == EVIDENCE else None
    if collection == VERIFICATIONS:
        _verify(snapshot, payload)
    inputs = _Inputs(snapshot)
    record = _make(inputs.project, dict(content_origin=inputs.state['content_origin'],
                   provenance_status='declared_only', **deepcopy(payload)))
    _require(record['id'] not in inputs.state.get(collection, {}), 'preparation_evidence_already_registered')
    objects = {record['id']: store._canonical(record)}
    if raw is not None:
        objects['preparation/raw/' + payload['sha256']] = raw
    return dict(state_patch={collection: {**inputs.state.get(collection, {}), record['id']: record}},
                event={**store._VERSION, 'type': _SPECS[collection][2], 'payload': dict(record_id=record['id'])},
                object_inputs=objects)


@validation_scope
def capture_evidence(snapshot, payload):
    typed_records(snapshot, EVIDENCE)
    return _plan(snapshot, payload, EVIDENCE)


@validation_scope
def verify_evidence(snapshot, payload):
    typed_records(snapshot, VERIFICATIONS)
    return _plan(snapshot, payload, VERIFICATIONS)


def check_item(snapshot, payload, category, item, checked_records=None):
    inputs = _Inputs(snapshot)
    evidence_records, records = checked_records or (typed_records(snapshot, EVIDENCE), typed_records(snapshot, VERIFICATIONS))
    _require(bool(item['verification_refs']), 'preparation_verification_required')
    _require(len({store._canonical(ref) for ref in item['verification_refs']}) == len(item['verification_refs']),
             'preparation_verification_duplicate')
    for ref in item['verification_refs']:
        verification = _resolve_record(inputs, ref, VERIFICATIONS, 'preparation_verification_ref_invalid', current=True)
        _require(verification in records and ref == _record_ref(inputs, VERIFICATIONS, verification), 'preparation_verification_ref_invalid')
        latest = [row for row in records if row['evidence_ref'] == verification['evidence_ref']]
        _require(latest[-1] == verification, 'preparation_verification_superseded')
        evidence = _verify(snapshot, {key: verification[key] for key in _VERIFY}, evidence_records)
        _require(verification['outcome'] == 'confirmed' and evidence['category'] == category
                 and evidence['owner_id'] == item['owner_id'] and evidence['disposition'] == item['status']
                 and evidence['review_ref'] == payload['review_ref'] and evidence['decision_refs'] == payload['decision_refs'],
                 'preparation_verification_binding_invalid')
