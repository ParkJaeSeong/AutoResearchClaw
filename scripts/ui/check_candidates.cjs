// Existing server UI plus read-only saved research data; no external source visits.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const bytes=fs.readFileSync(process.env.PILOT_UI_VIEW),view=JSON.parse(bytes);
 const revision=view.revisions.filter(r=>r.record.node==='screen'&&r.record.content.candidates?.length>100).at(-1);
 assert.ok(revision);const candidates=revision.record.content.candidates;
 const out=process.env.PILOT_UI_OUTPUT||'output/evaluations/candidate-list';fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch();let writes=0;const errors=[],layouts=[];
 try{
  const p=await browser.newPage({viewport:{width:1920,height:1080}});p.on('pageerror',e=>errors.push(e.message));
  await p.route('**/api/**',r=>{if(r.request().method()!=='GET'){writes++;return r.abort();}return r.request().url().includes('/api/view')?r.fulfill({json:view}):r.abort();});
  await p.goto(process.env.PILOT_UI_URL||'http://127.0.0.1:8771');await p.getByRole('tab',{name:'단계와 대화',exact:true}).click();
  await p.locator('[data-key="node:screen"]').click();await p.locator('[data-key=revision-select]').selectOption(revision.record.id);
  const list=p.locator('#record-panel .candidate-list'),input=list.getByRole('searchbox');
  assert.equal(await list.locator('.candidate-row').count(),candidates.length);assert.equal(await list.locator('.candidate-row[open]').count(),0);
  assert.deepEqual(await list.locator('.candidate-title').allTextContents(),candidates.map(c=>c.title||'제목 미기록'));
  await input.fill(candidates[0].doi.toUpperCase());
  const expected=candidates.filter(c=>[c.title,c.doi,c.arxiv_id].filter(Boolean).join(' ').toLowerCase().includes(candidates[0].doi.toLowerCase()));
  assert.equal(await list.locator('.candidate-item:visible').count(),expected.length);
  const row=list.locator('.candidate-item:visible .candidate-row').first();await row.locator(':scope > summary').focus();await p.keyboard.press('Enter');assert.equal(await row.getAttribute('open'),'');
  assert.deepEqual(JSON.parse(await row.locator('.record-json').textContent()),candidates[0]);
  assert.equal(await list.locator('.candidate-item:visible .candidate-link').first().getAttribute('href'),candidates[0].url);
  await p.locator('#record-panel').evaluate(n=>n.dataset.beforeRefresh='yes');view.head_id+='-candidate-ui-only';
  await p.locator('.record-tools > details > summary').click();await p.locator('[data-key=refresh]').click();
  await p.waitForFunction(()=>!document.querySelector('#record-panel')?.dataset.beforeRefresh);
  assert.equal(await input.inputValue(),candidates[0].doi.toUpperCase());assert.equal(await row.getAttribute('open'),'');
  await row.locator(':scope > summary').focus();await p.keyboard.press('Space');assert.equal(await row.getAttribute('open'),null);
  await input.fill('no-matching-candidate-000000');assert.equal(await list.locator('.candidate-item:visible').count(),0);assert.match(await list.innerText(),/一致|일치하는 후보 자료가 없습니다/);
  await input.fill('');assert.equal(await list.locator('.candidate-item:visible').count(),candidates.length);
  for(const mode of ['light','dark']){
   await p.emulateMedia({colorScheme:mode});for(const width of [320,390,768,1280,1920,2560]){
    await p.setViewportSize({width,height:1080});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    const widths=await list.evaluate(n=>({list:n.getBoundingClientRect().width,row:n.querySelector('.candidate-item').getBoundingClientRect().width}));assert.ok(Math.abs(widths.list-widths.row)<2);
    layouts.push({mode,width,...widths});if(width===1920){await list.evaluate(n=>n.scrollIntoView({block:'start'}));await p.screenshot({path:`${out}/${mode}.png`});}
   }
  }
  assert.equal(writes,0);assert.deepEqual(errors,[]);assert.ok(bytes.equals(fs.readFileSync(process.env.PILOT_UI_VIEW)));
  fs.writeFileSync(`${out}/verification.json`,JSON.stringify({count:candidates.length,layouts,originalRecords:true,filter:true,refreshState:true,keyboard:true,writes,errors},null,2));console.log({count:candidates.length,layouts:layouts.length,writes,errors});
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
