import test from 'node:test';
import assert from 'node:assert/strict';
import {knowledgeLabels} from '../../../researchclaw/codex/research_ui/knowledge_status.js';
test('answer receipt and wiki outcome remain separate',()=>{
 const x=knowledgeLabels({stored_answer:true,knowledge_status:'partial'});
 assert.equal(x.answer,'답변 수신 완료');assert.match(x.knowledge,/일부 반영/);
 assert.doesNotMatch(x.answer+x.knowledge,/연구 완료|검토 완료/);
 assert.equal(knowledgeLabels({stored_answer:false,answer_status:'ready'}).answer,'답변 가져오기 대기');
});
