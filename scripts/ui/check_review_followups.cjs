// This test submits reviews only to its named synthetic project.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch();try{
 const base=process.env.PILOT_UI_URL;if(!base)throw Error('PILOT_UI_URL required');
 const p=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 p.on('pageerror',e=>errors.push(e.message));
 const before=await(await p.request.get(base+'/api/view')).json();
 assert.equal(before.content_origin,'synthetic');assert.equal(before.project.topic,'합성 검증 · 검토 결과와 후속 계획');
 await p.goto(base+'/#workflow');
 for(const [id,action,feedback] of [['continue-case','계속 진행','합성 UI 검사: 보충자료 확인을 준비하세요.'],['revise-case','수정 요청','합성 UI 검사: 반증 가능한 조건을 더 구체적으로 적어 주세요.']]){
  const card=p.locator(`[data-key="episode:${id}"]`);await card.locator(':scope > summary').click();
  await card.getByLabel('검토 의견',{exact:true}).fill(feedback);
  await card.getByRole('button',{name:action,exact:true}).click();
  await card.locator('.episode-followup').waitFor();await card.locator('.episode-followup > summary').click();
  assert.match(await card.locator('.episode-followup').textContent(),/계획됨 · 실행 전/);
  await card.locator('.episode-followup').screenshot({path:`output/evaluations/review-followups/${id}.png`});
 }
 const after=await(await p.request.get(base+'/api/view')).json();
 assert.equal(after.work_followups.length,2);assert.equal(after.work_episodes.length,2);
 assert.deepEqual(after.work_episodes.map(r=>r.sequence),before.work_episodes.map(r=>r.sequence));
 const revision=after.work_followups.find(r=>r.kind==='revision');assert.match(revision.purpose,/반증 가능한 조건/);
 await p.reload();await p.locator('.episode-card').first().waitFor();
 assert.equal(await p.locator('.episode-followup').count(),2);
 await p.setViewportSize({width:390,height:1000});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
 assert.deepEqual(errors,[]);
 fs.writeFileSync('output/evaluations/review-followups/browser.json',JSON.stringify({base,head:after.head_id,plans:2,episodes:2,errors},null,2));
 console.log(JSON.stringify({plans:2,episodes:2,errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
