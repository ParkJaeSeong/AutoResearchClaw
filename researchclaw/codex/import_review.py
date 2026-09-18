"""Prepare durable import review inputs; never execute or adopt research decisions."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from .atlas_client import AtlasClient, unpack_raw
from .document_handoff import HandoffJournal, _json


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


class ImportReviewQueue:
    def __init__(self, journal):
        self.journal = journal
        with journal._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS import_reviews (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS import_review_blobs (sha256 TEXT PRIMARY KEY, raw BLOB NOT NULL)')

    def get(self, task_id):
        with self.journal._db() as db:
            row = db.execute('SELECT body FROM import_reviews WHERE id=?', (task_id,)).fetchone()
            if row is None:
                raise ValueError('review_missing')
            return json.loads(row[0])

    def reconcile(self, context):
        for field in ('question_revision', 'question', 'purpose', 'policy_revision'):
            if not isinstance(context.get(field), str) or not context[field].strip():
                raise ValueError('review_context_required')
        context = json.loads(_json(context))
        tasks = []
        with self.journal._db() as db:
            requests = {r['atlas_receipt']['import_id']: r['atlas_payload']
                        for body, in db.execute('SELECT body FROM handoffs')
                        if (r := json.loads(body)).get('atlas_receipt') and r.get('atlas_payload')}
            for body, processed in db.execute('SELECT body,processed FROM events WHERE processed IS NOT NULL ORDER BY sequence'):
                event, saved = json.loads(body), json.loads(processed)
                iid = event['import_id']; instance = self.journal.identity['atlas_instance_id']
                if event.get('atlas_instance_id') != instance or iid not in requests:
                    raise ValueError('review_identity_mismatch')
                if requests[iid].get('pilot_project_id') != self.journal.identity['project_id']:
                    raise ValueError('review_project_mismatch')
                ref = event.get('result_ref'); result = saved.get('result')
                if ref is not None:
                    if not result or _hash(result['record']) != ref.get('sha256') or result.get('sha256') != ref.get('sha256') or ref.get('import_id') != iid or result['record'].get('import_id') != iid:
                        raise ValueError('review_result_mismatch')
                record = result['record'] if result else {}
                scientific = event.get('outcome') in ('completed', 'partial') and bool(record.get('page_refs')) and bool(record.get('read_scope'))
                key = dict(atlas_instance_id=instance, import_id=iid, result_hash=ref['sha256'] if ref else _hash(event),
                           question_revision=context['question_revision'], purpose=context['purpose'], policy_revision=context['policy_revision'])
                tid = _hash(key)
                row = db.execute('SELECT body FROM import_reviews WHERE id=?', (tid,)).fetchone()
                if row:
                    task = json.loads(row[0])
                    if task['context'] != context:
                        raise ValueError('review_context_conflict')
                else:
                    task = dict(id=tid, key=key, context=context, event_id=event['event_id'],
                                request=requests[iid], result=result, diagnostic=saved.get('diagnostic'),
                                outcome=event.get('outcome'), status='awaiting_input' if scientific else 'needs_recovery')
                    db.execute('INSERT INTO import_reviews VALUES (?,?)', (tid, _json(task)))
                tasks.append(task)
        return tasks

    def execution(self, task_id, status):
        if status not in ('review_running', 'review_failed', 'review_complete'):
            raise ValueError('review_execution_status_invalid')
        with self.journal._db() as db:
            task = json.loads(db.execute('SELECT body FROM import_reviews WHERE id=?', (task_id,)).fetchone()[0])
            task['execution'] = {'status': status}
            db.execute('UPDATE import_reviews SET body=? WHERE id=?', (_json(task), task_id))

    def completed(self, task_id):
        task = self.get(task_id)
        result = task.get('review_result')
        if result is not None and _hash(result) != task.get('review_result_sha256'):
            raise ValueError('review_result_corrupt')
        return result

    def complete(self, task_id, result):
        with self.journal._db() as db:
            row = db.execute('SELECT body FROM import_reviews WHERE id=?', (task_id,)).fetchone()
            if row is None:
                raise ValueError('review_missing')
            task = json.loads(row[0])
            if (task.get('status') != 'input_ready' or result.get('stage') != 'review_complete'
                    or result.get('task_id') != task_id or result.get('packet_sha256') != task.get('packet_sha256')
                    or result.get('research_adoption') is not False):
                raise ValueError('review_completion_mismatch')
            if task.get('review_result') is not None and task['review_result'] != result:
                raise ValueError('review_completion_conflict')
            task.update(review_result=result, review_result_sha256=_hash(result))
            db.execute('UPDATE import_reviews SET body=? WHERE id=?', (_json(task), task_id))

    def materials(self, task_id):
        task = self.get(task_id)
        if task.get('status') != 'input_ready' or _hash(task['packet']) != task.get('packet_sha256'):
            raise ValueError('review_input_not_ready')
        pages = []
        with self.journal._db() as db:
            for ref in task['packet']['pages']:
                row = db.execute('SELECT raw FROM import_review_blobs WHERE sha256=?', (ref['sha256'],)).fetchone()
                if row is None or hashlib.sha256(bytes(row[0])).hexdigest() != ref['sha256']:
                    raise ValueError('review_blob_corrupt')
                pages.append(dict(ref=ref, raw_utf8=bytes(row[0]).decode('utf-8')))
        return dict(packet=task['packet'], pages=pages)

    def prepare(self, task_id, client):
        task = self.get(task_id)
        if task['status'] == 'needs_recovery':
            raise ValueError('review_requires_recovery')
        refs = task['result']['record']['page_refs']
        client.identity(self.journal.identity['atlas_instance_id'])
        pages = []
        for ref in refs:
            with self.journal._db() as db:
                saved = db.execute('SELECT raw FROM import_review_blobs WHERE sha256=?', (ref['sha256'],)).fetchone()
            if saved:
                raw = bytes(saved[0])
                if hashlib.sha256(raw).hexdigest() != ref['sha256']:
                    raise ValueError('review_blob_corrupt')
            else:
                page = client.request('GET', '/api/pages/' + quote(ref['page_id'], safe=''),
                                      params={'include_raw': 'true', 'expected_sha256': ref['sha256']})
                if page.get('atlas_instance_id') != self.journal.identity['atlas_instance_id'] or page.get('contract_version') != 'pilot-atlas/1.0' or page.get('id') != ref['page_id']:
                    raise ValueError('review_page_mismatch')
                raw = unpack_raw(page['raw'], ref['sha256'])
                with self.journal._db() as db:
                    db.execute('INSERT OR IGNORE INTO import_review_blobs VALUES (?,?)', (ref['sha256'], raw))
            pages.append(dict(page_id=ref['page_id'], sha256=ref['sha256']))
        packet = dict(context=task['context'], request=task['request'], result=task['result'], pages=pages,
                      provenance='Atlas interpretation; stored page bytes are not independent source/image verification')
        with self.journal._db() as db:
            current = json.loads(db.execute('SELECT body FROM import_reviews WHERE id=?', (task_id,)).fetchone()[0])
            if current.get('packet_sha256') not in (None, _hash(packet)):
                raise ValueError('review_packet_conflict')
            current.update(status='input_ready', packet=packet, packet_sha256=_hash(packet))
            db.execute('UPDATE import_reviews SET body=? WHERE id=?', (_json(current), task_id))
        return current


def load_queue(root):
    from researchclaw.core.research_graph import store
    root = store._checked_path(Path(root).resolve())
    path = store._checked_path(root / '.document-handoff/journal.sqlite3')
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        identity = json.loads(db.execute('SELECT body FROM identity WHERE id=1').fetchone()[0])
    if store.read_head(root)['state']['project_id'] != identity['project_id']:
        raise ValueError('review_project_mismatch')
    return ImportReviewQueue(HandoffJournal(path, **identity))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--context', required=True, type=Path)
    p.add_argument('--atlas-connection', required=True, type=Path)
    args = p.parse_args(argv)
    queue = load_queue(args.root)
    tasks = queue.reconcile(json.loads(args.context.read_text()))
    client = AtlasClient(args.atlas_connection)
    for task in tasks:
        if task['status'] != 'needs_recovery':
            task = queue.prepare(task['id'], client)
        print(json.dumps({'id': task['id'], 'status': task['status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
