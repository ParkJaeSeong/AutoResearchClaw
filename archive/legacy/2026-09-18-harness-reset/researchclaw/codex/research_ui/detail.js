import {refKey,resolveRef,rawURL,sourceURL,compareHypotheses} from './trace.js';
export function element(tag,text,className) {
  const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);if(className)node.className=className;return node;
}
export function button(text,action,key) {
  const node=element('button',text);node.type='button';if(key)node.dataset.key=key;node.addEventListener('click',action);return node;
}
export const LABELS={scope:'범위',questions:'연구 질문',search:'문헌 검색',screen:'문헌 선정',collect:'원문 수집',extract:'근거 추출',synthesize:'근거 종합',hypothesize:'가설',review:'최종 검토',handoff:'인계',
 ready:'필수 기록 갖춤',awaiting_input:'추가 검토 필요',not_started:'등록된 작업 없음',stale:'재검토 필요',unknown:'확인되지 않음',initial:'각자 쓴 첫 의견',response:'서로의 의견 검토',final:'최종 판단',complete:'의견 작성 완료',
 ready_with_limits:'범위를 정해 진행하자는 의견',revise:'수정 의견',defer:'판단을 보류하자는 의견',domain:'소재 전문가',methodology:'평가 방법 검토자',critical:'실험·실행 검토자',owner:'담당',resolver:'검토자',
 open:'해결 전',checking:'검증 중',resolved:'해결됨',reopened:'다시 검토 중',transferred:'담당 변경 · 해결 전',deferred:'대기',superseded:'후속 문제 있음 · 해결 전',pending_policy_revalidation:'이전 문제 · 진행 조건 재검토 대기',
 supported:'지지 결과',refuted:'반박 결과',inconclusive:'불충분',failed:'실패',pending:'결과 대기',accepted:'받는 쪽에서 수락함',issued_awaiting_acceptance:'인계 자료 발행 · 받는 쪽의 수락 대기',
 user_goal:'연구 목표',user_constraints:'사용자가 정한 조건',agent_assumptions:'에이전트가 둔 가정',question:'확인 질문',rationale:'판단 이유',revision_reason:'수정 이유',statement:'가설 내용',prediction:'예측',population:'대상 범위',falsification_condition:'반증 조건',
 findings:'종합 근거',claim:'주장',claims:'추출 근거',hypotheses:'가설 목록',rejected_alternatives:'채택하지 않은 대안',description:'설명',reason:'이유',limitations:'한계',evidence_refs:'근거 원문',counterevidence_refs:'반대 근거',
 sources:'자료',source_id:'자료 ID',source_ref:'원문 버전',title:'제목',url:'원문 주소',doi:'DOI',arxiv_id:'arXiv ID',raw_text:'제공 원문',access_status:'확인 범위',access_level:'확인 범위',locator:'원문 위치',span_start:'시작 위치',span_end:'끝 위치',extracted_text:'추출 구절',interpretation:'해석',
 source_type:'자료 유형',origin_group_id:'같은 원자료를 쓴 그룹',origin_description:'원자료 설명',source_groups:'같은 원자료를 쓴 그룹',origin_group_count:'원천 그룹 수',source_count:'자료 수',unknown_sources:'원자료를 확인하지 못한 자료',
 prior_issue_dispositions:'이전 문제의 처리 내역',open_questions:'아직 답하지 못한 질문',owner_assignment_id:'담당 배정 ID',disposition:'처리 방침',carry_forward:'그대로 보존',verification_planned:'검증 예정',native_resolved:'해소 기록 연결',transfer_proposed:'담당 이전 제안',
 method:'확인 방법',acceptance_rule:'판정 기준',resolution_condition:'해결됐다고 판단할 기준',verification_refs:'검증 기록',output_refs:'결과 근거',checked_scope:'실제 확인 범위',outcome:'결과',status:'상태',scope_refs:'승인 범위',binding:'승인 대상 버전',validity:'유효성',
 queries:'검색어',inclusion_criteria:'포함 기준',exclusion_criteria:'제외 기준',search_log:'검색 기록',candidates:'후보 자료',decisions:'선정 판단',decision:'판단',search_ids:'검색 기록 ID',stance:'입장',approve:'승인',approved:'승인 여부',
 from_milestone:'보낸 단계',to_milestone:'받는 단계',unresolved_issue_ids:'아직 해결하지 못한 문제',transfer_proposals:'담당 이전 제안',acceptance_ref:'수락 기록',artifact_refs:'패키지 원문',from_status:'이전 상태',to_status:'변경 상태',actor_assignment_id:'변경 담당 배정',successor_ids:'후속 쟁점',
 change_kind:'의견을 바꾼 이유',changed_from:'이전 입장',retained_position_refs:'유지한 의견',response_refs:'응답 대상',issue_proposals:'새 쟁점 제안',recommendation:'최종 의견',observation_refs:'관측 근거',provenance_status:'작성·실행 출처 확인 방식',content_origin:'자료 구분'};
