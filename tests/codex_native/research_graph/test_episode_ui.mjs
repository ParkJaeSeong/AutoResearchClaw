import test from 'node:test';
import assert from 'node:assert/strict';
const ui=await import('../../../researchclaw/codex/research_ui/episodes.js').catch(()=>({}));
class Element {
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this._text='';}
  set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set innerHTML(_){throw Error('HTML prohibited');} append(...v){this.children.push(...v);}
  setAttribute(k,v){this.attributes[k]=v;} addEventListener(){}
}
const row=(id,sequence,extra={})=>({id,sequence,stage:'자료 탐색',title:id,purpose:'설계 근거 찾기',execution_status:'running',review_required:true,review_status:'pending',depends_on:[],return_to:null,notes:[],conclusion:null,...extra});
test('start sequence determines order without modifying input or inventing old episodes',()=>{
 const rows=[row('first',1,{execution_status:'finished'}),row('second',2)];
 assert.deepEqual(ui.orderedEpisodes({work_episodes:rows}).map(r=>r.id),['second','first']);
 assert.deepEqual(rows.map(r=>r.id),['first','second']);assert.deepEqual(ui.orderedEpisodes({}),[]);
});
test('cards separate conclusion/review and display original notes as inert text',()=>{
 globalThis.document={createElement:tag=>new Element(tag)};
 try{const root=new Element('section');ui.renderEpisodes(root,{work_episodes:[row('analysis',2,{execution_status:'finished',return_to:'search',return_reason:'온도 정보 부족',
 conclusion:{judgment:'비교를 보류합니다.',remaining:'온도 미확인',next_action:'추가 탐색',next_reason:'조건을 맞추기 위해'},
 notes:[{kind:'dialogue',author:'분야 검토자',text:'<script>bad()</script>'},{kind:'tool',author:'Atlas',text:'부분 분석만 받았습니다.'},{kind:'output',author:'조정자',text:'비교표 초안'}]})]});
 assert.match(root.textContent,/작업 종료/);assert.match(root.textContent,/개발 검토 대기/);assert.match(root.textContent,/온도 정보 부족/);
 assert.match(root.textContent,/<script>bad\(\)<\/script>/);assert.match(root.textContent,/비교표 초안/);
 const nodes=n=>[n,...n.children.flatMap(nodes)];assert.ok(!nodes(root).some(n=>n.tagName==='SCRIPT'));
 assert.ok(nodes(root).some(n=>n.tagName==='DETAILS'&&n.dataset.key==='episode:analysis'&&!n.open));
 }finally{delete globalThis.document;}
});
test('missing episodes and not-required review do not claim research completion',()=>{
 globalThis.document={createElement:tag=>new Element(tag)};
 try{let root=new Element('section');ui.renderEpisodes(root,{});assert.match(root.textContent,/작업 회차가 아직 없습니다/);
 root=new Element('section');ui.renderEpisodes(root,{work_episodes:[row('x',1,{review_required:false,review_status:'not_required'})]});
 assert.doesNotMatch(root.textContent,/M1 완료|개발 검토 대기/);
 assert.match(root.textContent,/작업 중으로 기록됨/);
 }finally{delete globalThis.document;}
});

test('followup plans belong to their source card and do not become running episodes',()=>{
 globalThis.document={createElement:tag=>new Element(tag)};
 try{
 const root=new Element('section');
 ui.renderEpisodes(root,{work_episodes:[row('review',1,{execution_status:'finished',review_status:'revision_requested',conclusion:{judgment:'비교 보류',remaining:'온도',next_action:'추가 확인',next_reason:'조건 통일'}})],
  work_followups:[{id:'plan',source_episode_id:'review',kind:'revision',title:'재검토: 온도 조건',purpose:'<img src=x> 원문 온도를 확인해 주세요.',status:'planned'},
  {id:'other',source_episode_id:'hidden',title:'노출 금지',purpose:'다른 회차',status:'planned'}]});
 assert.match(root.textContent,/후속 작업 계획/);assert.match(root.textContent,/계획됨 · 실행 전/);
 assert.match(root.textContent,/<img src=x>/);assert.doesNotMatch(root.textContent,/노출 금지/);
 const nodes=n=>[n,...n.children.flatMap(nodes)];
 assert.equal(nodes(root).filter(n=>n.dataset.key?.startsWith('episode:')).length,1);
 assert.ok(!nodes(root).some(n=>n.tagName==='IMG'));
 }finally{delete globalThis.document;}
});

test('summary prioritizes next action and keeps details collapsed without inventing a review outcome',()=>{
 globalThis.document={createElement:tag=>new Element(tag)};
 try {
  const root=new Element('section');
  ui.renderEpisodes(root,{work_episodes:[row('x',1,{execution_status:'finished',review_required:false,review_status:'not_required',conclusion:{judgment:'자료 비교 초안',remaining:'원문 미확보',next_action:'추가 탐색',next_reason:'조건 확인'},notes:[{kind:'tool',author:'Atlas',text:'원문 대조 기록'}]})]});
  const text=root.textContent;
  assert.ok(text.indexOf('다음 행동')<text.indexOf('남은 문제'));
  assert.match(text,/결과 요약/);
  assert.doesNotMatch(text,/사용자 확인 필요|검사 통과|보완 중|진행 가능/);
  const nodes=n=>[n,...n.children.flatMap(nodes)];
  const history=nodes(root).find(n=>n.dataset.key==='episode-history:x');
  assert.equal(history?.tagName,'DETAILS');assert.ok(!history.open);assert.match(history.textContent,/원문 대조 기록/);
 }finally{delete globalThis.document;}
});

test('human help appears only for an explicit pending review of a concluded episode',()=>{
 globalThis.document={createElement:tag=>new Element(tag)};
 try {
  for(const [extra,expected] of [[{},false],[{conclusion:{judgment:'초안'},review_required:false},false],[{conclusion:{judgment:'초안'}},true],[{conclusion:{judgment:'초안'},review_status:'continued'},false]]){
   const root=new Element('section');ui.renderEpisodes(root,{work_episodes:[row('x',1,extra)]});
   assert.equal(root.textContent.includes('사용자 확인 필요'),expected);
  }
 }finally{delete globalThis.document;}
});
