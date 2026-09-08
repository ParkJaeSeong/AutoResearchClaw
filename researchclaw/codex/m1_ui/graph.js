export function visibleEdges(view, selectedId) {
  return view.edges.filter(edge => edge.kind !== 'return' || edge.from === selectedId);
}

const STATUS = {completed:'완료', current:'검토 중', pending:'진행 전', needs_revision:'수정 필요', awaiting_user:'사용자 결정 대기'};

export function renderGraph(container, view, selectedId, onSelect) {
  container.replaceChildren();
  const list = document.createElement('ol');
  list.className = 'node-list';
  list.setAttribute('aria-label', 'M1 작업 노드');
  view.nodes.forEach((node, index) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `node-button ${node.id === selectedId ? 'selected' : ''}`;
    button.dataset.nodeId = node.id;
    button.setAttribute('aria-pressed', String(node.id === selectedId));
    const number = document.createElement('span');
    number.className = `node-number ${node.status === 'completed' ? 'done' : ''}`;
    number.textContent = String(index + 1).padStart(2, '0');
    const name = document.createElement('span');
    name.className = 'node-name';
    name.textContent = node.title;
    const status = document.createElement('span');
    status.className = 'node-status';
    status.textContent = STATUS[node.status] ?? node.status;
    button.append(number, name, status);
    button.addEventListener('click', () => onSelect(node.id));
    item.append(button);
    list.append(item);
  });
  container.append(list);
  const returns = visibleEdges(view, selectedId).filter(edge => edge.kind === 'return');
  if (returns.length) {
    const title = document.createElement('h3');
    title.textContent = '이 작업에서 돌아간 경로';
    container.append(title);
    for (const edge of returns) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'return-link';
      const target = view.nodes.find(node => node.id === edge.to);
      button.textContent = `↶ ${target?.title ?? edge.to} · ${edge.label}`;
      button.addEventListener('click', () => onSelect(edge.to));
      container.append(button);
    }
  }
}