Object.assign(LABELS,{budget_ref:'예산 기록',event_id:'변경 기록 ID',id:'기록 ID',input_refs:'검토에 사용한 자료',issue_ids:'관련 문제 ID',producer_id:'작성자 ID',project_id:'프로젝트 ID',schema_version:'기록 형식 버전',workflow_version:'연구 절차 버전',positions:'주장별 의견',hypothesis_id:'가설 ID',collected_source_refs:'확보한 원문',extraction_refs:'추출한 근거',
 blocking:'진행 전 확인 필수',major:'주요 문제',minor:'보완할 문제',blocking_scope:'해결 전 보류할 작업',effective_blocking_scope:'현재 보류할 작업',
 category:'문제 유형',severity:'중요도',target_refs:'대상 자료',source_key:'자료 식별자',source_version:'자료 버전',reading_scope:'읽은 범위',
 filename:'파일 이름',evidence_ref:'근거 자료',review_ref:'검토 기록',decision_ref:'결정 기록',prior_ref:'이전 결정',allowed_uses:'사용할 수 있는 용도',held_uses:'사용을 보류할 용도',
 missing_evidence:'부족한 근거',decision_impact:'답에 따라 달라질 결정',source_refs:'출처 자료',consulted_pages:'참고한 위키 페이지',
 decision_refs:'준비의 바탕이 된 결정',items:'준비 항목',verification_refs:'검증 기록',not_applicable:'이 연구에 적용하지 않음',verified:'검증됨'});
