import {renderGraph} from './graph.js';
import {createLiveFeed} from './live.js';
import {element, renderNodeDetail, renderTrace, renderComparison, renderInspection, renderCouncil} from './detail.js';

const COLLECTIONS = ['nodes','edges','attempts','artifacts','sessions','issues','responses','decisions','approvals','next_actions'];

export function validateView(view) {
  if (!view || typeof view !== 'object') return ['연구 기록의 형식을 읽을 수 없습니다.'];
  const errors = [];
  if (view.schema_version !== 1) errors.push('지원하지 않는 기록 버전입니다.');
  if (!['demo','registered'].includes(view.data_origin)) errors.push('기록의 출처 구분이 없습니다.');
  for (const field of COLLECTIONS) if (!Array.isArray(view[field])) errors.push(`${field} 목록을 읽을 수 없습니다.`);
  if (!view.project || typeof view.project !== 'object' || Array.isArray(view.project)) errors.push('프로젝트 정보가 없습니다.');
  const arrayFields = {nodes:['roles','inputs','outputs'], decisions:['issue_ids','response_ids','evidence_refs','dissent','hypothesis_versions'], issues:['evidence_refs'], responses:['evidence_refs']};
  for (const field of COLLECTIONS) {
    if (!Array.isArray(view[field])) continue;
    for (const record of view[field]) {
      if (!record || typeof record !== 'object' || Array.isArray(record)) {
        errors.push(`${field}에 올바르지 않은 기록이 있습니다.`);
        continue;
      }
      for (const key of arrayFields[field] ?? []) {
        if ((field === 'nodes' || record[key] !== undefined) && !Array.isArray(record[key])) errors.push(`${field}.${key} 목록을 읽을 수 없습니다.`);
      }
    }
  }
  return errors;
}

export function decisionLabel(decision) {
  return decision.short_label ?? decision.title ?? decision.id;
}

export function selectDecision(view, id) {
  return view.decisions.find(item => item.id === id) ?? null;
}

export function traceDecision(view, id) {
  const decision = selectDecision(view, id);
  if (!decision) return null;
  const missing = [];
  const lookup = (collection, ids) => [...new Set(ids)].flatMap(key => {
    const record = collection.find(item => item.id === key);
    if (!record) { missing.push(key); return []; }
    return [record];
  });
  const issues = lookup(view.issues, decision.issue_ids ?? []);
  const responses = lookup(view.responses, decision.response_ids ?? []);
  const artifacts = lookup(view.artifacts, [
    ...(decision.evidence_refs ?? []),
    ...issues.flatMap(item => item.evidence_refs ?? []),
    ...responses.flatMap(item => item.evidence_refs ?? [])
  ]);
  return {decision, issues, responses, artifacts, missing:[...new Set(missing)]};
}

export function compareHypotheses(view, beforeId, afterId) {
  const hypotheses = view.artifacts.filter(item => item.kind === 'hypothesis');
  const before = hypotheses.find(item => item.id === beforeId);
  const after = hypotheses.find(item => item.id === afterId);
  const sameHypothesis = before?.hypothesis_id && before.hypothesis_id === after?.hypothesis_id;
  const child = after?.parent_revision === before?.revision
    || (view.data_origin === 'demo' && after?.revision > before?.revision);
  return before && after && sameHypothesis && child ? {before, after} : null;
}

export function decisionComparisons(view, decision) {
  const ids = decision?.hypothesis_versions ?? [];
  return ids.flatMap(before => ids.flatMap(after => {
    const pair = compareHypotheses(view, before, after);
    return pair ? [pair] : [];
  }));
}

