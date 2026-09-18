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

test('issues live in the wide record tab as initially collapsed independent details', () => {
  globalThis.document={createElement:tag=>new Element(tag)};
  try {
    const root=new Element('main'),view=publicView();
    app.renderResearchView(root,view,{nodeId:'hypothesize',tab:'issues'});
    const walk=n=>[n,...n.children.flatMap(walk)],nodes=walk(root);
    const sidebar=nodes.find(n=>n.className==='sidebar');
    assert.equal(walk(sidebar).some(n=>n.dataset.key==='issue:i1'),false);
    const panel=nodes.find(n=>n.id==='record-panel'),row=walk(panel).find(n=>n.dataset.key==='issue:i1');
    assert.ok(row);assert.equal(row.tagName,'DETAILS');assert.ok(!row.open);
    assert.equal(row.children[0].tagName,'SUMMARY');
    assert.match(row.children[0].textContent,/다음 확인/);
    assert.match(row.textContent,/대조 확인/);
    const body=row.children[1];
    assert.equal(body.children[0].textContent,'해결됐다고 판단할 기준');
    assert.equal(body.children.some(n=>n.tagName==='H2'||n.className==='badge'||n.textContent.startsWith('제기된 단계:')),false);
    assert.equal(body.children.some(n=>n.textContent===view.issues[0].record.id),false);
    assert.doesNotMatch(row.children[0].textContent,/이 단계에서 제기됨/);
    assert.ok(walk(body).some(n=>n.dataset.key==='issue-record:i1'));
    assert.ok(walk(panel).some(n=>n.dataset.key==='issue-scope:all'));
  }finally{delete globalThis.document;}
});

test('candidate records use title-first collapsed rows and preserve raw data without active URLs', () => {
  globalThis.document={createElement:tag=>new Element(tag)};
  try {
    const candidates=[{title:'<img src=x> Paper',source_id:'s1',doi:'10.1000/abc',access_status:'full_text',source_type:'reference_record',arxiv_id:null,search_ids:['lookup-1'],url:'https://example.org/paper'},
      {title:'Second',source_id:'s2',access_status:'future_scope',url:'javascript:alert(1)',custom_note:'Original note'}];
    const original=JSON.stringify(candidates),root=detail.renderValue({},candidates,'candidates','revision/candidates');
    const walk=n=>[n,...n.children.flatMap(walk)],nodes=walk(root),rows=nodes.filter(n=>n.className==='candidate-row');
    assert.equal(rows.length,2);assert.ok(rows.every(n=>n.tagName==='DETAILS'&&!n.open));
    assert.match(rows[0].children[0].textContent,/<img src=x> Paper/);
    assert.match(rows[0].children[0].textContent,/原文|원문/);
    assert.ok(nodes.some(n=>n.tagName==='INPUT'&&n.type==='search'));
    assert.ok(nodes.some(n=>n.tagName==='A'&&n.href==='https://example.org/paper'));
    assert.ok(!nodes.some(n=>n.tagName==='A'&&n.href?.startsWith('javascript:')));
    assert.ok(nodes.some(n=>n.tagName==='PRE'&&n.textContent===JSON.stringify(candidates[0],null,2)));
    assert.match(root.textContent,/future_scope/);assert.match(root.textContent,/Original note/);
    assert.equal(JSON.stringify(candidates),original);
  }finally{delete globalThis.document;}
});

