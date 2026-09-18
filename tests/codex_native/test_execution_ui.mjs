import test from 'node:test';
import assert from 'node:assert/strict';
const ui=await import('../../researchclaw/codex/research_ui/execution.js').catch(()=>({}));
class Element {
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.listeners={};this._text='';}
 set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 append(...v){this.children.push(...v);} setAttribute(k,v){this.attributes[k]=v;} addEventListener(k,v){this.listeners[k]=v;} click(){this.listeners.click?.();} focus(){this.focused=true;}
}
const nodes=n=>[n,...n.children.flatMap(nodes)];
const event=(type,payload={},sequence=1)=>({type,payload,sequence,event_id:`event-${sequence}`});
const work=(extra={})=>({work_id:'w',step_id:'evidence_review',purpose:'자료 사용 범위 검토',sequence:1,status:'running',attempts:[{attempt_id:'a',status:'running',events:[]}],...extra});
function render(rows){globalThis.document={createElement:tag=>new Element(tag)};const root=new Element('section');ui.renderExecutions(root,{executions:rows});return root;}
test('new work appears first and legacy snapshots produce no invented executions',()=>{
 assert.equal(typeof ui.orderedExecutions,'function');const rows=[work(),work({work_id:'next',sequence:2})];assert.equal(ui.orderedExecutions({executions:rows})[0].work_id,'next');assert.equal(rows[0].work_id,'w');assert.equal(render([]).textContent,'');
});
test('running and waiting reasons remain visible on collapsed rows; acceptance is not milestone completion',()=>{
 const root=render([work({status:'waiting_input',current_action:'본문 위치 확인 필요'})]);const card=nodes(root).find(n=>n.dataset.key==='execution:w');assert.match(card.children[0].textContent,/입력 대기.*본문 위치 확인 필요/);assert.ok(!card.open);
 assert.doesNotMatch(render([work({status:'accepted'})]).textContent,/M1 완료/);
});
test('phase tabs are independent and raw dialogue is inert and expandable',()=>{
 const root=render([work({attempts:[{attempt_id:'a',status:'running',events:[event('role_submitted',{phase:'initial',role:'소재',text:'<script>원문</script>'},1),event('role_submitted',{phase:'response',role:'방법',text:'상호 검토 원문'},2)]}]})]);
 const all=nodes(root),group=all.find(n=>n.dataset.councilPhase),tabs=all.filter(n=>n.attributes.role==='tab');assert.equal(tabs.length,3);tabs[1].click();assert.equal(group.dataset.councilPhase,'response');assert.equal(tabs[1].attributes['aria-selected'],'true');assert.equal(tabs[0].attributes['aria-selected'],'false');
 assert.ok(all.some(n=>n.tagName==='DETAILS'&&n.textContent.includes('<script>원문</script>')));assert.ok(!all.some(n=>n.tagName==='SCRIPT'));assert.match(root.textContent,/제출 원문/);
});
test('unpublished submissions show progress without content; failures retain checks and rework history',()=>{
 const root=render([work({status:'needs_work',attempts:[{attempt_id:'a',status:'needs_work',events:[event('role_submitted',{phase:'initial',role:'소재',published:false,text:'PRIVATE'},1),event('output_checked',{status:'needs_work',reason:'근거 위치 누락',next_action:'원문 위치 보완'},2),event('rework_assigned',{reason:'측정 조건 확인'},3)]}]})]);
 assert.doesNotMatch(root.textContent,/PRIVATE/);assert.match(root.textContent,/제출됨/);assert.match(root.textContent,/근거 위치 누락/);assert.match(root.textContent,/원문 위치 보완/);assert.match(root.textContent,/측정 조건 확인/);
});
test('heartbeat warning uses projected observation status without claiming failure',()=>{
 const root=render([work({observation_status:'stale'})]);assert.match(root.textContent,/실행 상태 확인 필요/);assert.doesNotMatch(root.textContent,/작업 실패/);
});
test('role start records show who is writing before any submission',()=>{
 const root=render([work({attempts:[{attempt_id:'a',status:'running',events:[event('role_started',{phase:'initial',role:'소재 검토자'})]}]})]);assert.match(root.textContent,/소재 검토자 · 의견 작성 중/);
});
test('result lists retain use limits and evidence locations without linking arbitrary schemes',()=>{
 const root=render([work({status:'accepted',attempts:[{attempt_id:'a',status:'accepted',result:{summary:'온도 범위 내에서 사용',allowed_uses:['조건 비교'],held_uses:['정량 예측'],evidence_refs:[{locator:'표 2',source_ref:'출처 버전'}]}}]})]);assert.match(root.textContent,/조건 비교/);assert.match(root.textContent,/정량 예측/);assert.match(root.textContent,/표 2/);
});
test('evidence review belongs to source stage and raw state codes do not replace current actions',()=>{
 assert.equal(ui.executionInGroup(work(),{id:'sources',nodes:['extract']}),true);assert.equal(ui.executionInGroup(work(),{id:'design',nodes:[]}),false);
 const root=render([work({current_action:'running'})]);assert.doesNotMatch(root.textContent,/running/);
});
test('actual contract claims and failed-check reasons are readable',()=>{
 const root=render([work({attempts:[{attempt_id:'a',status:'needs_work',checks:[{status:'needs_work',reason:'evidence_ref_unknown',next_action:'revise_input_or_result'}],result:{rationale:'검토 이유',recommendation:'limited',claims:[{text:'일부 조건에 사용',scope:'온도 범위',evidence_refs:['source-1']}],unresolved:[{question:'두께는?',impact:'비교 제한',next_action:'본문 확인'}]}}]})]);
 assert.match(root.textContent,/근거 연결을 확인해야 합니다/);assert.match(root.textContent,/온도 범위/);assert.match(root.textContent,/두께는/);assert.match(root.textContent,/source-1/);
});
test('observation refresh crosses 45 seconds without rerender and never marks historical records stale',()=>{
 const at=Date.parse('2026-09-18T01:00:00Z');const root=render([work({last_observed_at:new Date(at).toISOString()})]);
 const status=nodes(root).find(n=>n.dataset.executionObservation!==undefined);assert.ok(status);
 root.querySelectorAll=()=>[status];ui.refreshExecutionObservation(root,at+44999);assert.equal(status.hidden,true);
 ui.refreshExecutionObservation(root,at+45000);assert.equal(status.hidden,false);assert.equal(status.textContent,'실행 상태 확인 필요');
 root.dataset.executionHistorical='true';ui.refreshExecutionObservation(root,at+90000);assert.equal(status.hidden,true);
 root.dataset.executionHistorical='false';status.dataset.executionStatus='accepted';ui.refreshExecutionObservation(root,at+90000);assert.equal(status.hidden,true);
});
test('unknown observation and explicit recovery are distinct from execution failure',()=>{
 const root=render([work()]);const status=nodes(root).find(n=>n.dataset.executionObservation!==undefined);assert.ok(status);root.querySelectorAll=()=>[status];
 ui.refreshExecutionObservation(root,100000);assert.equal(status.textContent,'실행 상태 확인 안 됨');
});
test('unchanged HEAD status callback can refresh observation without rendering a new view',async()=>{
 const {createLiveFeed}=await import('../../researchclaw/codex/research_ui/live.js');
 const at=Date.parse('2026-09-18T01:00:00Z');let now=at,rendered=0;
 const root=render([work({last_observed_at:new Date(at).toISOString()})]);const status=nodes(root).find(n=>n.dataset.executionObservation!==undefined);root.querySelectorAll=()=>[status];
 const feed=createLiveFeed({load:async()=>({head_id:'same'}),onView:()=>rendered++,onStatus:()=>ui.refreshExecutionObservation(root,now),setTimer:()=>0,clearTimer:()=>{}});
 await feed.start();assert.equal(status.hidden,true);now+=45000;await feed.refresh();assert.equal(rendered,1);assert.equal(status.hidden,false);feed.stop();
 status.dataset.executionStatus='recovery_required';root.dataset.executionHistorical='true';ui.refreshExecutionObservation(root,now);assert.equal(status.textContent,'실행 상태 확인 필요');assert.equal(status.hidden,false);
});
