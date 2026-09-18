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
    const button = element('button', `${response.role_label ?? ROLE_LABELS[response.role_id] ?? response.assignment_id} · ${response.stance_label ?? response.stance}`, 'response-button');
    button.type = 'button';
    button.addEventListener('click', () => onInspect('response', response.id));
    responseItem.append(button);
  }
  chain.append(responseItem);
  const final = element('li');
  final.append(element('span', '결정', 'step-label'), element('p', decision.rationale));
  if (decision.dissent?.length) {
    const dissent = element('details', undefined, 'limitation');
    dissent.dataset.disclosureId = `dissent:${decision.id}`;
    dissent.append(element('summary', `남은 이견 ${decision.dissent.length}개`));
    for (const item of decision.dissent) dissent.append(element('p', typeof item === 'string' ? item : `${item.role_id} · ${narrative(item.rationale)}`, 'record-content'));
    final.append(dissent);
  }
  chain.append(final);
  container.append(chain);
  if (decision.hypothesis_dispositions?.length) {
    container.append(element('h3', '후보별 처리 이유'));
    const dispositionLabels = {selected:'선택', deferred:'보류', rejected:'기각', revise:'수정'};
    for (const item of decision.hypothesis_dispositions) {
      const candidate = element('section', undefined, 'candidate-disposition');
      candidate.append(element('strong', `${item.hypothesis_ref.id} · v${item.hypothesis_ref.revision} · ${dispositionLabels[item.disposition] ?? item.disposition}`), element('p', item.rationale));
      container.append(candidate);
    }
  }
  const sources = element('div', undefined, 'source-buttons');
  for (const artifact of trace.artifacts) {
    const button = element('button', `${artifact.title ?? artifact.logical_path ?? artifact.id}`, 'source-button');
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
  container.append(element('h3', `${comparison.before.hypothesis_id} · 가설은 어떻게 바뀌었나`));
  const versions = element('div', undefined, 'versions');
  for (const [label, hypothesis] of [['처음 제안', comparison.before], ['검토 후 수정', comparison.after]]) {
    const section = element('section');
    section.append(element('span', `${label} · v${hypothesis.revision}`, 'step-label'), element('p', hypothesis.statement));
    versions.append(section);
  }
  container.append(versions, element('p', comparison.after.change_reason, 'change-reason'));
}

export function renderInspection(container, view, kind, id, sourceLink = () => null) {
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
  if (kind === 'issue') {
    const severity = {blocking:'진행 차단', major:'주요 쟁점', minor:'보완 쟁점'}[item.severity] ?? item.severity;
    const status = {open:'미해소', resolved:'해소 확인'}[item.status] ?? item.status;
    if (severity || status) container.append(element('p', [severity, status].filter(Boolean).join(' · '), 'limitation'));
  }
  if (item.resolution_condition) container.append(element('p', `해결됐다고 판단할 기준: ${item.resolution_condition}`, 'secondary'));
  if (item.content_truncated) container.append(element('p', `미리보기 · 전체 ${item.content_length}자 중 일부입니다. 전체 내용은 원문 보기에서 확인하세요.`, 'secondary'));
  if (item.content_status === 'non_utf8') container.append(element('p', '텍스트로 표시할 수 없는 등록 자료입니다.', 'secondary'));
  if (item.locator) container.append(element('p', `원문 위치: ${item.locator}`, 'secondary'));
  if (item.access_level) container.append(element('p', `접근 수준: ${item.access_level}`, 'secondary'));
  const external = sourceLink(item.source_url ?? item.url);
  if (external) {
    const link = element('a', '출처 열기', 'artifact-link');
    link.href = external; link.target = '_blank'; link.rel = 'noopener noreferrer';
    container.append(link);
  }
  const registeredId = item.source_artifact_id ?? item.id;
  const registered = view.artifacts.find(ref => ref.id === registeredId && ref.sha256 && ref.logical_path);
  if (kind === 'artifact' && registered) {
    const link = element('a', '등록된 원문 보기', 'artifact-link');
    link.href = `/api/artifacts/${encodeURIComponent(registeredId)}`;
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    container.append(link);
  }
  if (item.assignment_id) {
    const provenance = view.data_origin === 'demo' ? ' · 이 시안은 실제 실행 기록이 아닙니다.' : ' · 실행 확인 범위는 해당 배정 기록에서 확인하세요.';
    container.append(element('p', `배정: ${item.assignment_id}${provenance}`, 'secondary'));
  }
}

