import test from 'node:test';
import assert from 'node:assert/strict';
const ui=await import('../../../researchclaw/codex/research_ui/episode_review.js').catch(()=>({}));
const app=await import('../../../researchclaw/codex/research_ui/app.js');
const episodes=await import('../../../researchclaw/codex/research_ui/episodes.js');
class Element {
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.events={};this._text='';this.value='';this.disabled=false;}
  set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set innerHTML(_){throw Error('unsafe HTML');} append(...v){this.children.push(...v);} replaceChildren(...v){this.children=v;}
  setAttribute(k,v){this.attributes[k]=v;} addEventListener(k,v){this.events[k]=v;}
}
const all=n=>[n,...n.children.flatMap(all)];
const byKey=(root,key)=>all(root).find(n=>n.dataset.key===key);
const episode=(extra={})=>({id:'e1',sequence:1,stage:'자료 검토',title:'비교 준비',purpose:'조건 확인',depends_on:[],notes:[],execution_status:'finished',conclusion:{judgment:'비교 가능'},review_required:true,review_status:'pending',review:null,...extra});
const response=(status=200)=>({ok:status===200,status,json:async()=>({head_id:'h2',episode_id:'e1',review_status:'continued',review:{decision:'continue',feedback:'확인했습니다.',reviewer:'local-ui-user'}})});
function setup(options={}) {
  globalThis.document={createElement:tag=>new Element(tag)};
  let context={view:{head_id:'h1',current_head_id:'h1',work_episodes:[episode()]},historical:false},ids=0;
  const root=new Element('section'),calls=[];
  const controller=ui.createEpisodeReviewController({getContext:()=>context,commandId:()=>`c${++ids}`,request:async(...args)=>{calls.push(args);return response();},onChange:render,...options});
  function render(){root.replaceChildren();episodes.renderEpisodes(root,context.view,controller);}
  render();
  return {root,controller,calls,render,get context(){return context;},set context(value){context=value;},input(value){const input=byKey(root,'episode-feedback:e1');input.value=value;input.events.input();},click(action){return byKey(root,`episode-${action}:e1`).events.click();}};
}
test('draft survives rerender and pinned current HEAD cannot save',async()=>{
  const s=setup();s.input('의견 <script>');s.render();assert.equal(byKey(s.root,'episode-feedback:e1').value,'의견 <script>');
  s.context.historical=true;s.render();assert.equal(byKey(s.root,'episode-continue:e1').disabled,true);await s.click('continue');assert.equal(s.calls.length,0);
  s.context.historical=false;s.render();await s.click('continue');assert.equal(s.calls.length,1);
  assert.equal(s.calls[0][0],'/api/episodes/review');assert.equal(s.calls[0][1].method,'POST');assert.deepEqual(JSON.parse(s.calls[0][1].body),{id:'e1',decision:'continue',feedback:'의견 <script>',expected_head:'h1',command_id:'c1'});
});
test('running, reviewed and autonomous episodes have no new review form',()=>{
  const s=setup();for(const extra of [{execution_status:'running',conclusion:null},{review_required:false},{review:{decision:'continue',feedback:'원래 의견',reviewer:'사람'},review_status:'continued'}]){
    s.context.view.work_episodes=[episode(extra)];s.render();assert.equal(byKey(s.root,'episode-continue:e1'),undefined);
  }
});
test('transport loss freezes payload and blocks editing/new decisions even after HEAD refresh',async()=>{
  const calls=[];let mode='lost';const s=setup({request:async(path,options)=>{calls.push(options.body);if(mode==='lost')throw Error('network');return response();}});
  s.input('첫 의견');await s.click('continue');assert.equal(byKey(s.root,'episode-feedback:e1').disabled,true);assert.equal(byKey(s.root,'episode-revise:e1').disabled,true);
  s.context.view.head_id='h9';s.context.view.current_head_id='h9';s.render();s.input('다른 의견');await s.controller.submit('e1','revise');assert.equal(calls.length,1);
  s.context.historical=true;s.render();await s.controller.retry('e1');assert.equal(calls.length,1);
  s.context.historical=false;s.render();mode='ok';await s.click('retry');assert.equal(calls.length,2);assert.equal(calls[0],calls[1]);
});
test('pending submit suppresses double click',async()=>{
  let resolve,calls=0;const s=setup({request:()=>{calls++;return new Promise(r=>resolve=r);}});s.input('의견');const pending=s.click('revise');
  await s.controller.submit('e1','continue');assert.equal(calls,1);assert.equal(byKey(s.root,'episode-feedback:e1').disabled,true);resolve({...response(),json:async()=>({head_id:'h2',episode_id:'e1',review_status:'revision_requested',review:{decision:'revise',feedback:'의견',reviewer:'local-ui-user'}})});await pending;
});
test('definite conflict preserves draft, refreshes records and permits corrected new command',async()=>{
  let mode=409,refreshes=0;const calls=[];const s=setup({request:async(path,options)=>{calls.push(JSON.parse(options.body));return response(mode);},onRefresh:async()=>{refreshes++;s.context.view.head_id='h3';s.context.view.current_head_id='h3';}});
  s.input('처음 의견');await s.click('continue');assert.equal(refreshes,1);assert.equal(byKey(s.root,'episode-feedback:e1').value,'처음 의견');
  mode=200;s.input('고친 의견');await s.click('continue');assert.equal(calls[1].command_id,'c2');assert.equal(calls[1].expected_head,'h3');assert.equal(calls[1].feedback,'고친 의견');
});
test('confirmed save followed by refresh failure stays saved and cannot resend',async()=>{
  const s=setup({onRefresh:async()=>{throw Error('read failed');}});s.input('의견');await s.click('continue');assert.match(s.root.textContent,/저장했습니다/);assert.match(s.root.textContent,/불러오지 못/);
  await s.controller.submit('e1','continue');await s.controller.retry('e1');assert.equal(s.calls.length,1);
});
test('5xx and unreadable success response permit only the original request retry',async()=>{
  for(const reply of [response(503),{ok:true,status:200,json:async()=>{throw Error('truncated');}}]){
    const s=setup({request:async()=>reply});s.input('의견');await s.click('continue');assert.ok(byKey(s.root,'episode-retry:e1'));assert.equal(byKey(s.root,'episode-continue:e1').disabled,true);
  }
});
test('blank feedback never sends a request',async()=>{const s=setup();s.input('  ');await s.click('continue');assert.equal(s.calls.length,0);assert.match(s.root.textContent,/의견을 입력/);});

test('full view forwards review controller and keeps existing selection callbacks',async()=>{
  const s=setup(),arrays=['heads','milestones','nodes','revisions','transitions','councils','issues','verifications','results','source_checks','approvals','dependencies','handoffs','artifacts','reason_codes','required_actions'];
  const view={...Object.fromEntries(arrays.map(k=>[k,[]])),...s.context.view,schema_version:1,workflow_version:'research-graph-v1',project:{topic:'합성 검토'},nodes:[{id:'questions',label:'질문',reason_codes:[]}]};
  let selected;app.renderResearchView(s.root,view,{}, {episodeReview:s.controller,onSelection:value=>selected=value});
  assert.ok(byKey(s.root,'episode-feedback:e1'));assert.ok(byKey(s.root,'episode:e1'));
  assert.equal(byKey(s.root,'node:questions'),undefined);
  assert.equal(selected,undefined); // No empty legacy map for episode-only projects.
});
