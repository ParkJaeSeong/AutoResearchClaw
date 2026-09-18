import {element,badge} from './detail.js';
const same=(a,b)=>a?.artifact_id===b?.artifact_id&&a?.sha256===b?.sha256;
export function currentDecisions(view){
  const rows=view.external_decisions??[];
  // Leaves of explicit predecessor chains. Do not invent chronology from IDs.
  return rows.filter(row=>!rows.some(other=>same(other.record.prior_ref,row.ref)));
}
function link(text,hash){const a=element('a',text,'action-link');a.href=hash;return a;}
export function renderOverview(root,view){
  const heading=element('div',undefined,'section-heading');heading.append(element('h2','연구의 현재 판단'),element('p','결론을 내린 이유와 검토 대화를 확인하세요.','muted'));root.append(heading);
  const rows=currentDecisions(view);
  if(!rows.length)root.append(element('p','아직 연구 방향을 결정한 기록이 없습니다. 단계별 내용과 에이전트 의견을 먼저 확인하세요.','card empty'));
  for(const {record:r} of rows){
    const card=element('article',undefined,'card decision-summary');card.append(element('p','연구 판단','eyebrow'),element('h3',r.title),badge(r.review_status==='council_final'?'에이전트 검토가 담긴 결정':'조정자가 작성한 결정'),element('p',r.conclusion,'prose'));
    const actions=element('div',undefined,'summary-actions');actions.append(link('판단 기록 보기',`#atlas-decision-${r.id}`),...(r.review_ref?[link('검토 대화와 근거 보기',`#atlas-review-${r.review_ref.artifact_id}`)]:[]));card.insertBefore(actions,card.children[3]);
    if(r.limitations?.length){const limits=element('details',undefined,'decision-limits');limits.dataset.key=`summary-limits:${r.id}`;limits.append(element('summary',`해석의 한계 ${r.limitations.length}가지`));const list=element('ul');for(const text of r.limitations)list.append(element('li',text));limits.append(list);card.append(element('p',r.limitations[0],'muted'),limits);}
    const nextStart=r.rationale?.indexOf('다음 작업은')??-1;
    if(nextStart>=0){const next=element('div',undefined,'discovery-latest');next.append(element('strong','다음 작업 · 저장된 결정에서 발췌'),element('p',r.rationale.slice(nextStart),'prose'));card.append(next);}
    const reason=element('details');reason.dataset.key=`summary-reason:${r.id}`;reason.append(element('summary','판단 이유와 다음 작업'),element('p',r.rationale,'prose'));card.append(reason);
    root.append(card);
  }
  const follow=element('section',undefined,'card');follow.append(element('h2','실험 착수 전 확인'));
  const prep=(view.m1_preparations??[]).filter(p=>!p.superseded);
  if(!prep.length)follow.append(element('p','아직 실험 준비 기록이 없습니다.','muted'));
  for(const entry of prep){follow.append(element('p',entry.current&&entry.preparation_ready?'항목별 준비 근거가 있습니다. 최종 검토와 인계 조건도 확인하세요.':'설계 초안은 실제 실험 준비와 따로 확인해야 합니다. 아직 준비가 끝났는지 확인하지 못한 항목이 있습니다.','prose'),link('항목별 준비 상태 보기',`#atlas-preparation-${entry.record.id}`));}
  follow.append(link('단계별 내용과 대화 보기','#workflow'));root.append(follow);
}
