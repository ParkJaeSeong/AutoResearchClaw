"""Project-local durable delivery; receiving data never adopts a scientific claim."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from researchclaw.core.research_graph import store


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('inbox_invalid_reference')
    return value


def _target(value):
    fields = {'work_id', 'role_id', 'round_id', 'input_revision'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('inbox_invalid_target')
    return {key: _text(value[key]) for key in sorted(fields)}


class ServiceInbox:
    def __init__(self, root, project_id):
        self.project_id = _text(project_id)
        base = store._checked_path(Path(root) / '.service-inbox')
        base.mkdir(parents=True, exist_ok=True)
        self.path = store._checked_path(base / 'journal.sqlite3')
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS owner (slot INTEGER PRIMARY KEY CHECK(slot=1), project TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO owner VALUES (1, ?)', (self.project_id,))
            if db.execute('SELECT project FROM owner WHERE slot=1').fetchone()[0] != self.project_id:
                raise ValueError('inbox_project_mismatch')
            db.execute('CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL)')

    def _db(self):
        return sqlite3.connect(self.path, timeout=30)

    def put(self, request_id, stage, result_sha256, recipient, result_ref):
        _text(request_id); _text(stage)
        if not isinstance(result_sha256, str) or not re.fullmatch('[0-9a-f]{64}', result_sha256):
            raise ValueError('inbox_invalid_hash')
        if not isinstance(result_ref, dict):
            raise ValueError('inbox_invalid_reference')
        body = dict(project_id=self.project_id, request_id=request_id, stage=stage,
                    result_sha256=result_sha256, recipient=_target(recipient))
        identity = hashlib.sha256(_canonical(body).encode()).hexdigest()
        body.update(id=identity, result_ref=result_ref)
        encoded = _canonical(body)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT body FROM deliveries WHERE id=?', (identity,)).fetchone()
            if old and old[0] != encoded:
                raise ValueError('inbox_result_conflict')
            db.execute('INSERT OR IGNORE INTO deliveries VALUES (?, ?, ?)',
                       (identity, encoded, 'delivery_pending'))
        return body

    def pending(self):
        with self._db() as db:
            return [dict(json.loads(body), state=state) for body, state in db.execute(
                'SELECT body,state FROM deliveries WHERE state=? ORDER BY rowid', ('delivery_pending',))]

    def acknowledge(self, identity, recipient):
        """Explicit recipient/input acknowledgement, not scientific review completion."""
        recipient = _target(recipient)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM deliveries WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise ValueError('inbox_delivery_unknown')
            if json.loads(row[0])['recipient'] != recipient:
                raise ValueError('inbox_target_mismatch')
            db.execute('UPDATE deliveries SET state=? WHERE id=?', ('received', identity))
