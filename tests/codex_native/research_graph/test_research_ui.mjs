import test from 'node:test';
import assert from 'node:assert/strict';
const base = '../../../researchclaw/codex/research_ui/';
const app = await import(base + 'app.js').catch(() => ({}));
const trace = await import(base + 'trace.js').catch(() => ({}));
const timeline = await import(base + 'timeline.js').catch(() => ({}));
const live = await import(base + 'live.js').catch(() => ({}));
const detail = await import(base + 'detail.js').catch(() => ({}));
const ref = (hash, head='h1') => ({project_id:'p',head_id:head,artifact_id:'m1/nodes/hypothesize',sha256:hash});
const revisions = [{record:{id:'r1',node:'hypothesize',content:{hypotheses:[{hypothesis_id:'A',statement:'old'}]}},ref:ref('old'),previous_ref:null},
 {record:{id:'r2',node:'hypothesize',content:{hypotheses:[{hypothesis_id:'A',statement:'new'}]}},ref:ref('new','h2'),previous_ref:ref('old')}];

test('poll selection preserves old revision and global Issue instead of jumping to current', () => {
  assert.equal(typeof app.resolveSelection, 'function');
  const view={nodes:[{id:'hypothesize',current_revision_id:'r2'}], revisions, councils:[],issues:[{record:{id:'i1'}}]};
  assert.deepEqual(app.resolveSelection(view,{nodeId:'hypothesize',revisionId:'r1',issueId:'i1',tab:'issues'}),
    {nodeId:'hypothesize',revisionId:'r1',issueId:'i1',councilId:null,tab:'issues'});
});

test('comparison requires exact predecessor and same hypothesis, missing refs never use latest', () => {
  assert.equal(typeof trace.compareHypotheses,'function');
  const view={revisions,artifacts:[{id:'a-new',ref:ref('new','h2'),raw_url:'/api/artifacts/a-new?head=h2'}]};
  assert.equal(trace.compareHypotheses(view,'r1','r2','A').before.statement,'old');
  assert.equal(trace.compareHypotheses(view,'r2','r1','A'),null);
  assert.equal(trace.compareHypotheses(view,'r1','r2','B'),null);
  assert.equal(trace.resolveRef(view,ref('old')),null);
  assert.equal(trace.resolveRef(view,ref('new','h1')),null);
});

test('transferred and unknown Issues never acquire resolved presentation; timeline keeps native order', () => {
  assert.equal(typeof timeline.traceIssue,'function');
  const row={record:{id:'i1'},status:'transferred',history:[{record:{id:'e1',to_status:'open'}},{record:{id:'e2',to_status:'transferred'}}]};
  assert.equal(timeline.issueState(row).tone,'pending');
  assert.equal(timeline.issueState({...row,status:'mystery'}).tone,'unknown');
  assert.deepEqual(timeline.traceIssue({issues:[row]},'i1').events.map(x=>x.record.id),['e1','e2']);
  assert.equal(timeline.issueState({...row,status:'pending_policy_revalidation',imported_pending:true}).tone,'pending');
});

function feed(load) {
  const views=[],statuses=[];
  assert.equal(typeof live.createLiveFeed,'function');
  const api=live.createLiveFeed({load,onView:v=>views.push(v),onStatus:s=>statuses.push(s),setTimer:()=>1,clearTimer:()=>{}});
  return {api,views,statuses};
}
test('past HEAD pin ignores an older live response and keeps selected version through reconnect', async () => {
  let finish; const calls=[];
  const f=feed(head=>{calls.push(head);return head ? Promise.resolve({head_id:head,current_head_id:'latest'}) : new Promise(done=>{finish=done;});});
  const pending=f.api.start(); await f.api.selectHead('past');
  finish({head_id:'latest',current_head_id:'latest'});await pending;
  assert.deepEqual(f.views.map(v=>v.head_id),['past']);
  await f.api.refresh(); assert.deepEqual(calls,[null,'past','past']);f.api.stop();
});

