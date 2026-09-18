// Run against a synthetic viewer. This browser check performs no writes.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.PILOT_UI_URL;
const out=process.env.PILOT_UI_OUTPUT||'output/evaluations/work-episodes';
if(!base)throw Error('PILOT_UI_URL must point to the synthetic viewer');
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch();const errors=[],writes=[];let checks=0;
 try{
 const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',route=>{if(route.request().method()!=='GET'){writes.push(route.request().url());return route.abort();}return route.continue();});
 const response=await page.request.get(base+'/api/view');assert.equal(response.status(),200);const view=await response.json();
 assert.equal(view.content_origin,'synthetic');assert.equal(view.work_episodes.length,3);checks++;
 await page.goto(base);await page.locator('[data-page-tab=workflow]').click();
 assert.equal(await page.locator('.episode-card').count(),3);
 assert.deepEqual(await page.locator('.episode-card').evaluateAll(nodes=>nodes.map(n=>n.dataset.key)),['episode:additional-search','episode:analysis','episode:search']);checks++;
 const card=page.locator('[data-key="episode:analysis"]');await card.locator('summary').click();
 await card.getByRole('heading',{name:'진행 과정',exact:true}).waitFor();
 assert.match(await card.textContent(),/개발 검토 대기/);assert.match(await card.textContent(),/온도/);checks++;
 // Keyboard activation uses native details and refreshing preserves the open episode.
 await card.locator('summary').focus();await page.keyboard.press('Enter');assert.equal(await card.getAttribute('open'),null);
 await page.keyboard.press('Enter');assert.notEqual(await card.getAttribute('open'),null);checks++;
 for(const theme of ['light','dark'])for(const width of [1440,768,390]){
  await page.setViewportSize({width,height:1000});
  await page.locator('[data-key=theme-select]').evaluate((s,v)=>{s.value=v;s.dispatchEvent(new Event('change'));},theme);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`${theme} ${width}`);
  await page.screenshot({path:`${out}/${theme}-${width}.png`});
  await card.screenshot({path:`${out}/${theme}-${width}-card.png`});checks++;
 }
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 fs.writeFileSync(`${out}/browser-verification.json`,JSON.stringify({checks,base,head:view.head_id,errors,writes},null,2));
 console.log(JSON.stringify({checks,errors,writes,out}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
