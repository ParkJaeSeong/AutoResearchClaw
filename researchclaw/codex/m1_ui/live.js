// Serial polling preserves the last rendered record during disconnection.
export function createLiveFeed({load, onView, onStatus, now = Date.now,
  setTimer = setTimeout, clearTimer = clearTimeout}) {
  let stopped = false, timer = null, inFlight = null;
  let head = null, lastUpdatedAt = null;

  function refresh() {
    if (stopped) return Promise.resolve();
    if (inFlight) return inFlight;
    if (timer !== null) { clearTimer(timer); timer = null; }
    let request;
    try { request = load(); } catch (error) { request = Promise.reject(error); }
    inFlight = Promise.resolve(request).then(view => {
      if (stopped) return;
      if (typeof view?.head_id !== 'string' || !view.head_id) {
        throw new Error('기록의 버전 식별자를 확인할 수 없습니다.');
      }
      if (view.head_id !== head) {
        onView(view);
        head = view.head_id;
        lastUpdatedAt = now();
      }
      onStatus({connected:true, lastUpdatedAt, checkedAt:now(), error:null});
    }).catch(error => {
      if (!stopped) onStatus({connected:false, lastUpdatedAt, checkedAt:now(),
        error: error instanceof Error ? error.message : String(error)});
    }).finally(() => {
      inFlight = null;
      if (!stopped) timer = setTimer(refresh, 3000);
    });
    return inFlight;
  }

  return {start:refresh, refresh, stop() {
    stopped = true;
    if (timer !== null) clearTimer(timer);
    timer = null;
  }};
}
