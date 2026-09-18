import test from 'node:test';
import assert from 'node:assert/strict';
import {statusInfo,filterItems,safeLink} from '../../../researchclaw/codex/research_ui/document_handoff.js';
test('status does not equate receipts or knowledge organization with research adoption',()=>{
 assert.match(statusInfo('atlas_submission_pending').label,/접수 대기/);
 assert.match(statusInfo('completed').next,/검토/);
 assert.equal(statusInfo('partial').group,'attention');
 assert.equal(statusInfo('future').group,'attention');
});
test('search and status filters work together',()=>{
 const rows=[{title:'혼련 논문',status:'partial',doi:'10.1/abc'},{title:'다른 논문',status:'completed'}];
 assert.deepEqual(filterItems(rows,'10.1','attention'),[rows[0]]);
 assert.equal(filterItems(rows,'','completed').length,1);
 assert.equal(filterItems(rows,'없는 내용','all').length,0);
});
test('original links never execute scripts or expose local paths',()=>{
 assert.equal(safeLink('javascript:alert(1)'),null);
 assert.equal(safeLink('file:///secret'),null);
 assert.equal(safeLink('https://example.org/paper'),'https://example.org/paper');
});
