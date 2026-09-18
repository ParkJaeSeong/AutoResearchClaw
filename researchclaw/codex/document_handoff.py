"""Project-local durable handoff journal; never mutates scientific decisions.

Transport adapters must verify service receipts/results before handing them to
this store. Pending entries are replayable, not exclusive worker claims: remote
idempotency keys remain mandatory. No credentials or original bytes belong here.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class HandoffConflict(ValueError):
    """A fixed identity, request, or acknowledgement would be overwritten."""


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _same(old, new):
    if _json(old) != _json(new):
        raise HandoffConflict('Fixed handoff data does not match')


class HandoffJournal:
    def __init__(self, path, project_id, atlas_instance_id, consumer_id):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.identity = dict(project_id=project_id, atlas_instance_id=atlas_instance_id, consumer_id=consumer_id)
        if not all(isinstance(v, str) and v.strip() for v in self.identity.values()):
            raise ValueError('Nonempty project, instance and consumer IDs required')
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS cursors (name TEXT PRIMARY KEY, value TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS handoffs (operation TEXT, key TEXT, body TEXT NOT NULL, PRIMARY KEY(operation,key))')
            db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, import_id TEXT NOT NULL, sequence INTEGER NOT NULL, body TEXT NOT NULL, processed TEXT, acked INTEGER NOT NULL DEFAULT 0, UNIQUE(import_id,sequence))')
            row = db.execute('SELECT body FROM identity WHERE id=1').fetchone()
            if row:
                _same(json.loads(row[0]), self.identity)
            else:
                db.execute('INSERT INTO identity VALUES (1,?)', (_json(self.identity),))

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _row(db, operation, key):
        row = db.execute('SELECT body FROM handoffs WHERE operation=? AND key=?', (operation, key)).fetchone()
        if not row:
            raise HandoffConflict('Unknown handoff')
        return json.loads(row[0])

    @staticmethod
    def _save(db, row):
        db.execute('UPDATE handoffs SET body=? WHERE operation=? AND key=?',
                   (_json(row), row['operation'], row['request_key']))

    def enqueue(self, operation, key, documents_request, atlas_request):
        if operation not in ('convert.file', 'convert.jats') or not isinstance(key, str) or not key.strip():
            raise ValueError('Conversion operation and request key required')
        request = dict(operation=operation, request_key=key,
                       documents_request=documents_request, atlas_request=atlas_request)
        # Serialize before opening a transaction; caller mutations cannot change saved data.
        request = json.loads(_json(request))
        with self._db() as db:
            existing = db.execute('SELECT body FROM handoffs WHERE operation=? AND key=?', (operation, key)).fetchone()
            if existing:
                row = json.loads(existing[0])
                _same({k: row[k] for k in request}, request)
            else:
                row = dict(request, destination='documents', documents_receipt=None, atlas_receipt=None)
                db.execute('INSERT INTO handoffs VALUES (?,?,?)', (operation, key, _json(row)))
            return row

    def pending(self):
        with self._db() as db:
            rows = [json.loads(r[0]) for r in db.execute('SELECT body FROM handoffs ORDER BY rowid')]
        return [r for r in rows if r['destination'] is not None]

    def accept_documents(self, operation, key, receipt):
        if receipt.get('operation') != operation or receipt.get('request_key') != key or not receipt.get('task_id'):
            raise HandoffConflict('Documents receipt identity mismatch')
        with self._db() as db:
            row = self._row(db, operation, key)
            if row['documents_receipt'] is not None:
                _same(row['documents_receipt'], receipt)
                return
            row.update(documents_receipt=receipt, destination='atlas')
            self._save(db, row)

    def accept_atlas(self, operation, key, receipt):
        if not isinstance(receipt.get('import_id'), str) or not receipt['import_id']:
            raise HandoffConflict('Atlas import identity required')
        with self._db() as db:
            row = self._row(db, operation, key)
            if row['documents_receipt'] is None:
                raise HandoffConflict('Documents receipt must be saved first')
            if row['atlas_receipt'] is not None:
                _same(row['atlas_receipt'], receipt)
                return
            for other, in db.execute('SELECT body FROM handoffs'):
                previous = json.loads(other)['atlas_receipt']
                if previous and previous['import_id'] == receipt['import_id']:
                    raise HandoffConflict('Atlas import already belongs to another handoff')
            row.update(atlas_receipt=receipt, destination=None)
            self._save(db, row)

    def receive(self, event):
        event = {k: v for k, v in event.items() if k != 'acknowledged'}
        for name in ('atlas_instance_id', 'consumer_id'):
            if event.get(name) != self.identity[name]:
                raise HandoffConflict('Event service or consumer mismatch')
        if not isinstance(event.get('event_id'), str) or not event['event_id']:
            raise HandoffConflict('Event ID required')
        if type(event.get('sequence')) is not int or event['sequence'] < 0:
            raise HandoffConflict('Invalid event sequence')
        with self._db() as db:
            existing = db.execute('SELECT body FROM events WHERE id=?', (event['event_id'],)).fetchone()
            if existing:
                _same(json.loads(existing[0]), event)
                return
            known = False
            for body, in db.execute('SELECT body FROM handoffs'):
                row = json.loads(body)
                receipt = row['atlas_receipt']
                if receipt and receipt['import_id'] == event.get('import_id') and row.get('atlas_payload', {}).get('request_key', row['request_key']) == event.get('request_key'):
                    known = True
                    break
            if not known:
                raise HandoffConflict('Event does not belong to an accepted handoff')
            try:
                db.execute('INSERT INTO events (id,import_id,sequence,body) VALUES (?,?,?,?)',
                           (event['event_id'], event['import_id'], event['sequence'], _json(event)))
            except sqlite3.IntegrityError as exc:
                raise HandoffConflict('Event sequence conflict') from exc

    def pending_events(self):
        with self._db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM events WHERE processed IS NULL ORDER BY sequence')]

    def processed(self, event_id, result):
        if not isinstance(result, dict) or not result:
            raise ValueError('Durable processing result required')
        with self._db() as db:
            row = db.execute('SELECT processed FROM events WHERE id=?', (event_id,)).fetchone()
            if row is None:
                raise HandoffConflict('Unknown event')
            if row[0] is not None:
                _same(json.loads(row[0]), result)
                return
            db.execute('UPDATE events SET processed=? WHERE id=?', (_json(result), event_id))

    def pending_acks(self):
        with self._db() as db:
            return [r[0] for r in db.execute('SELECT id FROM events WHERE processed IS NOT NULL AND acked=0 ORDER BY sequence')]

    def acknowledged(self, event_ids):
        with self._db() as db:
            for event_id in event_ids:
                row = db.execute('SELECT processed FROM events WHERE id=?', (event_id,)).fetchone()
                if row is None or row[0] is None:
                    raise HandoffConflict('Cannot acknowledge an unprocessed event')
                db.execute('UPDATE events SET acked=1 WHERE id=?', (event_id,))

    def latest(self, import_id):
        """Latest observed status; it does not imply result processing or adoption."""
        with self._db() as db:
            row = db.execute('SELECT body FROM events WHERE import_id=? ORDER BY sequence DESC LIMIT 1', (import_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def rows(self):
        with self._db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM handoffs ORDER BY rowid')]

    def pin_payload(self, operation, key, payload):
        with self._db() as db:
            row = self._row(db, operation, key)
            if row['documents_receipt'] is None:
                raise HandoffConflict('Documents receipt required')
            if row.get('atlas_payload') is not None:
                _same(row['atlas_payload'], payload)
                return row['atlas_payload']
            row['atlas_payload'] = payload
            self._save(db, row)
            return json.loads(_json(payload))

    def observe(self, operation, key, snapshot):
        with self._db() as db:
            row = self._row(db, operation, key)
            if snapshot.get('import_id') != (row.get('atlas_receipt') or {}).get('import_id'):
                raise HandoffConflict('Snapshot import mismatch')
            old = row.get('snapshot')
            if old and old['updated_at'] >= snapshot['updated_at']:
                return
            row['snapshot'] = snapshot
            self._save(db, row)

    def set_error(self, operation, key, code):
        with self._db() as db:
            row = self._row(db, operation, key)
            row['last_error'] = code
            self._save(db, row)

    def event_cursor(self):
        with self._db() as db:
            row = db.execute("SELECT value FROM cursors WHERE name='events'").fetchone()
            return row[0] if row else None

    def save_event_cursor(self, cursor):
        if cursor is not None and (not isinstance(cursor, str) or not cursor):
            raise HandoffConflict('Invalid event cursor')
        with self._db() as db:
            db.execute("INSERT INTO cursors(name,value) VALUES ('events',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (cursor,))
