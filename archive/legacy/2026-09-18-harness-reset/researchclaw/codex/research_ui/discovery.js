import {element,renderValue} from './detail.js';
import {createLiveFeed} from './live.js';

export function validateDiscovery(value) {
  if(!value || value.schema_version!==1 || typeof value.revision!=='string' || !value.revision || typeof value.available!=='boolean')throw Error('탐색 자료 형식이 올바르지 않습니다.');
  for(const key of ['roles','reports','sources','limitations'])if(!Array.isArray(value[key]) || value[key].some(v=>v===null))throw Error('탐색 목록을 확인할 수 없습니다.');
  for(const source of value.sources)if(typeof source.key!=='string' || !Array.isArray(source.observations) || source.observations.some(o=>!o || !o.source || typeof o.source!=='object'))throw Error('후보 출처를 확인할 수 없습니다.');
  if(value.selection!==null && value.selection!==undefined) {
    const draft=value.selection;
    for(const key of ['groups','hypotheses','unresolved'])if(!Array.isArray(draft[key]) || draft[key].some(v=>v===null))throw Error('선정 초안 형식이 올바르지 않습니다.');
    for(const group of draft.groups)if(!Array.isArray(group.source_keys))throw Error('선정 출처 연결이 올바르지 않습니다.');
  }
  return value;
}
export function createDiscoveryFeed(options) {
  // Use the discovery digest as this feed's identity, independently of native HEAD.
  return createLiveFeed({...options,load:async()=>{
    const view=validateDiscovery(await options.load());return {...view,head_id:view.revision};
  }});
}
const roleLabels={domain:'소재',methodology:'방법론',critical:'SDL·반증'};
const statusLabels={budget_reached_with_gaps:'이번 탐색 종료 · 추가 확인 필요',reviewed_candidate_set:'후보 검토 회차 종료',running:'진행 중',failed:'실행 오류',complete:'회차 보고 완료',pending:'대기',unknown:'확인 필요',draft:'현재 검토 요약',provisional:'잠정 초안'};
const roleLabel=value=>roleLabels[value]??'역할 확인 필요';
const statusLabel=value=>statusLabels[value]??'확인 필요';
const labels={summary:'요약',queries:'검색에 사용한 말',next_queries:'다음 검색어',disagreements:'의견 차이',gaps:'아직 부족한 근거',sufficient:'자료를 더 찾아야 하는지',
 url:'원문 주소',doi:'DOI',query:'에이전트가 보고한 검색어',query_observed:'실행 기록에서 검색어 확인',access_status:'접근 상태',reading_scope:'읽은 범위',finding:'이 자료에 대한 의견',limitations:'해석의 한계',interpretation:'이 자료에 대한 의견',access_level:'읽은 범위',
 status:'상태',reason:'선정 이유',statement:'가설',test:'검증 제안',limits:'한계',unresolved:'아직 확인할 것'};
