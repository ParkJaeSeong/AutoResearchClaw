import {element,button,label,renderRevision,renderCouncil,renderEvidence,renderHandoff,renderSourceAnalysis,renderScopeReviews} from './detail.js';
import {renderResearchGraph} from './graph.js';
import {renderIssueList,renderImpactSummary} from './timeline.js';
const TABS={revision:'작업 내용',council:'에이전트 대화',issues:'확인할 문제',evidence:'근거 자료',handoff:'준비와 인계'};
function selectControl(title,key,choices,value,onChange) {
  const wrap=element('label',undefined,'control');wrap.append(element('span',title));const select=element('select');select.dataset.key=key;
  for(const [id,text] of choices){const option=element('option',text);option.value=id;option.selected=id===value;select.append(option);}select.value=value??'';
  select.addEventListener('change',()=>onChange(select.value));wrap.append(select);return wrap;
}
export function renderLegacyRecords(workflowPage,view,chosen,group,callbacks){
  const node=view.nodes.find(n=>n.id===chosen.nodeId);
  const workspace=element('div',undefined,'workspace'),sidebar=element('aside',undefined,'sidebar'),map=element('section',undefined,'card');
  const change=patch=>callbacks.onSelection?.({...chosen,...patch});
  renderResearchGraph(map,group?{...view,nodes:view.nodes.filter(n=>group.nodes.includes(n.id)),transitions:view.transitions.filter(t=>group.nodes.includes(t.to_node))}:view,chosen,(id,revisionId)=>change({nodeId:id,revisionId:revisionId??null,councilId:null,issueId:null,issueScope:'stage',tab:'revision'}));
  sidebar.append(map);
  const panel=element('section',undefined,'detail-panel card');panel.dataset.scroll='detail';
  const versions=view.revisions.filter(r=>r.record.node===chosen.nodeId);
  const controls=element('div',undefined,'detail-controls');controls.append(element('h2',`${node?.label??'연구'} 기록`));
  controls.append(selectControl('기록 버전','revision-select',versions.map((r,i)=>[r.record.id,`${i+1}차 · ${r.current?'현재':'과거'} · ${r.record.id.slice(0,8)}`]),chosen.revisionId,id=>change({revisionId:id,councilId:null})));
  panel.append(controls);const tabs=element('div',undefined,'tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','기록 종류');
  for(const [id,text] of Object.entries(TABS)){const b=button(text,()=>change({tab:id}),`tab:${id}`);b.id=`tab-${id}`;b.setAttribute('role','tab');b.setAttribute('aria-selected',String(chosen.tab===id));b.setAttribute('aria-controls','record-panel');b.tabIndex=chosen.tab===id?0:-1;
    b.addEventListener('keydown',event=>{const ids=Object.keys(TABS);let index=ids.indexOf(id);if(event.key==='ArrowRight')index=(index+1)%ids.length;else if(event.key==='ArrowLeft')index=(index+ids.length-1)%ids.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=ids.length-1;else return;event.preventDefault();change({tab:ids[index]});document.querySelector(`[data-key="tab:${ids[index]}"]`)?.focus();});tabs.append(b);}
  panel.append(tabs);const body=element('div',undefined,'record-panel');body.id='record-panel';body.setAttribute('role','tabpanel');body.setAttribute('aria-labelledby',`tab-${chosen.tab}`);body.tabIndex=0;
  if(chosen.tab==='revision')renderRevision(body,view,view.revisions.find(r=>r.record.id===chosen.revisionId));
  if(chosen.tab==='council'){
    const revision=view.revisions.find(r=>r.record.id===chosen.revisionId),councils=view.councils.filter(c=>c.node===chosen.nodeId && c.attempt===revision?.record.attempt);
    if(councils.length>1)panel.append(selectControl('검토 회차','council-select',councils.map((c,i)=>[c.id,`${i+1}회 · ${label(c.phase)}`]),chosen.councilId,id=>change({councilId:id})));
    renderCouncil(body,view,councils.find(c=>c.id===chosen.councilId));
  }
  if(chosen.tab==='issues')renderIssueList(body,view,chosen,issueScope=>change({issueScope,issueId:null}));
  if(chosen.tab==='evidence')renderEvidence(body,view);
  if(chosen.tab==='handoff')renderHandoff(body,view);
  panel.append(body);workspace.append(sidebar,panel);workflowPage.append(workspace);
  if(!group){renderSourceAnalysis(workflowPage,view);renderScopeReviews(workflowPage,view);renderImpactSummary(workflowPage,view);}
}
