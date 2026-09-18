import {element,button} from './detail.js';
const states={
 submission_pending:['Documents 접수 확인 전','접수 기록을 확인한 뒤 같은 요청을 이어갑니다.','processing'],
 atlas_submission_pending:['Atlas 접수 대기','Documents 작업을 Atlas에 전달할 차례입니다.','processing'],
 accepted:['Atlas 접수됨','다음 처리 기록을 기다립니다.','processing'],
 waiting_conversion:['문서 변환 대기','Atlas가 Documents의 변환 결과를 기다립니다.','processing'],
 fetching:['변환 자료 가져오는 중','Atlas가 원문과 변환 결과를 확인합니다.','processing'],
 organizing:['Atlas 정리 중','Atlas가 내용을 정리하고 검색할 수 있도록 보관합니다.','processing'],
 completed:['정리 완료','Pilot이 읽은 범위와 내용을 검토해 연구에 사용할지 판단합니다.','completed'],
 partial:['일부 정리됨','빠진 내용과 사용 가능한 범위를 확인해야 합니다.','attention'],
 needs_attention:['확인 필요','처리를 이어가기 전에 연결 또는 자료 상태를 확인해야 합니다.','attention'],
 failed:['처리 실패','실패 원인을 확인해야 합니다. 기존 요청 기록은 보존됩니다.','attention'],
 cancelled:['처리 취소됨','이 요청의 후속 처리를 중단했습니다.','attention']
};
export function reviewLabel(status){return ({unrecorded:'검토 등록 전',awaiting_input:'검토 자료 준비 중',input_ready:'토론 대기',review_running:'토론 시작됨',review_failed:'실행 확인 필요',needs_recovery:'자료 보완 필요',review_complete:'개별 검토 완료'})[status]??'검토 상태 확인 필요';}
const roleLabels={domain:'소재·공정 검토자',methodology:'비교·평가 방법 검토자',critical:'반례·자료 공백 검토자'};
export function statusInfo(status){const [label,next,group]=states[status]??['상태 확인 필요','아직 처리 상태를 해석할 수 없습니다.','attention'];return {label,next,group};}
export function filterItems(items,query,group){const q=query.trim().toLocaleLowerCase();return items.filter(r=>(group==='all'||statusInfo(r.status).group===group)&&[r.title,r.doi,r.purpose].some(v=>String(v??'').toLocaleLowerCase().includes(q)));}
export function safeLink(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
export function createHandoffPanel(root,{load}={}){
 root.className='handoff-panel';
 let items=[],historical=false,busy=false,ready=false,stopped=false,timer;
 const heading=element('h2','자료 처리 현황'),intro=element('p','원문 변환부터 Atlas 정리까지, 자료별 진행 상황을 확인합니다.','muted');
 const notice=element('p','처리 기록을 불러오는 중입니다.','muted');notice.setAttribute('role','status');
 const controls=element('div',undefined,'handoff-controls'),searchLabel=element('label','자료 검색'),search=element('input');search.type='search';search.placeholder='제목 또는 DOI';search.dataset.key='handoff-search';
 const filterLabel=element('label','처리 상태'),filter=element('select');filter.dataset.key='handoff-filter';
 for(const [v,t] of [['all','전체'],['processing','처리 중'],['attention','확인 필요'],['completed','정리 완료']]){const o=element('option',t);o.value=v;filter.append(o);}
 searchLabel.append(search);filterLabel.append(filter);const refresh=button('상태 새로고침',()=>update(),'handoff-refresh');controls.append(searchLabel,filterLabel,refresh);
 const list=element('div',undefined,'handoff-list'),opened=new Set();
 function draw(){
   if(historical){list.replaceChildren();controls.hidden=true;notice.textContent='자료 처리 현황은 최신 기록에서 확인할 수 있습니다.';return;}
   controls.hidden=false;
   const focused=list.contains(document.activeElement)?document.activeElement?.dataset.key:null;
   const rows=filterItems(items,search.value,filter.value||'all');
   const nodes=rows.map(row=>{
     const info=statusInfo(row.status),details=element('details',undefined,'handoff-row');details.open=opened.has(row.id);details.dataset.key=`handoff:${row.id}`;
     const summary=element('summary'),title=element('strong',row.title),state=element('span',info.label,`handoff-status ${info.group}`);summary.dataset.key=`handoff-summary:${row.id}`;summary.append(title,state);if(row.pilot_review&&row.pilot_review!=='unrecorded')summary.append(element('span',reviewLabel(row.pilot_review),'handoff-status'));details.append(summary);
     details.addEventListener('toggle',()=>{if(details.open)opened.add(row.id);else opened.delete(row.id);});
     const body=element('div',undefined,'handoff-body');
     if(row.purpose)body.append(element('p',`이 연구에 필요한 이유: ${row.purpose}`));
     body.append(element('p',info.next,'handoff-next'));
     const stages=element('ol',undefined,'handoff-stages');
     for(const text of [`Documents 접수 · ${row.documents_received?'확인됨':'확인 전'}`,`Atlas 접수 · ${row.atlas_received?'확인됨':'확인 전'}`,`자료 정리 · ${info.label}`,`Pilot 개별 검토 · ${reviewLabel(row.pilot_review)}`])stages.append(element('li',text));
     body.append(stages);
     const url=safeLink(row.source_url);if(url){const link=element('a','원문 주소 열기');link.href=url;link.target='_blank';link.rel='noopener noreferrer';body.append(link);}
     body.append(element('p',row.result_received?(row.pilot_review==='review_complete'?'Atlas 결과를 바탕으로 개별 검토를 마쳤습니다. 아래에서 결론과 대화를 확인하세요.':'Atlas 결과를 받았습니다. Pilot 검토 상태를 확인하세요.'):'Pilot이 확인한 정리 결과가 아직 없습니다.','muted'));
     for(const review of row.reviews??[]){
       const section=element('section',undefined,'handoff-review');section.append(element('h3',reviewLabel(review.status)));
       const fold=(label,key)=>{const d=element('details');d.open=opened.has(key);d.append(element('summary',label));d.addEventListener('toggle',()=>{if(d.open)opened.add(key);else opened.delete(key);});return d;};
       if(review.conclusion){
         const conclusion=fold('조정자 결론과 다음 작업',`review:${review.id}:conclusion`);
         for(const paragraph of review.conclusion.split(/\n\s*\n/))conclusion.append(element('p',paragraph));
         section.append(conclusion);
       }
       for(const round of review.rounds??[]){
         const label=({initial:'처음 의견',response:'서로의 의견 검토',final:'최종 의견'})[round.phase]??round.phase;
         const phase=fold(label,`review:${review.id}:${round.phase}`);
         for(const [index,statement] of (round.statements??[]).entries()){
           const speech=fold(roleLabels[statement.role]??'검토자',`review:${review.id}:${round.phase}:${index}`);
           for(const paragraph of statement.text.split(/\n\s*\n/))speech.append(element('p',paragraph));
           phase.append(speech);
         }
         section.append(phase);
       }
       body.append(section);
     }
     if(row.result_received&&typeof row.read_scope==='string')body.append(element('p',`Atlas가 확인한 범위: ${row.read_scope}`));
     if(row.result_received&&Array.isArray(row.unresolved)&&row.unresolved.length){const gaps=element('details');gaps.append(element('summary','Atlas가 남긴 미확인 사항'));const ul=element('ul');for(const gap of row.unresolved)if(typeof gap==='string')ul.append(element('li',gap));gaps.append(ul);body.append(gaps);}
     const trace=element('details',undefined,'handoff-trace');trace.open=opened.has(`trace:${row.id}`);trace.addEventListener('toggle',()=>{if(trace.open)opened.add(`trace:${row.id}`);else opened.delete(`trace:${row.id}`);});trace.append(element('summary','접수 기록 보기'));const dl=element('dl');
     for(const [label,value] of [['DOI',row.doi],['요청',row.request_key],['Documents 작업',row.task_id],['Atlas 작업',row.import_id],['최근 알림',row.event_id]])if(value)dl.append(element('dt',label),element('dd',value));trace.append(dl);body.append(trace);details.append(body);return details;
   });
   list.replaceChildren(...nodes);
   if(focused)Array.from(list.querySelectorAll('[data-key]')).find(n=>n.dataset.key===focused)?.focus({preventScroll:true});
   if(!rows.length&&ready)list.append(element('p',items.length?'검색 조건에 맞는 자료가 없습니다.':'아직 변환·정리를 의뢰한 자료가 없습니다. 기존 탐색 자료는 아래에서 확인할 수 있습니다.','empty'));
 }
 async function update(){
   if(busy||historical||stopped)return;busy=true;refresh.disabled=true;
   try{const data=await load();if(stopped)return;if(data.schema_version!==1||!Array.isArray(data.items))throw Error('format');items=data.items;ready=true;draw();if(!historical)notice.textContent=`마지막 확인 ${new Date().toLocaleTimeString('ko-KR')} · ${items.length}건`;}
   catch{if(!historical)notice.textContent=ready?'새 상태를 확인하지 못했습니다. 마지막으로 받은 기록을 보여줍니다.':'처리 기록을 불러오지 못했습니다. 상태 새로고침으로 다시 확인하세요.';}
   finally{busy=false;refresh.disabled=false;}
 }
 search.addEventListener('input',draw);filter.addEventListener('change',draw);
 root.append(heading,intro,controls,notice,list);
 return {refresh:update,start(){update();timer=setInterval(update,60000);},stop(){stopped=true;clearInterval(timer);},setHistorical(value){const next=Boolean(value);if(next===historical)return;historical=next;draw();if(!historical)update();}};
}
