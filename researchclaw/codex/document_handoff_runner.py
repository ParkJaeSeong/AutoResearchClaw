"""Explicit observer for an existing project journal. Never creates research work.

python -m researchclaw.codex.document_handoff_runner ROOT
  --documents-connection PRIVATE_JSON --atlas-connection PRIVATE_JSON [--watch]
"""
import argparse
import json
import re
import sqlite3
import time
from pathlib import Path
from .document_handoff import HandoffJournal
from .document_handoff_adapter import HandoffAdapter
from .document_handoff_transport import HandoffHTTP
from researchclaw.core.research_graph import store


def configured_adapter(root, documents_connection, atlas_connection):
    root=store._checked_path(Path(root))
    path=store._checked_path(root/'.document-handoff/journal.sqlite3')
    # mode=ro ensures a typo never creates an empty journal or synthetic project.
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        identity=json.loads(db.execute('SELECT body FROM identity WHERE id=1').fetchone()[0])
    if store.read_head(root)['state']['project_id']!=identity['project_id']:
        raise ValueError('handoff_project_mismatch')
    journal=HandoffJournal(path,identity['project_id'],identity['atlas_instance_id'],identity['consumer_id'])
    return HandoffAdapter(journal,HandoffHTTP(documents_connection),HandoffHTTP(atlas_connection))


def cycle(adapter):
    # Poll received work even when an independent new submission cannot advance.
    errors=[]
    for operation in (adapter.advance,adapter.poll):
        try:operation()
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:
            code=str(exc)
            errors.append(code if re.fullmatch('[a-zA-Z_]+',code) else 'handoff_operation_failed')
    return {'ok':not errors,'errors':errors,'pending_requests':len(adapter.journal.pending()),
            'pending_events':len(adapter.journal.pending_events()),'pending_acks':len(adapter.journal.pending_acks())}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Resume saved document handoffs; no new research decisions')
    parser.add_argument('root',type=Path)
    parser.add_argument('--documents-connection',required=True,type=Path)
    parser.add_argument('--atlas-connection',required=True,type=Path)
    parser.add_argument('--watch',action='store_true',help='Observe every 60 seconds; Ctrl-C preserves all receipts')
    args=parser.parse_args(argv)
    adapter=configured_adapter(args.root,args.documents_connection,args.atlas_connection)
    try:
        while True:
            result=cycle(adapter);print(json.dumps(result),flush=True)
            if not args.watch:return 0 if result['ok'] else 1
            time.sleep(60)
    except KeyboardInterrupt:return 130


if __name__=='__main__':
    raise SystemExit(main())
