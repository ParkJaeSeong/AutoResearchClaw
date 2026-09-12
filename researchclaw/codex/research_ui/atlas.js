import {element,button,badge,renderValue,renderCouncil} from './detail.js';

const MAX_FILE_BYTES=10*1024*1024;
const reviewLabels={use:'사용',limited:'범위를 정해 사용',hold:'보류',exclude:'제외'};
const lines=value=>String(value??'').split(/\r?\n/).map(v=>v.trim()).filter(Boolean);
const sameRef=(left,right)=>Boolean(left&&right&&left.artifact_id===right.artifact_id&&left.sha256===right.sha256);
const keyOf=ref=>ref?`${ref.artifact_id??''}:${ref.sha256??''}`:'';
const anchorId=(kind,id)=>`atlas-${kind}-${String(id??'record').replace(/[^a-zA-Z0-9_-]/g,'-')}`;
function jump(text,target){const link=element('a',text);link.href=`#${target}`;return link;}
function questionText(value){return [`질문: ${value.question??''}`,`부족한 근거: ${value.missing_evidence??''}`,`답이 바꿀 판단: ${value.decision_impact??''}`,`요청 범위: ${value.scope??''}`].join('\n');}
export function findDescendantByKey(node,key){if(node?.dataset?.key===key)return node;for(const child of Array.from(node?.children??[])){const found=findDescendantByKey(child,key);if(found)return found;}return null;}
function commandId(){return globalThis.crypto?.randomUUID?.()??`atlas-${Date.now()}-${Math.random().toString(16).slice(2)}`;}
function base64(buffer){
  const bytes=new Uint8Array(buffer);let binary='';
  for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
  return btoa(binary);
}
async function post(path,payload){
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  let value={};try{value=await response.json();}catch{}
  if(!response.ok){const error=Error(value.error??value.message??`요청 실패 (${response.status})`);error.status=response.status;error.code=value.error;throw error;}return value;
}
function control(title,tag,key,state,field,options){
  const label=element('label',title,'atlas-control'),input=element(tag);input.dataset.key=key;
  if(options)for(const [value,text] of options){const option=element('option',text);option.value=value;input.append(option);}
  input.value=state[field]??'';input.addEventListener(tag==='select'?'change':'input',()=>{state[field]=input.value;});label.append(input);return label;
}
function setOptions(select,options,value){select.replaceChildren();for(const [id,text] of options){const option=element('option',text);option.value=id;select.append(option);}select.value=options.some(([id])=>id===value)?value:(options[0]?.[0]??'');return select.value;}
  function status(node,text,tone='muted'){node.textContent=text;node.className=tone;}
function refChoice(entries,title){return entries.map(entry=>[keyOf(entry.ref),entry.record?.title??entry.record?.qa?.question??entry.record?.id??title]);}

