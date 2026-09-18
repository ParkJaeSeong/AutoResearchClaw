import {element,button} from './detail.js';
import {projectId,projectFetch,projectURL,readProjectState,saveProjectState,switchURL} from './project.js';
export const STAGE_GROUPS=[
  {id:'scope',title:'연구 범위와 질문',nodes:['scope','questions']},
  {id:'sources',title:'자료 탐색과 검토',nodes:['search','screen','collect','extract']},
  {id:'hypotheses',title:'근거 종합과 가설',nodes:['synthesize','hypothesize']},
  {id:'design',title:'실험 설계',nodes:['experiment-design','experiment_design']},
  {id:'readiness',title:'착수 준비·최종 정리',nodes:['readiness','review']},
];
// Exact legacy labels are display mappings, never new episode identities.
export const LEGACY_STAGES={'자료 확인':'sources','근거 검토':'hypotheses','근거 검토·설계 보완':'design','착수 준비':'readiness','착수 준비·기록 점검':'readiness','재검토 진행 기준':'readiness','M1 POC 마무리':'readiness','자료 탐색':'sources','자료 검토':'sources','실험 설계':'design','실험 설계와 실행 준비':'design','실행 준비':'readiness','M1 최종 검토':'readiness'};
export function episodeGroup(row){return STAGE_GROUPS.find(g=>g.nodes.includes(row.stage)||g.title===row.stage)?.id??LEGACY_STAGES[row.stage]??null;}
export function stageEpisodes(view,group){return (view.work_episodes??[]).filter(row=>episodeGroup(row)===group);}
export function renderStageNavigation(root,view,selection,onSelect){
  root.replaceChildren();
  for(const group of STAGE_GROUPS){
    const details=element('details',undefined,'stage-group');details.open=selection.stageGroup===group.id;
    const summary=element('summary',group.title);details.append(summary);
    summary.dataset.key=`stage:${group.id}`;
    summary.addEventListener('click',event=>{
      // Opening a group selects its records; clicking the open group still collapses it.
      if(!details.open || selection.stageGroup!==group.id){
        event.preventDefault();
        onSelect({stageGroup:group.id,nodeId:view.nodes.find(n=>group.nodes.includes(n.id))?.id??null});
      }
    });
    for(const node of view.nodes.filter(n=>group.nodes.includes(n.id))){const b=button(node.label,()=>onSelect({stageGroup:group.id,nodeId:node.id}),`stage-node:${node.id}`);b.setAttribute('aria-current',selection.nodeId===node.id?'step':'false');details.append(b);}
    root.append(details);
  }
}
export async function loadCatalog(){const response=await fetch('/api/projects',{cache:'no-store'});if(!response.ok)throw Error('프로젝트 목록을 불러오지 못했습니다.');return response.json();}
export function projectGroups(catalog){return {active:catalog.projects.filter(p=>p.archived!==true),archived:catalog.projects.filter(p=>p.archived===true)};}
export function preferredProject(catalog){const {active}=projectGroups(catalog);return active.find(p=>p.id===catalog.default_project_id)?.id??active[0]?.id??catalog.default_project_id;}
export function mountProjectPicker(catalog){
  const root=document.getElementById('project-picker');if(!root)return;document.body.classList.add('workspace-navigation');
  const label=element('label','프로젝트','control'),select=element('select');select.id='project-select';
  const groups=projectGroups(catalog),selectedId=projectId()??preferredProject(catalog);
  const selected=catalog.projects.find(p=>p.id===selectedId);
  for(const p of [...groups.active,...(selected?.archived===true?[selected]:[])]){const option=element('option',`${p.archived===true?'보관 · ':''}${p.name}`);option.value=p.id;select.append(option);}select.value=selectedId;
  function navigate(id){saveProjectState({hash:location.hash,head:new URL(location.href).searchParams.get('head')});location.assign(switchURL(location.href,id,readProjectState(id)));}
  select.addEventListener('change',()=>navigate(select.value));label.append(select);
  const archived=element('details',undefined,'archived-projects');archived.dataset.key='archived-projects';
  archived.append(element('summary',`보관한 프로젝트 · ${groups.archived.length}`));
  for(const p of groups.archived)archived.append(button(p.name,()=>navigate(p.id),`archived-project:${p.id}`));
  const archiveNotice=element('p','보관한 연구 기록입니다. 이전 자료와 판단을 확인할 수 있습니다.','muted');
  const form=element('form',undefined,'project-create');form.hidden=true;
  const nameLabel=element('label','프로젝트 이름','control'),name=element('input');name.required=true;name.maxLength=160;name.dataset.key='new-project-name';nameLabel.append(name);
  const topicLabel=element('label','연구 주제','control'),topic=element('textarea');topic.required=true;topic.maxLength=2000;topic.dataset.key='new-project-topic';topicLabel.append(topic);
  const submit=element('button','프로젝트 만들기');submit.type='submit';const cancel=button('닫기',()=>{form.hidden=true;create.focus();});cancel.type='button';const status=element('p','','muted');status.setAttribute('role','status');
  let pending=null;const draft=readProjectState().createDraft;if(draft){name.value=draft.name??'';topic.value=draft.topic??'';pending=draft.pending??null;}
  const save=()=>saveProjectState({createDraft:{name:name.value,topic:topic.value,pending}});form.addEventListener('input',save);
  form.addEventListener('submit',async event=>{event.preventDefault();if(!form.reportValidity())return;
    const payload={name:name.value.trim(),topic:topic.value.trim()};
    if(pending&&(pending.name!==payload.name||pending.topic!==payload.topic)){status.textContent='이전 생성 결과부터 다시 확인하세요. 입력은 보존했습니다.';return;}
    pending??={...payload,request_id:crypto.randomUUID()};save();submit.disabled=true;
    try{const response=await fetch('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending)});const data=await response.json();if(!response.ok){if(response.status>=400&&response.status<500){pending=null;save();}throw Error(data.message??data.error??'프로젝트를 만들지 못했습니다.');}saveProjectState({createDraft:null});navigate(data.project.id);}
    catch(error){status.textContent=`${error.message} 입력을 보존했습니다. 다시 눌러 생성 결과를 확인하세요.`;submit.textContent=pending?'생성 결과 다시 확인':'프로젝트 만들기';}finally{submit.disabled=false;}
  });
  form.append(nameLabel,topicLabel,submit,cancel,status);const create=button('+ 새 프로젝트',()=>{form.hidden=!form.hidden;if(!form.hidden)name.focus();},'project-create-toggle');root.replaceChildren(label,...(selected?.archived===true?[archiveNotice]:[]),...(catalog.management_enabled===false?[]:[create,form]),...(groups.archived.length?[archived]:[]));
}
export async function loadMaterials(root){
  root.replaceChildren(element('h2','프로젝트 자료'),element('p','프로젝트에 보관한 문서와 결과 파일입니다. Atlas 자료실 검색은 Atlas 연결에서 확인하세요.','muted'));
  try{const response=await projectFetch('/api/project-files',{cache:'no-store'});if(!response.ok)throw Error('자료 목록을 불러오지 못했습니다.');const data=await response.json();
    root.append(element('p',`저장 위치: ${data.storage_path}`,'storage-path'));
    if(!data.files.length)root.append(element('p','아직 보관한 파일이 없습니다.','empty'));
    const list=element('ul',undefined,'material-files'),searchLabel=element('label','파일 이름이나 경로 검색','control'),search=element('input');search.type='search';searchLabel.append(search);const count=element('p',`${data.files.length}개 파일`,'muted');search.addEventListener('input',()=>{let shown=0;for(const li of list.children){li.hidden=!li.dataset.path.toLowerCase().includes(search.value.toLowerCase());if(!li.hidden)shown++;}count.textContent=`전체 ${data.files.length}개 중 ${shown}개 파일`;});root.append(searchLabel,count);for(const file of data.files){const li=element('li'),link=element('a',file.path.split('/').at(-1));link.href=projectURL(file.url);link.target='_blank';link.rel='noopener';li.dataset.path=file.path;li.append(link,element('span',file.path,'muted'),element('span',`${file.size.toLocaleString()} bytes`,'muted'));list.append(li);}root.append(list);
  }catch(error){root.append(element('p',error.message,'warning'),button('다시 불러오기',()=>loadMaterials(root)));}
}
