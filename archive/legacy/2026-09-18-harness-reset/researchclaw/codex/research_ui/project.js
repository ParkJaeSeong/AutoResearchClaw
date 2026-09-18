// A document owns one project. Switching projects always loads a new document.
export function projectId(href=globalThis.location?.href){return href?new URL(href).searchParams.get('project'):null;}
export function projectURL(path,id=projectId()){
  const url=new URL(path,'http://pilot.local');
  if(url.origin!=='http://pilot.local')throw Error('로컬 연구 경로가 아닙니다.');
  if(id)url.searchParams.set('project',id);
  return url.pathname+url.search+url.hash;
}
export function projectFetch(path,options){return fetch(projectURL(path),options);}
export function stateKey(id=projectId()){return `pilot.project.${id??'legacy'}`;}
export function readProjectState(id=projectId(),storage=globalThis.sessionStorage){try{return JSON.parse(storage.getItem(stateKey(id)))??{};}catch{return {};}}
export function saveProjectState(patch,id=projectId(),storage=globalThis.sessionStorage){try{storage.setItem(stateKey(id),JSON.stringify({...readProjectState(id,storage),...patch}));}catch{}}
export function switchURL(href,id,state={}){const url=new URL(href);url.search='';url.searchParams.set('project',id);if(state.head)url.searchParams.set('head',state.head);url.hash=state.hash||'overview';return url.href;}
