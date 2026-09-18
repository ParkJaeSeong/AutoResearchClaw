import test from 'node:test';
import assert from 'node:assert/strict';
const atlas=await import('../../../researchclaw/codex/research_ui/atlas.js').catch(()=>({}));

class Element {
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.events={};this._text='';this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.open=false;}
  set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set innerHTML(_){throw Error('unsafe HTML');} append(...v){this.children.push(...v);} replaceChildren(...v){this._text='';this.children=v;}
  setAttribute(k,v){this.attributes[k]=v;} addEventListener(k,v){this.events[k]=v;}
}
const all=n=>[n,...n.children.flatMap(all)];
const byKey=(root,key)=>all(root).find(n=>n.dataset.key===key);
const ref=(artifact_id,sha256)=>({project_id:'p',head_id:'h1',artifact_id,sha256});
const evidenceRef=ref('atlas/evidence/e1','evidence-sha');
const reviewRef=ref('atlas/reviews/r1','review-sha');
const decisionRef=ref('atlas/decisions/d1','decision-sha');
const view=()=>({head_id:'h1',external_evidence:[{ref:evidenceRef,latest:true,record:{id:'e1',filename:'qa.md',sha256:'file-sha',qa:{id:'qa-1',question:'공정 방향은?',answer:'<script>unsafe()</script>\n'.repeat(20),project:null,consulted_pages:[{title:'논문',locator:'/Users/name/private.pdf',sha256:'page-sha'}],candidates:[{title:'후보',url:'https://example.org/paper'}],missing_fields:['project']}}}],external_reviews:[{ref:reviewRef,record:{id:'r1',evidence_ref:evidenceRef,question_ref:evidenceRef,status:'limited',allowed_uses:['가설 비교'],held_uses:['수치 인용'],limitations:['원문 미확인'],rationale:'범위를 정해 사용'}}],external_decisions:[{ref:decisionRef,record:{id:'d1',review_ref:reviewRef,title:'조정자 판단',conclusion:'조건부 사용',rationale:'근거 범위 제한',limitations:['원문 미확인']}}],external_questions:[{ref:ref('atlas/questions/q1','q-sha'),record:{id:'q1',decision_ref:decisionRef,question:'측정 방향을 확인해 주세요',missing_evidence:'방향 정의',decision_impact:'사용 범위 변경',scope:'해당 논문'}}],revisions:[{ref:ref('m1/nodes/questions','native-sha'),record:{id:'native-question',node:'questions',content:{question:'Pilot 질문'}}}],councils:[{id:'c1',node:'external_evidence_review',input_binding:reviewRef,phase:'complete',participants:[],authors:[],required_roles:{},submitted_counts:{initial:0,response:0,final:0},disclosed_initials:[],disclosed_responses:[],disclosed_finals:[]}],artifacts:[]});

test('selected Atlas file preview and draft fields survive view refresh, while historical mode disables mutations',async()=>{
  assert.equal(typeof atlas.createAtlasPanel,'function');globalThis.document={createElement:t=>new Element(t)};
  const calls=[],root=new Element('section'),panel=atlas.createAtlasPanel(root,{getCurrentView:view,request:async(path,payload)=>{calls.push([path,payload]);return {id:'qa-1',question:'공정 방향은?',answer:'답변',project:null,consulted_pages:[],candidates:[],file_sha256:'abc',missing_fields:['project']};}});
  try{
    panel.update(view());const input=byKey(root,'atlas-file');input.files=[{name:'qa.md',size:12,arrayBuffer:async()=>Uint8Array.from([65,66]).buffer}];await input.events.change();
    assert.equal(calls[0][0],'/api/atlas/preview');assert.deepEqual(calls[0][1],{content_base64:'QUI='});assert.match(root.textContent,/공정 방향은\?/);
    const rationale=byKey(root,'atlas-review-rationale');rationale.value='내 판단';rationale.events.input();panel.update({...view(),head_id:'h2'});
    assert.equal(byKey(root,'atlas-file'),input);assert.equal(byKey(root,'atlas-review-rationale').value,'내 판단');assert.match(root.textContent,/공정 방향은\?/);
    panel.setHistorical(true);for(const key of ['atlas-import','atlas-review-submit','atlas-decision-submit','atlas-question-submit'])assert.equal(byKey(root,key).disabled,true,key);
  } finally {delete globalThis.document;}
});

