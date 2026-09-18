import {element,badge,dialogueSummary} from './detail.js';
import {renderEpisodeReview} from './episode_review.js';

// Sequence is assigned when work starts, never when it finishes.
export function orderedEpisodes(view) {
  return [...(view.work_episodes??[])].sort((a,b)=>b.sequence-a.sequence);
}
const EXECUTION={running:'작업 중으로 기록됨',finished:'작업 종료',failed:'작업 실패'};
const REVIEW={pending:'개발 검토 대기',continued:'후속 진행 허용',revision_requested:'수정 요청',not_required:'자율 진행'};
function paragraph(root,title,text) {
  root.append(element('h4',title),element('p',text||'아직 기록하지 않았습니다.','prose'));
}
function notes(root,rows,empty,keyPrefix) {
  if(!rows.length){root.append(element('p',empty,'muted'));return;}
  const list=element('ol',undefined,'episode-notes');
  for(const [index,row] of rows.entries()){
    const item=element('li');
    if(row.kind==='dialogue'){
      const disclosure=element('details',undefined,'statement');disclosure.dataset.key=`${keyPrefix}:${index}`;
      disclosure.append(dialogueSummary(`에이전트 의견 · ${row.author}`,row.text),element('p',row.text,'prose council-paragraph'));item.append(disclosure);
    }else item.append(element('p',`${{tool:'도구 사용 보고',output:'산출물 기록'}[row.kind]} · ${row.author}`,'muted'),element('p',row.text,'prose'));
    list.append(item);
  }
  root.append(list);
}
function renderFollowups(root,view,episodeId) {
  for(const plan of view.work_followups??[]){
    if(plan.source_episode_id!==episodeId)continue;
    const section=element('details',undefined,'episode-followup');section.dataset.key=`followup:${plan.id}`;
    const summary=element('summary');summary.append(element('strong',`후속 작업 계획 · ${plan.title}`),
      badge(plan.status==='blocked'?'선행 작업 확인 필요':'계획됨 · 실행 전',plan.status==='blocked'?'pending':''));
    section.append(summary,element('p',plan.purpose,'prose'));
    if(plan.kind==='revision')section.append(element('p','이 회차의 결과를 다시 검토할 계획입니다.','muted'));
    if(plan.status==='blocked')section.append(element('p','이전 작업이 실패해 후속 실행 전에 원인을 확인해야 합니다.','pending'));
    root.append(section);
  }
}
export function renderEpisodes(root,view,reviewController=null) {
  const section=element('section',undefined,'episode-stack');section.setAttribute('aria-label','작업 회차');
  section.append(element('h2','연구가 진행된 과정'),element('p','최근에 시작한 작업이 위에 쌓입니다. 작업을 펼치면 판단과 진행 기록을 볼 수 있습니다.','muted'));
  const rows=orderedEpisodes(view);
  if(!rows.length)section.append(element('p','작업 회차가 아직 없습니다. 이전 단계 기록은 아래에서 볼 수 있습니다.','empty'));
  const byId=new Map(rows.map(row=>[row.id,row]));
  const title=id=>{const row=byId.get(id);return row?`${String(row.sequence).padStart(3,'0')} · ${row.title}`:'연결된 이전 작업';};
  for(const row of rows){
    const card=element('details',undefined,'card episode-card');card.dataset.key=`episode:${row.id}`;
    const summary=element('summary');
    summary.append(element('span',`${String(row.sequence).padStart(3,'0')} · ${row.stage}`,'episode-stage'),
      element('strong',row.title,'episode-title'));
    const statuses=element('span',undefined,'episode-statuses');
    statuses.append(badge(EXECUTION[row.execution_status]??'작업 상태 미확인'));
    // A running episode has no concluded result for the human to review yet.
    if(row.conclusion)statuses.append(badge(REVIEW[row.review_status]??'검토 상태 미확인',row.review_status==='pending'||row.review_status==='revision_requested'?'pending':''));
    summary.append(statuses);card.append(summary);
    const body=element('div',undefined,'episode-body');
    paragraph(body,'이번 작업의 목적',row.purpose);
    if(row.conclusion){
      paragraph(body,'결과 요약',row.conclusion.judgment);
      paragraph(body,'다음 행동',row.conclusion.next_action);
      paragraph(body,'이 행동을 선택한 이유',row.conclusion.next_reason);
      paragraph(body,'남은 문제',row.conclusion.remaining);
    }else body.append(element('p','결과와 다음 행동이 아직 기록되지 않았습니다.','muted'));
    if(row.conclusion && row.review_required && row.review_status==='pending'){
      paragraph(body,'사용자 확인 필요','개발 검토가 요청되어 있습니다. 이 회차의 결과를 확인하고 아래에서 의견을 남겨 주세요.');
    }
    if(row.review){paragraph(body,`개발 검토 · ${row.review.reviewer}`,row.review.feedback);}
    renderEpisodeReview(body,row,reviewController);
    renderFollowups(body,view,row.id);
    const history=element('details',undefined,'episode-history');history.dataset.key=`episode-history:${row.id}`;
    history.append(element('summary','대화·도구 사용·이전 작업 보기'));
    if(row.return_to)paragraph(history,`다시 살펴보는 작업: ${title(row.return_to)}`,row.return_reason);
    if(row.depends_on.length)paragraph(history,'이 작업의 바탕',row.depends_on.map(title).join('\n'));
    history.append(element('p','담당자가 남긴 의견과 도구 사용 보고입니다.','muted'));
    notes(history,row.notes.filter(note=>note.kind!=='output'),'공개된 진행 기록이 아직 없습니다.',`episode-dialogue:${row.id}`);
    body.append(history);
    const outputs=element('details',undefined,'episode-outputs');outputs.dataset.key=`episode-outputs:${row.id}`;
    outputs.append(element('summary','산출물 보기'));notes(outputs,row.notes.filter(note=>note.kind==='output'),'등록한 산출물이 아직 없습니다.',`episode-output:${row.id}`);
    body.append(outputs);
    card.append(body);section.append(card);
  }
  root.append(section);
}
