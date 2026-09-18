import {projectFetch,projectId,readProjectState,saveProjectState} from './project.js';
import {element,button} from './detail.js';

function reviewable(row) {
  return row && ['finished','failed'].includes(row.execution_status) && row.conclusion && row.review_required===true && row.review_status==='pending' && !row.review;
}

// This controller outlives the rendered cards; drafts and uncertain commands belong
// to an episode, not a DOM node or whichever HEAD is currently on screen.
export function createEpisodeReviewController({getContext,request=(...args)=>projectFetch(...args),commandId=()=>crypto.randomUUID(),onRefresh=async()=>{},onChange=()=>{}}) {
  const states=new Map(projectId()?(readProjectState().episodeReviews??[]):[]);
  for(const s of states.values())if(s.phase==='pending'){s.phase='uncertain';s.message='저장 결과를 확인하지 못했습니다. 같은 요청으로 다시 확인하세요.';}
  const persist=()=>projectId()&&saveProjectState({episodeReviews:[...states]});
  function state(id) {
    if(!states.has(id))states.set(id,{draft:'',phase:'editing',message:'',payload:null});
    return states.get(id);
  }
  function historical(){return Boolean(getContext().historical);}
  function current(id){return getContext().view?.work_episodes?.find(row=>row.id===id);}
  async function refresh(s,saved) {
    try{await onRefresh();}
    catch{s.message=saved?'검토를 저장했습니다. 최신 기록을 불러오지 못했습니다. 새로고침으로 확인해 주세요.':'요청이 거절됐습니다. 의견은 그대로 있습니다. 최신 기록을 불러오지 못했으니 새로고침 후 다시 검토해 주세요.';}
    if(!saved)s.phase='editing';
    persist();onChange();
  }
  async function send(id) {
    const s=state(id);s.phase='pending';s.message='검토를 저장하고 있습니다.';persist();onChange();
    let response,result;
    try {
      response=await request('/api/episodes/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s.payload)});
      if(response.status>=400 && response.status<500){
        s.phase='refreshing';s.payload=null;s.message='요청이 거절됐습니다. 의견은 그대로 있습니다. 최신 기록을 확인한 뒤 다시 검토해 주세요.';persist();onChange();
        await refresh(s,false);return;
      }
      if(!response.ok)throw Error('Unconfirmed response');
      result=await response.json();
      if(typeof result?.head_id!=='string' || !result.head_id || result.episode_id!==id || !['continued','revision_requested'].includes(result.review_status) || !result.review)throw Error('Unconfirmed response');
    }catch{
      s.phase='uncertain';s.message='저장 결과를 확인하지 못했습니다. 입력한 의견은 보존했습니다. 같은 요청으로 다시 확인해 주세요.';persist();onChange();return;
    }
    // A later read failure cannot undo a confirmed mutation or make it retryable.
    s.phase='saved';s.payload=null;s.message='검토를 저장했습니다.';persist();onChange();await refresh(s,true);
  }
  return {state,historical,
    edit(id,value){const s=state(id);if(!historical() && s.phase==='editing'){s.draft=value;persist();}},
    async submit(id,decision){
      const s=state(id),{view}=getContext();
      if(historical() || s.phase!=='editing' || !reviewable(current(id)) || !['continue','revise'].includes(decision))return;
      if(!s.draft.trim()){s.message='검토 의견을 입력해 주세요.';persist();onChange();return;}
      s.payload=Object.freeze({id,decision,feedback:s.draft,expected_head:view.head_id,command_id:commandId()});
      return send(id);
    },
    async retry(id){if(historical() || state(id).phase!=='uncertain')return;return send(id);}
  };
}

export function renderEpisodeReview(root,row,controller) {
  if(!controller)return;
  const s=controller.state(row.id),eligible=reviewable(row),historical=controller.historical();
  if(!eligible && !s.message && !s.draft)return;
  const section=element('section',undefined,'episode-review');section.setAttribute('aria-label','개발 검토');
  section.append(element('h4','개발 검토'));
  if(eligible || s.draft){
    section.append(element('p','후속 작업의 진행 여부에 대한 의견입니다. 실제 실험 실행 권한은 별도로 확인합니다.','muted'));
    const label=element('label',undefined,'control');label.append(element('span','검토 의견'));
    const input=element('textarea');input.dataset.key=`episode-feedback:${row.id}`;input.rows=3;input.value=s.draft;
    input.disabled=historical || !eligible || s.phase!=='editing';input.addEventListener('input',()=>controller.edit(row.id,input.value));label.append(input);section.append(label);
    if(eligible){const actions=element('div',undefined,'episode-review-actions');
      for(const [decision,text] of [['continue','계속 진행'],['revise','수정 요청']]){
        const action=button(text,()=>controller.submit(row.id,decision),`episode-${decision}:${row.id}`);action.disabled=historical || s.phase!=='editing';actions.append(action);
      }
      section.append(actions);
    }
  }
  if(historical)section.append(element('p','과거 기록에서는 검토를 저장할 수 없습니다. 최신 기록으로 돌아가 주세요.','muted'));
  if(s.message){const message=element('p',s.message,s.phase==='uncertain'?'warning':'muted');message.setAttribute('role','status');message.setAttribute('aria-live','polite');section.append(message);}
  if(s.phase==='uncertain'){
    const retry=button('같은 요청 다시 확인',()=>controller.retry(row.id),`episode-retry:${row.id}`);retry.disabled=historical;section.append(retry);
  }
  root.append(section);
}
