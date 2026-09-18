"""Durable knowledge-job transport, isolated from research adoption and credentials."""
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote
from researchclaw.core.research_graph import store
from .knowledge_protocol import VERSION,validate_job,validate_resume
from .knowledge_package import collect_artifact,validate_manifest


class KnowledgeSession:
    def __init__(self,root,client,instance,consumer,project):
        self.client=client;self.instance=instance;self.consumer=consumer;self.project=project
        self.base=store._checked_path(Path(root)/'.knowledge-link');self.base.mkdir(parents=True,exist_ok=True)
        self.path=store._checked_path(self.base/'journal.sqlite3')
        binding=json.dumps([instance,consumer,project])
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS binding (id INTEGER PRIMARY KEY, body TEXT)')
            db.execute('INSERT OR IGNORE INTO binding VALUES (1,?)',(binding,))
            if db.execute('SELECT body FROM binding WHERE id=1').fetchone()[0]!=binding:raise ValueError('knowledge_binding_mismatch')
            db.execute('CREATE TABLE IF NOT EXISTS requests (key TEXT PRIMARY KEY,payload TEXT,job TEXT,body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS objects (sha TEXT PRIMARY KEY,raw BLOB NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS results (key TEXT,stage TEXT,attempt INTEGER,sha TEXT,PRIMARY KEY(key,stage,attempt))')
            db.execute('CREATE TABLE IF NOT EXISTS resumes (key TEXT,revision INTEGER,body TEXT,PRIMARY KEY(key,revision))')

    def _db(self):return sqlite3.connect(self.path,timeout=30)

    def _request(self,key):
        with self._db() as db:row=db.execute('SELECT payload,job,body FROM requests WHERE key=?',(key,)).fetchone()
        if not row:raise ValueError('knowledge_request_unknown')
        return json.loads(row[0]),row[1],json.loads(row[2]) if row[2] else None

    def connect(self):
        info=self.client.request('GET','/api/info')
        if info.get('ok') is not True or info.get('atlas_instance_id')!=self.instance:raise ValueError('knowledge_instance_mismatch')
        capability=info.get('knowledge_update',{})
        if 'ask_knowledge_update_v1' not in info.get('capabilities',[]) or capability.get('contract_version')!=VERSION:
            raise ValueError('knowledge_capability_unavailable')
        if self.project not in capability.get('allowed_project_ids',[]):raise ValueError('knowledge_project_forbidden')
        return info

    def submit(self,payload):
        if payload['project_id']!=self.project:raise ValueError('knowledge_project_mismatch')
        encoded=store._canonical(payload).decode();key=payload['request_key']
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT payload,job FROM requests WHERE key=?',(key,)).fetchone()
            if old and old[0]!=encoded:raise ValueError('knowledge_request_conflict')
            db.execute('INSERT OR IGNORE INTO requests VALUES (?,?,NULL,NULL)',(key,encoded))
        if old and old[1]:return self.saved(key)
        self.connect()
        body=self.client.request('POST','/api/knowledge-jobs',payload)
        validate_job(body,self.instance,body['job_id'],payload,self.consumer)
        with self._db() as db:db.execute('UPDATE requests SET job=?,body=? WHERE key=?',(body['job_id'],json.dumps(body),key))
        return body

    def _artifact(self,job,ref):
        with self._db() as db:cached=db.execute('SELECT raw FROM objects WHERE sha=?',(ref['sha256'],)).fetchone()
        if cached:
            raw=cached[0]
            if store._hash(raw)!=ref['sha256']:raise ValueError('knowledge_cached_hash')
            return raw
        def chunks():
            offset=0
            while True:
                part=self.client.request('GET','/api/knowledge-jobs/'+quote(job,safe='')+'/artifacts/'+quote(ref['artifact_id'],safe=''),params={'offset':offset,'limit':262144})
                if part.get('ok') is not True or part.get('atlas_instance_id')!=self.instance or part.get('contract_version')!=VERSION:raise ValueError('knowledge_artifact_identity')
                yield part
                if part['eof']:break
                offset=part['next_offset']
        raw=collect_artifact(chunks(),ref)
        with self._db() as db:db.execute('INSERT OR IGNORE INTO objects VALUES (?,?)',(ref['sha256'],raw))
        return raw

    def observe(self,key):
        payload,job,_=self._request(key)
        if not job:raise ValueError('knowledge_submission_uncertain')
        self.connect()
        body=self.client.request('GET','/api/knowledge-jobs/'+quote(job,safe=''))
        validate_job(body,self.instance,job,payload,self.consumer)
        answer=body['answer'].get('result')
        if answer:
            ref=answer['record']['package_ref']
            manifest=validate_manifest(self._artifact(job,ref),ref,self.instance,job)
            for artifact in manifest['artifacts']:self._artifact(job,artifact)
        records=[]
        for ref in body['stage_results']:
            raw=self._artifact(job,ref);record=json.loads(raw)
            for field in ('schema_version','atlas_instance_id','job_id','stage','attempt'):
                if record.get(field)!=ref[field]:raise ValueError('knowledge_stage_identity')
            records.append(ref)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            for ref in records:
                old=db.execute('SELECT sha FROM results WHERE key=? AND stage=? AND attempt=?',(key,ref['stage'],ref['attempt'])).fetchone()
                if old and old[0]!=ref['sha256']:raise ValueError('knowledge_immutable_result_changed')
                db.execute('INSERT OR IGNORE INTO results VALUES (?,?,?,?)',(key,ref['stage'],ref['attempt'],ref['sha256']))
            db.execute('UPDATE requests SET body=? WHERE key=?',(json.dumps(body),key))
        return body

    def resume(self,key,revision):
        _,job,_=self._request(key)
        self.connect()
        with self._db() as db:db.execute('INSERT OR IGNORE INTO resumes VALUES (?,?,NULL)',(key,revision))
        body=self.client.request('POST','/api/knowledge-jobs/'+quote(job,safe='')+'/resume',{'expected_revision':revision})
        receipt=validate_resume(body,self.instance,job,revision)
        with self._db() as db:
            prior=db.execute('SELECT body FROM resumes WHERE key=? AND revision=?',(key,revision)).fetchone()[0]
            if prior and json.loads(prior)!=receipt:raise ValueError('knowledge_resume_changed')
            db.execute('UPDATE resumes SET body=? WHERE key=? AND revision=?',(json.dumps(receipt),key,revision))
        return body

    def saved(self,key):return self._request(key)[2]

    def results(self,key):
        with self._db() as db:rows=db.execute('SELECT o.sha,o.raw FROM results r JOIN objects o ON r.sha=o.sha WHERE r.key=? ORDER BY r.stage,r.attempt',(key,)).fetchall()
        values=[]
        for sha,raw in rows:
            if store._hash(raw)!=sha:raise ValueError('knowledge_cached_hash')
            values.append(json.loads(raw))
        return values

    def deliver_saved(self,key,inbox,recipient):
        """Route immutable stage records; only answer stages can start evidence review."""
        payload,job,body=self._request(key)
        if not body:raise ValueError('knowledge_result_missing')
        delivered=[]
        for record in self.results(key):
            packet=dict(record,stage_result_sha256=store._hash(store._canonical(record)))
            if record['stage']=='answer':
                with self._db() as db:
                    raw=db.execute('SELECT raw FROM objects WHERE sha=?',(record['qa_ref']['sha256'],)).fetchone()
                if not raw or store._hash(raw[0])!=record['qa_ref']['sha256']:
                    raise ValueError('knowledge_answer_raw_missing')
                packet.update(answer_state='stored' if record.get('job_status') in ('completed','partial') else 'diagnostic_only',
                              atlas_qa_raw=raw[0].decode('utf-8'),reading_scope='QA only; source originals not supplied')
            digest=store._hash(store._canonical(packet))
            delivered.append(inbox.put('atlas-knowledge:'+self.instance+':'+job,
                record['stage'],digest,recipient,packet))
        return delivered
