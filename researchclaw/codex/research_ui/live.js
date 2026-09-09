// A generation belongs to one selected HEAD. Late requests cannot cross it.
export function createLiveFeed({load,onView,onStatus,setTimer=setTimeout,clearTimer=clearTimeout}) {
  let selected=null,generation=0,timer=null,pending=null,stopped=false,shown=null,lastUpdatedAt=null;
  function refresh() {
    if(stopped) return Promise.resolve();
    if(pending?.generation===generation) return pending.promise;
    if(timer!==null) clearTimer(timer);
    const own=generation, head=selected;
    let request;try{request=load(head);}catch(error){request=Promise.reject(error);}
    const promise=Promise.resolve(request).then(view=>{
      if(stopped || own!==generation) return;
      if(typeof view?.head_id!=='string' || !view.head_id || (head && head!==view.head_id)) throw new Error('선택한 기록 버전을 확인할 수 없습니다.');
      if(view.head_id!==shown) {onView(view);shown=view.head_id;lastUpdatedAt=Date.now();}
      onStatus({connected:true,lastUpdatedAt,currentHead:view.current_head_id,selectedHead:head});
    }).catch(error=>{
      if(!stopped && own===generation) onStatus({connected:false,lastUpdatedAt,selectedHead:head,error:String(error.message??error)});
    }).finally(()=>{
      if(own===generation) {pending=null;if(!stopped) timer=setTimer(refresh,3000);}
    });
    pending={generation:own,promise};return promise;
  }
  return {start:refresh,refresh,selectHead(head=null){selected=head;generation++;shown=null;pending=null;return refresh();},
    stop(){stopped=true;generation++;if(timer!==null)clearTimer(timer);}};
}