const CHECK_REASONS={
 return_plan_required:'무엇이 부족한지, 어떤 판단에 영향을 주는지, 확인할 근거와 확인되지 않을 때의 처리를 적어 주세요.',
 return_policy_invalid:'재검토 진행 기준을 읽지 못했습니다. 저장된 정책을 확인해 주세요.',
 repeated_work:'같은 입력으로 같은 작업을 이미 수행했습니다. 추가 근거나 접근 방법을 확인해 주세요.',
 semantic_identity_uncertain:'앞선 작업과 같은 논의인지 판단이 필요합니다. 달라진 근거나 접근 방법을 확인해 주세요.',
 blocking_issue_unresolved:'이 단계를 마치려면 남은 문제를 먼저 확인해야 합니다.',
 council_required:'다음 단계로 가기 전에 에이전트 검토가 필요합니다.',
 issue_reference_stale:'문제 기록이 바뀌었습니다. 이전 검토가 여전히 맞는지 확인해야 합니다.',
 node_missing:'필요한 단계의 기록이 아직 없습니다.',
 preparation_decision_superseded:'준비에 사용한 결정이 수정됐습니다. 새 결정에 맞춰 준비를 다시 확인해야 합니다.',
 preparation_draft_only:'실험 준비는 아직 초안입니다. 준비 근거를 확인해야 합니다.',
 preparation_items_missing:'아직 확인하지 않은 실험 준비 항목이 있습니다.',
 work_source_invalid:'작업의 근거 기록을 확인할 수 없습니다. 출처와 버전을 확인해야 합니다.'
};
export function renderChecks(root,codes=[],actions=[]) {
  if(!codes.length&&!actions.length)return;
  for(const code of [...new Set(codes)])root.append(element('p',CHECK_REASONS[code]??'추가로 확인할 조건이 있습니다. 자세한 내용은 확인 기록을 펼쳐보세요.','pending'));
  for(const action of actions){const known=/^Address ([a-z_]+) before advancing(?: this node)?\.$/.exec(action);if(known&&codes.includes(known[1]))continue;if(/[가-힣]/.test(action))root.append(element('p',action,'prose'));}
  const technical=element('details');technical.dataset.key='check-records';technical.append(element('summary','확인 기록 · 오류 코드'),element('pre',JSON.stringify({reason_codes:codes,required_actions:actions},null,2),'record-json'));root.append(technical);
}
export const label=value=>Object.hasOwn(LABELS,value)?LABELS[value]:String(value??'기록 없음');
export function badge(text,tone='neutral') {return element('span',text,`badge ${tone}`);}
export function recordDetails(title,value,key) {
  const node=element('details');if(key)node.dataset.key=key;
  node.append(element('summary',title),element('pre',JSON.stringify(value,null,2),'record-json'));return node;
}
export function renderRef(view,ref) {
  const wrap=element('span',undefined,'reference');const item=resolveRef(view,ref),url=rawURL(view,item);
  const source=(view.source_captures??[]).find(({record:r})=>r.project_id===ref?.project_id&&r.sha256===ref?.sha256&&ref?.artifact_id===`m1/intake/blobs/${r.sha256}`);
  if(url){const a=element('a',`${source?.record.filename??item.label} · 원문`);a.href=url;a.target='_blank';a.rel='noopener noreferrer';wrap.append(a);}
  else wrap.append(element('span',`${ref?.artifact_id??'참조'} · 이 버전의 공개 원문 없음`,'warning'));
  wrap.append(element('small',`${ref?.sha256?.slice(0,12)??'해시 없음'} · HEAD ${ref?.head_id?.slice(0,12)??'없음'}`));
  return wrap;
}
export function renderCandidates(view,candidates,path) {
  const root=element('section',undefined,'candidate-list'),filter=element('label',undefined,'candidate-filter');
  const input=element('input');input.type='search';input.placeholder='제목, DOI, arXiv ID로 찾기';input.dataset.key=`candidate-filter:${path}`;input.dataset.candidateFilter=path;
  filter.append(element('span','후보 자료 찾기'),input);
  const count=element('p',undefined,'muted');count.setAttribute('role','status');
  root.append(filter,count);
  const list=element('ul',undefined,'candidate-rows'),items=[];
  const accessLabels={full_text:'원문',abstract:'초록',metadata_only:'서지 정보',unavailable:'접근 불가'};
  const typeLabels={reference_record:'서지 기록',research_article:'연구 논문'};
  const stanceLabels={support:'지지',oppose:'반대',neutral:'중립',unknown:'판단 기록 없음'};
  candidates.forEach((candidate,index)=>{
    const item=element('li',undefined,'candidate-item'),row=element('details',undefined,'candidate-row');row.dataset.key=`candidate:${path}:${index}`;
    const summary=element('summary'),title=element('span',candidate.title||'제목 미기록','candidate-title');
    summary.append(title,element('span',`기록된 확인 범위: ${accessLabels[candidate.access_status]??candidate.access_status??'기록 없음'}`,'candidate-access muted'));
    row.append(summary);
    const fields={};
    for(const [key,value] of Object.entries(candidate)){
      if(['title','url','access_status','source_id','search_ids'].includes(key)||value==null)continue;
      fields[key]=key==='source_type'?(typeLabels[value]??value):key==='stance'?(stanceLabels[value]??value):value;
    }
    const body=element('div',undefined,'candidate-body');body.append(renderValue(view,fields),recordDetails('저장된 자료 정보',candidate,`candidate-record:${path}:${index}`));row.append(body);item.append(row);
    const url=sourceURL(candidate.url);
    if(url){const link=element('a','원문 열기','candidate-link');link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.setAttribute('aria-label',`${candidate.title||'제목 미기록'} · 원문 열기`);item.append(link);}
    items.push({item,text:[candidate.title,candidate.doi,candidate.arxiv_id].filter(Boolean).join(' ').toLocaleLowerCase()});list.append(item);
  });
  const empty=element('p','검색어와 일치하는 후보 자료가 없습니다.','muted');
  const update=()=>{const query=(input.value??'').trim().toLocaleLowerCase();let shown=0;for(const entry of items){entry.item.hidden=!entry.text.includes(query);if(!entry.item.hidden)shown++;}count.textContent=query?`${candidates.length}건 중 ${shown}건`:`후보 자료 ${candidates.length}건`;empty.hidden=shown!==0;};
  input.addEventListener('input',update);update();root.append(list,empty);return root;
}
export function renderValue(view,value,key='',path=key) {
  if(refKey(value)) return renderRef(view,value);
  if(value===null || value===undefined) return element('span','기록 없음','muted');
  if(Array.isArray(value)) {
    if(!value.length)return element('span','기록 없음','muted');
    if(key==='candidates'&&value.every(item=>item&&typeof item==='object'&&!Array.isArray(item)&&!refKey(item)))return renderCandidates(view,value,path);
    const list=element('ul',undefined,value.every(item=>typeof item==='string')?'records text-list':'records');value.forEach((item,i)=>{const li=element('li');li.append(renderValue(view,item,'',`${path}/${i}`));list.append(li);});return list;
  }
  if(typeof value==='object') {
    const fields=element('dl',undefined,'fields');for(const [field,item] of Object.entries(value)) {
      const dt=element('dt',label(field));const dd=element('dd');dd.append(renderValue(view,item,field,`${path}/${field}`));fields.append(dt,dd);
    }return fields;
  }
  if(key==='url' && sourceURL(value)){const a=element('a',value);a.href=sourceURL(value);a.target='_blank';a.rel='noopener noreferrer';return a;}
  if(key==='raw_text'){const d=element('details');d.dataset.key=path;d.append(element('summary','제공 원문 펼치기'),element('pre',value,'source-text'));return d;}
  const enums=['status','outcome','disposition','stance','decision','from_status','to_status','recommendation'];
  return element('span',typeof value==='boolean' ? (value?'예':'아니오') : enums.includes(key)?label(value):value,'prose');
}
export function assessment(root,title,value,flag='ready') {
  const section=element('section',undefined,'assessment');section.append(element('h3',title));
  section.append(badge(value?.[flag]===true ? '조건 충족' : value ? '조건 확인 필요' : '아직 기록 없음',value?.[flag]===true?'ok':'pending'));
  renderChecks(section,value?.reason_codes??[],value?.required_actions??[]);
  root.append(section);return section;
}
export function renderRevision(root,view,revision) {
  root.replaceChildren();if(!revision){root.append(element('p','아직 저장된 기록 버전이 없습니다.','empty'));return;}
  const r=revision.record;
  root.append(element('h2',`${label(r.node)} · 선택한 버전`),element('p',r.id,'mono'),badge(revision.current?'현재 버전':'이전 버전',revision.current?'neutral':'pending'));
  if(r.revision_reason)root.append(element('p',r.revision_reason,'callout'));
  root.append(renderValue(view,r.content,'content',r.id));
  if(revision.previous_ref){const prior=element('section');prior.append(element('h3','무엇이 바뀌었나'),renderRef(view,revision.previous_ref));
    const before=view.revisions.find(x=>refKey(x.ref)===refKey(revision.previous_ref));
    if(before && r.node==='hypothesize') for(const h of r.content.hypotheses??[]){const pair=compareHypotheses(view,before.record.id,r.id,h.hypothesis_id);if(pair){const box=element('div',undefined,'comparison');box.append(element('h4',h.hypothesis_id),element('p',`이전: ${pair.before.statement}`),element('p',`현재: ${pair.after.statement}`));prior.append(box);}}
    root.append(prior);
  }
  root.append(element('h3','검토에 사용한 자료 버전'),renderValue(view,r.input_refs),renderRef(view,revision.ref),recordDetails('등록 기록 전체',r,`record:${r.id}`));
}
const councilRoleLabel=(council,role)=>council.node==='source_analysis'&&role==='critical'?'반증 검토자':label(role??'검토자');
export function dialogueSummary(role,text) {
  const summary=element('summary',undefined,'statement-summary');
  const opening=text.split(/\n\s*\n/)[0],characters=Array.from(opening);
  const preview=characters.length>180?characters.slice(0,180).join('')+'…':opening;
  summary.append(element('strong',role),element('span','원문 보기','statement-expand'),element('span','접기','statement-collapse'),element('span',preview,'statement-preview'));
  return summary;
}
let councilViewId=0;
const COUNCIL_PHASES=[['initial','disclosed_initials','처음 의견'],['response','disclosed_responses','서로의 의견 검토'],['final','disclosed_finals','최종 판단']];
export function renderCouncil(root,view,council) {
  root.replaceChildren();if(!council){root.append(element('p','선택한 버전에는 에이전트 검토 기록이 없습니다.','empty'));return;}
  root.append(element('h2','에이전트가 검토한 내용'),element('p',`현재 단계: ${label(council.phase)}`),element('p','각 검토자가 내린 판단과 그 이유를 확인하세요.','muted'));
  const info=element('details');info.dataset.key='council-info';info.append(element('summary','대화 참여자와 작성 방식'),element('p','검토자는 먼저 각자의 의견을 쓰고 모두 제출한 뒤 서로의 의견을 읽습니다. 다른 의견을 먼저 읽지 말라는 지시는 있습니다. 다만 실제로 접근을 차단했는지, 서로 다른 모델을 사용했는지는 확인되지 않았습니다.','muted'));
  for(const actor of council.participants??[])info.append(element('p',`${councilRoleLabel(council,actor.council_role)}: ${actor.actor_id} · ${actor.id}`,'mono'));root.append(info);
  root.append(element('p','회차를 선택하고 발언을 펼치면 원문 전체를 볼 수 있습니다. 미리보기는 원문 앞부분입니다.','muted'));
  const group=element('div',undefined,'council-discussion'),tabs=element('div',undefined,'council-tabs');
  group.dataset.key=`council-tabs:${council.id}`;group.dataset.councilPhase='initial';
  tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','대화 회차');group.append(tabs);root.append(group);
  const instance=++councilViewId,entries=[];
  const select=phase=>{group.dataset.councilPhase=phase;for(const entry of entries){const active=entry.phase===phase;entry.tab.setAttribute('aria-selected',String(active));entry.tab.tabIndex=active?0:-1;entry.panel.hidden=!active;}};
  for(const [phase,field,title] of COUNCIL_PHASES) {
    const section=element('section',undefined,'round');const rows=council[field]??[],total=Object.keys(council.required_roles).length;
    const tab=button(`${title} · ${council.submitted_counts[phase]??0}/${total}`,()=>select(phase),`council-tab:${council.id}:${phase}`);
    tab.dataset.phase=phase;tab.id=`council-${instance}-${phase}-tab`;section.id=`council-${instance}-${phase}-panel`;
    tab.setAttribute('role','tab');tab.setAttribute('aria-controls',section.id);section.setAttribute('role','tabpanel');section.setAttribute('aria-labelledby',tab.id);section.tabIndex=0;
    tab.addEventListener('keydown',event=>{const keys=COUNCIL_PHASES.map(item=>item[0]);let index=keys.indexOf(phase);if(event.key==='ArrowRight')index=(index+1)%keys.length;else if(event.key==='ArrowLeft')index=(index+keys.length-1)%keys.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=keys.length-1;else return;event.preventDefault();select(keys[index]);entries[index].tab.focus({preventScroll:true});});
    entries.push({phase,tab,panel:section});tabs.append(tab);
    section.append(element('h3',`${title} · ${council.submitted_counts[phase]??0}/${total} 제출`));
    if(!rows.length)section.append(element('p','아직 의견을 모으고 있습니다. 모두 작성하면 함께 공개됩니다.','muted'));
    for(const {submission:s,submission_ref:ref} of rows){const article=element('details',undefined,'statement');article.dataset.key=`submission:${s.id}`;
      const actor=council.participants?.find(p=>p.id===s.assignment_id);
      article.append(dialogueSummary(councilRoleLabel(council,actor?.council_role),s.rationale));
      if(s.recommendation)article.append(element('p',`최종 판단: ${s.recommendation==='ready'?'진행 의견':label(s.recommendation)}`,'council-verdict'));
      for(const paragraph of s.rationale.split(/\n\s*\n/))article.append(element('p',paragraph,'prose council-paragraph'));
      const metadata=element('details');metadata.dataset.key=`metadata:${s.id}`;metadata.append(element('summary','사용한 근거와 작성 정보'));
      if(s.recommendation) article.append(badge(s.recommendation==='ready'?'진행 가능 의견':label(s.recommendation),['ready','ready_with_limits'].includes(s.recommendation)?'neutral':'pending'));
      for(const field of ['positions','retained_position_refs','issue_proposals','evidence_refs','response_refs'])if(s[field]?.length){metadata.append(element('h4',label(field)),renderValue(view,s[field],field,s.id));}
      metadata.append(element('p',`호스트: ${s.host_id??'미확인'} · 모델: ${s.model_id??'미확인'} · ${s.provenance_status??'declared_only'}`,'muted'));
      if(s.observation_refs?.length)article.append(renderValue(view,s.observation_refs));
      metadata.append(renderRef(view,ref),recordDetails('제출 기록 전체',s,`submission-record:${s.id}`));article.append(metadata);section.append(article);
    }group.append(section);
  }
  select('initial');
}
export function renderVerification(root,view,verificationId) {
  const entry=view.verifications.find(v=>v.record.id===verificationId);if(!entry){root.append(element('p','이 버전에는 검증 기록이 없습니다.','warning'));return;}
  const section=element('section',undefined,'verification');section.append(element('h3',entry.record.question),renderValue(view,entry.record),renderRef(view,entry.ref));
  const results=view.results.filter(r=>r.record.verification_id===verificationId);
  if(!results.length)section.append(element('p','준비 기록만 있습니다. 실제 확인 결과는 아직 없습니다.','pending'));
  for(const result of results)section.append(element('h4',label(result.record.outcome)),renderValue(view,result.record),renderRef(view,result.ref));
  root.append(section);
}
export function renderEvidence(root,view) {
  root.replaceChildren();root.append(element('h2','무엇을 근거로 판단했나요?'));
  assessment(root,'판단에 필요한 근거',view.evidence);
  if(view.evidence){root.append(element('h3','같은 자료를 함께 사용한 연구'),element('p','여러 논문이 같은 데이터를 사용했을 수 있습니다. 서로 다른 연구 결과인지 확인한 내용을 보여줍니다.','muted'));
    for(const key of ['source_groups','limitations','collected_source_refs','extraction_refs'])if(view.evidence[key])root.append(element('h4',label(key)),renderValue(view,view.evidence[key]));}
  for(const entry of view.verifications)renderVerification(root,view,entry.record.id);
  const extras=[...view.source_checks,...view.dependencies];for(const entry of extras)root.append(recordDetails(entry.kind,entry.record,`evidence:${entry.record.id}`),renderRef(view,entry.ref));
}
export function renderHandoff(root,view) {
  root.replaceChildren();root.append(element('h2','문헌 승인과 인계'));
  assessment(root,'문헌 사용 범위 승인',view.corpus,'approved');
  if(view.corpus)root.append(renderValue(view,view.corpus));
  for(const entry of view.approvals)root.append(recordDetails(`승인 기록 · ${entry.kind}`,entry.record,`approval:${entry.record.id}`),renderRef(view,entry.ref));
  assessment(root,'작업 기록·예산',view.accounting);
  if(view.accounting?.return_policy?.mode==='evidence_driven')root.append(element('p',
    `재검토 ${view.accounting.return_policy.returns_used}회 기록 · 횟수로 제한하지 않습니다. 부족한 근거와 다음 행동을 기준으로 판단합니다.`,'muted'));
  root.append(element('p','아직 비용이 기록되지 않았습니다. 비용이 들지 않았다는 뜻은 아닙니다. 실험을 시작하려면 별도 검토와 승인이 필요합니다.','callout'));
  if(!view.handoffs.length)root.append(element('p','아직 다음 단계로 넘길 인계 자료가 발행되지 않았습니다.','empty'));
  for(const entry of view.handoffs){const a=entry.assessment,section=element('section',undefined,'handoff');section.append(element('h3',`M1 → M2 · ${label(a?.status??'unknown')}`));
    assessment(section,'M2로 넘기기 위한 조건',a,'gate_ready');
    section.append(element('p','인계 자료 발행, 받는 쪽의 수락, 담당 변경, 진행 조건 충족을 각각 확인해야 합니다. 이 화면에서 M2 실험을 시작하지는 않습니다.','muted'),renderValue(view,entry.record));
    if(a?.manifest)section.append(element('h4','인계 시점의 자료 · 대안·질문·한계'),renderValue(view,a.manifest));
    section.append(renderRef(view,entry.ref),recordDetails('인계 평가 전체',a,`handoff:${entry.record.id}`));root.append(section);
  }
}

