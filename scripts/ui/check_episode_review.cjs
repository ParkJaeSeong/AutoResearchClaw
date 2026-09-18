// Writes one explicitly synthetic review. Never point at a real research project.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch();try{
 const base=process.env.PILOT_UI_URL;if(!base)throw Error('PILOT_UI_URL required');
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],writes=[];
 const view=await(await page.request.get(base+'/api/view')).json();
 assert.equal(view.content_origin,'synthetic');assert.equal(view.project.topic,'합성 테스트 · 개발 검토 의견 저장');
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',r=>{if(r.request().method()!=='GET'){assert.equal(new URL(r.request().url()).pathname,'/api/episodes/review');writes.push(r.request().postDataJSON());}return r.continue();});
 await page.goto(base+'/#workflow');const card=page.locator('.episode-card');await card.locator('summary').click();
 const field=card.getByLabel('검토 의견',{exact:true});await field.fill('UI 자동 검사: 조건 확인 후 후속 준비를 진행합니다.');
 await page.locator('[data-page-tab=overview]').click();await page.locator('[data-page-tab=workflow]').click();
 assert.match(await field.inputValue(),/UI 자동 검사/);
 for(const width of [1440,390]){await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);await card.screenshot({path:`output/evaluations/episode-review-ui/form-${width}.png`});}
 await card.getByRole('button',{name:'계속 진행',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.episode-card')?.textContent.includes('후속 진행 허용'));
 await page.reload();await page.locator('.episode-card').waitFor();await page.locator('.episode-card > summary').click();
 assert.match(await page.locator('.episode-card').textContent(),/UI 자동 검사/);
 const after=await(await page.request.get(base+'/api/view')).json();
 assert.equal(after.work_episodes[0].review.decision,'continue');assert.equal(after.work_episodes.length,1);
 assert.equal(writes.length,1);assert.deepEqual(errors,[]);
 fs.writeFileSync('output/evaluations/episode-review-ui/browser.json',JSON.stringify({base,head:after.head_id,writes:1,review:after.work_episodes[0].review,errors},null,2));
 console.log(JSON.stringify({saved:true,writes:1,errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
