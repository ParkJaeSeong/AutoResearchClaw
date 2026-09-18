import {createHandoffPanel} from './document_handoff.js';
import {projectFetch,projectId,readProjectState,saveProjectState,switchURL} from './project.js';
import {STAGE_GROUPS,stageEpisodes,renderStageNavigation,loadCatalog,mountProjectPicker,loadMaterials,preferredProject} from './workspace.js';
import {renderEpisodes} from './episodes.js';
import {renderExecutions,executionInGroup,refreshExecutionObservation} from './execution.js';
import {createEpisodeReviewController} from './episode_review.js';
import {pageTabs,pageSection,startShell} from './shell.js';
import {renderOverview} from './overview.js';
import {element,button,badge,renderChecks,renderSourceIntake} from './detail.js';
import {renderLegacyRecords} from './legacy_records.js';
import {issuesForSelection} from './timeline.js';
import {createLiveFeed} from './live.js';
import {createDiscoveryFeed,createDiscoveryPanel} from './discovery.js';
import {createAtlasPanel} from './atlas.js';
const ARRAYS=['heads','milestones','nodes','revisions','transitions','councils','issues','verifications','results','source_checks','approvals','dependencies','handoffs','artifacts','reason_codes','required_actions'];
const TABS={revision:'작업 내용',council:'에이전트 대화',issues:'확인할 문제',evidence:'근거 자료',handoff:'준비와 인계'};
export function validateView(view) {
  if(!view || view.schema_version!==1 || view.workflow_version!=='research-graph-v1' || !view.project || typeof view.head_id!=='string')throw new Error('지원하는 연구 기록 형식이 아닙니다.');
  for(const key of ARRAYS)if(!Array.isArray(view[key]) || view[key].some(row=>row===null))throw new Error(`${key} 기록을 읽을 수 없습니다.`);
  for(const row of view.revisions)if(!row.record?.content || !row.ref)throw new Error('이 기록 버전의 원문을 찾을 수 없습니다.');
  for(const row of view.councils)for(const key of ['disclosed_initials','disclosed_responses','disclosed_finals','participants','authors'])if(!Array.isArray(row[key]))throw new Error('에이전트 대화 형식이 올바르지 않습니다.');
  return view;
}
export function resolveSelection(view,previous={}) {
  const group=STAGE_GROUPS.find(g=>g.id===previous.stageGroup),nodes=group?view.nodes.filter(n=>group.nodes.includes(n.id)):view.nodes;
  const node=nodes.find(n=>n.id===previous.nodeId)??nodes.find(n=>n.status==='awaiting_input'||n.status==='stale')??nodes[0];
  const revisions=view.revisions.filter(r=>r.record.node===node?.id);
  const revision=revisions.find(r=>r.record.id===previous.revisionId)??revisions.find(r=>r.record.id===node?.current_revision_id)??revisions.at(-1);
  const councils=view.councils.filter(c=>c.node===node?.id && c.attempt===revision?.record.attempt);
  const issueScope=previous.issueScope==='all'?'all':'stage',issues=issuesForSelection(view,{nodeId:node?.id,issueScope});
  return {nodeId:node?.id??null,revisionId:revision?.record.id??null,
    ...(STAGE_GROUPS.some(g=>g.id===previous.stageGroup)?{stageGroup:previous.stageGroup}:{}),issueScope,issueId:issues.some(i=>i.record.id===previous.issueId)?previous.issueId:issues[0]?.record.id??null,
    councilId:councils.find(c=>c.id===previous.councilId)?.id??councils[0]?.id??null,tab:Object.hasOwn(TABS,previous.tab)?previous.tab:'revision'};
}
function selectControl(title,key,choices,value,onChange) {
  const wrap=element('label',undefined,'control');wrap.append(element('span',title));const select=element('select');select.dataset.key=key;
  for(const [id,text] of choices){const option=element('option',text);option.value=id;option.selected=id===value;select.append(option);}select.value=value??'';
  select.addEventListener('change',()=>onChange(select.value));wrap.append(select);return wrap;
}
export function renderResearchView(root,view,selection={},callbacks={}) {
  validateView(view);const chosen=resolveSelection(view,selection),content=element('div',undefined,'research-view');
  const top=element('header',undefined,'project-header');const title=element('div');title.append(element('h1',view.project.topic));
  const origin={synthetic:'합성 테스트 자료',real:'실제 연구 자료 · 확인한 범위에서 사용',mixed:'실제·합성 혼합 자료'}[view.content_origin]??'자료 구분 미확인';
  title.append(badge(origin));top.append(title);
  const milestones=element('nav',undefined,'milestones');milestones.setAttribute('aria-label','마일스톤');
  for(const m of view.milestones)milestones.append(element('span',`${m.id} · ${{M1:'실험 착수 준비',M2:'실험과 해석 · 준비 전',M3:'연구 마무리 · 준비 전'}[m.id]??m.id}`,m.id==='M1'?'milestone active':'milestone'));
  content.append(top,milestones,pageTabs());
  const materialsPage=pageSection('materials'),m2Page=pageSection('m2'),m3Page=pageSection('m3');
  for(const [page,title,text] of [[m2Page,'M2 · 실험과 해석','실험 수행, 결과 검증과 해석, 다음 실험의 방향을 정하는 단계입니다.'],[m3Page,'M3 · 연구 마무리','결론과 한계를 정리하고 재현 자료와 최종 산출물을 준비하는 단계입니다.']])page.append(element('h2',title),element('p',text,'prose'),element('p','현재 이 작업 공간은 M1 기록을 지원합니다. 이 단계의 실행과 기록 화면은 아직 지원하지 않습니다.','callout'));
  materialsPage.append(element('div',undefined,'materials-slot'));
  const overviewPage=pageSection('overview'),workflowPage=pageSection('workflow'),decisionsPage=pageSection('decisions'),sourcesPage=pageSection('sources'),atlasPage=pageSection('atlas');
  renderOverview(overviewPage,view);
  const group=STAGE_GROUPS.find(g=>g.id===chosen.stageGroup);
  if(group){workflowPage.append(element('h2',`M1 · ${group.title}`),element('p','이 단계와 명시적으로 연결된 실제 수행 회차입니다. 전체 수행 이력에서 다른 회차도 볼 수 있습니다.','muted'));}
  renderExecutions(workflowPage,group?{...view,executions:(view.executions??[]).filter(row=>executionInGroup(row,group))}:view);
  renderEpisodes(workflowPage,group?{...view,work_episodes:stageEpisodes(view,group.id)}:view,callbacks.episodeReview);
  if(group)workflowPage.append(button('전체 수행 이력 보기',()=>callbacks.onSelection?.({...chosen,stageGroup:null}),'all-episodes'));
  decisionsPage.append(element('h2','판단의 근거와 실험 준비'),element('p','답변을 어디에 사용했고 어떤 결정을 내렸는지 확인합니다. 실험 준비 항목도 함께 볼 수 있습니다.','muted'));
  const recordsSlot=element('div',undefined,'atlas-records-slot');decisionsPage.append(recordsSlot);
  const notice=element('details',undefined,'overview stage-notice');notice.dataset.key='stage-checks';
  const noticeSummary=element('summary');noticeSummary.append(element('strong','진행 조건'));notice.append(noticeSummary);
  const node=view.nodes.find(n=>n.id===chosen.nodeId);
  const reasons={blocking_issue_unresolved:'먼저 확인해야 할 문제가 남아 있습니다.',issue_reference_stale:'이전에 검토한 문제와 현재 기록이 달라 다시 확인해야 합니다.'};
  if(node?.reason_codes.length){
    noticeSummary.append(element('span',reasons[node.reason_codes[0]]??'다음 단계 전에 추가 확인이 필요합니다.','pending'),element('span','이유 보기','muted'));
    renderChecks(notice,node.reason_codes,node.required_actions??[]);
  }
  if(view.revisions.some(r=>r.record.node===chosen.nodeId) && node?.reason_codes.length)workflowPage.append(notice);
  sourcesPage.append(element('section',undefined,'handoff-slot'));
  renderSourceIntake(sourcesPage,view);
  const atlasSlot=element('div',undefined,'atlas-slot');atlasPage.append(atlasSlot);
  const discoverySlot=element('div',undefined,'discovery-slot');sourcesPage.append(discoverySlot);
  if(view.revisions.length){
    const legacy=element('details',undefined,'legacy-records');legacy.dataset.key='legacy-records';
    legacy.append(element('summary','이전 단계 기록 보기'));
    renderLegacyRecords(legacy,view,chosen,group,callbacks);workflowPage.append(legacy);
  }
  content.append(overviewPage,workflowPage,decisionsPage,sourcesPage,atlasPage,materialsPage,m2Page,m3Page);root.replaceChildren(content);return chosen;
}
function memory(root) {
  return {candidateFilters:[...root.querySelectorAll('[data-candidate-filter]')].map(n=>[n.dataset.key,n.value]),councilTabs:[...root.querySelectorAll('[data-council-phase]')].map(n=>[n.dataset.key,n.dataset.councilPhase]),open:[...root.querySelectorAll('details[open][data-key]')].map(d=>d.dataset.key),focused:document.activeElement?.closest('[data-key]')?.dataset.key,
    scroll:[...root.querySelectorAll('[data-scroll]')].map(n=>[n.dataset.scroll,n.scrollTop,n.scrollLeft]),x:window.scrollX,y:window.scrollY};
}
function restore(root,state) {
  for(const input of root.querySelectorAll('[data-candidate-filter]')){const saved=state.candidateFilters?.find(([key])=>key===input.dataset.key);if(saved){input.value=saved[1];input.dispatchEvent(new Event('input'));}}
  for(const group of root.querySelectorAll('[data-council-phase]')){const phase=state.councilTabs?.find(([key])=>key===group.dataset.key)?.[1];if(phase)group.querySelector(`[role=tab][data-phase="${phase}"]`)?.click();}
  for(const d of root.querySelectorAll('details[data-key]'))d.open=state.open.includes(d.dataset.key);
  for(const [key,top,left] of state.scroll){const n=[...root.querySelectorAll('[data-scroll]')].find(n=>n.dataset.scroll===key);if(n){n.scrollTop=top;n.scrollLeft=left;}}
  const focused=[...root.querySelectorAll('[data-key]')].find(n=>n.dataset.key===state.focused);
  (focused?.tagName==='DETAILS'?focused.querySelector('summary'):focused)?.focus({preventScroll:true});window.scrollTo(state.x,state.y);
}
export function startApp(root,toolbar,status,{shell=null,themeRoot=null}={}) {
  let view=null,selection=readProjectState().selection??{},head=new URL(window.location.href).searchParams.get('head'),knownHeads=[],theme='system',switchingHead=false,connected=false;
  const episodeReview=createEpisodeReviewController({getContext:()=>({view,historical:head!==null || switchingHead}),onChange:()=>{if(view)render();},onRefresh:async()=>{
    // Start a fresh generation: a poll begun before the POST may return old data.
    connected=false;await feed.selectHead(head);if(!connected)throw Error('기록 조회 실패');
  }});
  const handoffRoot=element('section');
  const handoffPanel=createHandoffPanel(handoffRoot,{load:async()=>{const response=await projectFetch('/api/document-handoffs',{cache:'no-store'});if(!response.ok)throw Error('handoff unavailable');return response.json();}});
  handoffPanel.setHistorical(head);handoffPanel.start();
  const discoveryRoot=element('section');
  const discoveryPanel=createDiscoveryPanel(discoveryRoot);discoveryPanel.setHistorical(head);
  const atlasRoot=element('section'),atlasRecords=element('section');
  const atlasPanel=createAtlasPanel(atlasRoot,{recordsRoot:atlasRecords,getCurrentView:()=>view,onRefresh:()=>feed.refresh()});atlasPanel.setHistorical(head);
  const discoveryFeed=createDiscoveryFeed({load:async()=>{
    const response=await projectFetch('/api/discovery',{cache:'no-store'});
    if(!response.ok)throw new Error(`탐색 조회 실패 (${response.status})`);return response.json();
  },onView:next=>discoveryPanel.update(next),onStatus:info=>discoveryPanel.setStatus(info)});
  try{theme=localStorage.getItem('research-theme')??'system';}catch{}
  function setTheme(value){theme=['system','light','dark'].includes(value)?value:'system';document.documentElement.dataset.theme=theme;try{localStorage.setItem('research-theme',theme);}catch{}}
  setTheme(theme);
  themeRoot?.append(selectControl('화면 모드','theme-select',[['system','시스템 설정'],['light','밝게'],['dark','어둡게']],theme,setTheme));
  const materialsRoot=element('section',undefined,'card');if(document.getElementById?.('project-picker'))loadMaterials(materialsRoot);
  let drafts=readProjectState().drafts??{};
  function saveDraft(event){const n=event.target;if(!n?.dataset?.key||!['INPUT','TEXTAREA','SELECT'].includes(n.tagName)||n.type==='file'||n.closest('#project-picker'))return;drafts[n.dataset.key]=n.value;saveProjectState({drafts});}
  document.addEventListener?.('click',event=>{if(event.target.closest?.('[data-all-episodes]')&&view){selection={...selection,stageGroup:null};render();}});
  document.addEventListener?.('input',saveDraft);document.addEventListener?.('change',saveDraft);
  function workspaceSync(){
    drafts=readProjectState().drafts??drafts;
    root.querySelector('.materials-slot')?.append(materialsRoot);
    root.querySelector('.handoff-slot')?.append(handoffRoot);
    handoffPanel.setHistorical(head);
    const nav=document.getElementById?.('stage-navigation');if(nav)renderStageNavigation(nav,view,selection,patch=>{selection={...selection,...patch,revisionId:null,councilId:null,issueId:null,issueScope:'stage',tab:'revision'};history.pushState({},'','#workflow');render();shell?.select('workflow');});
    for(const input of root.querySelectorAll('input[data-key],textarea[data-key],select[data-key]')){if(Object.hasOwn(drafts,input.dataset.key)&&input.type!=='file'&&!input.disabled&&!['head-select','revision-select','council-select'].includes(input.dataset.key)){input.value=drafts[input.dataset.key];input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input'));}}
    saveProjectState({selection,head,hash:window.location.hash});
  }
  function refreshObservation(){root.dataset.executionHistorical=String(head!==null||switchingHead);refreshExecutionObservation(root);}
  function render(){const saved=memory(root);selection=renderResearchView(root,view,selection,{episodeReview,onSelection:value=>{selection=value;render();}});root.querySelector('.atlas-slot').append(atlasRoot);root.querySelector('.discovery-slot').append(discoveryRoot);root.querySelector('.atlas-records-slot').append(atlasRecords);shell?.sync(view);workspaceSync();restore(root,saved);refreshObservation();}
  function controls(){toolbar.replaceChildren();toolbar.append(selectControl('기록 시점','head-select',[['','최신 기록 자동 갱신'],...[...knownHeads].reverse().map(h=>[h,`과거 기록 · ${h.slice(0,12)}`])],head??'',value=>{
      const target=value||null;const url=new URL(window.location.href);if(target)url.searchParams.set('head',target);else url.searchParams.delete('head');window.history.pushState({},'',url);head=target;switchingHead=true;if(view)render();discoveryPanel.setHistorical(head);atlasPanel.setHistorical(head);feed.selectHead(target);
    }),button('새로고침',()=>Promise.all([feed.refresh(),discoveryFeed.refresh()]),'refresh'));
    if(view)toolbar.append(element('span',head?'과거 기록을 보는 중 · 저장 불가':'최신 연구 기록','head-label'));
  }
  const feed=createLiveFeed({load:async selected=>{
    const response=await projectFetch(`/api/view${selected?`?head=${encodeURIComponent(selected)}`:''}`,{cache:'no-store'});if(!response.ok)throw new Error(`기록 조회 실패 (${response.status})`);return validateView(await response.json());},
    onView:next=>{
      switchingHead=false;const saved=memory(document.body),buffer=element('div');
      const nextSelection=renderResearchView(buffer,next,selection,{episodeReview,onSelection:value=>{selection=value;render();}});
      // Build completely before replacing the last valid screen.
      root.replaceChildren(...buffer.childNodes);root.querySelector('.atlas-slot').append(atlasRoot);root.querySelector('.discovery-slot').append(discoveryRoot);root.querySelector('.atlas-records-slot').append(atlasRecords);view=next;selection=nextSelection;atlasPanel.update(next);atlasPanel.refresh();shell?.sync(next);workspaceSync();
      knownHeads=[...new Set([...knownHeads,...next.heads.map(h=>h.head_id)])];controls();restore(document.body,saved);refreshObservation();
    },
    onStatus:info=>{refreshObservation();connected=info.connected;status.textContent=info.connected?`${head?'과거 기록을 보는 중 · 저장 불가':'연구 기록 연결됨'}${info.currentHead && view && info.currentHead!==view.head_id?' · 더 최근 기록이 있습니다':''}`:`연결 끊김 · ${info.error} · 마지막으로 불러온 기록을 보여주며 다시 연결합니다.`;status.className=info.connected?'connection':'connection warning';}});
  discoveryFeed.start();controls();if(head)feed.selectHead(head);else feed.start();window.addEventListener('popstate',()=>{head=new URL(window.location.href).searchParams.get('head');switchingHead=true;if(view)render();discoveryPanel.setHistorical(head);atlasPanel.setHistorical(head);feed.selectHead(head);});window.addEventListener('pagehide',()=>{saveProjectState({selection,head,hash:window.location.hash,drafts});feed.stop();discoveryFeed.stop();handoffPanel.stop();},{once:true});return feed;
}
if(typeof document!=='undefined') {
  const root=document.getElementById('research-app');if(root)(async()=>{
    try{const catalog=await loadCatalog();if(!projectId()&&catalog.default_project_id){const current=new URL(location.href);current.searchParams.set('project',preferredProject(catalog));location.replace(current.href);return;}
      if(projectId()&&!catalog.projects.some(p=>p.id===projectId()))throw Error('등록된 프로젝트를 찾을 수 없습니다.');
      mountProjectPicker(catalog);startApp(root,document.getElementById('toolbar'),document.getElementById('connection'),{shell:startShell(),themeRoot:document.getElementById('theme-control')});
    }catch(error){root.replaceChildren(element('p',error.message,'warning'));document.getElementById('connection').textContent='프로젝트를 열지 못했습니다.';}
  })();
}