export function renderSourceIntake(root,view) {
  const rows=view.source_captures??[];
  if(!rows.length)return;
  const section=element('section',undefined,'card');
  section.append(element('h2',`확보한 자료 · ${rows.length}개 파일 기록`),
    element('p','파일과 읽은 범위를 저장한 기록입니다. 사용할 수 있는지는 검토 기록에서 확인하세요.','muted'));
  const list=element('details');list.dataset.key='source-intake';
  list.append(element('summary','자료와 확인할 내용 보기'));
  for(const {record:r,ref} of rows){
    const item=element('section');
    item.append(element('h3',r.filename),element('p',r.reading_scope,'prose'));
    if(r.limitations.length){const limits=element('ul');for(const text of r.limitations)limits.append(element('li',text));item.append(limits);}
    const metadata=element('details');metadata.dataset.key=`capture:${r.id}`;
    metadata.append(element('summary','출처·버전·파일 확인 정보'),element('p',r.source_key,'prose'),
      element('p',`버전: ${r.source_version}`,'prose'),element('p',`SHA256: ${r.sha256}`,'prose'));
    if(sourceURL(r.access_url)){const link=element('a','출처 열기');link.href=sourceURL(r.access_url);link.target='_blank';link.rel='noopener noreferrer';metadata.append(link);}
    if(ref)metadata.append(renderRef(view,ref));
    item.append(metadata);list.append(item);
  }
  section.append(list);root.append(section);
}