test('poll selection preserves old revision and related Issue instead of jumping to current', () => {
  assert.equal(typeof app.resolveSelection, 'function');
  const view={nodes:[{id:'hypothesize',current_revision_id:'r2'}], revisions, councils:[],issues:[{record:{id:'i1',origin:{node:'hypothesize',milestone:'M1'}}}]};
  assert.deepEqual(app.resolveSelection(view,{nodeId:'hypothesize',revisionId:'r1',issueId:'i1',tab:'issues'}),
    {nodeId:'hypothesize',revisionId:'r1',issueScope:'stage',issueId:'i1',councilId:null,tab:'issues'});
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
    assert.match(root.textContent,/모두 작성하면 함께 공개/); assert.match(root.textContent,/실제로 접근을 차단했는지/);
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
    issues:[{record:{id:'i1',origin:{node:'hypothesize',milestone:'M1'},question:'다음 확인?',category:'methodology',severity:'major',blocking_scope:[],target_refs:[],resolution_condition:'대조 확인'},status:'transferred',history:[]}],
    evidence:{ready:false,reason_codes:['source_check_required'],required_actions:[],source_groups:{origin_group_count:1},limitations:['제공 자료만 확인']},corpus:null,accounting:null};
}
test('all five panels render closed public view as inert text with explicit M2/M3 and missing prerequisites', () => {
  globalThis.document={createElement:tag=>new Element(tag)};
  try {for(const tab of ['revision','council','issues','evidence','handoff']){const root=new Element('main');
    app.renderResearchView(root,publicView(),{nodeId:'hypothesize',revisionId:'r2',tab});
    assert.match(root.textContent,/<img src=x onerror=alert\(1\)> 연구/);
    assert.match(root.textContent,/M2 · 실험과 해석 · 준비 전/);assert.match(root.textContent,/M3 · 연구 마무리 · 준비 전/);
    assert.doesNotMatch(root.textContent,/researchclaw-codex research apply ROOT --operation council.submit/);
    assert.match(root.textContent,/이전 단계 기록 보기/);
    if(tab==='council')assert.match(root.textContent,/에이전트 검토 기록이 없습니다/);
    if(tab==='issues')assert.match(root.textContent,/담당 변경 · 해결 전/);
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
    for(const issue of view.issues){const root=new Element('main');app.renderResearchView(root,view,{tab:'issues',issueId:issue.record.id,issueScope:'all'});
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
    assert.match(root.textContent,/사용할 수 있는지는 검토 기록에서 확인하세요/);
    assert.match(root.textContent,/측정 절만 읽음/);
    assert.match(root.textContent,/단위 확인 필요/);
    assert.match(root.textContent,/<script>paper<\/script>/);
    assert.doesNotMatch(root.textContent,/사용 가능|M1 완료/);
  } finally {delete globalThis.document;}
});

test('impact groups preserve each issue and distinguish proposal from current blocking policy',()=>{
  assert.equal(typeof timeline.impactGroups,'function');
  const record=(id)=>({id,issue_ref:{artifact_id:id},group_key:'H1',group_title:'조건 확인',
    held_work:['학습'],preparation_work:['사용표 작성']});
  const view={issue_impacts:[{current:true,record:record('a')},{current:true,record:record('b')},
    {current:false,record:record('old')}]};
  const groups=timeline.impactGroups(view);
  assert.equal(groups.length,1);assert.deepEqual(groups[0].issueIds,['a','b']);
  globalThis.document={createElement:tag=>new Element(tag)};
  try{
    const root=new Element('section');timeline.renderImpactSummary(root,view);
    assert.match(root.textContent,/2개 쟁점 · 1개 작업 묶음/);
    assert.match(root.textContent,/조정자가 정리한 작업 제안/);
    assert.match(root.textContent,/사용표 작성/);assert.match(root.textContent,/학습/);
    assert.doesNotMatch(root.textContent,/해결 완료|승인됨/);
  }finally{delete globalThis.document;}
});

test('scope review exposes real council without labeling open issues resolved',()=>{
  globalThis.document={createElement:tag=>new Element(tag)};
  try{
    const root=new Element('section');
    const council={id:'scope-c',node:'issue_scope',phase:'complete',authors:[],participants:[],required_roles:{},
      submitted_counts:{initial:3,response:3,final:3},disclosed_initials:[],disclosed_responses:[],disclosed_finals:[]};
    detail.renderScopeReviews(root,{councils:[council],scope_changes:[{record:{council_id:'scope-c'},active_issue_ids:['i1']}],
      issues:[{scope_changed:true}],artifacts:[]});
    assert.match(root.textContent,/질문 단계의 진행 조건 검토/);
    assert.match(root.textContent,/적용됨/);assert.match(root.textContent,/검토자 대화 보기/);
    assert.doesNotMatch(root.textContent,/쟁점 해결 완료/);
  }finally{delete globalThis.document;}
});

test('pending scope proposal is visible and partial application is counted',()=>{
  globalThis.document={createElement:tag=>new Element(tag)};
  const proposal={record:{id:'p',rationale:'<script>질문 준비만 허용</script>',changes:[
    {issue_ref:{artifact_id:'i1'},original_scopes:[{kind:'node',milestone:'M1',target_id:'questions'}],replacement_scopes:[{kind:'node',milestone:'M1',target_id:'review'}]},
    {issue_ref:{artifact_id:'i2'},original_scopes:[{kind:'node',milestone:'M1',target_id:'questions'}],replacement_scopes:[{kind:'node',milestone:'M1',target_id:'review'}]}]}};
  try{
    const root=new Element('section');
    detail.renderScopeReviews(root,{scope_proposals:[proposal],councils:[],issues:[],artifacts:[]});
    assert.match(root.textContent,/검토 준비 전/);assert.match(root.textContent,/<script>질문 준비만 허용<\/script>/);
    const council={id:'c',attempt:'p',node:'issue_scope',phase:'complete',authors:[],participants:[],required_roles:{},
      submitted_counts:{initial:3,response:3,final:3},disclosed_initials:[],disclosed_responses:[],disclosed_finals:[]};
    root.replaceChildren();detail.renderScopeReviews(root,{scope_proposals:[proposal],councils:[council],issues:[],artifacts:[],
      scope_changes:[{record:{council_id:'c'},active_issue_ids:['i1']}]});
    assert.match(root.textContent,/일부 적용 · 1\/2개 쟁점/);
  }finally{delete globalThis.document;}
});

test('source analysis is visible outside stage councils and does not imply M1 completion',()=>{
  assert.equal(typeof detail.renderSourceAnalysis,'function');
  globalThis.document={createElement:tag=>new Element(tag)};
  try{
    const root=new Element('section');const council={id:'s',node:'source_analysis',phase:'response',participants:[{id:'c',council_role:'critical',actor_id:'source-reader-critical'}],authors:[],required_roles:{domain:'d',critical:'c',methodology:'m'},submitted_counts:{initial:3,response:0,final:0},disclosed_initials:[],disclosed_responses:[],disclosed_finals:[]};
    detail.renderSourceAnalysis(root,{councils:[council],artifacts:[]});
    assert.match(root.textContent,/원문 검토와 의견 교환/);
    assert.match(root.textContent,/의견 교환/);
    assert.match(root.textContent,/3\/3/);
    assert.match(root.textContent,/반증 검토자/);
    assert.doesNotMatch(root.textContent,/M1 완료|검증 완료/);
  }finally{delete globalThis.document;}
});

test('overview follows explicit decision chains instead of the order of UUID records', async()=>{
  const {currentDecisions}=await import(base+'overview.js');
  const old={record:{id:'old'},ref:ref('old')},next={record:{id:'new',prior_ref:ref('old')},ref:ref('new')};
  assert.deepEqual(currentDecisions({external_decisions:[next,old]}).map(x=>x.record.id),['new']);
  const independent={record:{id:'separate'},ref:ref('separate')};
  assert.deepEqual(currentDecisions({external_decisions:[next,independent,old]}).map(x=>x.record.id),['new','separate']);
});

test('progress checks explain blockers while retaining original codes in details',()=>{
  globalThis.document={createElement:tag=>new Element(tag)};
  try{
    const root=new Element('section');
    assert.equal(typeof detail.renderChecks,'function');
    detail.renderChecks(root,['council_required','future_rule'],['Address council_required before advancing this node.']);
    const visible=root.children.filter(n=>n.tagName!=='DETAILS').map(n=>n.textContent).join('');
    assert.match(visible,/에이전트 검토/);assert.doesNotMatch(visible,/Address|council_required|future_rule/);
    assert.match(root.children.find(n=>n.tagName==='DETAILS').textContent,/future_rule/);
  }finally{delete globalThis.document;}
});

test('council phases are tabs and disclosed statements start collapsed with original text intact', () => {
  globalThis.document={createElement:tag=>new Element(tag)};
  try {
    const root=new Element('section');
    const council={id:'tabbed-c',phase:'final',participants:[],required_roles:{domain:1},submitted_counts:{initial:1,response:0,final:0},disclosed_initials:[{submission_ref:ref('one'),submission:{id:'one',rationale:'첫 문단 원문\n\n두 번째 문단 원문',positions:[],evidence_refs:[]}}],disclosed_responses:[],disclosed_finals:[]};
    detail.renderCouncil(root,{artifacts:[]},council);
    const all=n=>[n,...n.children.flatMap(all)],nodes=all(root);
    const tabs=nodes.filter(n=>n.attributes.role==='tab');
    assert.equal(tabs.length,3);assert.equal(tabs.filter(n=>n.attributes['aria-selected']==='true').length,1);
    const panels=nodes.filter(n=>n.attributes.role==='tabpanel');
    assert.equal(panels.length,3);assert.equal(panels.filter(n=>!n.hidden).length,1);
    const statement=nodes.find(n=>n.dataset.key==='submission:one');
    assert.equal(statement.tagName,'DETAILS');assert.ok(!statement.open);
    assert.match(statement.textContent,/첫 문단 원문/);assert.match(statement.textContent,/두 번째 문단 원문/);
    assert.match(root.textContent,/모두 작성하면 함께 공개/);
  }finally{delete globalThis.document;}
});

test('stage issue filtering uses origin, exact target refs and effective scope without stale blocking fallback', () => {
  const issues=[
    {record:{id:'origin',origin:{milestone:'M1',node:'questions'},target_refs:[],blocking_scope:[]}},
    {record:{id:'scope',target_refs:[],blocking_scope:[{kind:'node',milestone:'M1',target_id:'questions'}]},effective_blocking_scope:[{kind:'node',milestone:'M1',target_id:'review'}]},
    {record:{id:'cleared',target_refs:[],blocking_scope:[{kind:'node',milestone:'M1',target_id:'questions'}]},effective_blocking_scope:[]},
    {record:{id:'target',target_refs:[ref('old')],blocking_scope:[]}},
    {record:{id:'unknown',target_refs:[],blocking_scope:[]}}
  ];
  const view={issues,revisions};
  assert.equal(typeof timeline.issuesForSelection,'function');
  assert.deepEqual(timeline.issuesForSelection(view,{nodeId:'questions'}).map(x=>x.record.id),['origin']);
  assert.deepEqual(timeline.issuesForSelection(view,{nodeId:'review'}).map(x=>x.record.id),['scope']);
  assert.deepEqual(timeline.issuesForSelection(view,{nodeId:'hypothesize'}).map(x=>x.record.id),['target']);
  assert.equal(timeline.issuesForSelection(view,{nodeId:'questions',issueScope:'all'}).length,5);
  assert.equal(timeline.issuesForSelection(view,{nodeId:'extract'}).length,0);
  const input=JSON.stringify(view);timeline.issuesForSelection(view,{nodeId:'review'});assert.equal(JSON.stringify(view),input);
});

test('stage selection cannot retain an unrelated issue while explicit all view can', () => {
  const view={nodes:[{id:'scope'},{id:'questions'}],revisions:[],councils:[],issues:[{record:{id:'a',origin:{node:'scope',milestone:'M1'}}},{record:{id:'b',origin:{node:'questions',milestone:'M1'}}}]};
  assert.equal(app.resolveSelection(view,{nodeId:'questions',issueId:'a'}).issueId,'b');
  assert.equal(app.resolveSelection(view,{nodeId:'questions',issueId:'a',issueScope:'all'}).issueId,'a');
});

test('episode-only projects do not show an empty legacy map or CLI mutation instructions',()=>{
 globalThis.document={createElement:tag=>new Element(tag)};
 try{const root=new Element('main'),view=publicView();view.revisions=[];view.councils=[];view.work_episodes=[];
 app.renderResearchView(root,view,{});
 assert.doesNotMatch(root.textContent,/M1 작업 지도|다음 작업을 CLI로 이어가기|실행 확인 시각/);
 }finally{delete globalThis.document;}
});
