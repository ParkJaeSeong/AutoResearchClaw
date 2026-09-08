import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {validateView, selectDecision, traceDecision, compareHypotheses, sourceLink} from '../../../researchclaw/codex/m1_ui/app.js';
import {visibleEdges} from '../../../researchclaw/codex/m1_ui/graph.js';

const fixture = JSON.parse(await readFile(new URL('./demo.json', import.meta.url), 'utf8'));

test('decision trace resolves the issue, actual response and source behind the choice', () => {
  const trace = traceDecision(fixture, 'D1');
  assert.equal(trace.decision.id, 'D1');
  assert.deepEqual(trace.issues.map(x => x.id), ['I1']);
  assert.deepEqual(trace.responses.map(x => x.id), ['R1', 'R2', 'R3']);
  assert.deepEqual(trace.artifacts.map(x => x.id), ['C1', 'C2']);
  assert.equal(trace.missing.length, 0);
  assert.equal(selectDecision(fixture, 'missing'), null);
});

test('unresolved reference is disclosed rather than silently using another version', () => {
  const view = structuredClone(fixture);
  view.artifacts = view.artifacts.filter(x => x.id !== 'C2');
  assert.deepEqual(traceDecision(view, 'D1').missing, ['C2']);
});

test('hypothesis comparison keeps the rejected earlier statement and change reason', () => {
  const result = compareHypotheses(fixture, 'H1-r1', 'H1-r2');
  assert.equal(result.before.revision, 1);
  assert.equal(result.after.revision, 2);
  assert.match(result.after.change_reason, /집단/);
  assert.notEqual(result.before.statement, result.after.statement);
  assert.equal(compareHypotheses(fixture, 'missing', 'H1-r2'), null);
});

test('view requires explicit demo or registered origin and valid collections', () => {
  assert.equal(validateView(fixture).length, 0);
  assert.ok(validateView({...fixture, data_origin: 'live-proof'}).length);
  assert.ok(validateView({...fixture, decisions: null}).length);
  assert.ok(validateView(null).length);
});

test('only the selected node return path appears alongside forward edges', () => {
  const edges = visibleEdges(fixture, 'review');
  assert.ok(edges.some(e => e.kind === 'return' && e.to === 'hypothesize'));
  assert.ok(edges.some(e => e.kind === 'forward' && e.to === 'review'));
  assert.ok(visibleEdges(fixture, 'scope').every(e => e.kind !== 'return'));
});

test('source links reject script and local-file protocols', () => {
  assert.equal(sourceLink('javascript:alert(1)'), null);
  assert.equal(sourceLink('file:///private/secret'), null);
  assert.equal(sourceLink('//example.org'), null);
  assert.equal(sourceLink('https://example.org/paper'), 'https://example.org/paper');
});

test('malformed nested records are rejected before rendering', () => {
  assert.ok(validateView({...fixture, nodes: [null]}).length);
  assert.ok(validateView({...fixture, nodes: [{id:'scope', roles:null}]}).length);
  assert.ok(validateView({...fixture, decisions: [{id:'D1', issue_ids:'I1'}]}).length);
  assert.ok(validateView({...fixture, project: []}).length);
});