test('10 MiB preflight rejects before preview request and invalidates the last importable preview',async()=>{
  globalThis.document={createElement:t=>new Element(t)};let calls=0;const root=new Element('section');
  const panel=atlas.createAtlasPanel(root,{getCurrentView:view,request:async()=>{calls++;return {id:'ok',question:'이전 질문',answer:'이전 답',consulted_pages:[],candidates:[],file_sha256:'ok',missing_fields:[]};}});
  try{panel.update(view());const input=byKey(root,'atlas-file');input.files=[{name:'ok.md',size:1,arrayBuffer:async()=>Uint8Array.from([65]).buffer}];await input.events.change();input.files=[{name:'large.md',size:10*1024*1024+1,arrayBuffer:async()=>new ArrayBuffer(0)}];await input.events.change();assert.equal(calls,1);assert.match(root.textContent,/10 MiB/);assert.doesNotMatch(root.textContent,/이전 질문/);assert.equal(byKey(root,'atlas-import').disabled,true);}finally{delete globalThis.document;}
});

test('a late preview response cannot replace the newer selected file',async()=>{globalThis.document={createElement:t=>new Element(t)};const completions=[],root=new Element('section'),panel=atlas.createAtlasPanel(root,{getCurrentView:view,request:()=>new Promise(done=>completions.push(done))});try{panel.update(view());const input=byKey(root,'atlas-file');input.files=[{name:'old.md',size:1,arrayBuffer:async()=>Uint8Array.from([65]).buffer}];const old=input.events.change();await Promise.resolve();input.files=[{name:'new.md',size:1,arrayBuffer:async()=>Uint8Array.from([66]).buffer}];const newer=input.events.change();await Promise.resolve();completions[1]({id:'new',question:'새 질문',answer:'새 답',consulted_pages:[],candidates:[],file_sha256:'new-sha'});await newer;completions[0]({id:'old',question:'옛 질문',answer:'옛 답',consulted_pages:[],candidates:[],file_sha256:'old-sha'});await old;assert.match(root.textContent,/새 질문/);assert.doesNotMatch(root.textContent,/옛 질문/);}finally{delete globalThis.document;}});

test('import and review send exact Atlas contracts and refresh current view',async()=>{
  globalThis.document={createElement:t=>new Element(t)};const calls=[];let refreshed=0;const root=new Element('section');
  const panel=atlas.createAtlasPanel(root,{getCurrentView:view,onRefresh:async()=>{refreshed++;},commandId:()=> 'cmd-1',request:async(path,payload)=>{calls.push([path,payload]);return path.endsWith('preview')?{id:'qa-1',question:'Q',answer:'A',consulted_pages:[],candidates:[],file_sha256:'abc',missing_fields:[]}:{head_id:'h2',record_id:'new'};}});
  try{panel.update(view());const file=byKey(root,'atlas-file');file.files=[{name:'qa.md',size:2,arrayBuffer:async()=>Uint8Array.from([65,66]).buffer}];await file.events.change();await byKey(root,'atlas-import').events.click();
    assert.deepEqual(calls[1],['/api/atlas/import',{content_base64:'QUI=',sha256:'abc',filename:'qa.md',expected_head:'h1',command_id:'cmd-1'}]);
    for(const [key,value,event='input'] of [['atlas-review-status','limited','change'],['atlas-review-allowed','가설 비교\n설계 참고'],['atlas-review-held','수치 인용'],['atlas-review-limitations','원문 미확인'],['atlas-review-rationale','범위를 정함']]){const input=byKey(root,key);input.value=value;input.events[event]();}await byKey(root,'atlas-review-submit').events.click();
    assert.deepEqual(calls[2],['/api/atlas/review',{expected_head:'h1',command_id:'cmd-1',evidence_ref:evidenceRef,question_ref:evidenceRef,status:'limited',allowed_uses:['가설 비교','설계 참고'],held_uses:['수치 인용'],limitations:['원문 미확인'],rationale:'범위를 정함'}]);assert.equal(refreshed,2);
  }finally{delete globalThis.document;}
});

