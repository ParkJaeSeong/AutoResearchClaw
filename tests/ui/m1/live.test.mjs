import test from 'node:test';
import assert from 'node:assert/strict';

const module = await import('../../../researchclaw/codex/m1_ui/live.js').catch(() => ({}));
function setup(load) {
  assert.equal(typeof module.createLiveFeed, 'function', 'live feed implementation is missing');
  const rendered = [], statuses = [], timers = new Map();
  let serial = 0, now = 100;
  const feed = module.createLiveFeed({load, onView: view => rendered.push(view),
    onStatus: status => statuses.push(status), now: () => ++now,
    setTimer: (fn, delay) => { const id = ++serial; timers.set(id, {fn, delay}); return id; },
    clearTimer: id => timers.delete(id)});
  return {feed, rendered, statuses, timers};
}

test('unchanged HEAD avoids rerendering; a new HEAD refreshes once', async () => {
  let head = 'one';
  const app = setup(async () => ({head_id: head}));
  await app.feed.start();
  await app.feed.refresh();
  assert.deepEqual(app.rendered.map(v => v.head_id), ['one']);
  head = 'two';
  await app.feed.refresh();
  assert.deepEqual(app.rendered.map(v => v.head_id), ['one', 'two']);
  assert.equal(app.timers.size, 1);
  assert.equal([...app.timers.values()][0].delay, 3000);
  app.feed.stop();
});

test('disconnect preserves last data and update time, then recovers without replacing unchanged data', async () => {
  let disconnected = false;
  const app = setup(async () => { if (disconnected) throw new Error('offline'); return {head_id:'one'}; });
  await app.feed.start();
  const updatedAt = app.statuses.at(-1).lastUpdatedAt;
  disconnected = true;
  await app.feed.refresh();
  assert.equal(app.rendered.length, 1);
  assert.equal(app.statuses.at(-1).connected, false);
  assert.equal(app.statuses.at(-1).lastUpdatedAt, updatedAt);
  assert.equal(app.statuses.at(-1).error, 'offline');
  disconnected = false;
  await app.feed.refresh();
  assert.equal(app.statuses.at(-1).connected, true);
  assert.equal(app.rendered.length, 1);
  app.feed.stop();
});

test('overlapping refreshes share one request and stop suppresses its late result', async () => {
  let resolve, calls = 0;
  const app = setup(() => { calls++; return new Promise(done => { resolve = done; }); });
  const first = app.feed.start(), second = app.feed.refresh();
  assert.equal(calls, 1);
  app.feed.stop();
  resolve({head_id:'one'});
  await Promise.all([first, second]);
  assert.equal(app.rendered.length, 0);
  assert.equal(app.statuses.length, 0);
  assert.equal(app.timers.size, 0);
});

test('invalid view identity cannot overwrite the last valid view', async () => {
  let value = {head_id:'one'};
  const app = setup(async () => value);
  await app.feed.start();
  value = {};
  await app.feed.refresh();
  assert.equal(app.rendered.length, 1);
  assert.equal(app.statuses.at(-1).connected, false);
  app.feed.stop();
});
