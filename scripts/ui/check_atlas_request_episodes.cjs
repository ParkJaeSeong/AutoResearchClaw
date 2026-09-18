// Inspect a synthetic viewer with a completed request and council episode.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch();
 try{
  const base=process.env.PILOT_UI_URL;if(!base)throw Error('PILOT_UI_URL required');
  const p=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],writes=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.route('**/api/**',r=>{if(r.request().method()!=='GET'){writes.push(r.request().url());return r.abort();}return r.continue();});
  const response=await p.request.get(base+'/api/view');const view=await response.json();assert.equal(view.content_origin,'synthetic');
  assert.equal(view.work_episodes.length,2);
  await p.goto(base+'/#workflow');await p.locator('.episode-card').first().waitFor();
  assert.equal(await p.locator('.episode-card').count(),2);
  for(const summary of await p.locator('.episode-card > summary').all())await summary.click();
  assert.match(await p.locator('.episode-stack').textContent(),/개발 검토 대기/);
  for(const width of [1440,390]){await p.setViewportSize({width,height:1000});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);await p.screenshot({path:`output/evaluations/atlas-request-episodes/screen-${width}.png`});}
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  fs.writeFileSync('output/evaluations/atlas-request-episodes/browser.json',JSON.stringify({base,head:view.head_id,episodes:2,errors,writes},null,2));
  console.log(JSON.stringify({episodes:2,errors,writes}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