test('coordinator decision and Atlas question draft use the bound refs without claiming agent work',async()=>{
  globalThis.document={createElement:t=>new Element(t)};const calls=[],root=new Element('section'),panel=atlas.createAtlasPanel(root,{getCurrentView:view,commandId:()=> 'cmd-2',request:async(path,payload)=>{calls.push([path,payload]);return {head_id:'h2',record_id:'saved'};}});
  const enter=(key,value)=>{const node=byKey(root,key);node.value=value;node.events.input();};
  try{panel.update(view());enter('atlas-decision-title','방향 판단');enter('atlas-decision-conclusion','조건부 채택');enter('atlas-decision-rationale','검토 범위에 맞음');enter('atlas-decision-limitations','원문 미확인');await byKey(root,'atlas-decision-submit').events.click();
    assert.deepEqual(calls[0],['/api/atlas/decision',{expected_head:'h1',command_id:'cmd-2',review_ref:reviewRef,title:'방향 판단',conclusion:'조건부 채택',rationale:'검토 범위에 맞음',limitations:['원문 미확인'],submission_refs:[],prior_ref:null}]);
    enter('atlas-question-text','방향 정의는?');enter('atlas-question-missing','측정축');enter('atlas-question-impact','인용 범위');enter('atlas-question-scope','본문 표');await byKey(root,'atlas-question-submit').events.click();
    assert.deepEqual(calls[1],['/api/atlas/question',{expected_head:'h1',command_id:'cmd-2',decision_ref:decisionRef,question:'방향 정의는?',missing_evidence:'측정축',decision_impact:'인용 범위',scope:'본문 표'}]);assert.match(root.textContent,/에이전트 의견을 대신 만들지 않습니다/);assert.match(root.textContent,/Atlas에는 아직 보내지 않습니다/);
  }finally{delete globalThis.document;}
});

test('ambiguous mutation retry is explicit, keeps command id, and distinguishes refresh failure',async()=>{globalThis.document={createElement:t=>new Element(t)};const calls=[],root=new Element('section');let attempt=0;const panel=atlas.createAtlasPanel(root,{getCurrentView:view,commandId:()=>`cmd-${++attempt}`,onRefresh:async()=>{throw Error('offline');},request:async(path,payload)=>{calls.push([path,payload]);if(calls.length===1)throw Error('network');return {head_id:'h2',record_id:'r'};}});try{panel.update(view());await byKey(root,'atlas-review-submit').events.click();assert.equal(byKey(root,'atlas-review-submit').disabled,true);assert.match(root.textContent,/범위를 정해 사용/);await byKey(root,'atlas-retry-review').events.click();assert.deepEqual(calls[0],calls[1]);assert.match(root.textContent,/저장은 완료됐지만 화면을 새로 불러오지 못했습니다/);}finally{delete globalThis.document;}});

test('forms are collapsed, missing prerequisites disable writes, and clipboard failure exposes full question context',async()=>{globalThis.document={createElement:t=>new Element(t)};Object.defineProperty(globalThis,'navigator',{value:{clipboard:{writeText:async()=>{throw Error('denied');}}},configurable:true});try{const root=new Element('section'),panel=atlas.createAtlasPanel(root,{getCurrentView:view,request:async()=>({})});panel.update({...view(),external_evidence:[],external_reviews:[],external_decisions:[],external_questions:[]});assert.equal(all(root).filter(n=>n.className==='atlas-form').every(n=>n.tagName==='DETAILS'&&!n.open),true);for(const key of ['atlas-review-submit','atlas-decision-submit','atlas-question-submit'])assert.equal(byKey(root,key).disabled,true);panel.update(view());const set=(key,value)=>{const n=byKey(root,key);n.value=value;n.events.input();};set('atlas-question-text','새 질문');set('atlas-question-missing','빠진 근거');set('atlas-question-impact','바뀔 판단');set('atlas-question-scope','표 2');await byKey(root,'atlas-question-copy').events.click();assert.match(byKey(root,'atlas-question-copy-text').textContent,/새 질문[\s\S]*빠진 근거[\s\S]*바뀔 판단[\s\S]*표 2/);assert.match(root.textContent,/선택해 복사/);}finally{delete globalThis.navigator;delete globalThis.document;}});

test('focus lookup accepts a real DOM-style HTMLCollection without Array methods',()=>{const target={dataset:{key:'wanted'},children:{length:0,[Symbol.iterator]:function*(){}}},children={0:target,length:1,[Symbol.iterator]:function*(){yield target;}};assert.equal(atlas.findDescendantByKey({dataset:{},children},'wanted'),target);});

