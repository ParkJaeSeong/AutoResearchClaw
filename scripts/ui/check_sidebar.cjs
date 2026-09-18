const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const base=process.env.PILOT_UI_URL||'http://127.0.0.1:8771',out=process.env.PILOT_UI_OUTPUT||'output/evaluations/pilot-sidebar-v042';fs.mkdirSync(out,{recursive:true});
 const view=JSON.parse(fs.readFileSync(process.env.PILOT_UI_VIEW));const b=await chromium.launch();let writes=0,rows=[];
 try{
 const p=await b.newPage({viewport:{width:1280,height:900}});
 await p.route('**/api/**',r=>{if(r.request().method()!=='GET'){writes++;return r.abort();}return r.request().url().includes('/api/view')?r.fulfill({json:view}):r.abort();});
 await p.goto(base);await p.getByRole('tab',{name:'Atlas 연결',exact:true}).click();const draft=p.locator('[data-key=atlas-service-question]');await draft.fill('메뉴 검수 초안 — 전송하지 않음');
 const toggle=p.locator('#sidebar-toggle');
 for(const mode of ['light','dark']){await p.emulateMedia({colorScheme:mode});for(const width of [1280,1920,2560]){await p.setViewportSize({width,height:900});for(const collapsed of [false,true]){
 if((await toggle.getAttribute('aria-expanded')==='false')!==collapsed)await toggle.click();
 const r=await p.evaluate(()=>{const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right}};return{button:rect('#sidebar-toggle'),icon:rect('#sidebar-toggle svg'),brand:rect('.product-brand img'),row:rect('.product-row'),sidebar:rect('.app-sidebar'),view:rect('.research-view'),menu:rect('.service-nav'),overflow:document.documentElement.scrollWidth>innerWidth+1};});
 assert.equal(r.sidebar.width,collapsed?64:280);assert.equal(r.button.width,40);assert.equal(r.button.height,40);assert.equal(r.icon.width,20);assert.equal(r.overflow,false);assert.equal(r.view.width,width-(collapsed?64:280)-80);
 if(collapsed){assert.equal(r.button.y-r.brand.bottom,20);assert.equal(r.button.x+r.button.width/2,32);assert.ok(r.button.bottom<=r.menu.y);}else{assert.equal(r.button.right,r.sidebar.right-21);assert.ok(Math.abs(r.button.y+r.button.height/2-r.brand.y-r.brand.height/2)<1);}
 assert.equal(await draft.inputValue(),'메뉴 검수 초안 — 전송하지 않음');assert.equal(await toggle.getAttribute('aria-label'),collapsed?'주 메뉴 펼치기':'주 메뉴 접기');
 rows.push({mode,width,collapsed,...r});if(width===1280)await p.screenshot({path:`${out}/${mode}-${collapsed?'collapsed':'expanded'}.png`});
 }}}
 await p.reload();await toggle.waitFor();assert.equal(await toggle.getAttribute('aria-expanded'),'false');
 await p.setViewportSize({width:390,height:900});await p.locator('#nav-toggle').click();assert.equal(await p.locator('#app-sidebar').getAttribute('aria-modal'),'true');await p.keyboard.press('Escape');assert.equal(await p.locator('#nav-toggle').evaluate(n=>n===document.activeElement),true);
 await p.setViewportSize({width:1280,height:900});await p.waitForFunction(()=>document.getElementById('sidebar-toggle').getAttribute('aria-expanded')==='false');assert.equal(await toggle.getAttribute('aria-expanded'),'false');await p.locator('#sidebar-settings').click();assert.equal(await toggle.getAttribute('aria-expanded'),'true');assert.equal(await p.locator('#theme-control select').evaluate(n=>n===document.activeElement),true);
 await p.evaluate(()=>{Storage.prototype.setItem=()=>{throw Error('blocked')};});await toggle.focus();await p.keyboard.press('Space');assert.equal(await toggle.getAttribute('aria-expanded'),'false');await p.keyboard.press('Enter');assert.equal(await toggle.getAttribute('aria-expanded'),'true');
 for(const width of [320,390,768]){await p.setViewportSize({width,height:900});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);}
 assert.equal(writes,0);fs.writeFileSync(`${out}/verification.json`,JSON.stringify({rows,writes,reload:true,mobileRestore:true,settingsFocus:true,storageFailure:true,keyboard:true},null,2));console.log(JSON.stringify({layouts:rows.length,writes,status:'passed'}));
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exit(1)});