function field(parent,key,value) {
  if(value===undefined || value===null)return;
  const section=element('div',undefined,'discovery-field');section.append(element('h4',labels[key]??key),renderValue({},key==='status'?statusLabel(value):value,key));parent.append(section);
}
function disclosure(title,key) {
  const node=element('details',undefined,'discovery-record');node.dataset.key=key;node.append(element('summary',title));return node;
}
export function createDiscoveryPanel(root) {
  let snapshot=null,historical=false;
  root.className='discovery-panel card';
  const header=element('header'),status=element('p','탐색 결과 연결 중…','muted'),metrics=element('p',undefined,'discovery-metrics'),limits=element('div'),roles=element('div',undefined,'discovery-roles');
  header.append(element('p','문헌 탐색','eyebrow'),element('h2','찾은 자료와 현재 판단'),element('p','에이전트가 찾은 논문과 관련 자료입니다. 자료를 어디까지 읽고 검토했는지 확인할 수 있습니다.','muted'),status,metrics);
  const filter=element('div',undefined,'detail-controls');
  const searchLabel=element('label','찾은 자료 검색'),search=element('input');search.type='search';search.placeholder='제목, DOI, 해석, 한계 검색';search.dataset.key='discovery-search';search.value='';searchLabel.append(search);
  const roleControlLabel=element('label','탐색 역할'),role=element('select');role.dataset.key='discovery-role';role.value='';roleControlLabel.append(role);
  const count=element('p',undefined,'muted'),list=element('div',undefined,'discovery-sources');list.dataset.scroll='discovery-sources';
  const reports=element('section'),selection=element('section');filter.append(searchLabel,roleControlLabel);
  const library=disclosure('후보 자료 검색 · 역할별 해석','discovery-library');library.append(filter,count,list);
  const reportGroup=disclosure('에이전트 탐색 보고서','discovery-reports');reportGroup.append(roles,reports);
  const scope=disclosure('자료를 읽을 때 알아둘 점','discovery-scope');scope.append(limits);
  const latest=element('p',undefined,'prose discovery-latest');
  const contents=disclosure('자료 목록과 에이전트 의견 보기','discovery-contents');contents.append(selection,library,reportGroup,scope);
  const guide=element('section',undefined,'discussion-guide');
  root.append(header,latest,guide,contents);
  const expanded=new Map();
  function remember(node) {for(const child of node.children??[]){if(child.tagName==='DETAILS')expanded.set(child.dataset.key,child.open===true);remember(child);}}
  function restore(node) {for(const child of node.children??[]){if(child.tagName==='DETAILS')child.open=expanded.get(child.dataset.key)??false;restore(child);}}
  function drawSources() {
    remember(list);const scroll=list.scrollTop,needle=search.value.trim().toLocaleLowerCase();
    const sources=snapshot.sources.filter(s=>(!role.value||s.observations.some(o=>o.role===role.value))&&(!needle||JSON.stringify(s).toLocaleLowerCase().includes(needle)));
    const nodes=sources.map(s=>{
      const item=disclosure(s.title||s.key,`source:${s.key}`);item.append(element('p',s.key,'mono'));
      for(const o of s.observations){const entry=element('article');entry.append(element('h4',`${roleLabel(o.role)} · ${o.round}차 자료 확인 기록`));
        for(const key of ['url','doi','query','query_observed','access_status','reading_scope','finding','limitations','interpretation','access_level'])field(entry,key,o.source[key]);item.append(entry);}
      return item;
    });list.replaceChildren(...nodes);restore(list);list.scrollTop=scroll;count.textContent=`${sources.length} / ${snapshot.sources.length}개 후보 기록 표시 · 중복 관찰은 자료 안에서 확인`;
  }
  search.addEventListener('input',()=>{if(snapshot)drawSources();});role.addEventListener('change',()=>{if(snapshot)drawSources();});
  function update(next) {
    validateDiscovery(next);latest.textContent=next.selection?.summary??'자료 선정과 가설 초안을 기다리고 있습니다.';
    guide.replaceChildren();
    if(next.selection?.reading_guide){
      guide.append(element('h3','근거 검토 요약'),element('p','조정자가 정리한 검토 요약입니다. 실제 발언과 출처는 해당 검토의 대화·근거에서 확인하세요.','muted'));
      field(guide,'summary',next.selection.reading_guide);
    }
    remember(reports);remember(selection);snapshot=next;root.hidden=historical||!next.available;
    metrics.textContent=`${next.candidate_records??0}회 자료 발견 · ${next.unique_candidates??next.sources.length}개 자료 기록 · ${next.completed_reports??0}개 탐색 보고서 · ${next.round??0}/${next.max_rounds??0}차 · ${statusLabel(next.status)}`;
    roles.replaceChildren(...next.roles.map(r=>element('p',`${roleLabel(r.role)} · ${r.round}차 · ${statusLabel(r.status)}${r.web_calls!==undefined?` · 웹 호출 ${r.web_calls}회`:''}${r.last_activity_at?` · ${r.last_activity_at}`:''}`,'badge')));
    limits.replaceChildren(element('p','찾은 자료 중에는 제목이나 초록만 확인한 것도 있습니다. 자료별 읽은 범위를 함께 확인하세요.','callout'),...next.limitations.map(v=>element('p',v,'muted')));
    const chosen=role.value,options=[element('option','전체 역할')];options[0].value='';
    for(const name of [...new Set(next.sources.flatMap(s=>s.observations.map(o=>o.role)))].sort()){const option=element('option',roleLabel(name));option.value=name;options.push(option);}
    role.replaceChildren(...options);role.value=options.some(o=>o.value===chosen)?chosen:'';
    drawSources();reports.replaceChildren(element('h3','역할별 회차 보고서 · 검색어 · 의견 차이'));
    for(const report of next.reports){const node=disclosure(`${report.round}차 · ${roleLabel(report.role)}`,`report:${report.round}:${report.role}`);
      for(const key of ['summary','queries','disagreements','gaps','next_queries','sufficient'])field(node,key,report[key]);reports.append(node);}
    selection.replaceChildren(element('h3','검토 중인 자료와 연구 가설'));
    if(!next.selection)selection.append(element('p','자료 선정과 가설 초안을 기다리고 있습니다.','muted'));
    else {const draft=next.selection;field(selection,'status',draft.status);field(selection,'summary',draft.summary);
      for(const group of draft.groups??[]){const node=disclosure(group.title,`group:${group.id}`);field(node,'reason',group.reason);
        for(const key of group.source_keys??[]){const source=next.sources.find(s=>s.key===key);node.append(element('p',`${source?.title??'현재 목록에서 확인되지 않는 후보'} · ${key}`,'prose'));}selection.append(node);}
      for(const hypothesis of draft.hypotheses??[]){const node=disclosure(`${hypothesis.id} · ${hypothesis.statement}`,`hypothesis:${hypothesis.id}`);for(const key of ['statement','test','limits'])field(node,key,hypothesis[key]);selection.append(node);}const unresolved=disclosure(`아직 확인할 것 · ${draft.unresolved.length}건`,'discovery-unresolved');field(unresolved,'unresolved',draft.unresolved);selection.append(unresolved);
    }
    restore(reports);restore(selection);
  }
  return {update,setHistorical(value){historical=Boolean(value);root.hidden=historical||snapshot?.available===false;},setStatus(info){status.textContent=info.connected?'탐색 기록 연결됨':'탐색 기록 연결 끊김 · 마지막으로 불러온 결과를 보여주며 다시 연결합니다.';status.className=info.connected?'muted':'warning';}};
}