test('definite 4xx uses corrected payload while transport retry freezes the submitted form',async()=>{globalThis.document={createElement:t=>new Element(t)};const root=new Element('section'),calls=[];let mode='400',ids=0;const panel=atlas.createAtlasPanel(root,{getCurrentView:view,commandId:()=>`cmd-${++ids}`,request:async(path,payload)=>{calls.push(payload);if(mode==='400'){const e=Error('bad');e.status=400;throw e;}if(mode==='network')throw Error('lost');return {};}});try{panel.update(view());await byKey(root,'atlas-review-submit').events.click();mode='ok';const rationale=byKey(root,'atlas-review-rationale');rationale.value='수정';rationale.events.input();await byKey(root,'atlas-review-submit').events.click();assert.equal(calls[0].command_id,'cmd-1');assert.equal(calls[1].command_id,'cmd-2');assert.equal(calls[1].rationale,'수정');mode='network';await byKey(root,'atlas-review-submit').events.click();rationale.value='새 수정';rationale.events.input();assert.equal(byKey(root,'atlas-review-submit').disabled,true);mode='ok';await byKey(root,'atlas-retry-review').events.click();assert.deepEqual(calls[2],calls[3]);await byKey(root,'atlas-review-submit').events.click();assert.equal(calls[4].rationale,'새 수정');assert.notEqual(calls[4].command_id,calls[3].command_id);}finally{delete globalThis.document;}});

test('failed import A never hides behind normal import after preview B',async()=>{globalThis.document={createElement:t=>new Element(t)};const root=new Element('section'),calls=[];let failImport=true;const panel=atlas.createAtlasPanel(root,{getCurrentView:view,commandId:()=>`cmd-${calls.length}`,request:async(path,payload)=>{calls.push([path,payload]);if(path.endsWith('preview'))return {id:payload.content_base64,question:payload.content_base64,answer:'A',consulted_pages:[],candidates:[],file_sha256:payload.content_base64};if(failImport)throw Error('lost');return {};}});try{panel.update(view());const input=byKey(root,'atlas-file');input.files=[{name:'A.md',size:1,arrayBuffer:async()=>Uint8Array.from([65]).buffer}];await input.events.change();await byKey(root,'atlas-import').events.click();input.files=[{name:'B.md',size:1,arrayBuffer:async()=>Uint8Array.from([66]).buffer}];await input.events.change();assert.match(root.textContent,/Qg==/);assert.equal(byKey(root,'atlas-import').disabled,true);failImport=false;await byKey(root,'atlas-retry-import').events.click();assert.equal(calls.at(-1)[1].filename,'A.md');await byKey(root,'atlas-import').events.click();assert.equal(calls.at(-1)[1].filename,'B.md');}finally{delete globalThis.document;}});

test('evidence, versions, decisions, drafts and exact review-bound real council render as inert text',()=>{
  globalThis.document={createElement:t=>new Element(t)};try{const root=new Element('section'),panel=atlas.createAtlasPanel(root,{getCurrentView:view,request:async()=>({})}),snapshot=view();snapshot.external_evidence[0].latest=false;snapshot.external_evidence[0].newer_ref=ref('atlas/evidence/e2','new-sha');snapshot.external_evidence[0].possible_duplicate_refs=[ref('atlas/evidence/other','dup-sha')];snapshot.external_decisions[0].record.review_status='coordinator_only';panel.update(snapshot);
    for(const text of ['Atlas에 질문하고 답변 가져오기','공정 방향은?','원문 미확인','조정자 판단','측정 방향을 확인해 주세요','실제 에이전트 대화','이전 버전 · 새 답변 있음','같은 내용일 수 있는 다른 QA','조정자 기록 · 연결된 에이전트 의견 없음','연결된 결정 보기'])assert.match(root.textContent,new RegExp(text));
    assert.equal(all(root).filter(n=>n.tagName==='SCRIPT').length,0);assert.equal(all(root).filter(n=>n.tagName==='A').some(n=>String(n.textContent).includes('/Users/name/private.pdf')),false);
    assert.ok(all(root).filter(n=>n.tagName==='A').some(n=>String(n.href).startsWith('#atlas-review-')));
  }finally{delete globalThis.document;}
});

test('preparation cards disclose missing and stale inputs and link exact source decisions without execution controls',()=>{
  globalThis.document={createElement:t=>new Element(t)};
  try{
    const root=new Element('section'),panel=atlas.createAtlasPanel(root,{getCurrentView:view}),snapshot=view();
    snapshot.m1_preparations=[{ref:ref('prep','prep-sha'),current:false,superseded:false,preparation_ready:false,missing_items:['measurement'],record:{id:'prep',decision_refs:{design:decisionRef,data_lineage:decisionRef},items:{measurement:{status:'missing',reason:'측정자와 교정 기록 미확인',owner_id:'owner',verification_refs:[]}}}}];
    panel.update(snapshot);
    assert.match(root.textContent,/실험 착수 준비/);
    assert.match(root.textContent,/검토에 사용한 자료가 바뀌었습니다/);
    assert.match(root.textContent,/측정자와 교정 기록 미확인/);
    assert.match(root.textContent,/준비 완료와 실험 실행 승인은 아직 확인되지 않았습니다/);
    assert.ok(all(root).some(n=>n.tagName==='A'&&n.textContent==='설계·분석 결정 보기'&&n.href==='#atlas-decision-d1'));
    assert.equal(all(root).some(n=>n.tagName==='BUTTON'&&n.textContent==='실험 시작'),false);
    snapshot.m1_preparations[0].current=true;snapshot.m1_preparations[0].superseded=true;panel.update(snapshot);
    assert.match(root.textContent,/이전 준비 기록/);
  }finally{delete globalThis.document;}
});

