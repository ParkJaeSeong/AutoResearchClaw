"""Documents/Atlas consumer workflow; transport injected, scientific state untouched."""
import hashlib
import json
import math
import re
from urllib.parse import quote

VERSION = 'pilot-documents-atlas/1.0'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def atlas_key(project, operation, key):
    return 'pilot-' + canonical_hash([project, operation, key])


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


class HandoffAdapter:
    def __init__(self, journal, documents, atlas):
        self.journal, self.documents, self.atlas = journal, documents, atlas

    def _atlas_info(self):
        info = self.atlas.request('GET', '/api/info')
        require(info.get('atlas_instance_id') == self.journal.identity['atlas_instance_id'], 'atlas_instance_mismatch')
        require(info.get('import_contract_version') == VERSION and 'documents_import_v1' in info.get('capabilities', []), 'atlas_capability_unavailable')

    def _envelope(self, value):
        require(value.get('ok') is True and value.get('contract_version') == VERSION and
                value.get('atlas_instance_id') == self.journal.identity['atlas_instance_id'], 'atlas_envelope_invalid')
        return value

    def _record(self, response, row):
        value = self._envelope(response)['import']
        p = row['atlas_payload']
        require(value.get('atlas_instance_id') == self.journal.identity['atlas_instance_id'] and
                value.get('consumer_id') == self.journal.identity['consumer_id'] and
                value.get('request_key') == p['request_key'] and value.get('payload') == p, 'atlas_request_mismatch')
        receipt = value.get('receipt_ref', {})
        require(receipt.get('import_id') == value.get('import_id') and isinstance(value.get('import_id'), str) and
                receipt.get('atlas_instance_id') == self.journal.identity['atlas_instance_id'] and
                receipt.get('operation') == 'documents.import' and receipt.get('request_key') == p['request_key'] and
                receipt.get('request_sha256') == canonical_hash({k:v for k,v in p.items() if k != 'request_key'}), 'atlas_receipt_invalid')
        previous = row.get('atlas_receipt')
        require(previous is None or previous == receipt, 'atlas_receipt_changed')
        require(type(value.get('updated_at')) in (int, float) and math.isfinite(value['updated_at']), 'atlas_timestamp_invalid')
        require(value.get('phase') in ('accepted','waiting_conversion','fetching','organizing','needs_attention','terminal'), 'atlas_phase_invalid')
        return value

    def advance(self):
        """Recover each saved Documents submission, then submit its fixed Atlas request."""
        self._atlas_info()
        errors = []
        for row in self.journal.pending():
            try:
                self._advance_one(row)
                self.journal.set_error(row['operation'], row['request_key'], None)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                code = str(exc)
                if not re.fullmatch('[a-zA-Z_]+', code):
                    code = 'handoff_connection_or_response_error'
                self.journal.set_error(row['operation'], row['request_key'], code)
                errors.append(exc)
        if errors:
            raise errors[0]

    def _advance_one(self, row):
        operation, key = row['operation'], row['request_key']
        info = self.documents.request('GET', '/api/integration/info')
        expected = row['atlas_request']['documents_service_ref']['instance_id']
        require(info.get('instance_id') == expected and info.get('contract_version') == VERSION, 'documents_instance_mismatch')
        require('document_handoff_v1' in info.get('capabilities', []), 'documents_capability_unavailable')
        if row['documents_receipt'] is None:
            # The transport may submit on an explicit RECEIPT_NOT_FOUND only.
            receipt = self.documents.recover_or_submit(row) if hasattr(self.documents, 'recover_or_submit') else self.documents.request(
                'GET', '/api/integration/receipts/' + quote(key, safe=''), params={'operation': operation})
            require(receipt.get('instance_id') == expected and receipt.get('contract_version') == VERSION and
                    receipt.get('submitted_by_consumer_id') == self.journal.identity['consumer_id'] and
                    receipt.get('retrieval_consumer_id') == row['documents_request']['retrieval_consumer_id'] and
                    receipt.get('config_revision') == row['documents_request']['config_revision'] and
                    isinstance(receipt.get('receipt_id'),str) and bool(receipt['receipt_id']) and digest(receipt.get('request_sha256')), 'documents_receipt_invalid')
            fixed = {k:v for k,v in receipt.items() if k not in ('result_ref','acknowledged_at')}
            self.journal.accept_documents(operation, key, fixed)
            row = next(r for r in self.journal.rows() if (r['operation'],r['request_key']) == (operation,key))
        if not row.get('atlas_payload'):
            receipt = row['documents_receipt']
            task = self.documents.request('GET', '/api/tasks/' + quote(receipt['task_id'], safe=''))
            require(task.get('instance_id') == expected and task.get('contract_version') == VERSION and task.get('id') == receipt['task_id'], 'documents_task_mismatch')
            # The supplier task's input_fingerprint is the package value, never request_sha256.
            package = task.get('package_fingerprint', task.get('input_fingerprint'))
            require(digest(package), 'documents_package_fingerprint_missing')
            require(task.get('file_hash') == row['atlas_request']['source']['sha256'], 'documents_source_mismatch')
            payload = dict(row['atlas_request'], contract_version=VERSION,
                request_key=atlas_key(self.journal.identity['project_id'], operation, key),
                consumer_id=self.journal.identity['consumer_id'], pilot_project_id=self.journal.identity['project_id'],
                task_id=receipt['task_id'], handoff_receipt_id=receipt['receipt_id'], package_fingerprint=package)
            for field in ('expected_result_ref','previous_import_ref','parent_task_id','root_task_id'):
                payload.setdefault(field, task.get(field) if field in ('parent_task_id','root_task_id') else None)
            payload['requested_indexes'] = sorted(payload['requested_indexes'])
            row['atlas_payload'] = self.journal.pin_payload(operation, key, payload)
        response = self.atlas.request('POST', '/api/document-imports', payload=row['atlas_payload'])
        record = self._record(response, row)
        self.journal.accept_atlas(operation, key, record['receipt_ref'])
        self.journal.observe(operation, key, self._snapshot(record))

    @staticmethod
    def _snapshot(record):
        return {k:record.get(k) for k in ('import_id','phase','outcome','updated_at','next_poll_at')}

    def poll(self):
        """One bounded observation cycle; caller schedules the next cycle after 60s."""
        self._atlas_info()
        rows = {r['atlas_receipt']['import_id']: r for r in self.journal.rows() if r.get('atlas_receipt') and r.get('atlas_payload')}
        for import_id,row in rows.items():
            record = self._record(self.atlas.request('GET', '/api/document-imports/' + quote(import_id,safe='')), row)
            self.journal.observe(row['operation'],row['request_key'],self._snapshot(record))
        cursor = self.journal.event_cursor()
        visited = set()
        cursor_reset = False
        while True:
            params = {'limit':50}
            if cursor is not None:params['cursor'] = cursor
            try:
                response = self._envelope(self.atlas.request('GET','/api/events',params=params))
            except ValueError as exc:
                if str(exc) == 'invalid_cursor' and cursor is not None and not cursor_reset:
                    cursor = None
                    cursor_reset = True
                    self.journal.save_event_cursor(None)
                    continue
                raise
            for event in response['events']:
                row = rows.get(event.get('import_id'))
                if row is None:
                    continue  # Another project owns this event; never acknowledge it here.
                self.journal.receive(event)
            cursor = response.get('next_cursor')
            # Save position only after this page's owned events are durable.
            self.journal.save_event_cursor(cursor)
            # Atlas retains a stream position even at an empty tail.
            if cursor is None or not response['events']:break
            require(isinstance(cursor,str) and cursor not in visited, 'atlas_cursor_invalid')
            visited.add(cursor)
        errors = []
        for event in self.journal.pending_events():
            row = rows[event['import_id']]
            try:
                self._process_event(event, row)
                self.journal.set_error(row['operation'], row['request_key'], None)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                code = str(exc)
                if not re.fullmatch('[a-zA-Z_]+', code):code = 'handoff_result_unavailable'
                self.journal.set_error(row['operation'], row['request_key'], code)
                errors.append(exc)
        pending = self.journal.pending_acks()
        if pending:
            for start in range(0,len(pending),50):
                ids = pending[start:start+50]
                response = self._envelope(self.atlas.request('POST','/api/events/ack',payload={'event_ids':ids}))
                require(set(response.get('acknowledged',[])) == set(ids), 'atlas_ack_invalid')
                self.journal.acknowledged(ids)
        if errors:
            raise errors[0]

    def _process_event(self, event, row):
        ref = event.get('result_ref')
        if ref is None:
            require(event.get('phase') == 'needs_attention', 'atlas_result_missing')
            self.journal.processed(event['event_id'], {'diagnostic':event})
            return
        record = self._record(self.atlas.request('GET','/api/document-imports/'+quote(event['import_id'],safe='')),row)
        result = record.get('result') or {}
        raw = result.get('record')
        require(isinstance(raw,dict) and digest(result.get('sha256')) and canonical_hash(raw) == result['sha256'] and
                ref.get('import_id') == event['import_id'] and ref.get('sha256') == result['sha256'] and raw.get('import_id') == event['import_id'] and
                record.get('phase') == event.get('phase') and record.get('outcome') == event.get('outcome'), 'atlas_result_mismatch')
        if event.get('outcome') in ('completed','partial'):
            require({'source_refs','extraction_refs','page_refs','read_scope','unresolved','index_status','ingest_job_ref','documents_result_ref'} <= raw.keys(), 'atlas_result_incomplete')
            doc = raw['documents_result_ref'];payload = row['atlas_payload']
            require(doc.get('instance_id') == payload['documents_service_ref']['instance_id'] and doc.get('task_id') == payload['task_id'] and digest(doc.get('manifest_sha256')) and bool(doc.get('result_revision')), 'documents_result_mismatch')
            require(payload.get('expected_result_ref') is None or payload['expected_result_ref'] == doc, 'documents_result_mismatch')
        self.journal.processed(event['event_id'], {'result':result})
