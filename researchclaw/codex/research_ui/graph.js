import {element,button,badge,label} from './detail.js';
export function renderResearchGraph(root,view,selection,onSelect=()=>{}) {
  root.replaceChildren();root.append(element('h2','M1 작업 지도'),element('p','01–09는 M1 내부 작업 번호입니다. 각 단계의 구조 조건 충족·협의 제출은 M1 전체 완료를 뜻하지 않습니다. 원문 수집·근거 추출·종합·가설·최종 검토와 인계 조건을 별도로 확인합니다.','muted'),element('p','이 화면은 기록 조회용입니다. 다음 작업을 자동 실행하지 않습니다. 실제 등록·이동은 아래 이력에 표시합니다.','muted'));
  const list=element('ol',undefined,'node-map');for(const [i,node] of view.nodes.entries()){
    const item=element('li'),b=button('',()=>onSelect(node.id),`node:${node.id}`);b.className='node-choice';b.setAttribute('aria-pressed',String(selection.nodeId===node.id));
    b.append(element('span',String(i+1).padStart(2,'0'),'step-number'),element('strong',node.label),badge(label(node.status),node.status==='ready'?'ok':node.status==='not_started'?'neutral':'pending'));item.append(b);list.append(item);
  }root.append(list);
  const history=element('details');history.dataset.key='moves';history.append(element('summary',`실제 등록·이동 ${view.transitions.length}건`));
  const moves=element('ol',undefined,'move-list');for(const move of view.transitions){const item=element('li');
    item.append(button(`${move.from_node?label(move.from_node):'시작'} → ${label(move.to_node)}${move.from_node===move.to_node?' · 같은 단계 개정':''}`,()=>onSelect(move.to_node,move.revision_id),`move:${move.revision_id}`),element('small',`HEAD ${move.head_id.slice(0,12)}`));moves.append(item);}
  history.append(moves);root.append(history);
}
