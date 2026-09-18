// Navigation only: never submits research operations or rewrites research records.
import {element} from './detail.js';
export const PAGES={overview:'연구 개요',workflow:'단계와 대화',decisions:'판단과 준비',sources:'자료와 근거',atlas:'Atlas 연결',materials:'프로젝트 자료',m2:'M2 · 실험과 해석',m3:'M3 · 연구 마무리'};
export function pageTabs(){
  const nav=element('div',undefined,'project-tabs');nav.setAttribute('role','tablist');nav.setAttribute('aria-label','연구 영역');
  for(const [id,title] of Object.entries(PAGES)){
    const tab=element('button',title);tab.id=`page-tab-${id}`;tab.dataset.pageTab=id;tab.dataset.key=`page-tab:${id}`;
    tab.setAttribute('role','tab');tab.setAttribute('aria-controls',`page-${id}`);nav.append(tab);
  }const wrap=element('div',undefined,'project-navigation'),hint=element('p','탭을 좌우로 밀어 더 볼 수 있습니다.','tab-scroll-hint');hint.hidden=true;wrap.append(nav,hint);return wrap;
}
export function pageSection(id){
  const section=element('section',undefined,'project-page');section.dataset.page=id;section.id=`page-${id}`;
  section.setAttribute('role','tabpanel');section.setAttribute('aria-labelledby',`page-tab-${id}`);section.tabIndex=0;return section;
}
export function startShell(){
  let selected='overview';const sidebar=document.getElementById('app-sidebar'),background=document.getElementById('app-main'),toggle=document.getElementById('nav-toggle'),backdrop=document.getElementById('nav-backdrop');
  const mobile=window.matchMedia('(max-width: 1023px)');
  const desktopToggle=document.getElementById('sidebar-toggle'),settings=document.getElementById('sidebar-settings');
  let collapsed=false;
  try { collapsed=localStorage.getItem('pilot.sidebar.collapsed')==='true'; } catch {}
  function applyDesktop(){
    const active=collapsed&&!mobile.matches;
    document.body.classList.toggle('sidebar-collapsed',active);
    const label=active?'주 메뉴 펼치기':'주 메뉴 접기';
    desktopToggle.setAttribute('aria-expanded',String(!active));
    desktopToggle.setAttribute('aria-label',label);desktopToggle.title=label;
    document.getElementById('sidebar-arrow').setAttribute('d',active?'m14 9 3 3-3 3':'m16 15-3-3 3-3');
    if(active&&sidebar.contains(document.activeElement)&&!document.activeElement.getClientRects().length)desktopToggle.focus({preventScroll:true});
  }
  desktopToggle.addEventListener('click',()=>{
    collapsed=!collapsed;try{localStorage.setItem('pilot.sidebar.collapsed',String(collapsed));}catch{}
    applyDesktop();
  });
  settings.addEventListener('click',()=>{
    collapsed=false;try{localStorage.setItem('pilot.sidebar.collapsed','false');}catch{}
    applyDesktop();document.querySelector('#theme-control select')?.focus({preventScroll:true});
  });
  applyDesktop();
  function close(){sidebar.classList.remove('is-open');sidebar.removeAttribute('role');sidebar.removeAttribute('aria-modal');background.inert=false;backdrop.hidden=true;toggle.setAttribute('aria-expanded','false');}
  function open(){sidebar.classList.add('is-open');sidebar.setAttribute('role','dialog');sidebar.setAttribute('aria-modal','true');background.inert=true;backdrop.hidden=false;toggle.setAttribute('aria-expanded','true');document.getElementById('nav-close').focus();}
  toggle.addEventListener('click',open);document.getElementById('nav-close').addEventListener('click',()=>{close();toggle.focus();});backdrop.addEventListener('click',()=>{close();toggle.focus();});
  sidebar.addEventListener('keydown',event=>{
    if(!mobile.matches||!sidebar.classList.contains('is-open'))return;
    if(event.key==='Escape'){event.preventDefault();close();toggle.focus();}
    if(event.key==='Tab'){
      const nodes=[...sidebar.querySelectorAll('button,a,select,summary,input,textarea')].filter(n=>n.getClientRects().length&&!n.disabled),first=nodes[0],last=nodes.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    }
  });
  mobile.addEventListener('change',()=>{const wasOpen=sidebar.classList.contains('is-open');close();applyDesktop();if(mobile.matches&&(wasOpen||document.activeElement===desktopToggle))toggle.focus();});
  function apply(){
    for(const link of document.querySelectorAll('.service-nav a')){if(link.getAttribute('href')===`#${selected}`)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}
    for(const panel of document.querySelectorAll('[data-page]'))panel.hidden=panel.dataset.page!==selected;
    for(const tab of document.querySelectorAll('[data-page-tab]')){const active=tab.dataset.pageTab===selected;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;}
    document.getElementById('location-label').textContent=PAGES[selected];
    const tabs=document.querySelector('.project-tabs'),hint=document.querySelector('.tab-scroll-hint');if(tabs&&hint)hint.hidden=tabs.scrollWidth<=tabs.clientWidth+1;
  }
  function fromHash(scroll=false){
    let hash;try{hash=decodeURIComponent(location.hash.slice(1));}catch{return;}
    const target=document.getElementById(hash),page=Object.hasOwn(PAGES,hash)?hash:target?.closest('[data-page]')?.dataset.page;
    if(page)selected=page;apply();
    if(scroll&&target){for(let node=target.parentElement;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;target.scrollIntoView({block:'start'});target.tabIndex=-1;target.focus({preventScroll:true});}
  }
  document.addEventListener('click',event=>{
    const tab=event.target.closest('[data-page-tab]');if(tab){selected=tab.dataset.pageTab;history.pushState({},'',`#${selected}`);apply();return;}
    const link=event.target.closest('a[href^="#"]');if(link){const hash=link.getAttribute('href');if(Object.hasOwn(PAGES,hash.slice(1))||document.getElementById(hash.slice(1))?.closest('[data-page]')){event.preventDefault();history.pushState({},'',hash);close();fromHash(true);if(Object.hasOwn(PAGES,hash.slice(1)))document.getElementById(`page-${selected}`)?.focus({preventScroll:true});}}
  });
  document.addEventListener('keydown',event=>{
    const tab=event.target.closest('[data-page-tab]');if(!tab)return;
    const ids=Object.keys(PAGES);let index=ids.indexOf(tab.dataset.pageTab);
    if(event.key==='ArrowRight')index=(index+1)%ids.length;else if(event.key==='ArrowLeft')index=(index+ids.length-1)%ids.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=ids.length-1;else return;
    event.preventDefault();selected=ids[index];history.replaceState({},'',`#${selected}`);apply();document.getElementById(`page-tab-${selected}`).focus();
  });
  window.addEventListener('resize',apply);
  window.addEventListener('hashchange',()=>fromHash(true));window.addEventListener('popstate',()=>fromHash(true));
  return {sync(view){document.getElementById('project-name').textContent=document.querySelector('#project-select option:checked')?.textContent??view.project.topic;document.title=`Pilot · ${view.project.topic}`;fromHash();},select(page){selected=page;close();apply();document.getElementById(`page-${selected}`)?.focus({preventScroll:true});}};
}