export function renderScopeReviews(root,view) {
  const councils=(view.councils??[]).filter(c=>c.node==='issue_scope');
  const proposals=view.scope_proposals??[];
  if(!councils.length&&!proposals.length)return;
  const section=element('section',undefined,'card');section.append(element('h2','질문 단계의 진행 조건 검토'));
  const matches=(c,p)=>c.attempt===p.record.id||c.input_binding?.artifact_id===p.record.id;
  const rows=proposals.flatMap(p=>{const linked=councils.filter(c=>matches(c,p));return linked.length?linked.map(c=>({proposal:p,council:c})):[{proposal:p}];});
  rows.push(...councils.filter(c=>!proposals.some(p=>matches(c,p))).map(c=>({council:c})));
  const scopeText=scopes=>(scopes??[]).map(s=>s.kind==='handoff'?'M1 → M2 인계':label(s.target_id??s.milestone)).join(', ');
  for(const {proposal,council} of rows){
    const changes=council?(view.scope_changes??[]).filter(e=>e.record.council_id===council.id):[];
    const active=new Set(changes.flatMap(e=>e.active_issue_ids??[])).size;
    const total=proposal?.record.changes.length??active;
    const status=active?`${active<total?'일부 적용':'적용됨'} · ${active}/${total}개 쟁점`:changes.length?'이전 변경 · 현재 조건 재검토':!council?'검토 준비 전':council.phase==='complete'?'검토 종료 · 적용 결과 대기':'검토 진행 중';
    section.append(element('p',status,'prose'),element('p','질문·요구사항 작성을 진행해도 되는지 검토합니다. 남은 문제는 최종 검토와 M2 인계 전에 확인해야 합니다.','muted'));
    if(proposal){
      section.append(element('p',proposal.record.rationale,'prose'));
      const details=element('details');details.dataset.key=`scope-proposal:${proposal.record.id}`;
      details.append(element('summary','어떤 쟁점의 진행 조건이 바뀌나요?'));
      for(const change of proposal.record.changes){
        const issue=(view.issues??[]).find(i=>(i.record??i.issue??i).id===change.issue_ref.artifact_id);
        details.append(element('p',(issue?.record??issue?.issue??issue)?.question??change.issue_ref.artifact_id),element('p',`${scopeText(change.original_scopes)} → ${scopeText(change.replacement_scopes)}`));
      }
      if(proposal.ref)details.append(renderRef(view,proposal.ref));
      section.append(details);
    }
    if(council){
      const discussion=element('details');discussion.dataset.key=`scope-council:${council.id}`;
      discussion.append(element('summary','검토자 대화 보기'));
      const body=element('div');renderCouncil(body,view,council);discussion.append(body);section.append(discussion);
    }
  }root.append(section);
}