export const SESSION_STATUS = {collecting_initials:'최초 의견 대기', collecting_responses:'의견 교환 중', collecting_final_positions:'최종 입장 대기', final_positions_complete:'다음 행동 결정 대기', decided:'다음 행동 결정됨'};
const ROLE_LABELS = {domain:'분야 연구자', methodology:'방법론 연구자', critical_reproducibility:'비판·재현성 검토자'};
const RECOMMENDATIONS = {ready:'인계 가능', ready_with_limits:'한계와 함께 인계 가능', revise:'수정 필요', defer:'판단 보류'};
const narrative = value => Array.isArray(value) ? value.join('\n\n') : value ?? '';

export function renderCouncil(container, sessions, onInspect) {
  container.replaceChildren();
  if (!sessions.length) return;
  container.append(element('span', '에이전트 협의', 'eyebrow'), element('h2', '의견이 어떻게 모였나'));
  for (const session of sessions) {
    const group = element('details', undefined, 'session-record');
    group.dataset.sessionId = session.id;
    group.dataset.disclosureId = `session:${session.id}`;
    group.open = sessions.length === 1;
    group.append(element('summary', `${session.title ?? '검토 회차'} · ${SESSION_STATUS[session.status] ?? session.status}`));
    group.append(element('p', `기록 ID: ${session.id}`, 'secondary'));
    group.append(element('p', session.content_origin === 'synthetic'
      ? '합성 자료에 대한 검토입니다. 배정의 실행 출처는 선언 기록이며 호스트 인증과 구분됩니다.'
      : '등록된 배정·제출 기록입니다. 실행 출처의 검증 범위는 배정 기록을 확인하세요.', 'secondary'));
    if (session.assignment_history?.length) {
      const history = element('details');
      history.dataset.disclosureId = `assignments:${session.id}`;
      history.append(element('summary', '배정 변경 기록'));
      for (const record of session.assignment_history) history.append(element('p', `${record.assignment?.id ?? ''} → ${record.replacement_assignment_id} · ${record.reason}`, 'record-content'));
      group.append(history);
    }
    for (const assignment of session.assignments ?? []) {
      const initials = session.disclosed_initials ?? [];
      const initial = initials.find(record => record.assignment_id === assignment.id);
      const response = (session.disclosed_responses ?? []).find(record => record.assignment_id === assignment.id);
      const final = (session.disclosed_final_positions ?? []).find(record => record.assignment_id === assignment.id);
      const role = element('section', undefined, 'role-record');
      role.append(element('h3', ROLE_LABELS[assignment.role_id] ?? assignment.role_id));
      role.append(element('p', `${assignment.id} · ${assignment.provenance_status ?? 'declared_only'}`, 'secondary'));
      if (!initial) {
        const state = {submitted:'제출 완료 · 전체 공개 대기', waiting:'제출 대기', failed:'검토자 배정 실패 · 다른 검토자 필요'}[assignment.initial_status] ?? '최초 의견 공개 대기';
        role.append(element('p', `${state} · 필수 역할의 제출이 모이면 공개됩니다.`, 'empty'));
      }
      for (const [label, record] of [['최초 의견', initial], ['다른 의견을 읽은 뒤', response], ['최종 입장', final]]) {
        if (!record) continue;
        const entry = element('details', undefined, 'opinion-record');
        entry.dataset.disclosureId = `${session.id}:${assignment.id}:${label}`;
        entry.append(element('summary', label + (record.recommendation ? ` · ${RECOMMENDATIONS[record.recommendation] ?? record.recommendation}` : '')));
        entry.append(element('p', narrative(record.rationale), 'record-content'));
        if (record.change_rationale) entry.append(element('p', `의견을 바꾼 이유: ${record.change_rationale}`, 'change-reason'));
        for (const issue of record.open_issues ?? record.new_issues ?? []) {
          const button = element('button', `쟁점: ${issue.question}`, 'response-button');
          button.type = 'button'; button.addEventListener('click', () => onInspect('issue', issue.id)); entry.append(button);
        }
        for (const item of record.responses ?? []) {
          const button = element('button', `응답 · ${item.stance} · ${item.issue_id}`, 'response-button');
          button.type = 'button'; button.addEventListener('click', () => onInspect('response', item.id)); entry.append(button);
        }
        for (const item of record.issue_dispositions ?? []) {
          const disposition = element('details');
          disposition.dataset.disclosureId = `${session.id}:${assignment.id}:final:${item.issue_id}`;
          disposition.append(element('summary', `${item.issue_id} · ${item.status === 'resolved' ? '해소 확인' : '미해소'}`), element('p', item.rationale, 'record-content'));
          entry.append(disposition);
        }
        role.append(entry);
      }
      group.append(role);
    }
    container.append(group);
  }
}
