export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

export function renderNodeDetail(container, node) {
  container.replaceChildren();
  if (!node) {
    container.append(element('p', '선택한 작업을 찾을 수 없습니다.', 'empty'));
    return;
  }
  container.append(element('span', '선택한 작업', 'eyebrow'), element('h2', node.title));
  container.append(element('p', node.question, 'node-question'));
  const dl = element('dl', undefined, 'facts');
  for (const [label, value] of [['담당', node.roles.join(' · ')], ['입력', node.inputs.join(' · ')], ['산출물', node.outputs.join(' · ')], ['완료 조건', node.acceptance]]) {
    dl.append(element('dt', label), element('dd', value));
  }
  container.append(dl);
}

export function renderTrace(container, trace, onInspect) {
  container.replaceChildren();
  if (!trace) {
    container.append(element('p', '이 작업에 연결된 결정 기록이 없습니다.', 'empty'));
    return;
  }
  const decision = trace.decision;
  container.append(element('span', '결정의 근거', 'eyebrow'), element('h2', decision.title));
  container.append(element('p', decision.rationale, 'decision-rationale'));
  const chain = element('ol', undefined, 'reason-chain');
  for (const issue of trace.issues) {
    const item = element('li');
    item.append(element('span', '쟁점', 'step-label'));
    const button = element('button', issue.question, 'text-link');
    button.type = 'button';
    button.addEventListener('click', () => onInspect('issue', issue.id));
    item.append(button, element('p', `${issue.raised_by} · ${issue.impact}`, 'secondary'));
    chain.append(item);
  }
  const responseItem = element('li');
  responseItem.append(element('span', '의견 교환', 'step-label'));
  for (const response of trace.responses) {
    const button = element('button', `${response.role_label} · ${response.stance_label}`, 'response-button');
    button.type = 'button';
    button.addEventListener('click', () => onInspect('response', response.id));
    responseItem.append(button);
  }
  chain.append(responseItem);
  const final = element('li');
  final.append(element('span', '결정', 'step-label'), element('p', decision.rationale));
  if (decision.dissent?.length) final.append(element('p', `남은 이견: ${decision.dissent.join(' ')}`, 'limitation'));
  chain.append(final);
  container.append(chain);
  const sources = element('div', undefined, 'source-buttons');
  for (const artifact of trace.artifacts) {
    const button = element('button', `${artifact.id} · ${artifact.title}`, 'source-button');
    button.type = 'button';
    button.addEventListener('click', () => onInspect('artifact', artifact.id));
    sources.append(button);
  }
  container.append(element('h3', '사용한 근거'), sources);
  if (trace.missing.length) {
    const warning = element('p', `연결된 기록을 찾을 수 없음: ${trace.missing.join(', ')}`, 'warning');
    warning.setAttribute('role', 'status');
    container.append(warning);
  }
}

export function renderComparison(container, comparison) {
  container.replaceChildren();
  if (!comparison) {
    container.append(element('p', '비교할 가설 버전을 찾을 수 없습니다.', 'empty'));
    return;
  }
  container.append(element('h3', '가설은 어떻게 바뀌었나'));
  const versions = element('div', undefined, 'versions');
  for (const [label, hypothesis] of [['처음 제안', comparison.before], ['검토 후 수정', comparison.after]]) {
    const section = element('section');
    section.append(element('span', `${label} · v${hypothesis.revision}`, 'step-label'), element('p', hypothesis.statement));
    versions.append(section);
  }
  container.append(versions, element('p', comparison.after.change_reason, 'change-reason'));
}

export function renderInspection(container, view, kind, id) {
  container.replaceChildren();
  const collection = {issue:'issues', response:'responses', artifact:'artifacts'}[kind];
  const item = view[collection]?.find(record => record.id === id);
  if (!item) {
    container.append(element('p', '이 기록은 현재 버전에 없습니다.', 'empty'));
    return;
  }
  const label = {issue:'쟁점 원문', response:'에이전트 응답', artifact:'근거 자료'}[kind];
  container.append(element('span', `${label} · ${id}`, 'eyebrow'));
  container.append(element('h3', item.question ?? item.role_label ?? item.title));
  container.append(element('p', item.rationale ?? item.content ?? item.impact, 'record-content'));
  if (item.resolution_condition) container.append(element('p', `해소 조건: ${item.resolution_condition}`, 'secondary'));
  if (item.locator) container.append(element('p', `원문 위치: ${item.locator}`, 'secondary'));
  if (item.access_level) container.append(element('p', `접근 수준: ${item.access_level}`, 'secondary'));
  if (item.assignment_id) container.append(element('p', `배정: ${item.assignment_id} · 이 시안은 실제 실행 기록이 아닙니다.`, 'secondary'));
}
