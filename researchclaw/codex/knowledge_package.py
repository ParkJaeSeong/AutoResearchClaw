"""Knowledge v1 immutable artifact transport validation; no remote writes."""
import base64
import hashlib
import json

MAX_ARTIFACT=10*1024*1024
MAX_PACKAGE=64*1024*1024


def collect_artifact(chunks,ref):
    data=bytearray();size=None;ended=False
    for chunk in chunks:
        if ended or chunk.get('artifact_id')!=ref['artifact_id'] or chunk.get('sha256')!=ref['sha256']:
            raise ValueError('knowledge_chunk_reference')
        current=chunk.get('size')
        if type(current) is not int or not 0<=current<=MAX_ARTIFACT:
            raise ValueError('knowledge_artifact_size')
        if size is None:size=current
        if current!=size or ('size' in ref and size!=ref['size']):raise ValueError('knowledge_artifact_size')
        if type(chunk.get('offset')) is not int or chunk['offset']!=len(data):raise ValueError('knowledge_chunk_offset')
        if chunk.get('encoding')!='base64':raise ValueError('knowledge_chunk_encoding')
        encoded=chunk.get('data')
        if not isinstance(encoded,str) or len(encoded)>4*((4194304+2)//3):raise ValueError('knowledge_chunk_size')
        raw=base64.b64decode(encoded,validate=True)
        if len(raw)>4194304 or len(data)+len(raw)>size:raise ValueError('knowledge_chunk_size')
        data.extend(raw)
        ended=len(data)==size
        if type(chunk.get('eof')) is not bool or chunk['eof']!=ended:raise ValueError('knowledge_chunk_eof')
        if ended:
            if chunk.get('next_offset') is not None:raise ValueError('knowledge_chunk_offset')
        elif not raw or type(chunk.get('next_offset')) is not int or chunk['next_offset']!=len(data):
            raise ValueError('knowledge_chunk_offset')
    if not ended or hashlib.sha256(data).hexdigest()!=ref['sha256']:raise ValueError('knowledge_artifact_hash')
    return bytes(data)


def validate_manifest(raw,ref,instance,job_id):
    if len(raw)>MAX_ARTIFACT or hashlib.sha256(raw).hexdigest()!=ref['sha256']:
        raise ValueError('knowledge_manifest_hash')
    m=json.loads(raw)
    if m.get('schema_version')!=1 or m.get('atlas_instance_id')!=instance or m.get('job_id')!=job_id:
        raise ValueError('knowledge_manifest_identity')
    artifacts=m['artifacts'];by_id={a['artifact_id']:a for a in artifacts}
    if len(by_id)!=len(artifacts) or ref['artifact_id'] in by_id:raise ValueError('knowledge_manifest_duplicates')
    for a in artifacts:
        if a['encoding']!='identity' or type(a['size']) is not int or not 0<=a['size']<=MAX_ARTIFACT:
            raise ValueError('knowledge_manifest_artifact')
    if sum(a['size'] for a in artifacts)+len(raw)>MAX_PACKAGE:raise ValueError('knowledge_package_size')
    qa=[a for a in artifacts if a['kind']=='qa']
    if len(qa)!=1 or qa[0]['sha256']!=m['qa_ref']['sha256']:raise ValueError('knowledge_manifest_qa')
    pages=m['consulted_pages'];page_ids=set();mapped=set()
    for page in pages:
        a=by_id.get(page['artifact_id'])
        if not a or a['kind']!='page' or a['sha256']!=page['sha256'] or page['page_id'] in page_ids or a['artifact_id'] in mapped:
            raise ValueError('knowledge_manifest_page')
        page_ids.add(page['page_id']);mapped.add(a['artifact_id'])
    if mapped!={a['artifact_id'] for a in artifacts if a['kind']=='page'}:raise ValueError('knowledge_manifest_page')
    candidates=set()
    for candidate in m['candidate_refs']:
        if candidate['qa_ref']!=m['qa_ref'] or candidate['candidate_id'] in candidates:raise ValueError('knowledge_manifest_candidate')
        candidates.add(candidate['candidate_id'])
    return m