test('disconnect and malformed view keep last valid snapshot; same HEAD avoids rerender', async () => {
  let value={head_id:'h'};
  const f=feed(async()=>{if(value instanceof Error) throw value;return value;});
  await f.api.start();await f.api.refresh();value=new Error('offline');await f.api.refresh();
  assert.equal(f.views.length,1);assert.equal(f.statuses.at(-1).connected,false);
  value={};await f.api.refresh();assert.equal(f.views.length,1);f.api.stop();
});

class Element {
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this._text='';}
  set textContent(value){this._text=String(value);this.children=[];} get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set innerHTML(_){throw new Error('HTML interpolation is forbidden');}
  append(...items){this.children.push(...items);} replaceChildren(...items){this._text='';this.children=items;}
  setAttribute(k,v){this.attributes[k]=v;} addEventListener(){}
}
test('disclosed council renders hostile text inert, never fabricates withheld messages', () => {
  assert.equal(typeof detail.renderCouncil,'function');
  globalThis.document={createElement:tag=>new Element(tag)};
  try {
    const root=new Element('section');
    detail.renderCouncil(root,{artifacts:[]},{id:'c',phase:'response',authors:[],participants:[],required_roles:{},submitted_counts:{initial:3,response:1,final:0},
      isolation_level:'instructions_only',identity_provenance:'declared_only',disclosed_initials:[{submission_ref:ref('s'),submission:{id:'s',phase:'initial',producer_id:'reviewer',rationale:'<script>window.BAD=true</script>',positions:[],issue_proposals:[],evidence_refs:[],response_refs:[],observation_refs:[]}}],disclosed_responses:[],disclosed_finals:[]});
    assert.match(root.textContent,/<script>window.BAD=true<\/script>/);
    assert.match(root.textContent,/모두 작성하면 함께 공개/); assert.match(root.textContent,/접근을 강제로 차단했는지는 확인되지/);
    const tags=node=>[node.tagName,...node.children.flatMap(tags)];assert.ok(!tags(root).includes('SCRIPT'));
  } finally {delete globalThis.document;}
});

test('raw links require exact provided allowlist route/head and external URLs reject active schemes', () => {
  assert.equal(typeof trace.rawURL,'function');
  const v={head_id:'h2',artifacts:[{id:'a-ok',ref:ref('new'),raw_url:'/api/artifacts/a-ok?head=h2'}]};
  assert.equal(trace.rawURL(v,v.artifacts[0]),'/api/artifacts/a-ok?head=h2');
  assert.equal(trace.rawURL(v,{...v.artifacts[0],raw_url:'javascript:alert(1)'}),null);
  assert.equal(trace.rawURL(v,{...v.artifacts[0],raw_url:'/api/artifacts/a-ok?head=h1'}),null);
  assert.equal(trace.sourceURL('javascript:alert(1)'),null);
  assert.equal(trace.sourceURL('https://example.org/paper'),'https://example.org/paper');
});

test('switching pin mode at identical HEAD updates mode once without repeated poll rerenders', async () => {
  const f=feed(async()=>({head_id:'h',current_head_id:'h'}));
  await f.api.start();await f.api.selectHead('h');await f.api.refresh();await f.api.selectHead(null);
  assert.equal(f.views.length,3);f.api.stop();
});

test('research prose that equals an enum remains original text', () => {
  globalThis.document={createElement:tag=>new Element(tag)};
  try {assert.equal(detail.renderValue({},'ready','statement').textContent,'ready');
    assert.equal(detail.renderValue({},'open','question').textContent,'open');}
  finally {delete globalThis.document;}
});

