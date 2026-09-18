import {element} from './detail.js';
const updates={pending:'위키 반영 대기',running:'위키에 반영 중',persisted:'위키 반영 완료',unchanged:'추가할 내용 없음',partial:'일부 반영 · 확인 필요',blocked:'위키 반영 보류',failed:'위키 반영 실패',not_started:'위키 반영 전'};
export function knowledgeLabels(row){return {answer:row.stored_answer?'답변 수신 완료':row.answer_status==='ready'?'답변 가져오기 대기':'답변 준비 중',knowledge:updates[row.knowledge_status]??'위키 상태 확인 필요'};}
export function renderKnowledge(root,rows){
 const opened=new Set([...root.querySelectorAll('details[open]')].map(n=>n.dataset.key));
 root.replaceChildren();if(!rows.length)return;
 root.append(element('h3','Atlas 답변과 위키 반영'),element('p','저장된 처리 기록입니다. 연구 검토 결과는 해당 작업에서 확인하세요.','muted'));
 for(const row of rows){
  const labels=knowledgeLabels(row),details=element('details');details.dataset.key=row.request_key;details.open=opened.has(row.request_key);
  details.append(element('summary',row.question),element('p',`${labels.answer} · ${labels.knowledge}`));
  const list=element('ul');for(const stage of row.stages)list.append(element('li',`${stage.stage==='answer'?'답변':stage.stage==='package'?'원형 보존':'위키 반영'} · ${stage.attempt}차 기록`));
  details.append(list);root.append(details);
 }
}
