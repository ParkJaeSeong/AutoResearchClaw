import {renderGraph} from './graph.js';
import {element, renderNodeDetail, renderTrace, renderComparison, renderInspection} from './detail.js';

const COLLECTIONS = ['nodes','edges','attempts','artifacts','sessions','issues','responses','decisions','approvals','next_actions'];

export function validateView(view) {
  if (!view || typeof view !== 'object') return ['기록이 올바른 객체가 아닙니다.'];
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
  return before && after ? {before, after} : null;
}

export function sourceLink(value) {
  try {
    const url = new URL(value);
    return ['http:','https:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

export function renderResearchView(root, view) {
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
  brand.append(element('span', 'RC', 'brand-mark'), element('span', 'ResearchClaw'));
  const origin = element('span', view.data_origin === 'demo' ? '예시 데이터 · 실제 연구 기록 아님' : '등록된 연구 기록', 'origin-label');
  top.append(brand, origin);
  const heading = element('section', undefined, 'project-heading');
  heading.append(element('span', '연구 결정 지도', 'eyebrow'), element('h1', view.project.title));
  heading.append(element('p', '근거에서 쟁점으로, 쟁점에서 다음 연구 방향으로.', 'secondary'));
  const milestones = element('nav', undefined, 'milestones');
  milestones.setAttribute('aria-label', '연구 마일스톤');
  for (const [id, title, status] of [['M1','근거와 가설 형성','선택됨'],['M2','실험과 방향 결정','후속 개발'],['M3','연구 마무리','후속 개발']]) {
    const item = element('div', undefined, id === 'M1' ? 'milestone active' : 'milestone');
    item.append(element('span', id, 'milestone-id'), element('strong', title), element('span', status, 'secondary'));
    milestones.append(item);
  }
  const workspace = element('div', undefined, 'workspace');
  const mapPanel = element('section', undefined, 'map-panel');
  mapPanel.append(element('span', 'M1 작업 흐름', 'eyebrow'), element('h2', '어디서, 왜 돌아왔나'));
  const graph = element('div');
  mapPanel.append(graph);
  const detailPanel = element('div', undefined, 'detail-panel');
  const nodeDetail = element('section', undefined, 'node-detail');
  const decisionSelect = element('div', undefined, 'decision-picker');
  const trace = element('section', undefined, 'trace-panel');
  const comparison = element('section', undefined, 'comparison-panel');
  const inspect = element('section', undefined, 'inspection-panel');
  inspect.setAttribute('aria-live', 'polite');
  detailPanel.append(nodeDetail, decisionSelect, trace, comparison, inspect);
  workspace.append(mapPanel, detailPanel);
  root.append(top, heading, milestones, workspace);
  const inspectItem = (kind, id) => renderInspection(inspect, view, kind, id);
  function showDecision(id) {
    const result = traceDecision(view, id);
    renderTrace(trace, result, inspectItem);
    const versions = result?.decision.hypothesis_versions;
    comparison.hidden = !versions?.length;
    if (versions?.length) renderComparison(comparison, compareHypotheses(view, versions[0], versions[1]));
    inspect.replaceChildren();
    for (const button of decisionSelect.querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.decisionId === id));
  }
  function selectNode(id) {
    const focusedNode = document.activeElement?.dataset?.nodeId;
    renderGraph(graph, view, id, selectNode);
    renderNodeDetail(nodeDetail, view.nodes.find(node => node.id === id));
    decisionSelect.replaceChildren();
    const decisions = view.decisions.filter(decision => decision.node_id === id);
    for (const decision of decisions) {
      const button = element('button', decision.short_label, 'decision-tab');
      button.type = 'button';
      button.dataset.decisionId = decision.id;
      button.addEventListener('click', () => showDecision(decision.id));
      decisionSelect.append(button);
    }
    showDecision(decisions[0]?.id);
    if (focusedNode) [...graph.querySelectorAll('[data-node-id]')].find(button => button.dataset.nodeId === id)?.focus();
  }
  selectNode(view.nodes.find(node => node.status === 'current')?.id ?? view.nodes[0]?.id);
}

if (typeof document !== 'undefined') {
  const root = document.getElementById('research-app');
  if (root) {
    const demoUrl = new URL('../../../tests/ui/m1/demo.json', import.meta.url);
    fetch(demoUrl).then(response => {
      if (!response.ok) throw new Error(`기록을 가져올 수 없습니다 (${response.status})`);
      return response.json();
    }).then(view => renderResearchView(root, view)).catch(() => {
      const message = element('p', '연구 기록을 불러오지 못했습니다. 서버 연결과 자료 위치를 확인해 주세요.', 'error');
      message.setAttribute('role', 'alert');
      root.replaceChildren(message);
    });
  }
}
