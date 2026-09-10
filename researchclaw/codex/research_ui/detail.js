import {refKey,resolveRef,rawURL,sourceURL,compareHypotheses} from './trace.js';
export function element(tag,text,className) {
  const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);if(className)node.className=className;return node;
}
export function button(text,action,key) {
  const node=element('button',text);node.type='button';if(key)node.dataset.key=key;node.addEventListener('click',action);return node;
}
export const LABELS={scope:'범위',questions:'연구 질문',search:'문헌 검색',screen:'문헌 선정',collect:'원문 수집',extract:'근거 추출',synthesize:'근거 종합',hypothesize:'가설',review:'최종 검토',handoff:'인계',
 ready:'필수 기록 갖춤',awaiting_input:'추가 검토 필요',not_started:'등록된 작업 없음',stale:'재검토 필요',unknown:'확인되지 않음',initial:'최초 의견',response:'의견 교환',final:'최종 판단',complete:'의견 작성 완료',
 ready_with_limits:'조건부 진행 의견',revise:'수정 의견',defer:'대기 의견',domain:'소재 전문가',methodology:'평가 방법 검토자',critical:'실험·실행 검토자',owner:'담당',resolver:'검토자',
 open:'열림',checking:'검증 중',resolved:'해소',reopened:'재개',transferred:'담당 이전 · 미해소',deferred:'대기',superseded:'후속 쟁점 있음 · 미해소',pending_policy_revalidation:'가져온 쟁점 · 정책 재검토 대기',
 supported:'지지 결과',refuted:'반박 결과',inconclusive:'불충분',failed:'실패',pending:'결과 대기',accepted:'수신 수락됨',issued_awaiting_acceptance:'발행됨 · 수신 수락 대기',
 user_goal:'연구 목표',user_constraints:'사용자 제약',agent_assumptions:'작업 가정',question:'확인 질문',rationale:'판단 이유',revision_reason:'수정 이유',statement:'가설 내용',prediction:'예측',population:'대상 범위',falsification_condition:'반증 조건',
 findings:'종합 근거',claim:'주장',claims:'추출 근거',hypotheses:'가설 목록',rejected_alternatives:'채택하지 않은 대안',description:'설명',reason:'이유',limitations:'한계',evidence_refs:'근거 원문',counterevidence_refs:'반대 근거',
 sources:'자료',source_id:'자료 ID',source_ref:'원문 버전',title:'제목',url:'원문 주소',doi:'DOI',arxiv_id:'arXiv ID',raw_text:'제공 원문',access_status:'확인 범위',access_level:'확인 범위',locator:'원문 위치',span_start:'시작 위치',span_end:'끝 위치',extracted_text:'추출 구절',interpretation:'해석',
 source_type:'자료 유형',origin_group_id:'공통 원천 그룹',origin_description:'원천 설명',source_groups:'공통 원천',origin_group_count:'원천 그룹 수',source_count:'자료 수',unknown_sources:'원천 미확인 자료',
 prior_issue_dispositions:'이전 쟁점 처리',open_questions:'미해결 확인 질문',owner_assignment_id:'담당 배정 ID',disposition:'처리 방침',carry_forward:'그대로 보존',verification_planned:'검증 예정',native_resolved:'해소 기록 연결',transfer_proposed:'담당 이전 제안',
 method:'확인 방법',acceptance_rule:'판정 기준',resolution_condition:'해소 조건',verification_refs:'검증 기록',output_refs:'결과 근거',checked_scope:'실제 확인 범위',outcome:'결과',status:'상태',scope_refs:'승인 범위',binding:'승인 대상 버전',validity:'유효성',
 queries:'검색어',inclusion_criteria:'포함 기준',exclusion_criteria:'제외 기준',search_log:'검색 기록',candidates:'후보 자료',decisions:'선정 판단',decision:'판단',search_ids:'검색 기록 ID',stance:'입장',approve:'승인',approved:'승인 여부',
 from_milestone:'보낸 단계',to_milestone:'받는 단계',unresolved_issue_ids:'미해소 쟁점',transfer_proposals:'담당 이전 제안',acceptance_ref:'수락 기록',artifact_refs:'패키지 원문',from_status:'이전 상태',to_status:'변경 상태',actor_assignment_id:'변경 담당 배정',successor_ids:'후속 쟁점',
 change_kind:'입장 변경 원인',changed_from:'이전 입장',retained_position_refs:'유지한 입장',response_refs:'응답 대상',issue_proposals:'새 쟁점 제안',recommendation:'최종 의견',observation_refs:'관측 근거',provenance_status:'출처 확인 방식',content_origin:'자료 구분'};
