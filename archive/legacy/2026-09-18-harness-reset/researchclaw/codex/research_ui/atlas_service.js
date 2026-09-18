import {renderKnowledge} from './knowledge_status.js';
import {projectId,readProjectState,saveProjectState} from './project.js';
import {element,button} from './detail.js';
const labels={queued:'답변 대기 중',running:'Atlas가 자료를 확인하는 중',completed:'답변 작성 완료',partial:'일부 답변 도착',failed:'작업 실패 · 기록 확인 필요',interrupted:'작업 중단 · 기록 보존됨'};
const messages={atlas_not_configured:'아직 Atlas 연결 설정이 없습니다.',atlas_instance_mismatch:'연결된 자료실이 바뀌었습니다. 기존 기록은 그대로 남아 있습니다.',atlas_transport_unavailable:'연결을 확인하지 못했습니다. 같은 요청으로 다시 확인할 수 있습니다.',atlas_qa_not_ready:'아직 가져올 답변이 없습니다. 진행 상황을 확인하세요.',atlas_raw_invalid:'답변 원본을 검증하지 못해 등록하지 않았습니다.'};
export function createAtlasService(root,{request,getCurrentView,onRefresh}={}){
  const saved=projectId()?(readProjectState().atlasService??{}):{};
  let historical=false,busy=false,binding=null,pending=saved.pending??null,previous=saved.previous??null;
  const persist=()=>projectId()&&saveProjectState({atlasService:{pending,previous}});
  root.className='atlas-intake';
  const status=element('p','Atlas에 연결해 질문하고 답변을 가져옵니다.','muted');status.setAttribute('aria-live','polite');
  const projects=element('select');projects.dataset.key='atlas-service-project';
  const projectLabel=element('label','Atlas 자료실 프로젝트','atlas-control');projectLabel.append(projects);
  const reason=element('input');reason.value='현재 연구의 문헌과 근거를 검토합니다.';reason.dataset.key='atlas-service-reason';
  const reasonLabel=element('label','이 프로젝트를 사용하는 이유','atlas-control');reasonLabel.append(reason);
  const question=element('textarea');question.dataset.key='atlas-service-question';if(pending)question.value=pending.question;
  const questionLabel=element('label','Atlas에 물어볼 질문','atlas-control');questionLabel.append(question);
  const context=element('p','','muted'),rows=element('section'),knowledge=element('section'),controls=[];
  function gate(){ask.textContent=pending?'접수 다시 확인':'질문 보내기';for(const b of controls)b.disabled=historical||busy||(Boolean(pending)&&b.dataset.followup==='true');question.disabled=historical||busy||Boolean(pending);projects.disabled=historical||busy;}
  async function run(fn){if(historical||busy)return;busy=true;gate();try{await fn();}catch(e){status.textContent=messages[e.message]??'요청을 확인하지 못했습니다. 기록을 유지한 채 다시 확인하세요.';}finally{busy=false;gate();}}
  async function call(action,payload={}){return request('/api/atlas/service-'+action,payload);}
  function draw(data){renderKnowledge(knowledge,data.knowledge_jobs??[]);binding=data.binding??binding;rows.replaceChildren();if(binding)status.textContent=`연결된 프로젝트: ${binding.title}`;
    for(const row of data.requests??[]){const card=element('article',undefined,'callout');card.append(element('h4',row.question),element('p',row.received?'답변을 연구에 가져왔습니다. 사용 범위를 검토하세요.':labels[row.job?.status]??'접수 결과 확인 필요'));
      if(row.job?.detail?.answer){const d=element('details');d.append(element('summary','Atlas 답변 읽기'),element('p',row.job.detail.answer,'prose'));card.append(d);}
      if(row.supporting?.some(s=>!s.received))card.append(element('p','일부 참고 원문을 받지 못했습니다. 근거 상세에서 확인하세요.'));
      const check=button('진행 상황 확인',()=>run(async()=>{await call('poll',{key:row.request_key});await refresh();}));
      const receive=button('답변과 근거 가져오기',()=>run(async()=>{await call('receive',{key:row.request_key,expected_head:getCurrentView().head_id});await refresh();await onRefresh?.();}));
      const follow=button('이어서 질문하기',()=>{if(historical||busy||pending)return;previous=row.request_key;pending=null;question.value=`이전 질문: ${row.question}\n이전 Atlas QA: ${row.qa_ref?.qa_id??row.job?.detail?.qa_ref?.qa_id??'아직 수신 전'}\n이번에 확인할 내용: `;context.textContent='이전 질문과 이번 확인 내용을 함께 Atlas에 보냅니다.';persist();question.dispatchEvent?.(new Event('input',{bubbles:true}));gate();});
      follow.dataset.followup='true';
      const support=button('참고 원문 다시 받기',()=>run(async()=>{await call('supporting',{key:row.request_key});await refresh();}));
      card.append(check,receive,follow,support);controls.push(check,receive,follow,support);
      const detail=element('details');detail.append(element('summary','요청과 근거 기록'),element('pre',JSON.stringify({request_key:row.request_key,project:row.binding?.title,receipt:row.job?.receipt_ref,qa:row.qa_ref,supporting:row.supporting,error:row.error},null,2)));card.append(detail);rows.append(card);
    }gate();
  }
  async function refresh(){draw(await call('status'));}
  const connect=button('Atlas 연결 확인',()=>run(async()=>{const data=await call('connect');projects.replaceChildren();for(const p of data.projects){const option=element('option',p.title);option.value=p.id;projects.append(option);}projects.value=data.binding?.project??data.projects[0]?.id??'';draw(data);if(!binding)status.textContent='Atlas에 연결됐습니다. 사용할 프로젝트를 선택하세요.';}),'atlas-service-connect');
  const bind=button('이 프로젝트 연결',()=>run(async()=>{binding=await call('bind',{project:projects.value,reason:reason.value});await refresh();}),'atlas-service-bind');
  const ask=button('질문 보내기',()=>run(async()=>{
    if(!question.value.trim()){status.textContent='질문을 입력하세요.';return;}
    pending??={key:globalThis.crypto?.randomUUID?.()??`pilot-${Date.now()}-${Math.random()}`,question:question.value,question_id:globalThis.crypto?.randomUUID?.()??`question-${Date.now()}`,previous};
    persist();await call('ask',pending);pending=null;previous=null;persist();question.value='';question.dispatchEvent?.(new Event('input',{bubbles:true}));
    if(projectId()){const drafts=readProjectState().drafts??{};drafts['atlas-service-question']='';saveProjectState({drafts});}context.textContent='';await refresh();
  }),'atlas-service-ask');
  controls.push(connect,bind,ask);
  root.append(element('h3','Atlas에 질문하기'),status,connect,projectLabel,reasonLabel,bind,context,questionLabel,ask,knowledge,rows);
  return {setHistorical(v){historical=Boolean(v);knowledge.hidden=historical;gate();},refresh:()=>run(refresh)};
}