function publicView() {
  const arrays=['heads','milestones','nodes','revisions','transitions','councils','issues','verifications','results','source_checks','approvals','dependencies','handoffs','artifacts','reason_codes','required_actions'];
  const view=Object.fromEntries(arrays.map(k=>[k,[]]));
  return {...view,schema_version:1,workflow_version:'research-graph-v1',head_id:'h1',current_head_id:'h1',project_id:'p',content_origin:'synthetic',project:{topic:'<img src=x onerror=alert(1)> 연구'},
    nodes:[{id:'hypothesize',label:'가설',current_revision_id:'r2',status:'ready',reason_codes:[],required_actions:[]}],revisions,
    milestones:[{id:'M1',status:'active'},{id:'M2',status:'unavailable'},{id:'M3',status:'unavailable'}],
    issues:[{record:{id:'i1',question:'다음 확인?',category:'methodology',severity:'major',blocking_scope:[],target_refs:[],resolution_condition:'대조 확인'},status:'transferred',history:[]}],
    evidence:{ready:false,reason_codes:['source_check_required'],required_actions:[],source_groups:{origin_group_count:1},limitations:['제공 자료만 확인']},corpus:null,accounting:null};
}
test('all five panels render closed public view as inert text with explicit M2/M3 and missing prerequisites', () => {
  globalThis.document={createElement:tag=>new Element(tag)};
  try {for(const tab of ['revision','council','issues','evidence','handoff']){const root=new Element('main');
    app.renderResearchView(root,publicView(),{nodeId:'hypothesize',revisionId:'r2',tab});
    assert.match(root.textContent,/<img src=x onerror=alert\(1\)> 연구/);
    assert.match(root.textContent,/M2 · 미구현/);assert.match(root.textContent,/M3 · 미구현/);
    assert.match(root.textContent,/researchclaw-codex research apply ROOT --operation council.submit/);
    if(tab==='council')assert.match(root.textContent,/협의 기록이 없습니다/);
    if(tab==='issues')assert.match(root.textContent,/담당 이전 · 미해소/);
    if(tab==='evidence')assert.match(root.textContent,/source_check_required/);
    if(tab==='handoff')assert.match(root.textContent,/비용이 들지 않았다는 뜻은 아닙니다/);
  }}finally{delete globalThis.document;}
});

if(process.env.RESEARCH_UI_VIEW) test('read-only native public snapshot renders every revision, disclosed council, and Issue',async()=>{
  const {readFile}=await import('node:fs/promises');const view=JSON.parse(await readFile(process.env.RESEARCH_UI_VIEW,'utf8'));
  app.validateView(view);globalThis.document={createElement:tag=>new Element(tag)};
  let rounds=0,issues=0;
  try {
    for(const revision of view.revisions){
      for(const tab of ['revision','council','evidence','handoff']){
        const root=new Element('main');app.renderResearchView(root,view,{nodeId:revision.record.node,revisionId:revision.record.id,tab});
        if(tab==='revision')assert.ok(root.textContent.includes(revision.record.id));
        if(tab==='council')for(const council of view.councils.filter(c=>c.node===revision.record.node && c.attempt===revision.record.attempt)){
          for(const field of ['disclosed_initials','disclosed_responses','disclosed_finals'])for(const row of council[field]){assert.ok(root.textContent.includes(row.submission.rationale));rounds++;}
        }
      }
    }
    for(const issue of view.issues){const root=new Element('main');app.renderResearchView(root,view,{tab:'issues',issueId:issue.record.id});
      assert.ok(root.textContent.includes(issue.record.id));assert.ok(root.textContent.includes(issue.record.resolution_condition));issues++;}
    console.log(`Native DOM smoke: HEAD ${view.head_id}; ${view.revisions.length} revisions, ${rounds} disclosed statements, ${issues} Issues.`);
  }finally{delete globalThis.document;}
});

test('source intake shows acquired files and reading limits without claiming usable evidence',()=>{
  globalThis.document={createElement:tag=>new Element(tag)};
  try {
    const root=new Element('section');
    detail.renderSourceIntake(root,{artifacts:[],source_captures:[{usage_status:'unassessed',
      record:{id:'capture-1',filename:'<script>paper</script>.pdf',source_key:'doi:example',
        reading_scope:'측정 절만 읽음',limitations:['단위 확인 필요'],source_version:'v1',sha256:'hash',byte_count:10}}]});
    assert.match(root.textContent,/확보한 자료 · 1개 파일/);
    assert.match(root.textContent,/사용 여부는 아직 판단하지 않았습니다/);
    assert.match(root.textContent,/측정 절만 읽음/);
    assert.match(root.textContent,/단위 확인 필요/);
    assert.match(root.textContent,/<script>paper<\/script>/);
    assert.doesNotMatch(root.textContent,/사용 가능|M1 완료/);
  } finally {delete globalThis.document;}
});
