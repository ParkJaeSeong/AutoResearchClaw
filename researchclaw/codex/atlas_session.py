"""Durable transport journal; scientific mutations use the existing graph commands."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote

from researchclaw.core.research_graph import store
from .atlas_client import VERSION, AtlasError, unpack_raw
from .atlas_intake import import_qa


def _text(value):
    if not isinstance(value,str) or not value.strip() or len(value)>100_000:
        raise AtlasError('atlas_input_invalid')
    return value


def _envelope(value,instance):
    if value.get('atlas_instance_id')!=instance:raise AtlasError('atlas_instance_mismatch')
    if value.get('ok') is not True or value.get('contract_version')!=VERSION:raise AtlasError('atlas_contract_unsupported')


class AtlasSession:
    def __init__(self, root, client):
        self.root=store._checked_path(Path(root));self.client=client
        self.project_id=store.read_head(self.root)['state']['project_id']
        self.base=store._checked_path(self.root/'.atlas-link');self.base.mkdir(exist_ok=True)
        self.db_path=store._checked_path(self.base/'journal.sqlite3')
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS bindings (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS requests (key TEXT PRIMARY KEY, body TEXT NOT NULL)')

    @contextmanager
    def _db(self):
        with sqlite3.connect(self.db_path,timeout=30) as db:
            yield db

    def _get(self,key):
        _text(key)
        with self._db() as db: row=db.execute('SELECT body FROM requests WHERE key=?',(key,)).fetchone()
        if not row: raise AtlasError('atlas_request_unknown')
        return json.loads(row[0])

    def _update(self,key,**fields):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT body FROM requests WHERE key=?',(key,)).fetchone()
            body=json.loads(row[0]);body.update(fields)
            db.execute('UPDATE requests SET body=? WHERE key=?',(json.dumps(body,ensure_ascii=False),key))
        return body

    def status(self):
        with self._db() as db:
            bindings=[json.loads(r[0]) for r in db.execute('SELECT body FROM bindings ORDER BY rowid')]
            rows=[json.loads(r[0]) for r in db.execute('SELECT body FROM requests ORDER BY rowid')]
        return dict(binding=bindings[-1] if bindings else None,bindings=bindings,
            requests=[self._public(r) for r in rows])

    @staticmethod
    def _public(row):
        return {k:v for k,v in row.items() if k not in ('raw','qa_envelope')}

    def connect(self):
        info=self.client.identity()
        return dict(info=info,projects=self.client.request('GET','/api/projects')['projects'],**self.status())

    def bind(self,project,reason):
        _text(project);_text(reason);info=self.client.identity()
        projects=self.client.request('GET','/api/projects')['projects']
        selected=next((p for p in projects if p['id']==project),None)
        if selected is None: raise AtlasError('unknown_project')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT body FROM bindings ORDER BY rowid DESC LIMIT 1').fetchone()
            previous=json.loads(old[0]) if old else None
            if previous and previous['project']==project and previous['atlas_instance_id']==info['atlas_instance_id'] and previous['reason']==reason: return previous
            binding=dict(id=str(uuid4()),pilot_project_id=self.project_id,project=project,title=selected['title'],
                atlas_instance_id=info['atlas_instance_id'],reason=reason,previous_binding_ref=previous['id'] if previous else None)
            db.execute('INSERT INTO bindings VALUES (?,?)',(binding['id'],json.dumps(binding,ensure_ascii=False)))
        return binding

    def ask(self,key,question,question_id,previous=None,*,research_context=None):
        for v in (key,question,question_id):_text(v)
        if previous is not None:_text(previous)
        if len(key)>256 or len(question)>32000:raise AtlasError('atlas_input_invalid')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT body FROM requests WHERE key=?',(key,)).fetchone()
            if existing:
                row=json.loads(existing[0])
                if row.get('research_context') != research_context:raise AtlasError('atlas_request_conflict')
                if (row['question'],row['question_id'],row['previous'])!=(question,question_id,previous):raise AtlasError('atlas_request_conflict')
            else:
                last=db.execute('SELECT body FROM bindings ORDER BY rowid DESC LIMIT 1').fetchone()
                if not last:raise AtlasError('atlas_binding_required')
                binding=json.loads(last[0])
                transmitted=question
                if previous:
                    earlier=db.execute('SELECT body FROM requests WHERE key=?',(previous,)).fetchone()
                    if not earlier:raise AtlasError('atlas_request_unknown')
                    prior=json.loads(earlier[0])
                    if prior['binding']['project']!=binding['project'] or prior['binding']['atlas_instance_id']!=binding['atlas_instance_id']:
                        raise AtlasError('atlas_reference_mismatch')
                    prior_ref=(prior.get('job') or {}).get('detail',{}).get('qa_ref')
                    transmitted=('이전 질문: '+prior['question']+'\n이전 Atlas QA 참조: '+json.dumps(prior_ref,ensure_ascii=False)+'\n이번 확인 질문: '+question)
                    if len(transmitted)>32000:raise AtlasError('atlas_input_invalid')
                payload=dict(contract_version=VERSION,kind='ask',request_key=key,question=transmitted,
                    project=binding['project'],execute=True,client_context=dict(pilot_project_id=self.project_id,
                    question_id=question_id,issue_id=None,round_id=key,binding_ref=binding['id']))
                row=dict(request_key=key,question=question,question_id=question_id,previous=previous,
                    binding=binding,payload=payload,job=None,received=False,research_context=research_context)
                db.execute('INSERT INTO requests VALUES (?,?)',(key,json.dumps(row,ensure_ascii=False)))
        return self.poll(key)

    def poll(self,key):
        row=self._get(key);self.client.identity(row['binding']['atlas_instance_id'])
        try:
            response=self.client.request('GET','/api/jobs/'+quote(row['job']['id'],safe='')) if row['job'] else self.client.request('POST','/api/jobs',row['payload'])
            _envelope(response,row['binding']['atlas_instance_id'])
            job=response['job']
            if row['job'] and job['id']!=row['job']['id']:raise AtlasError('atlas_reference_mismatch')
            if (job.get('atlas_instance_id')!=row['binding']['atlas_instance_id'] or job.get('request_key')!=key or job.get('payload',{}).get('question')!=row['payload']['question'] or job.get('payload',{}).get('project')!=row['binding']['project'] or job.get('payload',{}).get('client_context')!=row['payload']['client_context']):
                raise AtlasError('atlas_reference_mismatch')
            receipt=job.get('receipt_ref',response.get('receipt_ref'))
            if not receipt or receipt.get('operation')!='jobs.submit' or receipt.get('request_key')!=key or receipt.get('atlas_instance_id')!=row['binding']['atlas_instance_id'] or receipt.get('request_sha256')!=job.get('request_sha256'):
                raise AtlasError('atlas_receipt_invalid')
            if row['job'] and row['job']['request_sha256']!=job['request_sha256']:raise AtlasError('atlas_receipt_invalid')
            return self._public(self._update(key,job=job,error=None))
        except ValueError as exc:
            self._update(key,error=str(exc),error_info=dict(status=getattr(exc,'status',0),retryable=getattr(exc,'retryable',False),details=getattr(exc,'details',{})));raise

    def capture(self,key):
        """Preserve an answer without adopting it into the research graph."""
        row=self._get(key)
        envelope=row.get('qa_envelope')
        if envelope is None:
            self.poll(key);row=self._get(key)
            if row['job'].get('status') not in ('completed','partial','failed','interrupted'):
                raise AtlasError('atlas_qa_not_ready')
            ref=row['job'].get('detail',{}).get('qa_ref')
            if not ref:raise AtlasError('atlas_qa_not_ready')
            envelope=self.client.request('GET','/api/qa/'+quote(ref['qa_id'],safe=''),params={'expected_sha256':ref['sha256']})
        else:
            ref=row['qa_ref']
        _envelope(envelope,row['binding']['atlas_instance_id'])
        if envelope.get('qa_id')!=ref['qa_id']:raise AtlasError('atlas_reference_mismatch')
        data=unpack_raw(envelope['raw'],ref['sha256'])
        from researchclaw.core.research_graph.atlas_format import parse_atlas_qa
        qa=parse_atlas_qa(data)
        if qa['id']!=ref['qa_id'] or qa['question']!=row['payload']['question'] or qa.get('project')!=row['binding']['project']:
            raise AtlasError('atlas_reference_mismatch')
        # Original response and bytes are durable before graph mutation.
        self._update(key,qa_envelope=envelope,qa_ref=ref)
        self._save_blob(data,ref['sha256'])
        supporting=row.get('supporting')
        if supporting is None: supporting=self._supporting(qa,row['binding']['atlas_instance_id'])
        answer_state = 'needs_input' if any(not item.get('received') for item in supporting) else 'stored'
        if row['job'].get('status') in ('failed','interrupted'):
            answer_state = 'diagnostic_only'
        return self._public(self._update(key,supporting=supporting,answer_state=answer_state))

    def queue_answer(self,key,recipient):
        """Queue a frozen answer for an explicitly selected work/role/input revision."""
        from .service_inbox import ServiceInbox
        row=self.capture(key)
        packet=dict(schema_version=1,atlas_instance_id=row['binding']['atlas_instance_id'],
            project_id=self.project_id,request_key=key,job_id=row['job']['id'],
            qa_ref=row['qa_ref'],answer_state=row['answer_state'],
            atlas_status=row['job']['status'],supporting=row.get('supporting',[]))
        data=store._canonical(packet);digest=store._hash(data)
        self._save_blob(data,digest)
        return ServiceInbox(self.root,self.project_id).put(
            'atlas:'+row['binding']['atlas_instance_id']+':'+key,
            'answer',digest,recipient,packet)

    def receive(self,key,expected_head):
        row=self._get(key)
        if row.get('import_result'):return self._public(row)
        self.capture(key);row=self._get(key)
        ref=row['qa_ref']
        data=unpack_raw(row['qa_envelope']['raw'],ref['sha256'])
        result=import_qa(self.root,data=data,filename=ref['qa_id']+'.md',expected_head=expected_head,
            command_id='atlas-import-'+store._hash((row['binding']['atlas_instance_id']+key+ref['sha256']).encode()))
        return self._public(self._update(key,import_result=result,received=True))


    def _save_blob(self,data,digest):
        import os
        if store._hash(data)!=digest:raise AtlasError('atlas_raw_invalid')
        base=store._checked_path(self.base/'objects');base.mkdir(exist_ok=True)
        path=store._checked_path(base/digest)
        if path.exists():
            if store._hash(path.read_bytes())!=digest:raise AtlasError('atlas_raw_invalid')
            return
        # Atomic publication, so interrupted downloads never appear complete.
        import tempfile
        fd,name=tempfile.mkstemp(dir=base)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)

    def _supporting(self,qa,instance):
        result=[];sources=set()
        for ref in qa.get('consulted_pages',[]):
            if not ref.get('page_id') or not ref.get('sha256'):continue
            try:
                self.client.identity(instance)
                page=self.client.request('GET','/api/pages/'+quote(ref['page_id'],safe=''),
                    params={'include_raw':'true','expected_sha256':ref['sha256']})
                _envelope(page,instance)
                if page.get('id')!=ref['page_id']:raise AtlasError('atlas_reference_mismatch')
                data=unpack_raw(page['raw'],ref['sha256']);self._save_blob(data,ref['sha256'])
                result.append(dict(kind='page',ref=ref,sha256=ref['sha256'],received=True))
                for src in page.get('source_refs',[]):sources.add((src['source_id'],src['version']))
            except ValueError as exc:
                if str(exc) in ('atlas_instance_mismatch','atlas_contract_unsupported','atlas_reference_mismatch'):raise
                result.append(dict(kind='page',ref=ref,received=False,error=str(exc)))
        for source_id,version in sorted(sources):
            try:
                self.client.identity(instance);ref,data=self.client.source(source_id,version)
                self._save_blob(data,ref['sha256']);result.append(dict(kind='source',ref=ref,received=True))
            except ValueError as exc:
                if str(exc) in ('atlas_instance_mismatch','atlas_contract_unsupported','atlas_reference_mismatch'):raise
                result.append(dict(kind='source',ref=dict(source_id=source_id,version=version),received=False,error=str(exc)))
        return result

    def refresh_supporting(self,key):
        row=self._get(key)
        if not row.get('qa_envelope'):raise AtlasError('atlas_qa_not_ready')
        self.client.identity(row['binding']['atlas_instance_id'])
        from researchclaw.core.research_graph.atlas_format import parse_atlas_qa
        qa=parse_atlas_qa(unpack_raw(row['qa_envelope']['raw'],row['qa_ref']['sha256']))
        supporting=self._supporting(qa,row['binding']['atlas_instance_id'])
        return self._public(self._update(key,supporting=supporting,
            supporting_history=row.get('supporting_history',[])+[row.get('supporting',[])]))
