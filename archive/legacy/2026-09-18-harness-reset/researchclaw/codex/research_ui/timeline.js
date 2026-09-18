import {element,button,badge,label,renderValue,renderRef,recordDetails} from './detail.js';
import {refKey} from './trace.js';
export function issueState(issue) {
  const status=issue.imported_pending?'pending_policy_revalidation':issue.status;
  return {label:label(status??'unknown'),tone:status==='resolved'?'ok':['open','checking','reopened','transferred','deferred','superseded','pending_policy_revalidation'].includes(status)?'pending':'unknown'};
}
export function traceIssue(view,issueId) {
  const issue=view.issues.find(i=>i.record.id===issueId);return issue?{issue,events:issue.history??[]}:null;
}
export function issueRelations(view,issue,nodeId) {
  if(!nodeId)return [];
  const r=issue.record,relations=[],origin=r.origin;
  if(origin?.node===nodeId&&(!origin.milestone||origin.milestone==='M1'))relations.push('이 단계에서 제기됨');
  const targets=(r.target_refs??[]).some(target=>{
    if(view.project_id&&target.project_id!==view.project_id)return false;
    if(target.artifact_id===`m1/nodes/${nodeId}`)return true;
    return (view.revisions??[]).some(revision=>revision.record.node===nodeId&&refKey(target)!==null&&refKey(target)===refKey(revision.ref));
  });
  if(targets)relations.push('이 단계가 검토 대상');
  const scopes=issue.effective_blocking_scope??r.blocking_scope??[];
  if(scopes.some(scope=>scope.kind==='node'&&scope.milestone==='M1'&&scope.target_id===nodeId))relations.push('이 단계의 진행 조건에 연결');
  return relations;
}
export function issuesForSelection(view,selection={}) {
  return selection.issueScope==='all'?view.issues:view.issues.filter(issue=>issueRelations(view,issue,selection.nodeId).length);
}
export function renderIssueList(root,view,selection,onScope=()=>{}) {
  const issues=issuesForSelection(view,selection),all=selection.issueScope==='all';
  root.replaceChildren();root.append(element('h2',`확인할 문제 · ${issues.length}`));
  const filters=element('div',undefined,'issue-filters');filters.setAttribute('role','group');filters.setAttribute('aria-label','문제 범위');
  for(const [scope,title] of [['stage','이 단계'],['all',`전체 ${view.issues.length}`]]){
    const b=button(title,()=>onScope(scope),`issue-scope:${scope}`);b.setAttribute('aria-pressed',String((scope==='all')===all));filters.append(b);
  }
  root.append(filters,element('p',all?'프로젝트 전체 문제입니다. 단계 연결이 없는 문제도 포함합니다.':`${label(selection.nodeId)} 단계와 관련된 문제입니다. 항목을 펼치면 근거와 변경 이력을 볼 수 있습니다.`,'muted'));
  if(!issues.length)root.append(element('p',all?'이 시점에 공개된 문제 기록이 없습니다.':'이 단계와 연결된 문제 기록이 없습니다. 전체 목록에서 다른 문제를 확인할 수 있습니다.','muted'));
  const list=element('div',undefined,'issue-list');
  for(const issue of issues){
    const state=issueState(issue),row=element('details',undefined,'issue-row');row.dataset.key=`issue:${issue.record.id}`;
    const summary=element('summary'),heading=element('span',issue.record.question,'issue-question');
    summary.append(heading,badge(state.label,state.tone));
    const origin=issue.record.origin?.node,context=element('span',`제기된 단계: ${origin?label(origin):'연결 정보 없음'}`,'issue-context muted');
    const relations=all?[]:issueRelations(view,issue,selection.nodeId).filter(text=>text!=='이 단계에서 제기됨');
    if(relations.length)context.append(element('span',` · ${relations.join(' · ')}`));
    summary.append(context);row.append(summary);
    const body=element('div',undefined,'issue-body');renderTimeline(body,view,issue.record.id,selection);row.append(body);list.append(row);
  }
  root.append(list);
}
export function renderTimeline(root,view,issueId,selection={}) {
  root.replaceChildren();const trace=traceIssue(view,issueId);
  if(!trace){root.append(element('p',selection.nodeId&&selection.issueScope!=='all'?`${label(selection.nodeId)} 단계에 연결된 문제 기록이 없습니다. 전체 목록에서 다른 문제를 확인할 수 있습니다.`:'문제 목록에서 확인할 항목을 선택하세요.','empty'));return;}
  const {issue,events}=trace,r=issue.record;
  root.append(element('h3','해결됐다고 판단할 기준'),element('p',r.resolution_condition,'prose'));
  renderIssueImpacts(root,view,issueId);
  root.append(element('h3','해결 전까지 진행할 수 없는 작업'),renderValue(view,issue.effective_blocking_scope??r.blocking_scope),element('h3','대상 원문'),renderValue(view,r.target_refs));
  if(issue.scope_changed)root.append(element('p','독립 검토 후 보류할 작업의 범위를 바꿨습니다. 문제는 아직 해결되지 않았습니다.','prose'),recordDetails('이전에 보류한 작업 범위',r.blocking_scope,`original-scope:${r.id}`));
  if(issue.imported_pending)root.append(element('p','이전 기록에서 가져온 문제입니다. 새 문제가 없더라도 이 문제는 해결 전까지 남습니다. 현재 연구의 진행 조건에 맞는지 다시 확인해야 합니다.','callout'));
  const list=element('ol',undefined,'timeline');for(const event of events){const item=element('li');item.append(element('h3',`${label(event.record.from_status??'제기')} → ${label(event.record.to_status)}`),element('p',event.record.rationale,'prose'),element('p',`배정 ${event.record.actor_assignment_id}`,'mono'),renderValue(view,event.record.verification_refs),renderRef(view,event.ref),recordDetails('상태 변경 원문',event.record,`event:${event.record.id}`));list.append(item);}
  if(!events.length)root.append(element('p','선택한 기록 시점에는 상태 변경 내역이 없습니다.','muted'));
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
    element('p','조정자가 정리한 작업 제안입니다. 실제 진행 조건은 선택한 단계의 안내에서 확인하세요.','muted'));
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