export function sourceLink(value) {
  try {
    const url = new URL(value);
    return ['http:','https:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

export function resolveSelection(view, previous = {}) {
  const nodeId = view.nodes.find(node => node.id === previous.nodeId)?.id
    ?? view.nodes.find(node => node.id === view.current_node_id)?.id
    ?? view.nodes.find(node => node.current || node.status === 'current')?.id ?? view.nodes[0]?.id ?? null;
  const decisions = view.decisions.filter(decision => decision.node_id === nodeId);
  const decisionId = decisions.find(decision => decision.id === previous.decisionId)?.id
    ?? decisions[0]?.id ?? null;
  return {nodeId, decisionId};
}

export function renderResearchView(root, view, selection = {}) {
  const errors = validateView(view);
  if (errors.length) {
    const message = element('p', errors.join(' '), 'error');
    message.setAttribute('role', 'alert');
    root.replaceChildren(message);
    return;
  }
  root.replaceChildren();
  const top = element('header', undefined, 'topbar');
  const brand = element('div', undefined, 'brand');
  brand.append(element('span', 'P', 'brand-mark'), element('span', 'Pilot'));
  const synthetic = (view.content_origin ?? view.project.content_origin) === 'synthetic';
  const origin = element('span', view.data_origin === 'demo' ? '예시 데이터 · 실제 연구 기록 아님' : synthetic ? '등록 기록 · 합성 검증 자료' : '등록된 연구 기록', 'origin-label');
  top.append(brand, origin);
  const heading = element('section', undefined, 'project-heading');
  heading.append(element('span', '연구 결정 지도', 'eyebrow'), element('h1', view.project.title));
  heading.append(element('p', '근거에서 쟁점으로, 쟁점에서 다음 연구 방향으로.', 'secondary'));
  const milestones = element('nav', undefined, 'milestones');
  milestones.setAttribute('aria-label', '연구 마일스톤');
  for (const [id, title, status] of [['M1','근거와 가설 형성','선택됨'],['M2','실험과 방향 결정','예정'],['M3','연구 마무리','예정']]) {
    const item = element('div', undefined, id === 'M1' ? 'milestone active' : 'milestone');
    item.append(element('span', id, 'milestone-id'), element('strong', title), element('span', status, 'secondary'));
    milestones.append(item);
  }
  const overview = element('section', undefined, 'progress-overview');
  overview.setAttribute('aria-label', '현재 연구 상태');
  for (const action of view.next_actions) {
    const item = element('div');
    item.append(element('span', '현재 진행', 'eyebrow'), element('strong', ({collect_initials:'최초 의견 수집', collect_responses:'의견 교환', collect_final_positions:'최종 입장 수집', decide:'다음 행동 결정', await_user:'사용자 판단 대기', prepare_node:'작업 준비', revise:'수정 작업', apply_return:'복귀 계획 적용'})[action.action] ?? action.label ?? action.action));
    if (action.reason) item.append(element('p', action.reason, 'secondary'));
    for (const reason of action.wait_reasons ?? []) item.append(element('p', reason, 'warning'));
    overview.append(item);
  }
  if (view.budget) {
    const budget = element('div');
    budget.append(element('span', '복귀 사용', 'eyebrow'), element('strong', `${view.budget.returns_used} / ${view.budget.max_returns}회`));
    budget.append(element('p', view.budget.exhausted ? '앞 단계로 돌아갈 수 있는 횟수를 모두 사용했습니다.' : `${view.budget.remaining}회 남음`, 'secondary'));
    overview.append(budget);
  }
  if (view.missing_references?.length) overview.append(element('p', `연결된 기록 ${view.missing_references.length}개를 찾을 수 없습니다. 상세 기록의 누락 표시를 확인해 주세요.`, 'warning'));
  overview.hidden = !overview.childElementCount;
  const workspace = element('div', undefined, 'workspace');
  const mapPanel = element('section', undefined, 'map-panel');
  mapPanel.append(element('span', 'M1 작업 흐름', 'eyebrow'), element('h2', '어느 단계로 왜 돌아왔나요?'));
  const graph = element('div');
  mapPanel.append(graph);
  const detailPanel = element('div', undefined, 'detail-panel');
  const nodeDetail = element('section', undefined, 'node-detail');
  const council = element('section', undefined, 'council-panel');
  const decisionSelect = element('div', undefined, 'decision-picker');
  const trace = element('section', undefined, 'trace-panel');
  const comparison = element('section', undefined, 'comparison-panel');
  const inspect = element('section', undefined, 'inspection-panel');
  inspect.setAttribute('aria-live', 'polite');
  inspect.tabIndex = -1;
  detailPanel.append(nodeDetail, decisionSelect, trace, comparison, council, inspect);
  workspace.append(mapPanel, detailPanel);
  root.append(top, heading, milestones, overview, workspace);
  const inspectItem = (kind, id, reveal = true) => {
    selection.inspection = {kind, id};
    renderInspection(inspect, view, kind, id, sourceLink);
    if (reveal) { inspect.scrollIntoView({block:'nearest'}); inspect.focus({preventScroll:true}); }
  };
  function showDecision(id) {
    selection.decisionId = id ?? null;
    selection.inspection = null;
    const result = traceDecision(view, id);
    renderTrace(trace, result, inspectItem);
    const pairs = decisionComparisons(view, result?.decision);
    comparison.replaceChildren();
    comparison.hidden = !pairs.length;
    for (const pair of pairs) {
      const section = element('section');
      renderComparison(section, pair);
      comparison.append(section);
    }
    inspect.replaceChildren();
    for (const button of decisionSelect.querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.decisionId === id));
  }
  function selectNode(id, preferredDecision = null) {
    selection.nodeId = id;
    const focusedNode = graph.contains(document.activeElement);
    renderGraph(graph, view, id, selectNode);
    renderNodeDetail(nodeDetail, view.nodes.find(node => node.id === id));
    const attempts = view.attempts.filter(attempt => attempt.node_id === id);
    const attemptIds = new Set(attempts.map(attempt => attempt.id));
    const outputIds = new Set(attempts.flatMap(attempt => (attempt.output_refs ?? []).map(ref => typeof ref === 'string' ? ref : ref.id)));
    const outputs = view.artifacts.filter(artifact => outputIds.has(artifact.id));
    if (outputs.length) {
      const artifacts = element('details', undefined, 'attempt-history');
      artifacts.dataset.disclosureId = `outputs:${id}`;
      artifacts.append(element('summary', `등록된 산출물 ${outputs.length}개`));
      for (const artifact of outputs) {
        const button = element('button', artifact.title ?? artifact.logical_path ?? artifact.id, 'source-button');
        button.type = 'button'; button.addEventListener('click', () => inspectItem('artifact', artifact.id));
        artifacts.append(button);
      }
      nodeDetail.append(artifacts);
    }
    renderCouncil(council, view.sessions.filter(session => attemptIds.has(session.review_attempt_id) || session.node_id === id), inspectItem);
    if (attempts.length) {
      const history = element('details', undefined, 'attempt-history');
      history.dataset.disclosureId = `attempts:${id}`;
      history.append(element('summary', `작업 회차 ${attempts.length}개 · 과거 기록 보기`));
      for (const attempt of attempts) history.append(element('p', `${attempt.id} · ${attempt.status}`, 'secondary'));
      nodeDetail.append(history);
    }
    decisionSelect.replaceChildren();
    const decisions = view.decisions.filter(decision => decision.node_id === id);
    for (const decision of decisions) {
      const button = element('button', decisionLabel(decision), 'decision-tab');
      button.type = 'button';
      button.dataset.decisionId = decision.id;
      button.addEventListener('click', () => showDecision(decision.id));
      decisionSelect.append(button);
    }
    showDecision(decisions.find(item => item.id === preferredDecision)?.id ?? decisions[0]?.id);
    if (focusedNode) [...graph.querySelectorAll('[data-node-id]')].find(button => button.dataset.nodeId === id)?.focus();
  }
  const retainedInspection = selection.inspection;
  const resolved = resolveSelection(view, selection);
  selectNode(resolved.nodeId, resolved.decisionId);
  if (retainedInspection) inspectItem(retainedInspection.kind, retainedInspection.id, false);
}

if (typeof document !== 'undefined') {
  const root = document.getElementById('research-app');
  if (root) {
    const status = element('p', '등록 기록 연결 중…', 'connection-status');
    status.setAttribute('role', 'status');
    root.before(status);
    const selection = {};
    const feed = createLiveFeed({
      async load() {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10000);
        try {
          const response = await fetch('/api/view', {cache:'no-store', signal:controller.signal});
          if (!response.ok) throw new Error(`기록 조회 실패 (${response.status})`);
          const view = await response.json();
          const errors = validateView(view);
          if (errors.length) throw new Error(errors.join(' '));
          return view;
        } finally { clearTimeout(timeout); }
      },
      onView(view) {
        const scroll = {x:window.scrollX, y:window.scrollY};
        const disclosures = new Map([...root.querySelectorAll('[data-disclosure-id]')].map(item => [item.dataset.disclosureId, item.open]));
        const active = document.activeElement;
        const focused = active?.dataset.nodeId ? ['nodeId', active.dataset.nodeId]
          : active?.dataset.decisionId ? ['decisionId', active.dataset.decisionId]
          : active?.tagName === 'SUMMARY' && active.parentElement?.dataset.disclosureId ? ['disclosureId', active.parentElement.dataset.disclosureId] : null;
        renderResearchView(root, view, selection);
        for (const item of root.querySelectorAll('[data-disclosure-id]')) {
          if (disclosures.has(item.dataset.disclosureId)) item.open = disclosures.get(item.dataset.disclosureId);
        }
        if (focused) {
          const target = [...root.querySelectorAll('button, details[data-disclosure-id]')].find(item => item.dataset[focused[0]] === focused[1]);
          (target?.tagName === 'DETAILS' ? target.querySelector('summary') : target)?.focus({preventScroll:true});
        }
        window.scrollTo(scroll.x, scroll.y);
      },
      onStatus({connected, lastUpdatedAt, error}) {
        const time = lastUpdatedAt === null ? '아직 없음' : new Date(lastUpdatedAt).toLocaleTimeString('ko-KR');
        status.textContent = connected
          ? `연결됨 · 마지막 기록 갱신 ${time} · 읽기 전용`
          : `갱신 실패 · ${error ?? '서버 연결을 확인해 주세요.'} · 마지막 기록 갱신 ${time} · 이전 기록을 유지하며 재연결 중`;
        status.classList.toggle('warning', !connected);
      }
    });
    feed.start();
    window.addEventListener('pagehide', () => feed.stop(), {once:true});
  }
}
