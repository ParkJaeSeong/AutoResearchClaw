"""Read-only, allowlisted projection of the project handoff journal."""
import json
import hashlib
from .document_handoff import _json
import sqlite3
from pathlib import Path
from researchclaw.core.research_graph import store


def _reviews(db):
    grouped = {}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_reviews'").fetchone():
        return grouped
    for body, in db.execute('SELECT body FROM import_reviews ORDER BY rowid DESC'):
        task = json.loads(body)
        result = task.get('review_result')
        if result is not None and hashlib.sha256(_json(result).encode()).hexdigest() != task.get('review_result_sha256'):
            raise ValueError('handoff_review_corrupt')
        execution = task.get('execution', {})
        status = 'review_complete' if result else execution.get('status', task['status'])
        review = dict(id=task['id'], status=status, question_revision=task['context']['question_revision'],
                      conclusion=(result or {}).get('coordinator', {}).get('answer', {}).get('rationale'), rounds=[])
        for phase in ('initial', 'response', 'final'):
            rows = (result or {}).get('rounds', {}).get(phase, [])
            if not rows:continue
            review['rounds'].append(dict(phase=phase, statements=[dict(role=r.get('role'),
                text=r.get('answer', {}).get('rationale', '')) for r in rows]))
        grouped.setdefault(task['key']['import_id'], []).append(review)
    return grouped


def build_handoff_view(root, project_id):
    path = store._checked_path(Path(root) / '.document-handoff/journal.sqlite3')
    result = dict(schema_version=1, project_id=project_id, items=[])
    if not path.exists():
        return result
    try:
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('BEGIN')
            identity = json.loads(db.execute('SELECT body FROM identity WHERE id=1').fetchone()[0])
            if identity['project_id'] != project_id:
                raise ValueError('handoff_project_mismatch')
            reviews = _reviews(db)
            for body, in db.execute('SELECT body FROM handoffs ORDER BY rowid DESC'):
                row = json.loads(body)
                request = row['atlas_request']
                bibliography = request.get('bibliography') or {}
                receipt = row.get('atlas_receipt') or {}
                event_row = db.execute('SELECT body FROM events WHERE import_id=? ORDER BY sequence DESC LIMIT 1', (receipt.get('import_id'),)).fetchone()
                event = json.loads(event_row[0]) if event_row else {}
                status = {'documents': 'submission_pending', 'atlas': 'atlas_submission_pending'}.get(row['destination'], 'accepted')
                if row.get('snapshot'):
                    snapshot = row['snapshot']
                    status = snapshot.get('outcome') if snapshot.get('phase') == 'terminal' else snapshot.get('phase')
                elif event:
                    status = event.get('outcome') if event.get('phase') == 'terminal' else event.get('phase')
                if row.get('last_error'):
                    status = 'needs_attention'
                processed_row = db.execute('SELECT processed FROM events WHERE import_id=? AND processed IS NOT NULL ORDER BY sequence DESC LIMIT 1', (receipt.get('import_id'),)).fetchone()
                processed = json.loads(processed_row[0]) if processed_row else {}
                verified = processed.get('result', {}).get('record')
                result['items'].append(dict(
                    result_received=verified is not None,
                    read_scope=verified.get('read_scope') if verified else None,
                    unresolved=verified.get('unresolved', []) if verified else [],
                    id=json.dumps([row['operation'], row['request_key']]),
                    title=bibliography.get('title') or row['documents_request'].get('filename') or '제목이 기록되지 않은 자료',
                    doi=bibliography.get('doi') or '', purpose=request.get('purpose') or '',
                    source_url=request.get('source_url') or bibliography.get('url') or '',
                    status=status or 'unknown', pilot_review=(reviews.get(receipt.get('import_id')) or [{'status':'unrecorded'}])[0]['status'],
                    reviews=reviews.get(receipt.get('import_id'), []),
                    documents_received=bool(row.get('documents_receipt')),
                    atlas_received=bool(receipt), request_key=row['request_key'],
                    task_id=(row.get('documents_receipt') or {}).get('task_id'),
                    import_id=receipt.get('import_id'), event_id=event.get('event_id')))
        finally:
            db.close()
    except (sqlite3.Error, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('handoff_records_unavailable') from exc
    return result
