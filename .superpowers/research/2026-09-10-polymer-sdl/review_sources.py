"""One durable source-reading council. No model training or issue resolution."""
import base64
import concurrent.futures
import csv
import fcntl
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import study_host as host
from researchclaw.codex.source_review import SCHEMA, checked_text, make_prompt, validate_answer, readable_answer
from researchclaw.codex.literature_loop import wait_for_host
from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.councils import reviewer_packet

RUN=host.BASE/'source-analysis-01'
DATA=host.BASE/'discovery-runs/restart-02/coordinator-audit'
QUESTION='현재 확보한 PC/CNT 데이터로 공정·측정 조건의 영향을 비교할 수 있는가? Abbasi 2010의 25개 대응 행을 원문과 대조하고, PC/CNT 전체로 넓혀 주장할 수 있는 범위를 구분한다.'


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)


def saved(path,fn):
    if path.exists():return json.loads(path.read_text())
    value=fn();save(path,value);return value


def apply(name,operation,fn):
    payload=saved(RUN/(name+'-payload.json'),fn)
    return commands.apply_command(host.ROOT,operation=operation,payload=payload,expected_head=host.head()['id'],command_id='source-analysis-01:'+name)


def prepare():
    original=json.loads((DATA/'native-source-capture.json').read_text())['captures']
    meta={r['filename']:r for r in original}
    for name,r in meta.items():
        data=(DATA/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=r['sha256']:raise ValueError('source_hash_mismatch')
        shutil.copyfile(DATA/name,RUN/'sources'/name)
    def text(name):return checked_text((DATA/name).read_bytes(),meta[name]['sha256'])
    rows=list(csv.DictReader(text('data_EC.csv').splitlines()))
    detail=list(csv.DictReader(text('sample_detail_EC.csv').splitlines()))
    # CSV record numbers, not physical line numbers (quoted cells can span lines).
    columns=['id','PID','filler','rid','expt','vol%','log10(EC)','temperature','log10(thickness)','dc','ac','disk','film','sheet','two-probe','four-probe']
    pc=[(i,r) for i,r in enumerate(rows,1) if r['PID']=='P150011' and 'CNT' in r['filler']]
    projected=['CSV data record number (header excluded) | '+' | '.join(columns)]
    projected += [str(i)+' | '+' | '.join(r[k] for k in columns) for i,r in pc]
    cols=['Sample ID','Name','Additives','[proc] Compression','[proc] Microinjection','[proc] Microinjection-compression','[proc] Shape of Test Piece','[proc] Remarks','Method','Condition','elecon','[elecon] condition','[elecon] remarks','[elecon] method','[elecon] temp','thickness_raw','thickness','log10(thickness)','Reference']
    details=['Each line is one original CSV record projected to named columns. Empty original cells remain empty.']
    details += [json.dumps({'csv_record':i,**{k:r[k] for k in cols}},ensure_ascii=False) for i,r in enumerate(detail,1) if r['Sample ID'].startswith('42969-')]
    subprocess.run(['pdftotext','-layout',str(RUN/'sources/abbasi-2010.pdf'),str(RUN/'sources/abbasi-full.txt')],check=True)
    full=(RUN/'sources/abbasi-full.txt').read_text();pages=full.split('\f')
    pdf='\n'.join(f'PDF page {i}; printed page {920+i}\n'+pages[i-1] for i in [3,4,12])
    notebook=json.loads(text('upstream-make_expt_id.ipynb'))
    code='\n'.join(f'Notebook cell {i} ({c["cell_type"]})\n'+''.join(c['source']) for i,c in enumerate(notebook['cells']))
    specs=[('S1','PC/CNT 전체 처리 데이터의 선택 열','data_EC.csv','\n'.join(projected)),
           ('S2','Abbasi 논문에 대응하는 원자료 행','sample_detail_EC.csv','\n'.join(details)),
           ('S3','Abbasi 2010 제조·측정 방법과 그림12 주변 본문','abbasi-2010.pdf',pdf),
           ('S4','저자 저장소 README','upstream-README.md',text('upstream-README.md')),
           ('S5','저자 공개 그룹 생성 노트북의 전체 셀','upstream-make_expt_id.ipynb',code)]
    mats=[];captures=[]
    for identity,title,name,content in specs:
        source=meta[name]
        header=f'{title}\n원자료: {name}\n원자료 SHA256: {source["sha256"]}\n출처: {source["access_url"]}\n변환: CSV 열 선택/JSON 셀 표시 또는 pdftotext -layout. 과학적 해석을 추가하지 않은 전달 자료.\n'
        content=header+content
        m=dict(id=identity,title=title,text=content,original_sha256=source['sha256'],source_url=source['access_url'])
        (RUN/'sources'/f'{identity}.txt').write_text(content)
        captures.append(dict(source_key=source['source_key']+':reading-excerpt:'+identity,source_version=source['source_version'],
            access_url=source['access_url'],access_status='full_text',filename=identity+'-reading-excerpt.txt',
            reading_scope=title+'; source-analysis-01 mechanical excerpt. Full source hash is embedded.',
            limitations=['기계적으로 추출한 전달 자료이며 원문 전체 독해·자료 사용 승인·과학적 검증 완료가 아니다.','PDF 텍스트 추출에는 열 순서·수식·그림 값 손실이 있을 수 있다.'],
            producer_id='source-reader-preparation',sha256=hashlib.sha256(content.encode()).hexdigest(),content_base64=base64.b64encode(content.encode()).decode()))
        mats.append(m)
    return dict(materials=mats,captures=captures,pc_rows=len(pc),detail_rows=len(details)-1)


def run_host(role,phase,materials,peers,inbound):
    folder=RUN/f'{phase}-{role}';folder.mkdir(exist_ok=True)
    prompt=make_prompt(role,phase,QUESTION,materials,peers,inbound)
    if (folder/'prompt.txt').exists() and (folder/'prompt.txt').read_text()!=prompt:raise ValueError('resume_input_changed')
    (folder/'prompt.txt').write_text(prompt)
    save(folder/'schema.json',SCHEMA)
    workspace=folder/'workspace';workspace.mkdir(exist_ok=True)
    if not (workspace/'sources').exists():shutil.copytree(RUN/'sources',workspace/'sources')
    if not (folder/'answer.json').exists():
        if (folder/'events.jsonl').exists():raise RuntimeError('Preserved incomplete host attempt: '+str(folder))
        with (folder/'prompt.txt').open() as inp,(folder/'events.jsonl').open('w') as out,(folder/'stderr.txt').open('w') as err:
            process=subprocess.Popen([str(host.HOST),'exec','--sandbox','read-only','--skip-git-repo-check','--json','--output-schema',str(folder/'schema.json'),'--output-last-message',str(folder/'answer.json'),'-'],stdin=inp,stdout=out,stderr=err,cwd=workspace)
            if wait_for_host(process,folder):raise RuntimeError('Host failed: '+str(folder))
    a=json.loads((folder/'answer.json').read_text())
    original_folder=folder
    original_prompt=prompt
    try:
        validate_answer(a,materials,phase,inbound,role=role)
    except ValueError as error:
        # Preserve the invalid original; a new real host must correct its own citations.
        folder=original_folder/'correction-01';folder.mkdir(exist_ok=True)
        prompt=original_prompt+'\nVALIDATION_ERROR: '+str(error)+'\nPREVIOUS_ANSWER: '+json.dumps(a,ensure_ascii=False)+"\n이전 응답을 검증기가 거부했다. 모든 인용을 sources/S*.txt의 정확한 줄과 대조해 수정한 전체 JSON을 제출하라. PDF 두 단의 문장을 합치거나 공백을 바꾸어 인용하지 말고 연속된 짧은 원문 부분을 그대로 복사하라. 근거가 없으면 주장을 수정하고 불확실성을 남긴다. 다른 역할의 미공개 자료는 읽지 않는다."
        if (folder/'prompt.txt').exists() and (folder/'prompt.txt').read_text()!=prompt:raise ValueError('correction_input_changed')
        (folder/'prompt.txt').write_text(prompt);save(folder/'schema.json',SCHEMA)
        if not (folder/'answer.json').exists():
            if (folder/'events.jsonl').exists():raise RuntimeError('Preserved incomplete correction: '+str(folder))
            with (folder/'prompt.txt').open() as inp,(folder/'events.jsonl').open('w') as out,(folder/'stderr.txt').open('w') as err:
                process=subprocess.Popen([str(host.HOST),'exec','--sandbox','read-only','--skip-git-repo-check','--json','--output-schema',str(folder/'schema.json'),'--output-last-message',str(folder/'answer.json'),'-'],stdin=inp,stdout=out,stderr=err,cwd=workspace)
                if wait_for_host(process,folder):raise RuntimeError('Correction host failed: '+str(folder))
        a=json.loads((folder/'answer.json').read_text());validate_answer(a,materials,phase,inbound,role=role)
    events=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines() if l.startswith('{')]
    thread=next(e['thread_id'] for e in events if e['type']=='thread.started')
    result=dict(role=role,phase=phase,answer=a,host_id='codex-exec:'+thread,
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                material_hashes={m['id']:hashlib.sha256(m['text'].encode()).hexdigest() for m in materials},
                tool_calls=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type') not in ('reasoning','agent_message')])
    result['original_prompt_sha256']=hashlib.sha256(original_prompt.encode()).hexdigest()
    result['answer_path']=str(folder/'answer.json')
    result['corrected']=folder!=original_folder
    save(original_folder/'verified-answer.json',result)
    return result


def main():
    RUN.mkdir(exist_ok=True);(RUN/'sources').mkdir(exist_ok=True)
    lock=(RUN/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    prepared=saved(RUN/'prepared.json',prepare)
    apply('capture','m1.source.capture',lambda:dict(captures=prepared['captures']))
    materials=prepared['materials'];h=host.head()
    for m,c in zip(materials,prepared['captures']):
        m['ref']=dict(project_id=h['state']['project_id'],head_id=saved(RUN/'capture-head.json',lambda:h['id']),artifact_id='m1/intake/blobs/'+c['sha256'],sha256=c['sha256'])
    save(RUN/'materials.json',materials)
    def setup():
        project=host.head()['state']['project_id']
        authors=[dict(id=host.uid(),project_id=project,actor_id='source-analysis-coordinator',role='owner',milestone='M1',active=True)]
        actors=[dict(id=host.uid(),project_id=project,actor_id='source-reader-'+r,role='resolver',milestone='M1',active=True) for r in host.ROLES]
        session=dict(id=host.uid(),project_id=project,input_binding=materials[0]['ref'],participant_assignment_ids=[a['id'] for a in actors],frozen=True)
        council={**host.envelope('source-analysis-coordinator'),'session_id':session['id'],'milestone':'M1','node':'source_analysis','attempt':host.uid(),
                 'author_assignment_ids':[authors[0]['id']],'required_roles':dict(zip(host.ROLES,[a['id'] for a in actors])),
                 'allowed_evidence_refs':[m['ref'] for m in materials],'issue_ids':[]}
        return dict(assignments=authors+actors,review_session=session,council=council)
    apply('council','council.prepare',setup)
    config=json.loads((RUN/'council-payload.json').read_text());council=config['council'];actors=config['assignments'][1:]
    for phase in ('initial','response','final'):
        prior=[] if phase=='initial' else [json.loads((RUN/f'{p}-{r}/verified-answer.json').read_text()) for p in (['initial'] if phase=='response' else ['initial','response']) for r in host.ROLES]
        jobs=[]
        for role,actor in zip(host.ROLES,actors):
            saved(RUN/f'{phase}-{role}-packet.json',lambda:reviewer_packet(host.snap(),actor['id']))
            peers=[dict(role=x['role'],phase=x['phase'],answer=x['answer']) for x in prior]
            target_phase='initial' if phase=='response' else 'response'
            inbound=[q for x in prior if x['phase']==target_phase for q in x['answer']['questions'] if q['to_role']==role]
            jobs.append((role,phase,materials,peers,inbound))
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            answers=list(pool.map(lambda args:run_host(*args),jobs))
        for actor,result in zip(actors,answers):
            role=result['role'];a=result['answer']
            def payload():
                packet=json.loads((RUN/f'{phase}-{role}-packet.json').read_text())
                citations=[c for f in a['findings'] for c in f['citations']]+[c for x in a['answers'] for c in x['citations']]
                refs=[m['ref'] for m in materials if m['id'] in {c['source_id'] for c in citations}]
                prior_rows=packet['disclosed_initials'] if phase=='response' else packet['disclosed_responses']
                return dict(submission={**host.envelope(actor['actor_id']),'session_id':council['session_id'],'assignment_id':actor['id'],
                    'input_binding':materials[0]['ref'],'phase':phase,'rationale':readable_answer(a),'evidence_refs':refs,
                    'positions':[],'retained_position_refs':[],'response_refs':[x['submission_ref'] for x in prior_rows] if phase!='initial' else [],
                    'issue_proposals':[],'recommendation':None if phase!='final' else {'usable_for_comparison':'ready','limited_use':'ready_with_limits','insufficient':'defer'}[a['decision']],
                    'host_id':result['host_id'],'model_id':'codex-cli-default-unverified'})
            apply(phase+'-'+role,'council.submit',payload)
        print(json.dumps(dict(phase=phase,council_id=council['id'],head=host.head()['id']),ensure_ascii=False),flush=True)
    save(RUN/'result.json',dict(head_id=host.head()['id'],council_id=council['id'],question=QUESTION,
        decisions={r:json.loads((RUN/f'final-{r}/verified-answer.json').read_text())['answer']['decision'] for r in host.ROLES},
        scientific_verification=False,issues_resolved=False))

if __name__=='__main__':main()
