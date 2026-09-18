import test from 'node:test';
import assert from 'node:assert/strict';
import {projectURL,readProjectState,saveProjectState,switchURL} from '../../../researchclaw/codex/research_ui/project.js';
import {STAGE_GROUPS,episodeGroup,stageEpisodes} from '../../../researchclaw/codex/research_ui/workspace.js';
import {resolveSelection} from '../../../researchclaw/codex/research_ui/app.js';
import {rawURL} from '../../../researchclaw/codex/research_ui/trace.js';
test('every route retains its operation and HEAD while explicitly binding the project',()=>{
 for(const path of ['/api/view?head=old','/api/discovery','/api/atlas/service-ask','/api/episodes/review','/api/project-files','/api/artifacts/a-one?head=h']){
 const url=new URL(projectURL(path,'A'),'http://pilot.local');assert.equal(url.searchParams.get('project'),'A');assert.equal(url.pathname,path.split('?')[0]);
 }assert.equal(projectURL('/api/view?project=B&head=h','A'),'/api/view?project=A&head=h');assert.throws(()=>projectURL('https://other.example/api/view','A'));
});
test('project draft, selection, HEAD and page state is isolated and project switch drops old parameters',()=>{
 const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};
 saveProjectState({drafts:{question:'A only'},selection:{nodeId:'search'},head:'head-A',hash:'#atlas'},'A',storage);
 saveProjectState({drafts:{question:'B only'},selection:{nodeId:'scope'},hash:'#workflow'},'B',storage);
 assert.equal(readProjectState('A',storage).drafts.question,'A only');assert.equal(readProjectState('B',storage).drafts.question,'B only');assert.deepEqual(readProjectState('C',storage),{});
 const target=new URL(switchURL('http://localhost/?project=A&head=head-A#atlas','B',readProjectState('B',storage)));
 assert.equal(target.search,'?project=B');assert.equal(target.hash,'#workflow');
 assert.equal(new URL(switchURL(target.href,'A',readProjectState('A',storage))).searchParams.get('head'),'head-A');
});
test('stage navigation maps exact actual episodes without fabricating execution or mutating sequence',()=>{
 const rows=[{id:'e1',sequence:1,stage:'자료 확인'},{id:'e3',sequence:3,stage:'실험 설계'},{id:'e5',sequence:5,stage:'근거 검토·설계 보완'},{id:'e9',sequence:9,stage:'M1 POC 마무리'},{id:'unknown',sequence:10,stage:'future'}];
 assert.deepEqual(stageEpisodes({work_episodes:rows},'design').map(r=>r.id),['e3','e5']);assert.equal(episodeGroup(rows.at(-1)),null);assert.deepEqual(rows.map(r=>r.sequence),[1,3,5,9,10]);assert.equal(STAGE_GROUPS.length,5);
});
test('a stage without native nodes never falls back to an unrelated node or revision',()=>{
 const view={nodes:[{id:'scope'}],revisions:[],councils:[],issues:[]};const s=resolveSelection(view,{stageGroup:'design',nodeId:'scope'});assert.equal(s.nodeId,null);assert.equal(s.revisionId,null);assert.equal(s.stageGroup,'design');
});
test('artifact links accept only current exact snapshot and bind to current project',()=>{
 globalThis.location={href:'http://localhost/?project=A'};
 try{const artifact={id:'a-one',raw_url:'/api/artifacts/a-one?head=h&project=A',ref:{project_id:'A',head_id:'h',artifact_id:'x',sha256:'s'}},view={head_id:'h',artifacts:[artifact]};assert.equal(rawURL(view,artifact),artifact.raw_url);artifact.raw_url='/api/artifacts/a-one?head=h&project=B';assert.equal(rawURL(view,artifact),null);}finally{delete globalThis.location;}
});
test('switching documents preserves an uncertain episode request and retries the original command',async()=>{
 const {createEpisodeReviewController}=await import('../../../researchclaw/codex/research_ui/episode_review.js');
 const values=new Map();globalThis.sessionStorage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};globalThis.location={href:'http://localhost/?project=A'};
 const row={id:'e',execution_status:'finished',conclusion:{judgment:'x'},review_required:true,review_status:'pending'},context={view:{head_id:'old',work_episodes:[row]},historical:false};let original;
 try{const first=createEpisodeReviewController({getContext:()=>context,commandId:()=> 'exact-command',request:async(_,options)=>{original=options.body;throw Error('lost');}});first.edit('e','A review');await first.submit('e','continue');
 globalThis.location.href='http://localhost/?project=B';const other=createEpisodeReviewController({getContext:()=>context});assert.equal(other.state('e').draft,'');
 globalThis.location.href='http://localhost/?project=A';context.view.head_id='new';let retried;const restored=createEpisodeReviewController({getContext:()=>context,request:async(_,options)=>{retried=options.body;throw Error('lost');}});assert.equal(restored.state('e').phase,'uncertain');assert.equal(restored.state('e').draft,'A review');await restored.retry('e');assert.equal(retried,original);
 }finally{delete globalThis.location;delete globalThis.sessionStorage;}
});

test('archive grouping preserves access while default prefers an active project',async()=>{
 const {projectGroups,preferredProject}=await import('../../../researchclaw/codex/research_ui/workspace.js');
 const catalog={projects:[{id:'old',archived:true},{id:'new'}],default_project_id:'old'};
 assert.deepEqual(projectGroups(catalog),{active:[catalog.projects[1]],archived:[catalog.projects[0]]});
 assert.equal(preferredProject(catalog),'new');
 assert.equal(preferredProject({...catalog,projects:[catalog.projects[0]]}),'old');
 assert.equal(catalog.projects.length,2);
});

test('named stage groups include live work episodes',()=>{
 for(const group of STAGE_GROUPS)assert.equal(episodeGroup({stage:group.title}),group.id);
});
