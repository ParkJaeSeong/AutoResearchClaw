import test from 'node:test';
import assert from 'node:assert/strict';
import * as app from '../../../researchclaw/codex/m1_ui/app.js';
const view = {nodes:[{id:'review',status:'completed'},{id:'hypothesize',status:'current'}],decisions:[{id:'D1',node_id:'review'},{id:'D2',node_id:'review'}]};
test('a new head preserves a historical node and decision selection', () => {
  assert.deepEqual(app.resolveSelection(view,{nodeId:'review',decisionId:'D2'}),{nodeId:'review',decisionId:'D2'});
});
test('removed selection falls back to the current node without retaining another node decision', () => {
  assert.deepEqual(app.resolveSelection(view,{nodeId:'missing',decisionId:'D2'}),{nodeId:'hypothesize',decisionId:null});
  assert.deepEqual(app.resolveSelection(view,{nodeId:'review',decisionId:'missing'}),{nodeId:'review',decisionId:'D1'});
});

test('registered current node uses engine identity independently of attempt status', () => {
  const actual = {current_node_id:'review',nodes:[{id:'scope',status:'completed',current:false},{id:'review',status:'collecting_initials',current:true}],decisions:[]};
  assert.deepEqual(app.resolveSelection(actual),{nodeId:'review',decisionId:null});
});

test('decision comparison pairs only pinned parent-child versions of each candidate', () => {
  const artifacts = [
    {kind:'hypothesis',id:'a',hypothesis_id:'H1',revision:1},
    {kind:'hypothesis',id:'b',hypothesis_id:'H2',revision:1},
    {kind:'hypothesis',id:'c',hypothesis_id:'H1',revision:2,parent_revision:1},
    {kind:'hypothesis',id:'d',hypothesis_id:'H2',revision:2,parent_revision:1},
    {kind:'hypothesis',id:'unrelated',hypothesis_id:'H1',revision:3,parent_revision:2}
  ];
  const pairs = app.decisionComparisons({artifacts}, {hypothesis_versions:['a','b','c','d']});
  assert.deepEqual(pairs.map(p => [p.before.id,p.after.id]),[['a','c'],['b','d']]);
  assert.deepEqual(app.decisionComparisons({artifacts},{hypothesis_versions:['a','b']}),[]);
});

test('registered decisions and permitted return edges have meaningful navigation labels', async () => {
  const graph = await import('../../../researchclaw/codex/m1_ui/graph.js');
  assert.equal(app.decisionLabel({id:'D1',title:'가설 수정 결정'}),'가설 수정 결정');
  assert.equal(app.decisionLabel({id:'D2'}),'D2');
  assert.equal(graph.returnLinkLabel({to:'hypothesize'}, {title:'가설 형성'}),'↶ 가설 형성 · 가능한 복귀 경로');
  assert.equal(graph.isCurrentNode({current_node_id:'review'}, {id:'review',status:'collecting_initials'}),true);
});
