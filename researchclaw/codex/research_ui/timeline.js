import {element,button,badge,label,renderValue,renderRef,recordDetails} from './detail.js';
export function issueState(issue) {
  const status=issue.imported_pending?'pending_policy_revalidation':issue.status;
  return {label:label(status??'unknown'),tone:status==='resolved'?'ok':['open','checking','reopened','transferred','deferred','superseded','pending_policy_revalidation'].includes(status)?'pending':'unknown'};
}
export function traceIssue(view,issueId) {
  const issue=view.issues.find(i=>i.record.id===issueId);return issue?{issue,events:issue.history??[]}:null;
}
export function renderIssueList(root,view,selection,onSelect) {
  root.replaceChildren();root.append(element('h2',`전체 쟁점 · ${view.issues.length}`));
  if(!view.issues.length)root.append(element('p','공개된 쟁점 기록 없음 · 이전 기록의 해소를 뜻하지 않습니다.','muted'));
  for(const issue of view.issues){const state=issueState(issue),b=button(issue.record.question,()=>onSelect(issue.record.id),`issue:${issue.record.id}`);
    b.className='issue-choice';b.setAttribute('aria-pressed',String(selection.issueId===issue.record.id));b.append(badge(state.label,state.tone),element('small',issue.record.origin?.local_issue_id??issue.record.id));root.append(b);}
}
export function renderTimeline(root,view,issueId) {
  root.replaceChildren();const trace=traceIssue(view,issueId);
  if(!trace){root.append(element('p','왼쪽 목록에서 쟁점을 선택하세요.','empty'));return;}
  const {issue,events}=trace,state=issueState(issue),r=issue.record;
  root.append(element('h2',r.question),badge(state.label,state.tone),element('p',r.id,'mono'),element('p',`분류: ${r.category} · 중요도: ${r.severity}`,'muted'),element('h3','해소 조건'),element('p',r.resolution_condition,'prose'));
  renderIssueImpacts(root,view,issueId);
  root.append(element('h3','현재 단계 조건의 차단 범위'),renderValue(view,r.blocking_scope),element('h3','대상 원문'),renderValue(view,r.target_refs));
  if(issue.imported_pending)root.append(element('p','가져온 이전 쟁점입니다. 새 회차에 새 쟁점이 없어도 이 쟁점은 미해소로 남습니다. 네이티브 정책 확인이 필요합니다.','callout'));
  const list=element('ol',undefined,'timeline');for(const event of events){const item=element('li');item.append(element('h3',`${label(event.record.from_status??'제기')} → ${label(event.record.to_status)}`),element('p',event.record.rationale,'prose'),element('p',`배정 ${event.record.actor_assignment_id}`,'mono'),renderValue(view,event.record.verification_refs),renderRef(view,event.ref),recordDetails('상태 변경 원문',event.record,`event:${event.record.id}`));list.append(item);}
  if(!events.length)root.append(element('p','이 snapshot에 네이티브 상태 변경 기록이 없습니다.','muted'));
  root.append(list,recordDetails('쟁점 원문',r,`issue-record:${r.id}`));
  if(issue.ref)root.append(renderRef(view,issue.ref));
}

export function impactGroups(view) {
  const groups=new Map();
  for(const {record:r,current} of view.issue_impacts??[]){
    if(!current)continue;
    if(!groups.has(r.group_key))groups.set(r.group_key,{key:r.group_key,title:r.group_title,issueIds:[],held:[],prepare:[]});
    const group=groups.get(r.group_key);group.issueIds.push(r.issue_ref.artifact_id);
    group.held=[...new Set([...group.held,...r.held_work])];group.prepare=[...new Set([...group.prepare,...r.preparation_work])];
  }
  return [...groups.values()];
}
export function renderImpactSummary(root,view) {
  const groups=impactGroups(view);if(!groups.length)return;
  const section=element('section',undefined,'card'),count=groups.reduce((n,g)=>n+g.issueIds.length,0);
  section.append(element('h2',`다음 작업 정리 · ${count}개 쟁점 · ${groups.length}개 작업 묶음`),
    element('p','조정자가 정리한 작업 제안입니다. 실제 단계 진행 조건은 위의 연구 진행 상황에서 확인하세요.','muted'));
  const list=element('details');list.dataset.key='issue-impact-summary';list.append(element('summary','준비할 일과 보류할 일 보기'));
  for(const group of groups){const row=element('section');row.append(element('h3',`${group.title} · 쟁점 ${group.issueIds.length}개`));
    for(const text of group.prepare)row.append(element('p',`계속 준비: ${text}`,'prose'));
    for(const text of group.held)row.append(element('p',`보류 제안: ${text}`,'prose'));
    list.append(row);
  }section.append(list);root.append(section);
}
function renderIssueImpacts(root,view,issueId) {
  const rows=(view.issue_impacts??[]).filter(e=>e.record.issue_ref.artifact_id===issueId);
  if(!rows.length)return;
  root.append(element('h3','이 문제는 어떤 작업에 영향을 주나요?'));
  for(const {record:r,current,ref} of rows){
    const section=element('details');section.dataset.key=`impact:${r.id}`;section.open=current;
    section.append(element('summary',`${current?'현재 작업 제안':'이전 제안 · 재검토 필요'}: ${r.group_title}`),
      element('p',r.rationale,'prose'),element('p',`대상: ${r.affected_sources.join(', ')||'특정 자료 없음'} · ${r.hypotheses.join(', ')||'공통 작업'}`,'prose'));
    for(const work of r.preparation_work)section.append(element('p',`계속 준비: ${work}`,'prose'));
    for(const work of r.held_work)section.append(element('p',`보류 제안: ${work}`,'prose'));
    section.append(element('p',`다음 확인: ${r.next_check}`,'prose'),element('p',`확인되지 않으면: ${r.if_unresolved}`,'prose'),
      element('p',`담당 역할: ${r.owner_role} · 정리: ${r.producer_id}`,'muted'));
    if(ref)section.append(renderRef(view,ref));root.append(section);
  }
}
