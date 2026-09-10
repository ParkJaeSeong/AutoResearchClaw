import {element,button,badge,label,renderRevision,renderCouncil,renderEvidence,renderHandoff,renderSourceIntake} from './detail.js';
import {renderResearchGraph} from './graph.js';
import {renderIssueList,renderTimeline} from './timeline.js';
import {createLiveFeed} from './live.js';
import {createDiscoveryFeed,createDiscoveryPanel} from './discovery.js';
const ARRAYS=['heads','milestones','nodes','revisions','transitions','councils','issues','verifications','results','source_checks','approvals','dependencies','handoffs','artifacts','reason_codes','required_actions'];
const TABS={revision:'내용·개정',council:'에이전트 대화',issues:'쟁점 이력',evidence:'근거·검증',handoff:'승인·인계'};
export function validateView(view) {
  if(!view || view.schema_version!==1 || view.workflow_version!=='research-graph-v1' || !view.project || typeof view.head_id!=='string')throw new Error('지원하는 연구 기록 형식이 아닙니다.');
  for(const key of ARRAYS)if(!Array.isArray(view[key]) || view[key].some(row=>row===null))throw new Error(`${key} 기록을 읽을 수 없습니다.`);
  for(const row of view.revisions)if(!row.record?.content || !row.ref)throw new Error('개정의 원문 연결이 없습니다.');
  for(const row of view.councils)for(const key of ['disclosed_initials','disclosed_responses','disclosed_finals','participants','authors'])if(!Array.isArray(row[key]))throw new Error('에이전트 대화 형식이 올바르지 않습니다.');
  return view;
}
export function resolveSelection(view,previous={}) {
  const node=view.nodes.find(n=>n.id===previous.nodeId)??view.nodes.find(n=>n.status==='awaiting_input'||n.status==='stale')??view.nodes[0];
  const revisions=view.revisions.filter(r=>r.record.node===node?.id);
  const revision=revisions.find(r=>r.record.id===previous.revisionId)??revisions.find(r=>r.record.id===node?.current_revision_id)??revisions.at(-1);
  const councils=view.councils.filter(c=>c.node===node?.id && c.attempt===revision?.record.attempt);
  return {nodeId:node?.id??null,revisionId:revision?.record.id??null,
    issueId:view.issues.some(i=>i.record.id===previous.issueId)?previous.issueId:view.issues[0]?.record.id??null,
    councilId:councils.find(c=>c.id===previous.councilId)?.id??councils[0]?.id??null,tab:Object.hasOwn(TABS,previous.tab)?previous.tab:'revision'};
}
function selectControl(title,key,choices,value,onChange) {
  const wrap=element('label',undefined,'control');wrap.append(element('span',title));const select=element('select');select.dataset.key=key;
  for(const [id,text] of choices){const option=element('option',text);option.value=id;option.selected=id===value;select.append(option);}select.value=value??'';
  select.addEventListener('change',()=>onChange(select.value));wrap.append(select);return wrap;
}
export function renderResearchView(root,view,selection={},callbacks={}) {
  validateView(view);const chosen=resolveSelection(view,selection),content=element('div',undefined,'research-view');
  const top=element('header',undefined,'project-header');const title=element('div');title.append(element('p','RESEARCHCLAW / M1','eyebrow'),element('h1',view.project.topic));
  const origin={synthetic:'합성 테스트 자료',real:'실제 자료 · 확인 범위별 판단',mixed:'실제·합성 혼합 자료'}[view.content_origin]??'자료 구분 미확인';
  title.append(badge(origin),element('p','지금까지 확인한 내용과 에이전트가 판단한 이유를 살펴보세요.','muted'));top.append(title);
  const milestones=element('nav',undefined,'milestones');milestones.setAttribute('aria-label','마일스톤');
  for(const m of view.milestones)milestones.append(element('span',`${m.id} · ${m.id==='M1'?'근거·가설':'미구현'}`,m.id==='M1'?'milestone active':'milestone'));
  content.append(top,milestones);
  const notice=element('section',undefined,'overview');notice.append(element('strong','연구 진행 상황'),element('p','이 화면에서 연구 기록을 확인할 수 있습니다. 단계를 선택하면 해당 작업의 내용과 대화가 나옵니다.','muted'));
  const node=view.nodes.find(n=>n.id===chosen.nodeId);
  const reasons={blocking_issue_unresolved:'먼저 확인해야 할 문제가 남아 있습니다.',issue_reference_stale:'이전에 검토한 문제와 현재 기록이 달라 다시 확인해야 합니다.'};
  if(node?.reason_codes.length){
    notice.append(element('p',reasons[node.reason_codes[0]]??'다음 단계로 가기 전에 추가 확인이 필요합니다.','pending'));
    const technical=element('details');technical.dataset.key='stage-checks';technical.append(element('summary','상세 확인 정보'));
    for(const code of node.reason_codes)technical.append(element('p',code,'reason'));
    for(const action of node.required_actions??[])technical.append(element('p',action,'prose'));notice.append(technical);
  }
  content.append(notice);
  renderSourceIntake(content,view);
  const discoverySlot=element('div',undefined,'discovery-slot');content.append(discoverySlot);
  const workspace=element('div',undefined,'workspace'),sidebar=element('aside',undefined,'sidebar'),map=element('section',undefined,'card'),issues=element('section',undefined,'card');
  const change=patch=>callbacks.onSelection?.({...chosen,...patch});
  renderResearchGraph(map,view,chosen,(id,revisionId)=>change({nodeId:id,revisionId:revisionId??null,councilId:null,tab:'revision'}));
  renderIssueList(issues,view,chosen,id=>change({issueId:id,tab:'issues'}));sidebar.append(map,issues);
  const panel=element('section',undefined,'detail-panel card');panel.dataset.scroll='detail';
  const versions=view.revisions.filter(r=>r.record.node===chosen.nodeId);
  const controls=element('div',undefined,'detail-controls');controls.append(element('h2',`${node?.label??'연구'} 기록`));
  controls.append(selectControl('개정 선택','revision-select',versions.map((r,i)=>[r.record.id,`${i+1}차 · ${r.current?'현재':'과거'} · ${r.record.id.slice(0,8)}`]),chosen.revisionId,id=>change({revisionId:id,councilId:null})));
  panel.append(controls);const tabs=element('div',undefined,'tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','기록 종류');
  for(const [id,text] of Object.entries(TABS)){const b=button(text,()=>change({tab:id}),`tab:${id}`);b.id=`tab-${id}`;b.setAttribute('role','tab');b.setAttribute('aria-selected',String(chosen.tab===id));b.setAttribute('aria-controls','record-panel');b.tabIndex=chosen.tab===id?0:-1;
    b.addEventListener('keydown',event=>{const ids=Object.keys(TABS);let index=ids.indexOf(id);if(event.key==='ArrowRight')index=(index+1)%ids.length;else if(event.key==='ArrowLeft')index=(index+ids.length-1)%ids.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=ids.length-1;else return;event.preventDefault();change({tab:ids[index]});document.querySelector(`[data-key="tab:${ids[index]}"]`)?.focus();});tabs.append(b);}
  panel.append(tabs);const body=element('div',undefined,'record-panel');body.id='record-panel';body.setAttribute('role','tabpanel');body.setAttribute('aria-labelledby',`tab-${chosen.tab}`);body.tabIndex=0;
  if(chosen.tab==='revision')renderRevision(body,view,view.revisions.find(r=>r.record.id===chosen.revisionId));
  if(chosen.tab==='council'){
    const revision=view.revisions.find(r=>r.record.id===chosen.revisionId),councils=view.councils.filter(c=>c.node===chosen.nodeId && c.attempt===revision?.record.attempt);
    if(councils.length>1)panel.append(selectControl('협의 회차','council-select',councils.map((c,i)=>[c.id,`${i+1}회 · ${label(c.phase)}`]),chosen.councilId,id=>change({councilId:id})));
    renderCouncil(body,view,councils.find(c=>c.id===chosen.councilId));
  }
  if(chosen.tab==='issues')renderTimeline(body,view,chosen.issueId);
  if(chosen.tab==='evidence')renderEvidence(body,view);
  if(chosen.tab==='handoff')renderHandoff(body,view);
  panel.append(body);workspace.append(sidebar,panel);content.append(workspace);
  const next=element('details',undefined,'card next-steps');next.dataset.key='next-steps';next.append(element('summary','다음 작업을 CLI로 이어가기'),element('p','ROOT를 프로젝트 경로로 바꾸세요. 검토자는 자신의 packet을 읽고 본인이 작성한 정확한 payload를 등록합니다. 이 화면은 실행·승인을 대신하지 않습니다.','prose'),element('pre',`researchclaw-codex research inspect ROOT --head ${view.head_id} --json\nresearchclaw-codex research packet ROOT --assignment ASSIGNMENT_ID --json\nresearchclaw-codex research apply ROOT --operation council.submit --payload submission.json --expected-head ${view.head_id} --command-id UNIQUE_ID --json`,'source-text'));
  for(const reason of view.reason_codes)next.append(element('p',reason,'reason'));
  for(const action of view.required_actions)next.append(element('p',action,'prose'));
  content.append(next);root.replaceChildren(content);return chosen;
}
function memory(root) {
  return {open:[...root.querySelectorAll('details[open][data-key]')].map(d=>d.dataset.key),focused:document.activeElement?.closest('[data-key]')?.dataset.key,
    scroll:[...root.querySelectorAll('[data-scroll]')].map(n=>[n.dataset.scroll,n.scrollTop,n.scrollLeft]),x:window.scrollX,y:window.scrollY};
}
function restore(root,state) {
  for(const d of root.querySelectorAll('details[data-key]'))d.open=state.open.includes(d.dataset.key);
  for(const [key,top,left] of state.scroll){const n=[...root.querySelectorAll('[data-scroll]')].find(n=>n.dataset.scroll===key);if(n){n.scrollTop=top;n.scrollLeft=left;}}
  const focused=[...root.querySelectorAll('[data-key]')].find(n=>n.dataset.key===state.focused);
  (focused?.tagName==='DETAILS'?focused.querySelector('summary'):focused)?.focus({preventScroll:true});window.scrollTo(state.x,state.y);
}
export function startApp(root,toolbar,status) {
  let view=null,selection={},head=new URL(window.location.href).searchParams.get('head'),knownHeads=[],theme='system';
  const discoveryRoot=element('section');
  const discoveryPanel=createDiscoveryPanel(discoveryRoot);discoveryPanel.setHistorical(head);
  const discoveryFeed=createDiscoveryFeed({load:async()=>{
    const response=await fetch('/api/discovery',{cache:'no-store'});
    if(!response.ok)throw new Error(`탐색 조회 실패 (${response.status})`);return response.json();
  },onView:next=>discoveryPanel.update(next),onStatus:info=>discoveryPanel.setStatus(info)});
  try{theme=localStorage.getItem('research-theme')??'system';}catch{}
  function setTheme(value){theme=['system','light','dark'].includes(value)?value:'system';document.documentElement.dataset.theme=theme;try{localStorage.setItem('research-theme',theme);}catch{}}
  setTheme(theme);
  function render(){const saved=memory(root);selection=renderResearchView(root,view,selection,{onSelection:value=>{selection=value;render();}});root.querySelector('.discovery-slot').append(discoveryRoot);restore(root,saved);}
  function controls(){toolbar.replaceChildren();toolbar.append(selectControl('기록 시점','head-select',[['','최신 기록 따라가기'],...[...knownHeads].reverse().map(h=>[h,`과거 고정 · ${h.slice(0,12)}`])],head??'',value=>{
      const target=value||null;const url=new URL(window.location.href);if(target)url.searchParams.set('head',target);else url.searchParams.delete('head');window.history.pushState({},'',url);head=target;discoveryPanel.setHistorical(head);feed.selectHead(target);
    }),selectControl('화면','theme-select',[['system','시스템'],['light','밝게'],['dark','어둡게']],theme,setTheme),button('지금 새로고침',()=>Promise.all([feed.refresh(),discoveryFeed.refresh()]),'refresh'));
    if(view)toolbar.append(element('span',`${head?'과거 기록 고정':'최신 기록'} · 표시 HEAD ${view.head_id.slice(0,12)}`,'mono head-label'));
  }
  const feed=createLiveFeed({load:async selected=>{
    const response=await fetch(`/api/view${selected?`?head=${encodeURIComponent(selected)}`:''}`,{cache:'no-store'});if(!response.ok)throw new Error(`기록 조회 실패 (${response.status})`);return validateView(await response.json());},
    onView:next=>{
      const saved=memory(document.body),buffer=element('div');
      const nextSelection=renderResearchView(buffer,next,selection,{onSelection:value=>{selection=value;render();}});
      // Build completely before replacing the last valid screen.
      root.replaceChildren(...buffer.childNodes);root.querySelector('.discovery-slot').append(discoveryRoot);view=next;selection=nextSelection;
      knownHeads=[...new Set([...knownHeads,...next.heads.map(h=>h.head_id)])];controls();restore(document.body,saved);
    },
    onStatus:info=>{status.textContent=info.connected?`${head?'과거 버전 유지':'연결됨'} · 표시 기록은 읽기 전용${info.currentHead && view && info.currentHead!==view.head_id?' · 최신 HEAD가 별도로 있습니다':''}`:`연결 끊김 · ${info.error} · 마지막 정상 기록을 유지하며 재연결합니다.`;status.className=info.connected?'connection':'connection warning';}});
  discoveryFeed.start();controls();if(head)feed.selectHead(head);else feed.start();window.addEventListener('popstate',()=>{head=new URL(window.location.href).searchParams.get('head');discoveryPanel.setHistorical(head);feed.selectHead(head);});window.addEventListener('pagehide',()=>{feed.stop();discoveryFeed.stop();},{once:true});return feed;
}
if(typeof document!=='undefined') {
  const root=document.getElementById('research-app');if(root)startApp(root,document.getElementById('toolbar'),document.getElementById('connection'));
}