test('preparation assessment distinguishes checked evidence from M2 acceptance and old records',()=>{
  globalThis.document={createElement:t=>new Element(t)};
  try{
    const root=new Element('section'),panel=atlas.createAtlasPanel(root,{getCurrentView:view}),snapshot=view();
    snapshot.m1_preparations=[{ref:ref('prep','prep-sha'),current:true,superseded:false,preparation_ready:true,review_ready:true,external_handoff_supported:true,missing_items:[],record:{id:'prep',decision_refs:{design:decisionRef,data_lineage:decisionRef},items:{measurement:{status:'verified',reason:'교정 및 측정 범위 확인',owner_id:'owner',verification_refs:[ref('check','check-sha')]}}}}];
    snapshot.m1_preparation_verifications=[{ref:ref('check','check-sha'),record:{id:'check',evidence_ref:ref('source','source-sha'),rationale:'교정 기록과 단위를 확인했습니다',excerpt:'교정 확인 기록'}}];
    snapshot.m1_preparation_evidence=[{ref:ref('source','source-sha'),record:{id:'source',source_version:'2026-09-13'},source_ref:ref('raw','raw-sha')}];
    panel.update(snapshot);
    assert.match(root.textContent,/교정 기록과 단위를 확인했습니다/);
    assert.match(root.textContent,/자료 버전: 2026-09-13/);
    assert.match(root.textContent,/준비 증거 확인됨/);
    assert.match(root.textContent,/M2로 넘겼는지/);
    assert.doesNotMatch(root.textContent,/아직 구현되지 않았습니다/);
    snapshot.m1_preparations[0].current=false;panel.update(snapshot);
    assert.match(root.textContent,/다시 검토해야 합니다/);
    assert.doesNotMatch(root.textContent,/준비 증거 확인됨/);
  }finally{delete globalThis.document;}
});

test('Atlas service controls connect and preserve question key for retry',async()=>{
  const {createAtlasService}=await import('../../../researchclaw/codex/research_ui/atlas_service.js');
  globalThis.document={createElement:t=>new Element(t)};const root=new Element('section'),calls=[];
  try{
    const panel=createAtlasService(root,{getCurrentView:view,request:async(path,payload)=>{
      calls.push([path,payload]);if(path.endsWith('connect'))return {projects:[{id:'P',title:'Polymer'}],binding:{project:'P',title:'Polymer'},requests:[]};
      if(path.endsWith('ask'))throw Error('atlas_transport_unavailable');return {requests:[]};
    }});
    await byKey(root,'atlas-service-connect').events.click();
    assert.equal(byKey(root,'atlas-service-ask').textContent,'질문 보내기');
    byKey(root,'atlas-service-question').value='공정 조건은?';
    await byKey(root,'atlas-service-ask').events.click();assert.equal(byKey(root,'atlas-service-ask').textContent,'접수 다시 확인');await byKey(root,'atlas-service-ask').events.click();
    assert.equal(calls[1][1].key,calls[2][1].key);assert.match(root.textContent,/연결|확인/);
    panel.setHistorical(true);assert.equal(byKey(root,'atlas-service-ask').disabled,true);
  }finally{delete globalThis.document;}
});

test('stored service records load without a remote connect and historical views skip refresh',async()=>{
 globalThis.document={createElement:t=>new Element(t)};
 const calls=[],root=new Element('section');
 // Empty query is enough for the stored-knowledge renderer in this DOM test double.
 const original=Element.prototype.querySelectorAll;Element.prototype.querySelectorAll=()=>[];
 try {
  const panel=atlas.createAtlasPanel(root,{getCurrentView:view,request:async(path)=>{calls.push(path);return {requests:[],knowledge_jobs:[]};}});
  await panel.refresh();assert.deepEqual(calls,['/api/atlas/service-status']);
  panel.setHistorical(true);await panel.refresh();assert.equal(calls.length,1);
 } finally {if(original)Element.prototype.querySelectorAll=original;else delete Element.prototype.querySelectorAll;delete globalThis.document;}
});