export function createAtlasPanel(root,options={}) {
  const request=options.request??post,getCurrentView=options.getCurrentView??(()=>null),newCommand=options.commandId??commandId;
  let view=null,historical=false,file=null,contentBase64=null,preview=null,fileGeneration=0,previewBusy=false;
  const mutationBusy=new Set(),retryPayloads=new Map();
  const state={reviewEvidence:'',reviewQuestion:'',reviewStatus:'limited',reviewAllowed:'',reviewHeld:'',reviewLimitations:'',reviewRationale:'',decisionReview:'',decisionPrior:'',decisionTitle:'',decisionConclusion:'',decisionRationale:'',decisionLimitations:'',questionDecision:'',question:'',missingEvidence:'',decisionImpact:'',questionScope:''};
  root.className='atlas-panel card';
  const header=element('header');header.append(element('p','ATLAS 연결','eyebrow'),element('h2','Atlas 답변 가져오기'),element('p','Atlas의 답변과 출처를 가져와, 이 연구에서 어떻게 사용할지 정리합니다.','muted'));
  const intake=element('section',undefined,'atlas-intake'),fileLabel=element('label','QA Markdown 파일','atlas-control'),fileInput=element('input');fileInput.type='file';fileInput.accept='.md,text/markdown';fileInput.dataset.key='atlas-file';fileLabel.append(fileInput);
  const intakeStatus=element('p','파일을 선택하면 내용을 먼저 확인합니다.','muted'),mutationStatus=element('p','저장할 내용을 확인한 뒤 실행하세요.','muted'),retryRoot=element('section',undefined,'atlas-retries'),previewRoot=element('div'),importButton=button('이 연구에 가져오기',importFile,'atlas-import');importButton.disabled=true;
  intake.append(element('h3','파일 미리보기'),fileLabel,intakeStatus,previewRoot,importButton,mutationStatus,retryRoot);
  const records=element('section'),forms=element('section',undefined,'atlas-forms');root.append(header,intake,records,forms);
  const mutationButtons=[],retryButtons=[];
  fileInput.addEventListener('change',previewFile);

  async function previewFile(){
    const generation=++fileGeneration,next=fileInput.files?.[0];file=null;contentBase64=null;preview=null;previewBusy=Boolean(next);drawPreview();gate();if(!next)return;
    if(next.size>MAX_FILE_BYTES){previewBusy=false;status(intakeStatus,'10 MiB를 넘는 파일은 미리 보거나 가져올 수 없습니다. 다른 파일을 선택하세요.','error');gate();return;}
    status(intakeStatus,`${next.name} · 미리보기 확인 중…`);
    try{const encoded=base64(await next.arrayBuffer()),parsed=await request('/api/atlas/preview',{content_base64:encoded});if(generation!==fileGeneration)return;file=next;contentBase64=encoded;preview=parsed;status(intakeStatus,`${next.name} · 미리보기 완료`);}
    catch(error){if(generation!==fileGeneration)return;status(intakeStatus,`미리보기에 실패했습니다. 가져오기는 실행되지 않습니다. ${error.message}`,'error');}
    finally{if(generation===fileGeneration){previewBusy=false;drawPreview();gate();}}
  }
  function drawPreview(){
    previewRoot.replaceChildren();if(!preview)return;
    const imported=(view?.external_evidence??[]).some(e=>e.record?.sha256===preview.file_sha256);const box=element('article',undefined,'atlas-preview');box.append(element('h4',preview.question??'질문 미제공'),badge(imported?'가져온 답변 미리보기':'가져오기 전 미리보기'));
    if(preview.answer!==undefined){const answer=element('details');answer.dataset.key='atlas-preview-answer';answer.append(element('summary','Atlas 답변 원문 펼치기'),element('p',preview.answer,'prose atlas-answer'));box.append(answer);}
    box.append(element('p',`참조 위키 ${preview.consulted_pages?.length??0}페이지 · 추가 후보 ${preview.candidates?.length??0}건`,'muted'));
    if(preview.missing_fields?.length)box.append(element('p',`미제공 항목: ${preview.missing_fields.join(', ')}`,'pending'));
    const meta=element('details');meta.append(element('summary','Atlas ID와 파일 해시'),element('p',preview.id??'ID 미제공','mono'),element('p',preview.file_sha256??'해시 미제공','mono'));box.append(meta);previewRoot.append(box);
  }
  const operationName=path=>({'/api/atlas/import':'답변 가져오기','/api/atlas/review':'사용 판단 저장','/api/atlas/decision':'조정자 결정 저장','/api/atlas/question':'질문 초안 저장'}[path]??'저장');
  function retrySummary(path,payload){if(path==='/api/atlas/import')return `${payload.filename} · ${(payload.sha256??'').slice(0,12)}`;if(path==='/api/atlas/review')return `${reviewLabels[payload.status]??payload.status} · ${payload.rationale||'이유 미입력'}`;if(path==='/api/atlas/decision')return `${payload.title||'제목 미입력'} · ${payload.conclusion||'결론 미입력'}`;return payload.question||'질문 미입력';}
  function drawRetries(){retryRoot.replaceChildren();retryButtons.length=0;for(const [path,payload] of retryPayloads){const row=element('article',undefined,'callout');row.append(element('strong',`${operationName(path)} 결과 확인 필요`),element('p',retrySummary(path,payload),'prose'),element('p','아래 버튼은 표시된 동일 요청과 command ID를 다시 보냅니다. 현재 입력의 일반 저장은 이 요청을 확인할 때까지 잠깁니다.','muted'));const retry=button('이 요청 그대로 다시 확인',()=>mutate(path,payload,retry,true),`atlas-retry-${path.split('/').at(-1)}`);retry.dataset.path=path;retryButtons.push(retry);row.append(retry);retryRoot.append(row);}}
  async function mutate(path,payload,buttonNode,explicitRetry=false){
    if(historical||mutationBusy.has(path)||retryPayloads.has(path)&&!explicitRetry)return;const sent=retryPayloads.get(path)??payload;mutationBusy.add(path);buttonNode.disabled=true;
    try{await request(path,sent);retryPayloads.delete(path);status(mutationStatus,'저장했습니다. 최신 연구 기록을 다시 불러옵니다.');
      try{await options.onRefresh?.();}catch(error){status(mutationStatus,`저장은 완료됐지만 화면을 새로 불러오지 못했습니다. 새로고침해 확인하세요. ${error.message}`,'warning');}}
    catch(error){if(error.status>=400&&error.status<500){retryPayloads.delete(path);status(mutationStatus,`저장되지 않았습니다. 입력을 고친 뒤 다시 시도하세요. ${error.message}`,'error');if(error.status===409){try{await options.onRefresh?.();}catch{}}}else{retryPayloads.set(path,sent);status(mutationStatus,`저장 결과를 확인하지 못했습니다. 아래에 고정된 요청을 명시적으로 다시 확인하세요. ${error.message}`,'warning');}}
    finally{mutationBusy.delete(path);drawRetries();gate();}
  }
  async function importFile(){if(!preview||!file||!contentBase64)return;const current=getCurrentView();await mutate('/api/atlas/import',{content_base64:contentBase64,sha256:preview.file_sha256,filename:file.name,expected_head:current.head_id,command_id:newCommand()},importButton);}
  function selectByKey(entries,key){return entries.find(entry=>keyOf(entry.ref)===key)?.ref??null;}
  function makeForm(title,description,fields,submitText,key,handler){const form=element('details',undefined,'atlas-form');form.dataset.key=`form:${key}`;form.append(element('summary',title),element('p',description,'muted'),...fields);const submit=button(submitText,handler,key);submit.dataset.operation=key;mutationButtons.push(submit);form.append(submit);return [form,submit];}
  let reviewEvidence,reviewQuestion,decisionReview,decisionPrior,questionDecision;
  function drawForms(){
    const active=document.activeElement,activeKey=active?.dataset?.key,start=active?.selectionStart,end=active?.selectionEnd;
    forms.replaceChildren();mutationButtons.length=0;
    const evidence=view?.external_evidence??[],reviews=view?.external_reviews??[],decisions=view?.external_decisions??[];
    const evidenceOptions=evidence.map(e=>[keyOf(e.ref),`${e.record?.qa?.question??e.record?.id??'Atlas 답변'} · ${e.latest===false?'이전':'현재'} · ${(e.record?.sha256??e.ref?.sha256??'').slice(0,8)}`]);
    const reviewOptions=reviews.map(r=>{const e=evidence.find(x=>sameRef(x.ref,r.record?.evidence_ref));return [keyOf(r.ref),`${e?.record?.qa?.question??'Atlas 답변'} · ${reviewLabels[r.record?.status]??r.record?.status??'미검토'} · ${(r.ref?.sha256??'').slice(0,8)}`];});
    reviewEvidence=element('select');reviewEvidence.dataset.key='atlas-review-evidence';state.reviewEvidence=setOptions(reviewEvidence,evidenceOptions,state.reviewEvidence);reviewEvidence.addEventListener('change',()=>state.reviewEvidence=reviewEvidence.value);
    const evidenceLabel=element('label','검토할 Atlas 답변','atlas-control');evidenceLabel.append(reviewEvidence);
    reviewQuestion=element('select');reviewQuestion.dataset.key='atlas-review-question';const nativeQuestions=(view?.revisions??[]).filter(r=>r.record?.node==='questions');const questionOptions=[...evidenceOptions,...nativeQuestions.map((r,i)=>[keyOf(r.ref),r.record.content?.question??`연구 질문 ${i+1}차`])];state.reviewQuestion=setOptions(reviewQuestion,questionOptions,state.reviewQuestion||state.reviewEvidence);reviewQuestion.addEventListener('change',()=>state.reviewQuestion=reviewQuestion.value);const questionLabel=element('label','관련 연구 질문','atlas-control');questionLabel.append(reviewQuestion);
    const statusControl=control('사용 판단','select','atlas-review-status',state,'reviewStatus',Object.entries(reviewLabels));
    const reviewBuilt=makeForm('답변 사용 범위 판단','가져온 사실과 사용할 수 있다는 판단을 구분해 저장합니다.',[evidenceLabel,questionLabel,statusControl,control('허용 용도 · 한 줄에 하나','textarea','atlas-review-allowed',state,'reviewAllowed'),control('보류 용도 · 한 줄에 하나','textarea','atlas-review-held',state,'reviewHeld'),control('한계 · 한 줄에 하나','textarea','atlas-review-limitations',state,'reviewLimitations'),control('판단 이유','textarea','atlas-review-rationale',state,'reviewRationale')],'사용 판단 저장','atlas-review-submit',async()=>{const current=getCurrentView();await mutate('/api/atlas/review',{expected_head:current.head_id,command_id:newCommand(),evidence_ref:selectByKey(evidence,state.reviewEvidence),question_ref:selectByKey([...evidence,...(view?.revisions??[])],state.reviewQuestion),status:state.reviewStatus,allowed_uses:lines(state.reviewAllowed),held_uses:lines(state.reviewHeld),limitations:lines(state.reviewLimitations),rationale:state.reviewRationale},reviewBuilt[1]);});forms.append(reviewBuilt[0]);
    decisionReview=element('select');decisionReview.dataset.key='atlas-decision-review';state.decisionReview=setOptions(decisionReview,reviewOptions,state.decisionReview);decisionReview.addEventListener('change',()=>state.decisionReview=decisionReview.value);const drLabel=element('label','근거 사용 판단','atlas-control');drLabel.append(decisionReview);
    decisionPrior=element('select');decisionPrior.dataset.key='atlas-decision-prior';state.decisionPrior=setOptions(decisionPrior,[['','새 결정'],...refChoice(decisions,'이전 결정')],state.decisionPrior);decisionPrior.addEventListener('change',()=>state.decisionPrior=decisionPrior.value);const priorLabel=element('label','이어 쓰는 이전 결정','atlas-control');priorLabel.append(decisionPrior);
    const decisionBuilt=makeForm('조정자 결정','조정자가 검토 기록을 바탕으로 내린 결정을 저장합니다. 에이전트 의견을 대신 만들지 않습니다.',[drLabel,priorLabel,control('결정 제목','input','atlas-decision-title',state,'decisionTitle'),control('결론','textarea','atlas-decision-conclusion',state,'decisionConclusion'),control('이유','textarea','atlas-decision-rationale',state,'decisionRationale'),control('한계 · 한 줄에 하나','textarea','atlas-decision-limitations',state,'decisionLimitations')],'조정자 결정 저장','atlas-decision-submit',async()=>{const current=getCurrentView();await mutate('/api/atlas/decision',{expected_head:current.head_id,command_id:newCommand(),review_ref:selectByKey(reviews,state.decisionReview),title:state.decisionTitle,conclusion:state.decisionConclusion,rationale:state.decisionRationale,limitations:lines(state.decisionLimitations),submission_refs:[],prior_ref:selectByKey(decisions,state.decisionPrior)},decisionBuilt[1]);});forms.append(decisionBuilt[0]);
    questionDecision=element('select');questionDecision.dataset.key='atlas-question-decision';state.questionDecision=setOptions(questionDecision,refChoice(decisions,'결정'),state.questionDecision);questionDecision.addEventListener('change',()=>state.questionDecision=questionDecision.value);const qdLabel=element('label','연결할 결정','atlas-control');qdLabel.append(questionDecision);
    const questionBuilt=makeForm('Atlas에 물어볼 질문','질문 초안을 연구 기록에 저장합니다. Atlas로 전송됐다는 상태는 만들지 않습니다.',[qdLabel,control('질문','textarea','atlas-question-text',state,'question'),control('부족한 근거','textarea','atlas-question-missing',state,'missingEvidence'),control('답이 바꿀 판단','textarea','atlas-question-impact',state,'decisionImpact'),control('요청 범위','input','atlas-question-scope',state,'questionScope')],'질문 초안 저장','atlas-question-submit',async()=>{const current=getCurrentView();await mutate('/api/atlas/question',{expected_head:current.head_id,command_id:newCommand(),decision_ref:selectByKey(decisions,state.questionDecision),question:state.question,missing_evidence:state.missingEvidence,decision_impact:state.decisionImpact,scope:state.questionScope},questionBuilt[1]);});
    const fallback=element('pre',undefined,'source-text atlas-copy-fallback');fallback.dataset.key='atlas-question-copy-text';const copy=button('질문 전체 복사',async()=>{const text=questionText({question:state.question,missing_evidence:state.missingEvidence,decision_impact:state.decisionImpact,scope:state.questionScope});fallback.textContent=text;try{if(!globalThis.navigator?.clipboard?.writeText)throw Error('clipboard unavailable');await globalThis.navigator.clipboard.writeText(text);status(intakeStatus,'질문 전체를 복사했습니다. 전송은 사용자가 직접 합니다.');}catch{status(intakeStatus,'자동 복사를 사용할 수 없습니다. 아래 전체 내용을 선택해 복사하세요.','warning');}},'atlas-question-copy');questionBuilt[0].append(copy,fallback);forms.append(questionBuilt[0]);gate();
    if(activeKey){const next=findDescendantByKey(forms,activeKey);next?.focus?.({preventScroll:true});if(Number.isInteger(start)&&next?.setSelectionRange)next.setSelectionRange(start,end);}
  }
  function drawRecords(){
    records.replaceChildren();const evidence=view?.external_evidence??[],reviews=view?.external_reviews??[],decisions=view?.external_decisions??[],questions=view?.external_questions??[];
    records.append(element('h3','가져온 Atlas 답변과 판단'));
    if(!evidence.length)records.append(element('p','아직 가져온 Atlas 답변이 없습니다. 파일을 선택해 내용을 먼저 확인하세요.','empty'));
    for(const entry of evidence){const r=entry.record,qa=r.qa??{},card=element('article',undefined,'atlas-record');card.id=anchorId('evidence',r.id);const linkedReviews=reviews.filter(x=>sameRef(x.record?.evidence_ref,entry.ref));const version=entry.latest===false?(entry.newer_ref?'이전 버전 · 새 답변 있음':'이전 버전'):'현재 버전';card.append(element('h4',qa.question??qa.id??r.id),badge(version,entry.latest===false?'pending':'neutral'),element('p',`가져옴 · ${linkedReviews.length?'사용 판단 있음':'검토 전'}`,'muted'));if(entry.possible_duplicate_refs?.length)card.append(element('p','같은 내용일 수 있는 다른 QA가 있습니다. 별개의 근거 수로 자동 합산하지 않습니다.','callout'),renderValue(view,entry.possible_duplicate_refs));for(const review of linkedReviews)card.append(jump('이 답변의 사용 판단 보기',anchorId('review',review.record.id)));
      const answer=element('details');answer.dataset.key=`atlas-answer:${r.id}`;answer.append(element('summary','Atlas 답변 원문 펼치기'),element('p',qa.answer??'답변 미제공','prose atlas-answer'));card.append(answer);
      const provenance=element('details');provenance.dataset.key=`atlas-source:${r.id}`;provenance.append(element('summary','출처·후보·버전 확인'),element('h4','Atlas가 확인했다고 기록한 출처'),renderValue(view,qa.consulted_pages??[]),element('h4','위키 반영 전 추가 후보'),renderValue(view,qa.candidates??[]),element('p',`QA ID: ${qa.id??'미제공'} · 파일: ${r.filename??'미제공'}`,'mono'),element('p',`SHA256: ${r.sha256??'미제공'}`,'mono'));card.append(provenance);records.append(card);}
    if(reviews.length){records.append(element('h3','답변 사용 범위'));for(const entry of reviews){const r=entry.record,card=element('article',undefined,'atlas-record');card.id=anchorId('review',r.id);card.append(element('h4',reviewLabels[r.status]??r.status??'미검토'),jump('검토한 Atlas 답변 보기',anchorId('evidence',evidence.find(e=>sameRef(e.ref,r.evidence_ref))?.record?.id)),element('p',r.rationale??'판단 이유 미제공','prose'),element('h4','허용 용도'),renderValue(view,r.allowed_uses??[]),element('h4','보류 용도'),renderValue(view,r.held_uses??[]),element('h4','한계'),renderValue(view,r.limitations??[]));for(const decision of decisions.filter(d=>sameRef(d.record?.review_ref,entry.ref)))card.append(jump('이 판단으로 내린 조정자 결정 보기',anchorId('decision',decision.record.id)));const councils=(view?.councils??[]).filter(c=>sameRef(c.input_binding,entry.ref));for(const council of councils){const details=element('details');details.dataset.key=`atlas-council:${council.id}`;details.append(element('summary','실제 에이전트 대화'));const body=element('div');renderCouncil(body,view,council);details.append(body);card.append(details);}records.append(card);}}
    if(decisions.length){records.append(element('h3','조정자 결정'));for(const entry of decisions){const r=entry.record,card=element('article',undefined,'atlas-record');card.id=anchorId('decision',r.id);const review=reviews.find(x=>sameRef(x.ref,r.review_ref)),used=evidence.find(x=>sameRef(x.ref,review?.record?.evidence_ref)),prior=decisions.find(x=>sameRef(x.ref,r.prior_ref));card.append(element('h4',r.title??r.id),badge(r.review_status==='council_final'?'실제 협의 최종 판단':'조정자 기록 · 연결된 에이전트 제출 없음',r.review_status==='council_final'?'neutral':'pending'),jump('근거 사용 판단 보기',anchorId('review',review?.record?.id)),element('p',r.conclusion??'결론 미제공','prose'),element('p',r.rationale??'이유 미제공','prose'),renderValue(view,r.limitations??[]));if(prior)card.append(jump('이어 쓴 이전 결정 보기',anchorId('decision',prior.record.id)));if(r.submission_refs?.length){const submissions=element('details');submissions.append(element('summary','결정에 사용한 에이전트 제출'),renderValue(view,r.submission_refs));card.append(submissions);}if(used?.newer_ref)card.append(element('p','이 결정은 이전 Atlas 답변으로 내렸습니다. 새 답변을 검토해 결정을 유지하거나 새 결정으로 이어 쓰세요.','callout'));records.append(card);}}
    if(questions.length){records.append(element('h3','저장한 추가 질문 초안'));for(const entry of questions){const r=entry.record,card=element('article',undefined,'atlas-record'),text=questionText(r),decision=decisions.find(x=>sameRef(x.ref,r.decision_ref));card.append(element('h4',r.question??r.id),jump('연결된 결정 보기',anchorId('decision',decision?.record?.id)),element('pre',text,'source-text'));const copy=button('이 질문 전체 복사',async()=>{try{if(!globalThis.navigator?.clipboard?.writeText)throw Error();await globalThis.navigator.clipboard.writeText(text);status(intakeStatus,'질문 전체를 복사했습니다. 전송은 사용자가 직접 합니다.');}catch{status(intakeStatus,'자동 복사를 사용할 수 없습니다. 표시된 전체 내용을 선택해 복사하세요.','warning');}},`atlas-copy:${r.id}`);card.append(copy);records.append(card);}}
  }
  function gate(){
    importButton.disabled=historical||previewBusy||!preview||mutationBusy.has('/api/atlas/import')||retryPayloads.has('/api/atlas/import');
    const available={'atlas-review-submit':Boolean(view?.external_evidence?.length),'atlas-decision-submit':Boolean(view?.external_reviews?.length),'atlas-question-submit':Boolean(view?.external_decisions?.length)};
    const paths={'atlas-review-submit':'/api/atlas/review','atlas-decision-submit':'/api/atlas/decision','atlas-question-submit':'/api/atlas/question'};
    for(const node of mutationButtons)node.disabled=historical||mutationBusy.has(paths[node.dataset.operation])||retryPayloads.has(paths[node.dataset.operation])||!available[node.dataset.operation];root.dataset.historical=String(historical);
    for(const node of retryButtons)node.disabled=historical||mutationBusy.has(node.dataset.path);
  }
  function update(next){view=next;drawRecords();drawForms();drawPreview();}
  function setHistorical(value){historical=Boolean(value);gate();}
  return {update,setHistorical};
}
