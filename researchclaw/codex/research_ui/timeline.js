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
  root.append(element('h3','차단 범위'),renderValue(view,r.blocking_scope),element('h3','대상 원문'),renderValue(view,r.target_refs));
  if(issue.imported_pending)root.append(element('p','가져온 이전 쟁점입니다. 새 회차에 새 쟁점이 없어도 이 쟁점은 미해소로 남습니다. 네이티브 정책 확인이 필요합니다.','callout'));
  const list=element('ol',undefined,'timeline');for(const event of events){const item=element('li');item.append(element('h3',`${label(event.record.from_status??'제기')} → ${label(event.record.to_status)}`),element('p',event.record.rationale,'prose'),element('p',`배정 ${event.record.actor_assignment_id}`,'mono'),renderValue(view,event.record.verification_refs),renderRef(view,event.ref),recordDetails('상태 변경 원문',event.record,`event:${event.record.id}`));list.append(item);}
  if(!events.length)root.append(element('p','이 snapshot에 네이티브 상태 변경 기록이 없습니다.','muted'));
  root.append(list,recordDetails('쟁점 원문',r,`issue-record:${r.id}`));
  if(issue.ref)root.append(renderRef(view,issue.ref));
}
