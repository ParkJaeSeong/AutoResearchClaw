// Read-only browser verification against a saved public research view.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
(async()=>{
  const fixture=process.env.PILOT_UI_VIEW,out=process.env.PILOT_UI_OUTPUT||'output/evaluations/stage-issues';
  const bytes=fs.readFileSync(fixture),view=JSON.parse(bytes),digest=b=>crypto.createHash('sha256').update(b).digest('hex');
  const {issuesForSelection}=await import('../../researchclaw/codex/research_ui/timeline.js');
  fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch();let writes=0;const errors=[],counts=[];
  try{
    const page=await browser.newPage({viewport:{width:1920,height:1080}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/**',route=>{
      if(route.request().method()!=='GET'){writes++;return route.abort();}
      return route.request().url().includes('/api/view')?route.fulfill({json:view}):route.abort();
    });
    await page.goto(process.env.PILOT_UI_URL||'http://127.0.0.1:8771');
    await page.getByRole('tab',{name:'단계와 대화',exact:true}).click();
    for(const node of view.nodes){
      await page.locator(`[data-key="node:${node.id}"]`).click();
      await page.locator('[data-key="tab:issues"]').click();
      const expected=issuesForSelection(view,{nodeId:node.id});
      assert.equal(await page.locator('[data-key="issue-scope:stage"]').getAttribute('aria-pressed'),'true');
      assert.deepEqual(await page.locator('.issue-row').evaluateAll(nodes=>nodes.map(n=>n.dataset.key)),expected.map(i=>`issue:${i.record.id}`));
      const panel=page.locator('#record-panel');
      if(expected.length){assert.equal(await panel.locator('.issue-question').first().textContent(),expected[0].record.question);assert.equal(await panel.locator('.issue-row[open]').count(),0);}
      else assert.match(await panel.textContent(),/연결된 문제 기록이 없습니다/);
      counts.push({node:node.id,count:expected.length});
    }
    assert.ok(new Set(counts.map(row=>row.count)).size>1,'Fixture must demonstrate different stage lists');
    await page.locator('[data-key="issue-scope:all"]').click();
    assert.equal(await page.locator('.issue-row').count(),view.issues.length);
    // A question-origin issue currently affects final review as well.
    const cross=view.issues.find(i=>i.record.origin?.node==='questions'&&i.effective_blocking_scope?.some(s=>s.kind==='node'&&s.target_id==='review'));
    assert.ok(cross);
    await page.locator('[data-key="node:review"]').click();await page.locator('[data-key="tab:issues"]').click();
    assert.equal(await page.locator('[data-key="issue-scope:stage"]').getAttribute('aria-pressed'),'true');
    const crossRow=page.locator(`[data-key="issue:${cross.record.id}"]`);await crossRow.locator(':scope > summary').focus();await page.keyboard.press('Enter');assert.equal(await crossRow.getAttribute('open'),'');
    assert.equal(await crossRow.locator('.issue-body > h2, .issue-body > .badge').count(),0);
    assert.equal((await crossRow.innerText()).split(cross.record.question).length-1,1);
    await crossRow.locator(':scope > summary').scrollIntoViewIfNeeded();await page.screenshot({path:`${out}/opened.png`});
    const other=page.locator('.issue-row').nth(1);await other.locator(':scope > summary').click();assert.equal(await page.locator('.issue-row[open]').count(),2);
    assert.match(await page.locator('#record-panel').textContent(),/제기된 단계: 연구 질문/);
    assert.match(await page.locator('#record-panel').textContent(),/이 단계의 진행 조건에 연결/);
    assert.doesNotMatch(await page.locator('#record-panel').textContent(),/선택 단계와의 관계: 이 단계에서 제기됨/);
    // Re-render with an in-memory HEAD only; production research is never changed.
    await page.locator('#record-panel').evaluate(n=>n.dataset.beforeRefresh='yes');
    view.head_id+='-browser-check';
    await page.locator('.record-tools > details > summary').click();
    await page.locator('[data-key=refresh]').click();
    await page.waitForFunction(()=>!document.querySelector('#record-panel')?.dataset.beforeRefresh);
    assert.equal(await crossRow.getAttribute('open'),'');assert.equal(await page.locator('.issue-row[open]').count(),2);
    await crossRow.locator(':scope > summary').focus();await page.keyboard.press('Space');assert.equal(await crossRow.getAttribute('open'),null);
    await other.locator(':scope > summary').click();
    assert.equal(await page.locator('.sidebar .issue-row').count(),0);
    const layouts=[];
    for(const mode of ['light','dark']){
      await page.emulateMedia({colorScheme:mode});
      for(const width of [320,390,768,1280,1920,2560]){
        await page.setViewportSize({width,height:1080});
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
        const rowWidth=await page.locator('.issue-row').first().evaluate(n=>n.getBoundingClientRect().width),panelWidth=await page.locator('#record-panel').evaluate(n=>n.getBoundingClientRect().width);assert.ok(Math.abs(rowWidth-panelWidth)<2);
        layouts.push({mode,width,rowWidth,panelWidth});
        if(width===1920){await page.locator('#record-panel').scrollIntoViewIfNeeded();await page.screenshot({path:`${out}/${mode}-review.png`});}
      }
    }
    assert.equal(writes,0);assert.deepEqual(errors,[]);assert.equal(digest(fs.readFileSync(fixture)),digest(bytes));
    fs.writeFileSync(`${out}/verification.json`,JSON.stringify({counts,total:view.issues.length,layouts,originAndImpact:true,accordionKeyboard:true,multipleOpen:true,refreshOpenState:true,fixtureUnchanged:true,writes,errors},null,2));
    console.log({counts,total:view.issues.length,layouts:layouts.length,writes,errors});
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
