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
const statusLabels={budget_reached_with_gaps:'설정 회차 종료 · 미해결 쟁점 있음',reviewed_candidate_set:'후보 검토 회차 종료',running:'진행 중',failed:'실행 오류',complete:'회차 보고 완료',pending:'대기',unknown:'확인 필요',draft:'조정자 초안',provisional:'잠정 초안'};
const roleLabel=value=>roleLabels[value]??'역할 확인 필요';
const statusLabel=value=>statusLabels[value]??'확인 필요';
const labels={summary:'요약',queries:'에이전트가 보고한 검색어',next_queries:'다음 검색어',disagreements:'의견 차이',gaps:'남은 공백',sufficient:'역할별 탐색 충분성 판단',
 url:'원문 주소',doi:'DOI',query:'에이전트가 보고한 발견 검색어',query_observed:'검색어 관측 여부',access_status:'접근 상태',reading_scope:'에이전트가 보고한 읽은 범위',finding:'에이전트의 자료 해석 · 미검증',limitations:'해석의 한계',interpretation:'에이전트의 해석 · 미검증',access_level:'에이전트가 보고한 읽은 범위',
 status:'상태',reason:'선정 이유',statement:'가설',test:'검증 제안',limits:'한계',unresolved:'미해결 사항'};
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
  header.append(element('p','LIVE DISCOVERY / 연구 초안','eyebrow'),element('h2','문헌 탐색 · 후보 선정 · 가설'),element('p','최신 탐색 결과를 별도로 표시합니다. 후보 기록은 논문·저장소·버전을 포함하며, 검증된 근거나 완료된 M1을 뜻하지 않습니다.','muted'),status,metrics);
  const filter=element('div',undefined,'detail-controls');
  const searchLabel=element('label','후보 검색'),search=element('input');search.type='search';search.placeholder='제목, DOI, 해석, 한계 검색';search.dataset.key='discovery-search';search.value='';searchLabel.append(search);
  const roleControlLabel=element('label','탐색 역할'),role=element('select');role.dataset.key='discovery-role';role.value='';roleControlLabel.append(role);
  const count=element('p',undefined,'muted'),list=element('div',undefined,'discovery-sources');list.dataset.scroll='discovery-sources';
  const reports=element('section'),selection=element('section');filter.append(searchLabel,roleControlLabel);
  const library=disclosure('후보 자료 검색 · 역할별 해석','discovery-library');library.append(filter,count,list);
  const reportGroup=disclosure('에이전트 탐색 보고서','discovery-reports');reportGroup.append(roles,reports);
  const scope=disclosure('자료의 확인 범위와 한계','discovery-scope');scope.append(limits);
  const latest=element('p',undefined,'prose discovery-latest');
  const contents=disclosure('선정 초안 · 후보 자료 · 에이전트 보고서 열기','discovery-contents');contents.append(selection,library,reportGroup,scope);
  root.append(header,latest,contents);
  const expanded=new Map();
  function remember(node) {for(const child of node.children??[]){if(child.tagName==='DETAILS')expanded.set(child.dataset.key,child.open===true);remember(child);}}
  function restore(node) {for(const child of node.children??[]){if(child.tagName==='DETAILS')child.open=expanded.get(child.dataset.key)??false;restore(child);}}
  function drawSources() {
    remember(list);const scroll=list.scrollTop,needle=search.value.trim().toLocaleLowerCase();
    const sources=snapshot.sources.filter(s=>(!role.value||s.observations.some(o=>o.role===role.value))&&(!needle||JSON.stringify(s).toLocaleLowerCase().includes(needle)));
    const nodes=sources.map(s=>{
      const item=disclosure(s.title||s.key,`source:${s.key}`);item.append(element('p',s.key,'mono'));
      for(const o of s.observations){const entry=element('article');entry.append(element('h4',`${roleLabel(o.role)} · ${o.round}차 출처 관찰`));
        for(const key of ['url','doi','query','query_observed','access_status','reading_scope','finding','limitations','interpretation','access_level'])field(entry,key,o.source[key]);item.append(entry);}
      return item;
    });list.replaceChildren(...nodes);restore(list);list.scrollTop=scroll;count.textContent=`${sources.length} / ${snapshot.sources.length}개 후보 기록 표시 · 중복 관찰은 자료 안에서 확인`;
  }
  search.addEventListener('input',()=>{if(snapshot)drawSources();});role.addEventListener('change',()=>{if(snapshot)drawSources();});
  function update(next) {
    validateDiscovery(next);latest.textContent=next.selection?.summary??'선정·가설 초안 대기 중';remember(reports);remember(selection);snapshot=next;root.hidden=historical||!next.available;
    metrics.textContent=`${next.candidate_records??0}개 후보 관찰 · ${next.unique_candidates??next.sources.length}개 식별자 통합 후보 기록 · ${next.completed_reports??0}개 역할 보고서 · ${next.round??0}/${next.max_rounds??0}차 · ${statusLabel(next.status)}`;
    roles.replaceChildren(...next.roles.map(r=>element('p',`${roleLabel(r.role)} · ${r.round}차 · ${statusLabel(r.status)}${r.web_calls!==undefined?` · 웹 호출 ${r.web_calls}회`:''}${r.last_activity_at?` · ${r.last_activity_at}`:''}`,'badge')));
    limits.replaceChildren(element('p','이 탐색 결과는 M1 완료를 입증하지 않습니다. 검색 결과 수와 원문 읽기 수는 후보 수와 다릅니다.','callout'),...next.limitations.map(v=>element('p',v,'muted')));
    const chosen=role.value,options=[element('option','전체 역할')];options[0].value='';
    for(const name of [...new Set(next.sources.flatMap(s=>s.observations.map(o=>o.role)))].sort()){const option=element('option',roleLabel(name));option.value=name;options.push(option);}
    role.replaceChildren(...options);role.value=options.some(o=>o.value===chosen)?chosen:'';
    drawSources();reports.replaceChildren(element('h3','역할별 회차 보고서 · 검색어 · 의견 차이'));
    for(const report of next.reports){const node=disclosure(`${report.round}차 · ${roleLabel(report.role)}`,`report:${report.round}:${report.role}`);
      for(const key of ['summary','queries','disagreements','gaps','next_queries','sufficient'])field(node,key,report[key]);reports.append(node);}
    selection.replaceChildren(element('h3','잠정 선정과 검증 전 가설'));
    if(!next.selection)selection.append(element('p','선정·가설 초안 대기 중','muted'));
    else {const draft=next.selection;field(selection,'status',draft.status);field(selection,'summary',draft.summary);
      for(const group of draft.groups??[]){const node=disclosure(group.title,`group:${group.id}`);field(node,'reason',group.reason);
        for(const key of group.source_keys??[]){const source=next.sources.find(s=>s.key===key);node.append(element('p',`${source?.title??'현재 목록에서 확인되지 않는 후보'} · ${key}`,'prose'));}selection.append(node);}
      for(const hypothesis of draft.hypotheses??[]){const node=disclosure(`${hypothesis.id} · ${hypothesis.statement}`,`hypothesis:${hypothesis.id}`);for(const key of ['statement','test','limits'])field(node,key,hypothesis[key]);selection.append(node);}const unresolved=disclosure(`미해결 사항 · ${draft.unresolved.length}건`,'discovery-unresolved');field(unresolved,'unresolved',draft.unresolved);selection.append(unresolved);
    }
    restore(reports);restore(selection);
  }
  return {update,setHistorical(value){historical=Boolean(value);root.hidden=historical||snapshot?.available===false;},setStatus(info){status.textContent=info.connected?'탐색 결과 연결됨 · 읽기 전용':'탐색 연결 끊김 · 마지막 정상 탐색 결과를 유지하며 재연결합니다.';status.className=info.connected?'muted':'warning';}};
}