export function renderSourceAnalysis(root,view) {
  const councils=(view.councils??[]).filter(c=>c.node==='source_analysis');
  if(!councils.length)return;
  const section=element('section',undefined,'card');
  section.append(element('h2','원문 검토와 의견 교환'),element('p','자료에서 확인한 내용과 검토자끼리 주고받은 질문·답변입니다. 이 자료를 어디에 사용할지 검토합니다.','muted'));
  for(const council of councils){
    section.append(element('p',`현재: ${label(council.phase)}`,'prose'));
    const finals=council.disclosed_finals??[];
    for(const {submission:s} of finals){
      const actor=council.participants.find(p=>p.id===s.assignment_id);
      section.append(element('p',`${councilRoleLabel(council,actor?.council_role)}: ${s.recommendation==='ready'?'해당 비교에 사용 가능 의견':s.recommendation==='ready_with_limits'?'사용 범위를 제한해야 한다는 의견':'추가 근거가 필요하다는 의견'}`,'prose'));
    }
    const discussion=element('details');discussion.dataset.key=`source-analysis:${council.id}`;
    discussion.append(element('summary','원문 근거와 질문·답변 보기'));
    const body=element('div');renderCouncil(body,view,council);discussion.append(body);section.append(discussion);
  }
  root.append(section);
}
