import test from 'node:test';
import assert from 'node:assert/strict';
const ui=await import('../../../researchclaw/codex/research_ui/discovery.js').catch(()=>({}));
class Element {
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.events={};this._text='';}
 set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 set innerHTML(_){throw Error('unsafe HTML');} append(...v){this.children.push(...v);} replaceChildren(...v){this._text='';this.children=v;}
 setAttribute(k,v){this.attributes[k]=v;} addEventListener(k,v){this.events[k]=v;}
}
const all=n=>[n,...n.children.flatMap(all)];
const fixture=()=>({schema_version:1,revision:'r1',available:true,status:'complete',round:3,max_rounds:3,completed_reports:9,unique_candidates:2,candidate_records:197,m1_complete:false,limitations:['Abstract-only access'],roles:[{role:'domain',round:3,status:'complete',web_calls:4}],reports:[{role:'domain',round:1,summary:'Field summary',queries:['polymer automation'],disagreements:['weak transfer'],gaps:['missing control']}],sources:[{key:'a',title:'<script>candidate A</script>',observations:[{role:'domain',round:1,source:{url:'javascript:alert(1)',interpretation:'Useful catalyst',access_level:'abstract'}}]},{key:'b',title:'Candidate B',observations:[{role:'critical',round:2,source:{url:'https://example.org/paper',interpretation:'Contrary result',access_level:'metadata'}}]}],selection:{status:'provisional',summary:'Draft choice',groups:[{id:'g',title:'Controls',reason:'Need comparator',source_keys:['b']}],hypotheses:[{id:'h',statement:'Testable claim',test:'Randomized comparison',limits:'Not validated'}],unresolved:['Need full text']}});
test('discovery displays candidates, scientific reports and draft limits as inert text',()=>{
 assert.equal(typeof ui.createDiscoveryPanel,'function');globalThis.document={createElement:t=>new Element(t)};
 try{const root=new Element('section'),panel=ui.createDiscoveryPanel(root);panel.update(fixture());
 for(const text of ['197','Field summary','polymer automation','weak transfer','missing control','Useful catalyst','Abstract-only access','Draft choice','Testable claim','Not validated'])assert.ok(root.textContent.includes(text),text);
 assert.equal(all(root).filter(n=>n.tagName==='SCRIPT').length,0);
 assert.deepEqual(all(root).filter(n=>n.tagName==='A').map(n=>n.href),['https://example.org/paper']);
 }finally{delete globalThis.document;}
});
test('search and role filters survive updates with expanded source details and historical mode hides latest',()=>{
 assert.equal(typeof ui.createDiscoveryPanel,'function');globalThis.document={createElement:t=>new Element(t)};
 try{const root=new Element('section'),panel=ui.createDiscoveryPanel(root);panel.update(fixture());
 const input=all(root).find(n=>n.dataset.key==='discovery-search');input.value='contrary';input.events.input();
 const role=all(root).find(n=>n.dataset.key==='discovery-role');role.value='critical';role.events.change();
 let detail=all(root).find(n=>n.dataset.key==='source:b');detail.open=true;
 panel.update({...fixture(),revision:'r2'});
 assert.equal(all(root).find(n=>n.dataset.key==='discovery-search'),input);
 assert.equal(all(root).find(n=>n.dataset.key==='source:b').open,true);
 assert.equal(all(root).filter(n=>n.dataset.key==='source:a').length,0);
 panel.setHistorical(true);assert.equal(root.hidden,true);panel.setHistorical(false);assert.equal(root.hidden,false);
 }finally{delete globalThis.document;}
});
test('independent revision polling updates despite unchanged native HEAD and retains last good on error',async()=>{
 assert.equal(typeof ui.createDiscoveryFeed,'function');let value=fixture();const seen=[],statuses=[];
 const feed=ui.createDiscoveryFeed({load:async()=>value,onView:v=>seen.push(v),onStatus:s=>statuses.push(s),setTimer:()=>1,clearTimer:()=>{}});
 await feed.start();await feed.refresh();value={...fixture(),revision:'r2',head_id:'unchanged'};await feed.refresh();value={schema_version:1};await feed.refresh();
 assert.deepEqual(seen.map(v=>v.revision),['r1','r2']);assert.equal(statuses.at(-1).connected,false);feed.stop();
});

