"""Native source acquisition, independent of selection and evidence readiness.

Bytes and supplied hashes are compared; authorship, reading scope and source
identity remain declarations. No capture grants approval or resolves an issue.
"""
import base64
import binascii
from copy import deepcopy
from urllib.parse import urlsplit
from uuid import UUID, uuid5

from . import store
from .issues import _Inputs, _require

_FIELDS = {'source_key', 'source_version', 'access_url', 'access_status', 'filename',
           'reading_scope', 'limitations', 'producer_id', 'sha256', 'content_base64'}


def _decode(row):
    _require(type(row) is dict and set(row) == _FIELDS, 'source_capture_invalid')
    _require(all(type(row[k]) is str and row[k].strip() for k in _FIELDS - {'limitations'}),
             'source_capture_invalid')
    _require(type(row['limitations']) is list and all(type(v) is str and v.strip() for v in row['limitations']),
             'source_capture_invalid')
    try:
        url = urlsplit(row['access_url'])
        _require(url.scheme in ('https', 'http') and bool(url.hostname) and not url.username and not url.password,
                 'source_capture_url_invalid')
    except ValueError:
        raise ValueError('source_capture_url_invalid') from None
    _require(row['access_status'] in ('metadata_only', 'abstract', 'full_text'), 'source_capture_access_invalid')
    _require(row['access_status'] == 'full_text' or bool(row['limitations']), 'source_capture_limitation_required')
    try:
        data = base64.b64decode(row['content_base64'], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('source_capture_bytes_invalid') from None
    _require(bool(data) and store._hash(data) == row['sha256'], 'source_capture_hash_mismatch')
    return data


def _record(snapshot, row, data):
    record = {**store._VERSION, 'project_id': snapshot['state']['project_id'],
              'content_origin': snapshot['state']['content_origin'], 'provenance_status': 'declared_only',
              **{k: deepcopy(v) for k, v in row.items() if k != 'content_base64'}, 'byte_count': len(data)}
    record['id'] = str(uuid5(UUID(record['project_id']), store._hash(store._canonical(record))))
    return record


def captured_records(snapshot):
    """Only immutable, natively produced captures can enter the public view."""
    inputs = _Inputs(snapshot)
    records = inputs.state.get('source_captures', {})
    _require(type(records) is dict, 'source_capture_collection_invalid')
    for identity in records:
        record = inputs.registered('source_captures', identity)
        first = next(old for _, old in inputs.history if identity in old['state'].get('source_captures', {}))
        event = first['events'][-1]
        _require(first['state']['source_captures'][identity] == record
                 and event['type'] == 'source_captured'
                 and identity in event['payload'].get('capture_ids', []), 'source_capture_native_invalid')
        data = inputs.objects.get(record.get('sha256'))
        _require(type(data) is bytes, 'source_capture_bytes_invalid')
        row = {k: record[k] for k in _FIELDS - {'content_base64'}}
        row['content_base64'] = base64.b64encode(data).decode()
        _decode(row)
        _require(_record(snapshot, row, data) == record, 'source_capture_record_invalid')
    return list(records.values())


def capture_sources(snapshot, payload):
    _require(type(payload) is dict and set(payload) == {'captures'}
             and type(payload['captures']) is list and bool(payload['captures']), 'source_capture_invalid')
    records = {r['id']: deepcopy(r) for r in captured_records(snapshot)}
    objects, identities = {}, []
    for row in payload['captures']:
        data = _decode(row)
        record = _record(snapshot, row, data)
        identity = record['id']
        if identity not in records:
            records[identity] = record
            objects[identity] = store._canonical(record)
            objects['m1/intake/blobs/' + record['sha256']] = data
        identities.append(identity)
    return dict(state_patch={'source_captures': records}, object_inputs=objects,
                event={**store._VERSION, 'type': 'source_captured',
                       'payload': {'capture_ids': list(dict.fromkeys(identities))}})
