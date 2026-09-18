// Browser smoke test; read-only API fixtures prevent research mutations.
// PLAYWRIGHT_MODULE=/path/to/playwright PILOT_UI_VIEW=/path/to/view.json node scripts/ui/check_research_design.cjs
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.PILOT_UI_URL||'http://127.0.0.1:8771';
const out=process.env.PILOT_UI_OUTPUT||'/tmp/pilot-ui-design';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch();let checks=0;
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1000},colorScheme:'light'});
 let view=process.env.PILOT_UI_VIEW?JSON.parse(fs.readFileSync(process.env.PILOT_UI_VIEW)):await(await fetch(base+'/api/view')).json();
 const baseline=view.head_id,errors=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',route=>{if(route.request().method()!=='GET'){writes.push(route.request().url());return route.abort();}if(route.request().url().includes('/api/view'))return route.fulfill({json:view});return route.continue();});
 await page.goto(base);await page.getByRole('tab',{name:'연구 개요',exact:true}).waitFor();
 assert.equal(await page.locator('[data-page=overview]').isVisible(),true);assert.equal(await page.locator('[data-page=atlas]').isVisible(),false);checks++;
 await page.getByRole('tab',{name:'Atlas 연결',exact:true}).click();
 const draft=page.locator('[data-key=atlas-service-question]');await draft.fill('UI 점검 중인 질문 — 전송하지 않습니다.');
 await page.getByRole('tab',{name:'연구 개요',exact:true}).click();await page.getByRole('tab',{name:'Atlas 연결',exact:true}).click();assert.equal(await draft.inputValue(),'UI 점검 중인 질문 — 전송하지 않습니다.');checks++;
 await page.getByRole('tab',{name:'연구 개요',exact:true}).click();
 const review=page.getByRole('link',{name:'검토 대화와 근거 보기'}).first();
 if(await review.count()){await review.click();assert.equal(await page.locator('[data-page=decisions]').isVisible(),true);const target=page.locator(await page.evaluate(()=>location.hash));await target.locator('summary').filter({hasText:'실제 에이전트 대화'}).first().click();assert.equal(await target.locator('details[open]').count()>0,true);await page.goBack();assert.equal(await page.locator('[data-page=overview]').isVisible(),true);checks++;}
 // A real rerender from a new snapshot preserves the previously opened conversation and draft.
 const opened=await page.locator('[data-page=decisions] details[open][data-key]').evaluateAll(nodes=>nodes.map(n=>n.dataset.key));
 view={...view,head_id:'f'.repeat(64)};
 await page.getByText('기록 시점과 새로고침',{exact:true}).click();await page.getByRole('button',{name:'새로고침',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.next-steps pre')?.textContent.includes('f'.repeat(64)));
 assert.equal(await draft.inputValue(),'UI 점검 중인 질문 — 전송하지 않습니다.');for(const key of opened)assert.equal(await page.locator(`[data-key="${key}"]`).getAttribute('open')!==null,true);checks++;
 const theme=page.locator('[data-key=theme-select]');await theme.selectOption('system');await page.emulateMedia({colorScheme:'dark'});assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).colorScheme),'dark');await theme.selectOption('light');assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).colorScheme),'light');await page.emulateMedia({colorScheme:'light'});await theme.selectOption('dark');assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).colorScheme),'dark');checks++;
 // Roving tab focus switches only the project panel.
 await page.getByRole('tab',{name:'연구 개요',exact:true}).focus();await page.keyboard.press('ArrowRight');assert.equal(await page.locator('[data-page=workflow]').isVisible(),true);checks++;
 view={...view,head_id:baseline};await page.getByRole('button',{name:'새로고침',exact:true}).click();await page.waitForFunction(head=>document.querySelector('.next-steps pre')?.textContent.includes(head),baseline);await page.getByText('기록 시점과 새로고침',{exact:true}).click();
 const sizes=[320,390,768,1280,1440];
 for(const color of ['light','dark']){
   await page.locator('[data-key=theme-select]').evaluate((select,color)=>{select.value=color;select.dispatchEvent(new Event('change'));},color);
   for(const width of sizes){await page.setViewportSize({width,height:1000});for(const id of ['overview','workflow','decisions','sources','atlas']){
     await page.locator(`[data-page-tab=${id}]`).click();
     const overflow=await page.evaluate(()=>({page:document.documentElement.scrollWidth>innerWidth+1,bad:[...document.querySelectorAll('main *')].filter(n=>n.getClientRects().length&&getComputedStyle(n).position!=='absolute'&&n.getBoundingClientRect().right>innerWidth+2&&!n.closest('.project-tabs')).slice(0,5).map(n=>n.className)}));
     assert.equal(overflow.page,false,`${width} ${color} ${id}: ${JSON.stringify(overflow)}`);checks++;
   }await page.locator('[data-page-tab=overview]').click();await page.screenshot({path:`${out}/${color}-${width}.png`});}
 }
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'탐색 열기',exact:true}).click();assert.equal(await page.locator('#app-main').evaluate(n=>n.inert),true);await page.keyboard.press('Shift+Tab');assert.equal(await page.evaluate(()=>document.activeElement.textContent),'글꼴 라이선스');await page.keyboard.press('Escape');assert.equal(await page.locator('#app-main').evaluate(n=>n.inert),false);assert.equal(await page.getByRole('button',{name:'탐색 열기',exact:true}).evaluate(n=>n===document.activeElement),true);checks++;
 // 200% layout equivalent: Chromium page zoom via CSS, including fixed navigation.
 await page.setViewportSize({width:1440,height:1000});await page.evaluate(()=>document.documentElement.style.zoom='2');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);await page.screenshot({path:`${out}/zoom-200.png`});await page.evaluate(()=>document.documentElement.style.zoom='');checks++;
 // Resource routes and the actual loaded font, not just CSS declarations.
 for(const [path,type] of [['/assets/pilot.svg','image/svg+xml'],['/assets/krict-logo.png','image/png'],['/assets/Pretendard-Regular.woff2','font/woff2'],['/assets/LICENSE.txt','text/plain']]){const r=await page.request.get(base+path);assert.equal(r.status(),200);assert.ok(r.headers()['content-type'].startsWith(type));}await page.evaluate(()=>document.fonts.ready);assert.equal(await page.evaluate(()=>document.fonts.check('16px Pretendard')),true);checks++;
 // Invalid storage choice must not disable system mode.
 await page.evaluate(()=>localStorage.setItem('research-theme','invalid'));await page.emulateMedia({colorScheme:'dark'});await page.reload();await page.getByRole('tab',{name:'연구 개요',exact:true}).waitFor();assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'system');assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).colorScheme),'dark');checks++;
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 fs.writeFileSync(`${out}/verification.json`,JSON.stringify({checks,baseline,errors,writes,sizes,zoom:'CSS 2x layout; browser UI zoom separately checked when supported'},null,2));console.log(JSON.stringify({checks,errors,writes,out}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