test('app refresh updates discovery at the same native HEAD and pinning hides latest discovery',async()=>{
 const {startApp}=await import('../../../researchclaw/codex/research_ui/app.js');
 const root=new Element('main'),toolbar=new Element('nav'),status=new Element('p'),body=new Element('body');
 Element.prototype.querySelectorAll=function(){return [];};
 Element.prototype.querySelector=function(selector){return all(this).find(n=>n.className===selector.slice(1))??null;};
 body.append(root);
 Object.defineProperty(Element.prototype,'childNodes',{get(){return this.children;},configurable:true});
 Object.defineProperty(globalThis,'localStorage',{value:{getItem(){return null;},setItem(){}},configurable:true});
 const handlers={};globalThis.document={createElement:t=>new Element(t),documentElement:new Element('html'),body};
 globalThis.window={location:{href:'http://localhost/'},scrollTo(){},history:{pushState(){}},addEventListener(k,fn){handlers[k]=fn;}};
 let value=fixture();const native={schema_version:1,workflow_version:'research-graph-v1',project:{topic:'Native project'},head_id:'unchanged',heads:[{head_id:'unchanged'}]};
 for(const name of ['milestones','nodes','revisions','transitions','councils','issues','verifications','results','source_checks','approvals','dependencies','handoffs','artifacts','reason_codes','required_actions'])native[name]=[];
 globalThis.fetch=async url=>({ok:true,json:async()=>url.startsWith('/api/view')?native:value});
 try{startApp(root,toolbar,status);await new Promise(resolve=>setImmediate(resolve));
 assert.ok(root.textContent.includes('Native project'));assert.ok(body.textContent.includes('197'));assert.match(status.textContent,/Atlas 답변과 판단 저장 가능/);assert.doesNotMatch(status.textContent,/읽기 전용/);
 value={...fixture(),revision:'new',candidate_records:202};
 await all(toolbar).find(n=>n.dataset.key==='refresh').events.click();assert.ok(body.textContent.includes('202'));
 const pin=all(toolbar).find(n=>n.dataset.key==='head-select');pin.value='unchanged';pin.events.change();await new Promise(resolve=>setImmediate(resolve));assert.equal(all(root).find(n=>n.className==='discovery-panel card').hidden,true);assert.match(status.textContent,/저장 기능 잠김/);
 }finally{handlers.pagehide?.();delete globalThis.fetch;delete globalThis.document;delete globalThis.window;}
});

test('malformed nested selection is rejected before altering the last good panel',()=>{
 globalThis.document={createElement:t=>new Element(t)};
 try{const root=new Element('section'),panel=ui.createDiscoveryPanel(root);panel.update(fixture());const before=root.textContent;
 assert.throws(()=>panel.update({...fixture(),selection:{groups:[null]}}));assert.equal(root.textContent,before);
 }finally{delete globalThis.document;}
});

test('discovery labels report declarations and roles without asserting scientific completion',()=>{
 globalThis.document={createElement:t=>new Element(t)};
 try{const root=new Element('section'),panel=ui.createDiscoveryPanel(root),value=fixture();
 value.status='budget_reached_with_gaps';value.m1_complete=true;value.sources[0].observations[0].source.reading_scope='abstract';value.selection.status='draft';panel.update(value);
 for(const text of ['검색에 사용한 말','읽은 범위','소재','SDL·반증','이번 탐색 종료 · 추가 확인 필요','현재 검토 요약'])assert.ok(root.textContent.includes(text),text);
 assert.ok(!root.textContent.includes('완료로 보고됨'));assert.ok(!root.textContent.includes('budget_reached_with_gaps'));
 }finally{delete globalThis.document;}
});
