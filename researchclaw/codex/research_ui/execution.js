import {element,button,badge,dialogueSummary} from './detail.js';

const STATUS={planned:'실행 준비',checking_input:'입력 검사 중',running:'실행 중',waiting_input:'입력 대기',blocked:'진행 보류',checking_output:'결과 검사 중',accepted:'사용 범위 채택',needs_work:'보완 필요',failed:'작업 실패',paused:'일시정지',recovery_required:'실행 상태 확인 필요'};
const PHASES=[['initial','처음 의견'],['response','서로의 의견 검토'],['final','최종 판단']];
const REASONS={input_available:'검토할 자료가 있습니다.',source_missing:'검토할 자료와 원문 위치가 필요합니다.',output_invalid:'결과에 필요한 항목을 확인해야 합니다.',claim_invalid:'주장과 사용 범위를 보완해야 합니다.',evidence_ref_unknown:'근거 연결을 확인해야 합니다.',unresolved_invalid:'남은 문제와 다음 행동을 보완해야 합니다.',source_on_hold:'자료 사용 판단을 보류했습니다.',structure_valid:'필수 기록을 갖췄습니다. 과학적 타당성은 검토 의견을 함께 확인하세요.',review_missing:'필요한 검토 의견이 남아 있습니다.',policy_stale:'실행 조건이 바뀌어 다시 검토해야 합니다.',revise_input_or_result:'입력 자료나 검토 결과를 보완하세요.',complete_reviews:'남은 검토 의견을 작성하세요.',revise_attempt:'바뀐 조건으로 다시 검토하세요.'};
const ROLE={domain:'분야 검토자',methodology:'평가 방법 검토자',critical:'반론 검토자',coordinator:'판단 정리자'};
const CHECK={pass:'필수 기록 갖춤',needs_work:'보완 필요',blocked:'진행 보류',not_applicable:'적용 제외'};
function observation(node,now,historical){
 const status=node.dataset.executionStatus,recorded=node.dataset.executionObservation;
 const active=['running','recovery_required'].includes(status),at=Date.parse(node.dataset.lastObservedAt??'');
 const explicit=recorded==='inspection_required'||status==='recovery_required';
 const elapsed=!historical&&active&&Number.isFinite(at)&&now-at>=45000;
 const unknown=!historical&&active&&!Number.isFinite(at);
 node.textContent=explicit||elapsed||recorded==='stale'?'실행 상태 확인 필요':unknown?'실행 상태 확인 안 됨':'';
 node.hidden=!(explicit||elapsed||unknown||recorded==='stale');
}
export function refreshExecutionObservation(root,now=Date.now()){
 for(const node of root.querySelectorAll('[data-execution-observation]'))observation(node,now,root.dataset.executionHistorical==='true');
}
export function executionInGroup(work,group){return group.nodes.includes(work.step_id)||(group.id==='sources'&&work.step_id==='evidence_review');}
export function orderedExecutions(view){return [...(view.executions??[])].sort((a,b)=>(b.sequence??0)-(a.sequence??0));}
function paragraph(root,title,text){if(typeof text==='string'&&text)root.append(element('h4',title),element('p',text,'prose'));}
function resultList(root,title,rows){if(!Array.isArray(rows)||!rows.length)return;root.append(element('h4',title));const list=element('ul');for(const row of rows){const text=typeof row==='string'?row:[row.title,row.source_ref,row.locator,row.reason].filter(value=>typeof value==='string').join(' · ');if(text)list.append(element('li',text,'prose'));}root.append(list);}
function disclosure(title,key){const node=element('details');node.dataset.key=key;node.append(element('summary',title));return node;}
function eventRows(attempt){return attempt.events??[];}
function dialogue(root,work,attempt){
 const group=element('div',undefined,'council-discussion'),tabs=element('div',undefined,'council-tabs'),entries=[];
 const key=`execution-dialogue:${work.work_id}:${attempt.attempt_id}`;group.dataset.key=key;group.dataset.councilPhase='initial';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','대화 회차');group.append(tabs);
 const select=phase=>{group.dataset.councilPhase=phase;for(const e of entries){const active=e.phase===phase;e.tab.setAttribute('aria-selected',String(active));e.tab.tabIndex=active?0:-1;e.panel.hidden=!active;}};
 for(const [phase,title] of PHASES){
  const panel=element('section',undefined,'round'),tab=button(title,()=>select(phase),`${key}:${phase}`);
  tab.dataset.phase=phase;tab.id=`${key}:${phase}:tab`;panel.id=`${key}:${phase}:panel`;tab.setAttribute('role','tab');tab.setAttribute('aria-controls',panel.id);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tab.id);panel.tabIndex=0;
  tab.addEventListener('keydown',event=>{let index=PHASES.findIndex(p=>p[0]===phase);if(event.key==='ArrowRight')index=(index+1)%3;else if(event.key==='ArrowLeft')index=(index+2)%3;else if(event.key==='Home')index=0;else if(event.key==='End')index=2;else return;event.preventDefault();select(PHASES[index][0]);entries[index].tab.focus({preventScroll:true});});
  entries.push({phase,panel,tab});tabs.append(tab);
  const rows=eventRows(attempt).filter(e=>e.type==='role_submitted'&&e.payload?.phase===phase);
  for(const started of eventRows(attempt).filter(e=>e.type==='role_started'&&e.payload?.phase===phase)){const role=started.payload.role??started.actor??'검토자';if(!rows.some(e=>(e.payload.role??e.actor??'검토자')===role))panel.append(element('p',`${ROLE[role]??role} · 의견 작성 중`,'muted'));}
  if(!rows.length)panel.append(element('p','공개된 의견이 아직 없습니다.','muted'));
  for(const [index,row] of rows.entries()){
   const p=row.payload,role=p.role??row.actor??'검토자',text=p.published===false?'':p.text??p.rationale;
   if(!text){panel.append(element('p',`${ROLE[role]??role} · 제출됨 · 공개 대기`,'muted'));continue;}
   const statement=element('details');statement.dataset.key=`${key}:${phase}:${row.event_id??index}`;
   // Native details preserve keyboard interaction and original text is never interpreted as HTML.
   statement.className='statement';statement.append(dialogueSummary(`${ROLE[role]??role} · 제출 원문`,text),element('p',text,'prose council-paragraph'));panel.append(statement);
  }
  group.append(panel);
 }
 select('initial');root.append(group);
}
function resultClaims(root,result){for(const claim of result.claims??[]){paragraph(root,'검토한 주장',claim.text);paragraph(root,'사용 범위',claim.scope);resultList(root,'연결된 근거',claim.evidence_refs);}for(const issue of result.unresolved??[]){paragraph(root,'남은 문제',issue.question);paragraph(root,'영향',issue.impact);paragraph(root,'다음 확인',issue.next_action);}}
function notes(root,rows){const list=element('ul');for(const row of rows){const p=row.payload??row;const li=element('li');if(p.status)li.append(element('strong',CHECK[p.status]??STATUS[p.status]??'상태 미확인'));for(const field of ['summary','reason','next_action','text'])if(typeof p[field]==='string')li.append(element('p',REASONS[p[field]]??p[field],'prose'));if(li.children.length)list.append(li);}if(list.children.length)root.append(list);else root.append(element('p','아직 기록이 없습니다.','muted'));}
export function renderExecutions(root,view){
 const rows=orderedExecutions(view);if(!rows.length)return;
 const section=element('section',undefined,'episode-stack execution-stack');section.setAttribute('aria-label','연구 실행 기록');section.append(element('h2','연구 실행 기록'));
 for(const work of rows){
  const card=disclosure('',`execution:${work.work_id}`);card.className='card episode-card execution-card';const summary=card.children[0];
  summary.append(element('span',work.step_title??(work.step_id==='evidence_review'?'근거 검토':'연구 단계'),'episode-stage'),element('strong',work.title??work.purpose??'연구 작업','episode-title'),badge(STATUS[work.status]??'실행 상태 미확인',work.status==='needs_work'||work.status==='blocked'?'pending':''));
  const action=work.current_action||work.next_action||work.reason;
  if(action&&!Object.hasOwn(STATUS,action))summary.append(element('span',REASONS[action]??action,'execution-action'));
  const observed=element('span',undefined,'execution-action pending');observed.dataset.executionObservation=work.observation_status??'unknown';observed.dataset.executionStatus=work.status;observed.dataset.lastObservedAt=work.last_observed_at??'';observed.setAttribute('aria-live','polite');observation(observed,Date.now(),view.head_id!==undefined&&view.head_id!==view.current_head_id);summary.append(observed);
  const body=element('div',undefined,'episode-body');paragraph(body,'이번 작업의 목적',work.purpose);
  if(work.redacted)body.append(element('p','화면에서는 인증 정보와 로컬 경로를 가렸습니다. 보관된 원문은 유지됩니다.','muted'));
  for(const [index,attempt] of [...(work.attempts??[])].reverse().entries()){
   const run=disclosure(`수행 ${work.attempts.length-index} · ${STATUS[attempt.status]??'상태 미확인'}`,`execution-attempt:${work.work_id}:${attempt.attempt_id}`);run.className='execution-attempt';
   paragraph(run,'보완 이유',attempt.return_reason);paragraph(run,'다음 행동',attempt.next_action);
   run.append(element('h4','에이전트 대화'));dialogue(run,work,attempt);
   const tools=disclosure('도구 진행',`execution-tools:${work.work_id}:${attempt.attempt_id}`);notes(tools,eventRows(attempt).filter(e=>e.type.startsWith('tool_')));run.append(tools);
   const checks=disclosure('검사·재작업',`execution-checks:${work.work_id}:${attempt.attempt_id}`);notes(checks,[...(attempt.checks??[]),...eventRows(attempt).filter(e=>/check|rework|failed/.test(e.type))]);run.append(checks);
   const result=disclosure('결과·근거',`execution-result:${work.work_id}:${attempt.attempt_id}`);if(attempt.result){resultClaims(result,attempt.result);paragraph(result,'판단',attempt.result.summary??attempt.result.rationale??attempt.result.judgment);paragraph(result,'사용 범위',attempt.result.allowed_use);paragraph(result,'남은 한계',attempt.result.limitations);resultList(result,'사용할 수 있는 용도',attempt.result.allowed_uses);resultList(result,'사용을 보류할 용도',attempt.result.held_uses);resultList(result,'근거 위치',attempt.result.evidence_refs);}else result.append(element('p','채택된 결과가 아직 없습니다.','muted'));run.append(result);body.append(run);
  }
  card.append(body);section.append(card);
 }
 root.append(section);
}
