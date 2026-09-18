"""Offline, allowlisted display of stored knowledge jobs; never opens credentials."""
import json
import sqlite3
from pathlib import Path
from researchclaw.core.research_graph import store


def knowledge_status(root):
    path=store._checked_path(Path(root)/'.knowledge-link'/'journal.sqlite3')
    if not path.exists():return []
    rows=[]
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        for key,payload,job,body in db.execute('SELECT key,payload,job,body FROM requests ORDER BY rowid'):
            request=json.loads(payload);state=json.loads(body) if body else {}
            answer=state.get('answer',{});knowledge=state.get('knowledge',{})
            records=[]
            for stage,attempt,sha,raw in db.execute('SELECT r.stage,r.attempt,o.sha,o.raw FROM results r JOIN objects o ON r.sha=o.sha WHERE r.key=? ORDER BY r.stage,r.attempt',(key,)):
                if store._hash(raw)!=sha:raise ValueError('knowledge_cached_hash')
                records.append(dict(stage=stage,attempt=attempt))
            rows.append(dict(request_key=key,job_id=job,question=request['question'],
                answer_status=answer.get('status','pending'),knowledge_status=knowledge.get('status','pending'),
                revision=state.get('revision'),stages=records,stored_answer=any(r['stage']=='answer' for r in records),
                index_status=(knowledge.get('result') or {}).get('record',{}).get('index_status',{})))
    return rows