export const label=value=>Object.hasOwn(LABELS,value)?LABELS[value]:String(value??'기록 없음');
export function badge(text,tone='neutral') {return element('span',text,`badge ${tone}`);}
export function recordDetails(title,value,key) {
  const node=element('details');if(key)node.dataset.key=key;
  node.append(element('summary',title),element('pre',JSON.stringify(value,null,2),'record-json'));return node;
}
export function renderRef(view,ref) {
  const wrap=element('span',undefined,'reference');const item=resolveRef(view,ref),url=rawURL(view,item);
  if(url){const a=element('a',`${item.label} · 원문`);a.href=url;a.target='_blank';a.rel='noopener noreferrer';wrap.append(a);}
  else wrap.append(element('span',`${ref?.artifact_id??'참조'} · 이 버전의 공개 원문 없음`,'warning'));
  wrap.append(element('small',`${ref?.sha256?.slice(0,12)??'해시 없음'} · HEAD ${ref?.head_id?.slice(0,12)??'없음'}`));
  return wrap;
}
export function renderValue(view,value,key='',path=key) {
  if(refKey(value)) return renderRef(view,value);
  if(value===null || value===undefined) return element('span','기록 없음','muted');
  if(Array.isArray(value)) {
    if(!value.length)return element('span','기록 없음','muted');
    const list=element('ul',undefined,'records');value.forEach((item,i)=>{const li=element('li');li.append(renderValue(view,item,'',`${path}/${i}`));list.append(li);});return list;
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
  section.append(badge(value?.[flag]===true ? '조건 충족' : value ? '대기·미충족' : '입력 없음',value?.[flag]===true?'ok':'pending'));
  for(const reason of value?.reason_codes??[])section.append(element('p',reason,'reason'));
  for(const action of value?.required_actions??[])section.append(element('p',action,'prose'));
  root.append(section);return section;
}
export function renderRevision(root,view,revision) {
  root.replaceChildren();if(!revision){root.append(element('p','등록된 개정이 없습니다.','empty'));return;}
  const r=revision.record;
  root.append(element('h2',`${label(r.node)} · 선택한 개정`),element('p',r.id,'mono'),badge(revision.current?'현재 개정':'보존된 과거 개정',revision.current?'neutral':'pending'));
  if(r.revision_reason)root.append(element('p',r.revision_reason,'callout'));
  root.append(renderValue(view,r.content,'content',r.id));
  if(revision.previous_ref){const prior=element('section');prior.append(element('h3','무엇이 바뀌었나'),renderRef(view,revision.previous_ref));
    const before=view.revisions.find(x=>refKey(x.ref)===refKey(revision.previous_ref));
    if(before && r.node==='hypothesize') for(const h of r.content.hypotheses??[]){const pair=compareHypotheses(view,before.record.id,r.id,h.hypothesis_id);if(pair){const box=element('div',undefined,'comparison');box.append(element('h4',h.hypothesis_id),element('p',`이전: ${pair.before.statement}`),element('p',`현재: ${pair.after.statement}`));prior.append(box);}}
    root.append(prior);
  }
  root.append(element('h3','사용한 입력 버전'),renderValue(view,r.input_refs),renderRef(view,revision.ref),recordDetails('등록 기록 전체',r,`record:${r.id}`));
}
export function renderCouncil(root,view,council) {
  root.replaceChildren();if(!council){root.append(element('p','선택한 개정의 협의 기록이 없습니다.','empty'));return;}
  root.append(element('h2','에이전트가 검토한 내용'),element('p',`현재 단계: ${label(council.phase)}`),element('p','각 역할이 무엇을 판단했고, 왜 그렇게 생각하는지 확인하세요.','muted'));
  const info=element('details');info.dataset.key='council-info';info.append(element('summary','대화 참여자와 작성 방식'),element('p','검토자들은 먼저 각자의 의견을 쓰고, 모두 제출한 뒤 서로의 의견을 읽습니다. 다른 의견을 먼저 읽지 않도록 지시하지만, 접근을 강제로 차단했는지는 확인되지 않았습니다. 서로 다른 모델을 사용했는지도 확인되지 않았습니다.','muted'));
  for(const actor of council.participants??[])info.append(element('p',`${label(actor.council_role)}: ${actor.actor_id} · ${actor.id}`,'mono'));root.append(info);
  root.append(element('p','처음 의견 → 서로의 의견 검토 → 최종 판단 순서입니다. 아래 발언은 저장된 원문입니다.','muted'));
  for(const [phase,field] of [['initial','disclosed_initials'],['response','disclosed_responses'],['final','disclosed_finals']]) {
    const section=element('section',undefined,'round');const rows=council[field]??[],total=Object.keys(council.required_roles).length;
    section.append(element('h3',`${label(phase)} · ${council.submitted_counts[phase]??0}/${total} 제출`));
    if(!rows.length)section.append(element('p','아직 의견을 모으고 있습니다. 모두 작성하면 함께 공개됩니다.','muted'));
    for(const {submission:s,submission_ref:ref} of rows){const article=element('article',undefined,'statement');article.dataset.key=`submission:${s.id}`;
      const actor=council.participants?.find(p=>p.id===s.assignment_id);
      article.append(element('h4',label(actor?.council_role??'검토자')));
      if(s.recommendation)article.append(element('p',`최종 판단: ${s.recommendation==='ready'?'진행 의견':label(s.recommendation)}`,'council-verdict'));
      for(const paragraph of s.rationale.split(/\n\s*\n/))article.append(element('p',paragraph,'prose council-paragraph'));
      const metadata=element('details');metadata.dataset.key=`metadata:${s.id}`;metadata.append(element('summary','근거 연결과 기록 정보'));
      if(s.recommendation) article.append(badge(s.recommendation==='ready'?'진행 가능 의견':label(s.recommendation),['ready','ready_with_limits'].includes(s.recommendation)?'neutral':'pending'));
      for(const field of ['positions','retained_position_refs','issue_proposals','evidence_refs','response_refs'])if(s[field]?.length){metadata.append(element('h4',label(field)),renderValue(view,s[field],field,s.id));}
      metadata.append(element('p',`호스트: ${s.host_id??'미확인'} · 모델: ${s.model_id??'미확인'} · ${s.provenance_status??'declared_only'}`,'muted'));
      if(s.observation_refs?.length)article.append(renderValue(view,s.observation_refs));
      metadata.append(renderRef(view,ref),recordDetails('제출 기록 전체',s,`submission-record:${s.id}`));article.append(metadata);section.append(article);
    }root.append(section);
  }
}
export function renderVerification(root,view,verificationId) {
  const entry=view.verifications.find(v=>v.record.id===verificationId);if(!entry){root.append(element('p','이 버전의 검증 기록 없음','warning'));return;}
  const section=element('section',undefined,'verification');section.append(element('h3',entry.record.question),renderValue(view,entry.record),renderRef(view,entry.ref));
  const results=view.results.filter(r=>r.record.verification_id===verificationId);
  if(!results.length)section.append(element('p','준비 기록만 있습니다. 실제 확인 결과는 아직 없습니다.','pending'));
  for(const result of results)section.append(element('h4',label(result.record.outcome)),renderValue(view,result.record),renderRef(view,result.ref));
  root.append(section);
}
export function renderEvidence(root,view) {
  root.replaceChildren();root.append(element('h2','무엇을 근거로 판단했나요?'));
  assessment(root,'현재 근거 연결',view.evidence);
  if(view.evidence){root.append(element('h3','같은 자료를 함께 사용한 연구'),element('p','여러 논문이 같은 데이터를 사용했을 수 있습니다. 서로 다른 연구 결과인지 확인한 내용을 보여줍니다.','muted'));
    for(const key of ['source_groups','limitations','collected_source_refs','extraction_refs'])if(view.evidence[key])root.append(element('h4',label(key)),renderValue(view,view.evidence[key]));}
  for(const entry of view.verifications)renderVerification(root,view,entry.record.id);
  const extras=[...view.source_checks,...view.dependencies];for(const entry of extras)root.append(recordDetails(entry.kind,entry.record,`evidence:${entry.record.id}`),renderRef(view,entry.ref));
}
export function renderHandoff(root,view) {
  root.replaceChildren();root.append(element('h2','문헌 승인과 인계'));
  assessment(root,'현재 문헌 범위 승인',view.corpus,'approved');
  if(view.corpus)root.append(renderValue(view,view.corpus));
  for(const entry of view.approvals)root.append(recordDetails(`승인 기록 · ${entry.kind}`,entry.record,`approval:${entry.record.id}`),renderRef(view,entry.ref));
  assessment(root,'작업 기록·예산',view.accounting);
  root.append(element('p','아직 비용이 기록되지 않았습니다. 비용이 들지 않았다는 뜻은 아닙니다. 실험을 시작하려면 별도 검토와 승인이 필요합니다.','callout'));
  if(!view.handoffs.length)root.append(element('p','발행된 인계 패키지가 없습니다.','empty'));
  for(const entry of view.handoffs){const a=entry.assessment,section=element('section',undefined,'handoff');section.append(element('h3',`M1 → M2 · ${label(a?.status??'unknown')}`));
    assessment(section,'현재 인계 게이트',a,'gate_ready');
    section.append(element('p','발행, 수신 수락, 담당 이전, 현재 게이트 충족은 서로 다른 기록입니다. M2 실행은 이 화면에서 시작하지 않습니다.','muted'),renderValue(view,entry.record));
    if(a?.manifest)section.append(element('h4','고정 패키지 · 대안·질문·한계'),renderValue(view,a.manifest));
    section.append(renderRef(view,entry.ref),recordDetails('인계 평가 전체',a,`handoff:${entry.record.id}`));root.append(section);
  }
}

export function renderSourceIntake(root,view) {
  const rows=view.source_captures??[];
  if(!rows.length)return;
  const section=element('section',undefined,'card');
  section.append(element('h2',`확보한 자료 · ${rows.length}개 파일 기록`),
    element('p','파일과 읽은 범위를 저장했습니다. 사용 여부는 아직 판단하지 않았습니다.','muted'));
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
