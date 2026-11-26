// Leaderboard maintenance tools; all changes use the existing revision-checked APIs.
(() => {
 'use strict';
 const root=document.getElementById('nai-media-host')?.shadowRoot,cards=root?.naiCards;if(!cards)return;
 const el=(tag,cls='',text='')=>{const e=document.createElement(tag);e.className=cls;e.textContent=text;return e;};
 const style=el('style');style.textContent=`
 .naiCardDebugPanel{box-sizing:border-box;height:266px;overflow:auto;padding:10px;background:#111c2a;border:1px solid #47566a;border-radius:8px;display:flex;flex-direction:column;gap:8px;color:#e4eaf4;font:12px/1.35 system-ui;scrollbar-width:thin}
 .naiCardDebugPanel strong{overflow-wrap:anywhere}.naiCardDebugPanel button,.naiCardDebugPanel select{font:12px system-ui;min-width:0;max-width:100%;padding:5px 7px}
 .naiCardDebugPanel label{display:flex;align-items:center;gap:6px}.naiCardDebugPanel label select{flex:1;width:0}.naiDebugRow{display:flex;flex-wrap:wrap;gap:5px;align-items:center}.naiDebugTraits{display:flex;flex-wrap:wrap;gap:4px;max-height:72px;overflow:auto;min-height:20px;flex-shrink:0}
 .naiDebugTrait{display:inline-flex;align-items:center;gap:4px;border:1px solid #566275;border-radius:5px;padding:2px 5px;background:#233146}.naiDebugTrait button{padding:0 4px!important;border:0}.naiDebugTrait small{color:#b8c5d8}
 .naiDebugCrop{font-weight:700;color:#9bc9ae}.naiDebugCrop[data-custom=true]{color:#ffd58b}.naiDebugMessage{margin:0!important;min-height:16px;font-size:11px;color:#ffb9a9}.naiDebugFilename{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .naiDebugCrop[data-positioning=auto-unchecked]{color:#ffd58b}.naiDebugCrop[data-positioning=auto-checked]{color:#9bc9ae}
 .naiBattleRankCard[data-debug=true] .naiFramedSource{box-shadow:0 0 0 2px #ff263f!important}
 .naiBattleRankCard[data-debug=true]>.naiCardDetails{display:none}
 .naiDebugHelp{font-size:12px;color:#bac8dc;margin:8px 0}.naiDebugToggle{display:inline-flex;align-items:center;gap:6px;margin-left:14px}
 `;root.append(style);
 const frameFor=(owner,mid)=>cards.cache.get(owner)?.collection.frames['image:'+mid];
 const metaFor=(owner,mid)=>cards.cache.get(owner)?.collection.frame_meta?.['image:'+mid];
 const custom=frame=>!!frame&&(Number(frame.x||0)!==0||Number(frame.y||0)!==0||Number(frame.zoom??1)!==1||(frame.fit||'contain')!=='contain'||!!frame.reference);
 cards.hasCustomCrop=(owner,mid)=>custom(frameFor(owner,mid));
 cards.framingStatus=(owner,mid)=>metaFor(owner,mid)?.mode==='auto'?(metaFor(owner,mid).checked?'auto-checked':'auto-unchecked'):custom(frameFor(owner,mid))?'custom':'default';
 cards.matchesCropFilter=(owner,mid,filter)=>filter==='all'||(filter==='auto'?cards.framingStatus(owner,mid).startsWith('auto-'):cards.framingStatus(owner,mid)===filter);
 style.textContent += `
 .naiCropSheet{width:min(1260px,100%)}
 .naiCropSheet .naiCollectionHeader{margin-bottom:8px}
 .naiCropToolbar{position:sticky;top:0;z-index:3;background:#101923;border-bottom:1px solid #33445a;border-radius:8px;padding:10px;display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:16px}
 .naiCropFilters,.naiCropPages,.naiCropEditActions{display:flex;flex-wrap:wrap;gap:6px}
 .naiCropToolbar .naiCropFilters button[aria-pressed=true]{background:#3b526a;border-color:#7395b5;color:white}
 .naiCropStatus{margin-left:auto;font-size:13px;color:#d2dfef}
 .naiCropGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
 .naiCropTile{min-width:0;padding:9px;border:1px solid #394b63;border-radius:10px;background:#172332}
 .naiCropTile[data-marked=true]{background:#242a32;border-color:#e0b86b}
 .naiCropPreview{display:grid;place-items:center;aspect-ratio:7/10;overflow:hidden;color:#c8d3e3;background:#24344a;border-radius:6px}
 .naiCropPreview>.naiPortraitCard,.naiCropScene>.naiPortraitCard,.naiCropTreatments .naiCropTreatmentCard{width:100%;height:auto;max-width:none;margin:0}
 .naiCropDetails{display:grid;gap:2px;margin:8px 0;min-height:40px}
 .naiCropDetails strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .naiCropDetails small{color:#c1d1e6}
 .naiCropActions{display:flex;flex-wrap:wrap;align-items:center;gap:6px;justify-content:space-between}
 .naiCropActions label{display:flex;gap:5px;align-items:center;cursor:pointer;font-size:12px}
 .naiCropActions input{margin:0;width:16px;height:16px;accent-color:#e0b86b}
 .naiCropActions button{padding:4px 9px;font-size:12px}
 .naiCropException{max-width:960px;margin:auto}
 .naiCropException>button{margin-bottom:12px}
 .naiCropEditLayout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:start;gap:20px}
 .naiCropEditView{position:relative;isolation:isolate;overflow:hidden;width:min(100%,50vh);aspect-ratio:7/10;margin:auto;background:#152438;border-radius:8px}
 .naiCropScene{position:absolute;inset:0;transform-origin:top left}
 .naiCropScene>.naiTradingCard>*:not(.naiCardPhotoWindow){pointer-events:none}
 .naiCropEditView[data-mode=crop],.naiCropEditView[data-mode=overflow]{cursor:grab;touch-action:none;user-select:none}
 .naiCropEditView[data-dragging=true],.naiCropEditView[data-dragging=true] .naiCardPhotoWindow{cursor:grabbing}
 .naiCropEditView[data-mode=original] .naiCardPhotoWindow{cursor:default;touch-action:auto}
 .naiCropEditView[data-mode=crop] .naiFramedSource{box-shadow:0 0 0 2px #ff263f!important}
 .naiCropEditView[data-mode=overflow] .naiCropScene>.naiTradingCard{opacity:.44;background:transparent!important}
 .naiCropEditView[data-mode=overflow] .naiCropScene>.naiTradingCard>.naiCardPhotoWindow{background:transparent!important;box-shadow:none}
 .naiCropEditView[data-mode=overflow] .naiCropScene .naiFramedSource{opacity:0}
 .naiCropOverflowPhoto,.naiCropAperture,.naiCropCardBoundary{position:absolute;pointer-events:none}
 .naiCropOverflowPhoto{display:block;max-width:none!important;max-height:none!important;object-fit:fill}
 .naiCropAperture{outline:2px solid #f7db8e;box-shadow:0 0 0 3px #151b26}
 .naiCropCardBoundary{outline:1px dashed #d9e4f3}
 .naiCropEditTools{display:grid;gap:10px;min-width:0}
 .naiCropEditTools h3{overflow-wrap:anywhere}
 .naiCropTreatments{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
 .naiCropTreatments button{display:grid;grid-template-columns:clamp(30px,10vw,52px) minmax(0,1fr);align-items:center;gap:6px;min-width:0;padding:5px;text-align:left;overflow-wrap:anywhere}
 .naiCropTreatmentCard{pointer-events:none}
 .naiCropTreatments button,.naiCropEditActions button{min-height:40px}
 .naiCropTreatments button[aria-pressed=true],.naiCropEditActions button[aria-pressed=true]{background:#3b526a;border-color:#7395b5;color:white}
 .naiCropPositionTools{display:grid;gap:8px}
 .naiCropPositionTools label{display:grid;grid-template-columns:1fr auto;gap:2px 8px}
 .naiCropPositionTools select,.naiCropPositionTools input{grid-column:1/-1;width:100%;min-width:0}
 .naiCropPositionTools input{padding:0;accent-color:#e0b86b}
 .naiCropPositionTools button{justify-self:start}
 .naiCropPositionTools .naiCardPanControl{margin:0}
 @media(max-width:940px){.naiCropGrid{grid-template-columns:repeat(3,minmax(0,1fr))}}
 @media(max-width:680px){.naiCropGrid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.naiCropEditLayout{grid-template-columns:1fr}.naiCropStatus{margin-left:0}.naiCropEditView{width:min(100%,32vh)}}
 @media(max-width:350px){.naiCropGrid{grid-template-columns:1fr}}
`;

 const cropRequest=(action,owner,body={})=>{
  const analysis=action==='state'&&body.media_ids?.length&&body.analyze!==false;
  return root.naiOutfitRequest('/api/collection/crop-review-'+action,{character_id:owner,...body},analysis?{timeout:300000}:undefined);
 };
 const cropButton=(name,click)=>{const b=el('button','',name);b.type='button';b.onclick=click;return b;};
 const defaultFrame={x:0,y:0,zoom:1,fit:'contain'};
 const flagged=(owner,mid)=>!!cards.cache.get(owner)?.collection.crop_review?.[mid]?.flagged;
 const flagRequests=new Map();
 cards.cropReviewFlag=function(owner,getMedia,onError,canUse=()=>true){
  const flag=cropButton('',async event=>{
   event.stopPropagation();
   const mid=getMedia(),key=owner+':'+mid;
   if(flagRequests.has(key)||!canUse())return;
   const work=(async()=>{
    const current=await cropRequest('state',owner,{media_ids:[mid],analyze:false});
    const proposal=current.proposals[mid];
    if(!proposal?.token||proposal.category==='unavailable')throw Error('This photo is unavailable for crop review.');
    const saved=await cropRequest('save',owner,{revision:current.revision,reviews:[{media_id:mid,token:proposal.source_token||proposal.token,choice:proposal.flagged?'unflag':'flag'}]});
    cards.cache.set(owner,saved);
   })();
   flagRequests.set(key,work);flag.refresh();
   try{await work;}catch(e){onError(e.message||String(e));}
   finally{flagRequests.delete(key);for(const control of root.querySelectorAll('.naiFlagCrop'))control.refresh();}
  });
  flag.className='naiFlagCrop';
  flag.refresh=()=>{
   const mid=getMedia(),marked=flagged(owner,mid),busy=flagRequests.has(owner+':'+mid);
   flag.textContent=marked?'Crop flagged':'Flag crop for review';
   flag.title=marked?'Clear crop review flag':'Flag this crop for review later';
   flag.setAttribute('aria-pressed',String(marked));
   flag.disabled=busy||!canUse();
  };
  flag.refresh();
  return flag;
 };

 cards.reviewCrops=function(owner,onClose){
  if(root.querySelector('.naiCropSheet'))return;
  const pageSize=12,storageKey='nai-crop-review:'+owner,urls=new Set();
  let resume={};
  try{resume=JSON.parse(sessionStorage.getItem(storageKey)||'{}')||{};}catch{}
  const marked=new Map(Array.isArray(resume.marked)?resume.marked:[]),scanned=new Set(),missing=new Set();
  let scanWork=null,scanError='',scanTimer;
  let generation=0,page=0,anchor=resume.anchor,filter=['all','later'].includes(resume.filter)?resume.filter:'needs';
  let snapshot,rows=[],cardsById=new Map(),queue=[],visible=[],exceptionIds=Array.isArray(resume.exceptionIds)?resume.exceptionIds:[],exception=null;
  let saving=false,loading=false,stale=false,changed=false,undoToken=resume.undoToken;
  const release=()=>{generation++;clearTimeout(scanTimer);exception?.dispose();exception=null;for(const url of urls)URL.revokeObjectURL(url);urls.clear();};
  function remember(){
   try{sessionStorage.setItem(storageKey,JSON.stringify({anchor,filter,marked:[...marked].slice(-120),undoToken,exceptionIds}));}catch{}
  }
  const clearPeek=()=>exception?.endPeek();
  const m=cards.modal('Review card crops',()=>{
   exceptionIds=[];remember();release();window.removeEventListener('blur',clearPeek);
   if(changed)onClose?.();
  });
  m.inner.classList.add('naiCropSheet');
  if(!owner){m.body.textContent='Choose a character to review card crops.';return;}
  const status=el('span','naiCropStatus'),toolbar=el('div','naiCropToolbar'),grid=el('div','naiCropGrid'),editor=el('section','naiCropException');
  status.setAttribute('role','status');editor.hidden=true;
  const filters=el('div','naiCropFilters');
  const needs=cropButton('Needs a look',()=>setFilter('needs')),all=cropButton('All auto crops',()=>setFilter('all'));
  const laterFilter=cropButton('Later',()=>setFilter('later'));
  filters.append(needs,all,laterFilter);
  const approve=cropButton('Approve all',approvePage),undo=cropButton('Undo last',undoLast),refresh=cropButton('Refresh',()=>reload(true,true));
  const previous=cropButton('Previous',()=>goPage(page-1)),next=cropButton('Next',()=>goPage(page+1));
  approve.dataset.primary='true';approve.title='Approve the ready crops shown on this page';
  const pages=el('div','naiCropPages');pages.append(previous,next);
  toolbar.append(filters,approve,undo,refresh,pages,status);
  m.body.append(toolbar,grid,editor);

  function setFilter(value){
   if(filter===value)return;
   filter=value;page=0;anchor=null;
   if(snapshot?.queue){queue=queueIds(snapshot.queue);drawPage(true);}
   else reload();
  }
  function goPage(value){page=value;anchor=null;drawPage(true);}
  function readRows(data){
   rows=data.boards?.find(b=>b.kind==='images')?.entries||[];
   const media=new Map((root.naiGetLibrary?.()?.media||[]).map(m=>[m.id,m]));
   cardsById=new Map();
   for(const entry of rows){
    if(entry.flagged_for_removal)continue;
    entry.images.forEach((mid,side)=>{
     const photo=media.get(mid);
     if(cardsById.has(mid)||photo?.in_all===false||photo?.in_review||photo?.in_purgatory||photo?.flagged_for_removal) return;
     const face=entry.duo_side?(side?'back':'front'):null;
     cardsById.set(mid,{mid,filename:(photo?.original_name||entry.name)+(face?' · '+face:''),entry:face?{...entry,duo_side:face}:entry});
    });
   }
  }
  function queueIds(buckets){
   const order=filter==='later'?['later']:filter==='needs'?['flagged','needs_look','unavailable']:['flagged','needs_look','unavailable','likely','fit','later','checked','pending'];
   return [...new Set(order.flatMap(name=>buckets[name]||[]))].filter(mid=>cardsById.has(mid));
  }
  const canApprove=v=>v.ready&&v.pending&&!v.check.checked&&!['pending','unavailable'].includes(v.proposal.analysis_status);
  function pendingIds(){return (snapshot?.queue?.pending||[]).filter(mid=>cardsById.has(mid)&&!scanned.has(mid));}
  function pageStatus(){
   if(loading||!editor.hidden)return;
   const first=page*pageSize,failed=visible.filter(v=>!v.ready).length;
   const count=visible.length?((first+1)+'–'+(first+visible.length)+' of '+queue.length+(failed?' · '+failed+(failed===1?' preview':' previews')+' unavailable':'')):'';
   const manual=visible.filter(v=>v.ready&&v.pending&&['unavailable','pending'].includes(v.proposal.analysis_status)).length;
   const remains=filter==='later'?0:pendingIds().length;
   const progress=remains?(scanError?remains+' waiting for analysis':'Analyzing '+remains+' more crops…'):'';
   status.textContent=[count,manual?manual+' to check individually':'',filter!=='later'&&missing.size?missing.size+' '+(missing.size===1?'original':'originals')+' unavailable':'',filter==='later'?'':scanError,filter==='all'||!scanError?progress:''].filter(Boolean).join(' · ')||
      (filter==='later'?'No crops saved for later.':filter==='needs'?'No crops need a closer look.':'No automatic crops are available.');
  }
  function saveStatus(){
   const count=visible.filter(canApprove).length;
   const markedCount=visible.filter(v=>v.ready&&v.check.checked).length;
   approve.textContent=markedCount?(count?'Approve others & edit '+markedCount:'Edit '+markedCount):(count?'Approve all ('+count+')':'Approve all');
   const editing=!editor.hidden;
   approve.hidden=editing;needs.disabled=all.disabled=laterFilter.disabled=saving||editing;
   approve.disabled=saving||loading||stale||(!count&&!markedCount);
   m.head.querySelector('button').disabled=saving;
   undo.disabled=saving||loading||stale||!undoToken;
   refresh.disabled=saving;
   pages.hidden=editing;
   previous.disabled=saving||loading||page===0;
   next.disabled=saving||loading||(page+1)*pageSize>=queue.length;
   needs.setAttribute('aria-pressed',String(filter==='needs'));
   all.setAttribute('aria-pressed',String(filter==='all'));
   const laterCount=(snapshot?.queue?.later||[]).filter(mid=>cardsById.has(mid)).length;
   laterFilter.textContent=laterCount?'Later ('+laterCount+')':'Later';
   laterFilter.setAttribute('aria-pressed',String(filter==='later'));
   for(const v of visible){
    v.check.disabled=saving||loading||stale||!v.ready;
    v.edit.disabled=v.check.disabled;
   }
   for(const control of editor.querySelectorAll('button,input,select')){
    control.disabled=saving||(stale&&control.dataset.save==='true')||control.dataset.unavailable==='true'||(exception?.peeking()&&control.dataset.cropPosition==='true');
   }
  }
  function recordAnchor(){
   if(queue.length){
    if(anchor&&queue.includes(anchor))page=Math.floor(queue.indexOf(anchor)/pageSize);
    page=Math.min(page,Math.ceil(queue.length/pageSize)-1);
    anchor=queue[page*pageSize];
   }else{page=0;anchor=null;}
   remember();
  }
  function checkCurrent(current){return current===generation&&m.wrap.isConnected;}
  function acceptState(result,current){
   if(Object.keys(result.changed_frames||{}).length){
    changed=true;
    const cached=cards.cache.get(owner)?.collection;
    if(cached)Object.assign(cached.frames,result.changed_frames);
    if(!m.wrap.isConnected)onClose?.();
   }
   if(checkCurrent(current)&&!saving)snapshot=result;
  }
  async function reload(keepException=false,retry=false){
   release();const current=generation;
   if(!keepException)exceptionIds=[];
   if(retry){scanError='';scanned.clear();missing.clear();}
   loading=true;visible=[];
   const editing=exceptionIds.length>0;
   editor.replaceChildren();
   if(editing)editor.append(cropButton('Back to sheet',exitEditor));
   editor.hidden=!editing;grid.hidden=editing;
   grid.replaceChildren();m.error.textContent='';stale=false;
   status.textContent='Loading crop review…';saveStatus();
   try{
    const data=await cards.load(owner);
    if(!checkCurrent(current))return;
    readRows(data);
    const result=await cropRequest('state',owner);
    if(!checkCurrent(current))return;
    acceptState(result,current);queue=queueIds(result.queue);
    if(exceptionIds.length){await drawException(retry);return;}
    await drawPage(false,retry);
   }catch(e){
    if(checkCurrent(current)){status.textContent='';m.error.textContent=e.message||String(e);loading=false;saveStatus();}
   }
  }
  async function loadPreview(v,current){
   const im=el('img');im.alt=v.filename;im.draggable=false;
   const card=cards.lightCard(v.entry,rows,owner,im,true,v.mid);
   v.preview.replaceChildren(card);
   try{
    await root.naiLoadThumbnail(v.mid,im);
    if(!checkCurrent(current))return false;
    if(!im.getAttribute('src'))throw Error('Thumbnail unavailable');
    await im.decode();
    if(!checkCurrent(current))return false;
    cards.applyFrame(im,v.proposal.options.suggested.frame);
    v.thumbnail=im;
    return true;
   }catch(e){
    if(checkCurrent(current)){
     v.preview.textContent='Preview unavailable';v.preview.title=e.message||String(e);
    }
    return false;
   }
  }
  async function drawPage(scroll=false,retry=false){
   release();const current=generation;
   editor.hidden=true;editor.replaceChildren();grid.hidden=false;visible=[];grid.replaceChildren();
   m.error.textContent='';stale=false;recordAnchor();
   if(scroll){m.wrap.scrollTop=0;}
   const start=page*pageSize,ids=queue.slice(start,start+pageSize);
   if(!ids.length){
    loading=false;pageStatus();saveStatus();scheduleScan();return;
   }
   loading=true;status.textContent=retry?'Analyzing '+ids.length+' card crops…':'Loading card previews…';saveStatus();
   try{
    const result=await cropRequest('state',owner,{media_ids:ids,retry,analyze:retry});
    acceptState(result,current);
    if(!checkCurrent(current))return;
    status.textContent='Loading card previews…';
    await appendTiles(ids,result,current);
    if(!checkCurrent(current))return;
    loading=false;pageStatus();saveStatus();scheduleScan();
   }catch(e){
    if(checkCurrent(current)){loading=false;status.textContent='';m.error.textContent=e.message||String(e);saveStatus();}
   }
  }
  async function appendTiles(ids,result,current){
    const tiles=ids.map(mid=>{
     const item=cardsById.get(mid),proposal=result.proposals[mid];
     const tile=el('article','naiCropTile'),preview=el('div','naiCropPreview');
     const details=el('div','naiCropDetails'),name=el('strong','',item.filename),note=el('small','',proposal?.reason||'Crop unavailable');
     name.title=item.filename;details.append(name,note);
     const actions=el('div','naiCropActions'),label=el('label'),check=el('input'),edit=cropButton('Edit',()=>startExceptions([mid]));
     check.type='checkbox';check.setAttribute('aria-label','Mark '+item.filename+' for editing');
     edit.setAttribute('aria-label','Edit crop for '+item.filename);
     label.append(check,document.createTextNode('Mark to edit'));actions.append(label,edit);
     tile.append(preview,details,actions);grid.append(tile);
     const v={...item,proposal,preview,note,check,edit,ready:false,pending:!proposal?.checked||!!proposal?.flagged};
     check.checked=!!proposal?.token&&marked.get(mid)===proposal.token;
     tile.dataset.marked=String(check.checked);
     check.onchange=()=>{
      if(check.checked)marked.set(mid,v.proposal.token);else marked.delete(mid);
      tile.dataset.marked=String(check.checked);remember();saveStatus();
     };
     if(!proposal?.options?.suggested||!proposal.token){preview.textContent='Preview unavailable';}
     return v;
    });
    visible.push(...tiles);saveStatus();
    const work=tiles.values();
    await Promise.all(Array.from({length:Math.min(4,ids.length)},async()=>{
     for(const v of work){
      if(!checkCurrent(current))return;
      if(v.proposal?.options?.suggested&&v.proposal.token)v.ready=await loadPreview(v,current);
      if(checkCurrent(current))saveStatus();
     }
    }));
  }
  function refreshTiles(proposals){
   let marksChanged=false;
   for(const tile of visible){
    const proposal=proposals[tile.mid];
    if(!proposal||proposal.token===tile.proposal?.token)continue;
    tile.proposal=proposal;
    tile.pending=!proposal.checked||!!proposal.flagged;
    tile.note.textContent=proposal.reason||'Crop unavailable';
    if(proposal.options?.suggested&&proposal.token){
     if(tile.thumbnail)cards.applyFrame(tile.thumbnail,proposal.options.suggested.frame);
     if(tile.check.checked){marked.set(tile.mid,proposal.token);marksChanged=true;}
    }else{
     tile.ready=false;tile.thumbnail=null;tile.preview.textContent='Preview unavailable';
    }
   }
   if(marksChanged)remember();
  }
  function scheduleScan(){
   clearTimeout(scanTimer);
   if(!m.wrap.isConnected||!editor.hidden||filter==='later'||saving||loading||stale||scanError||!pendingIds().length)return;
   scanTimer=setTimeout(scanMore,100);
  }
  async function scanMore(){
   if(!m.wrap.isConnected||!editor.hidden||filter==='later'||saving||loading||stale||scanWork)return;
   const ids=pendingIds().slice(0,4),current=generation;
   if(!ids.length)return;
   let result;
   scanWork=(async()=>{
    try{
     result=await cropRequest('state',owner,{media_ids:ids});
     acceptState(result,current);
     if(checkCurrent(current))for(const mid of ids)scanned.add(mid);
    }catch(e){
     if(checkCurrent(current)){
      scanError='Analysis paused. Refresh to retry.';
      m.error.textContent=e.message||String(e);
      stale=/refresh|stale/i.test(m.error.textContent)&&!/timed out|respond/i.test(m.error.textContent);
     }
    }
   })();
   await scanWork;scanWork=null;
   if(!checkCurrent(current)||saving||loading){scheduleScan();return;}
   if(result){
    refreshTiles(result.proposals);
    for(const mid of ids)if(!result.proposals[mid]?.token)missing.add(mid);
    const analyzed=Object.values(result.proposals).filter(proposal=>proposal.token);
    if(analyzed.length&&analyzed.every(proposal=>proposal.analysis_status==='unavailable')){
     scanError='Automatic analysis unavailable. Refresh to retry.';
    }
    const existing=new Set(queue),additions=queueIds(result.queue).filter(mid=>!existing.has(mid));
    queue=queue.concat(additions);
    const first=page*pageSize;
    const toShow=queue.slice(first+visible.length,first+pageSize);
    if(toShow.some(mid=>!result.proposals[mid])){await drawPage();return;}
    if(toShow.length){
     if(!anchor)recordAnchor();
     await appendTiles(toShow,result,current);
    }
   }
   if(!checkCurrent(current))return;
   pageStatus();saveStatus();scheduleScan();
  }
  async function mutate(action,body){
   if(saving)return false;
   saving=true;clearTimeout(scanTimer);saveStatus();m.error.textContent='';
   try{
    const saved=await cropRequest(action,owner,{revision:snapshot.revision,...body});
    cards.cache.set(owner,saved);
    snapshot={...snapshot,revision:saved.collection.revision};
    undoToken=action==='undo'?null:saved.undo_token||undoToken;
    changed=true;remember();return true;
   }catch(e){
    const message=e.message||String(e);
    stale=/refresh|stale/i.test(message);
    m.error.textContent=message;return false;
   }finally{saving=false;saveStatus();scheduleScan();}
  }
  async function approvePage(){
   if(approve.disabled)return;
   const edits=visible.filter(v=>v.ready&&v.check.checked).map(v=>v.mid);
   const accepted=visible.filter(canApprove);
   const reviews=accepted.map(v=>({media_id:v.mid,token:v.proposal.token,choice:'suggested'}));
   if(reviews.length&&!await mutate('save',{reviews}))return;
   if(edits.length)startExceptions(edits);
   else reload();
  }
  async function undoLast(){
   if(undo.disabled)return;
   if(await mutate('undo',{undo_token:undoToken}))await reload(!editor.hidden);
  }
  function startExceptions(ids){exceptionIds=ids;remember();drawException();}
  function exitEditor(){
   exceptionIds=[];editor.hidden=true;grid.hidden=false;reload();refresh.focus();
  }
  async function drawException(retry=false){
   if(!exceptionIds.length){exitEditor();return;}
   release();const current=generation;
   const mid=exceptionIds[0],item=cardsById.get(mid);
   grid.hidden=true;editor.hidden=false;editor.tabIndex=0;editor.replaceChildren();
   status.textContent='Loading original…';m.error.textContent='';stale=false;
   loading=true;saveStatus();m.wrap.scrollTop=0;editor.focus({preventScroll:true});
   const back=cropButton('Back to sheet',exitEditor),later=cropButton('Later',()=>{if(checkCurrent(current)&&!loading)advance();});
   editor.append(back);
   try{
    const data=await cropRequest('state',owner,{media_ids:[mid],retry,analyze:retry});
    acceptState(data,current);
    if(!checkCurrent(current))return;
    const proposal=data.proposals[mid];
    if(!item||!proposal?.token||!proposal.options?.suggested)throw Error('This crop is no longer available.');
    const original=await root.naiOutfitOriginal(mid);
    if(!checkCurrent(current))return;
    const url=URL.createObjectURL(original);urls.add(url);
    const im=el('img');im.alt=item.filename;im.src=url;im.draggable=false;
    await im.decode();
    if(!checkCurrent(current))return;
    const preview=cards.lightCard(item.entry,rows,owner,im,true,mid);
    const opening=im.parentElement,view=el('div','naiCropEditView'),scene=el('div','naiCropScene');
    const overflowPhoto=el('img','naiCropOverflowPhoto'),aperture=el('span','naiCropAperture'),boundary=el('span','naiCropCardBoundary');
    overflowPhoto.alt='';overflowPhoto.src=url;overflowPhoto.draggable=false;
    for(const node of [overflowPhoto,aperture,boundary]){node.hidden=true;node.setAttribute('aria-hidden','true');}
    const tools=el('div','naiCropEditTools'),layout=el('div','naiCropEditLayout');
    view.tabIndex=0;view.setAttribute('role','group');view.setAttribute('aria-label','Card crop preview');
    view.dataset.mode='crop';scene.append(preview);view.append(overflowPhoto,scene,boundary,aperture);
    layout.append(view,tools);editor.append(layout);
    status.textContent=exceptionIds.length+' to edit';

    const {options}=proposal;
    const frame={...defaultFrame,...options.suggested.frame};
    const pending=['pending','unavailable'].includes(proposal.analysis_status);
    const frameKey=option=>JSON.stringify([option?.frame?.fit,option?.frame?.x,option?.frame?.y,option?.frame?.zoom,option?.frame?.reference]);
    const sameAsFit=frameKey(options.suggested)===frameKey(options.fit);
    const fallback=pending?(sameAsFit?'fit':'manual'):'suggested';
    let selected=pending&&sameAsFit?'fit':'suggested',choice=fallback;
    let showBeyond=false,peekHeld=false,peekLatched=false,scale=1,drag=null;
    const peeking=()=>peekHeld||peekLatched;
    const canEdit=()=>checkCurrent(current)&&!loading&&!saving&&!stale&&!peeking();

    const choices=el('div','naiCropTreatments'),actions=el('div','naiCropEditActions'),position=el('div','naiCropPositionTools');
    const help=el('p','naiCollectionMuted');
    const save=cropButton('Save & next',()=>commit(choice));
    save.dataset.save='true';save.dataset.primary='true';save.dataset.cropPosition='true';
    const peekButton=cropButton('Peek original',()=>{peekLatched=!peekLatched;changeView();});
    const overflowButton=cropButton('Show photo beyond frame',()=>{showBeyond=!showBeyond;changeView();});
    overflowButton.dataset.cropPosition='true';
    actions.append(save,later,peekButton,overflowButton);
    later.onclick=()=>commit('later');
    tools.append(el('h3','',item.filename),el('p','naiCollectionMuted',proposal.reason||''),actions,help,choices,position);

    const treatments=new Map();
    const controls=cards.positionTools(preview,im,position,frame,{
     canEdit,onEdit(){choice='manual';selected=null;syncTreatment();},onRender:layoutOverflow,
     displayFrame:()=>peeking()?defaultFrame:frame,
    });
    for(const control of position.querySelectorAll('button,input,select')){
     control.dataset.save='true';control.dataset.cropPosition='true';
    }
    for(const [index,name] of ['fit','suggested','wider','fuller'].entries()){
     if(!options[name]||(pending&&name==='suggested'&&sameAsFit))continue;
     const key=String(index+1),option=options[name];
     const label='['+key+'] '+(pending&&name==='suggested'?'Keep current crop':option.label);
     const button=cropButton(label,event=>{
      if(!canEdit())return;
      endDrag();
      choice=name==='suggested'?fallback:name;selected=name;
      controls.setFrame(option.frame);syncTreatment();
      if(event.detail)view.focus({preventScroll:true});
     });
     button.dataset.save='true';button.dataset.cropPosition='true';
     button.setAttribute('aria-label',label);button.setAttribute('aria-keyshortcuts',key);
     const sample=el('img');sample.src=url;sample.alt='';sample.draggable=false;
     const sampleCard=cards.lightCard(item.entry,rows,owner,sample,true,mid);
     sampleCard.classList.add('naiCropTreatmentCard');sampleCard.setAttribute('aria-hidden','true');
     button.prepend(sampleCard);cards.applyFrame(sample,option.frame);
     treatments.set(key,{name,button});choices.append(button);
    }
    function syncTreatment(){
     for(const {name,button} of treatments.values())button.setAttribute('aria-pressed',String(name===selected));
    }
    function changeView(){
     if(!checkCurrent(current))return;
     endDrag();
     const mode=peeking()?'original':showBeyond?'overflow':'crop';
     view.dataset.mode=mode;
     peekButton.setAttribute('aria-pressed',String(peeking()));
     overflowButton.setAttribute('aria-pressed',String(showBeyond));
     const outside=mode==='overflow';
     for(const node of [overflowPhoto,aperture,boundary])node.hidden=!outside;
     if(!outside){scene.style.transform='';scale=1;}
     help.textContent=peeking()?'Original photo fitted in the card.':outside?
      'Solid outline: photo opening. Dashed outline: card edge. Drag to position or scroll to zoom.':
      'Drag the photo to position it. Scroll to zoom or hold Space to peek at the original.';
     controls.render();saveStatus();
    }
    // Measure the actual rendered photo and aperture in scene coordinates, then
    // scale the union with the card so even a large offset stays visible.
    function layoutOverflow(){
     if(view.dataset.mode!=='overflow')return;
     const origin=scene.getBoundingClientRect();
     const measure=node=>{
      const rect=node.getBoundingClientRect();
      return {x:(rect.left-origin.left)/scale,y:(rect.top-origin.top)/scale,w:rect.width/scale,h:rect.height/scale};
     };
     const photo=measure(im),card=measure(preview),windowRect=measure(opening);
     const width=view.clientWidth,height=view.clientHeight,pad=10;
     if(width<=2*pad||height<=2*pad||!card.w||!photo.w)return;
     let x=drag?.sceneX,y=drag?.sceneY;
     if(!drag){
      const left=Math.min(card.x,photo.x),top=Math.min(card.y,photo.y);
      const unionWidth=Math.max(card.x+card.w,photo.x+photo.w)-left;
      const unionHeight=Math.max(card.y+card.h,photo.y+photo.h)-top;
      scale=Math.min(1,(width-2*pad)/unionWidth,(height-2*pad)/unionHeight);
      x=(width-unionWidth*scale)/2-left*scale;
      y=(height-unionHeight*scale)/2-top*scale;
     }
     scene.style.transform='translate('+x+'px,'+y+'px) scale('+scale+')';
     view.dataset.sceneX=String(x);view.dataset.sceneY=String(y);
     for(const [node,rect] of [[overflowPhoto,photo],[aperture,windowRect],[boundary,card]]){
      node.style.left=x+rect.x*scale+'px';node.style.top=y+rect.y*scale+'px';
      node.style.width=rect.w*scale+'px';node.style.height=rect.h*scale+'px';
     }
    }
    view.addEventListener('wheel',event=>{
     if(!canEdit()||event.ctrlKey)return;
     event.preventDefault();
     const zoom=frame.zoom*Math.exp(-Math.max(-100,Math.min(100,event.deltaY))*.0025);
     controls.edit({zoom:Math.max(1,Math.min(3,zoom))});
    },{passive:false});
    view.addEventListener('pointerdown',event=>{
     if(drag||event.button!==0||event.isPrimary===false||!canEdit())return;
     const ref=controls.reference(),rect=ref?preview.getBoundingClientRect():opening.getBoundingClientRect();
     const width=ref?(preview.clientWidth*scale||rect.width)*ref.width:rect.width;
     const height=ref?(preview.clientHeight*scale||rect.height)*ref.height:rect.height;
     if(!width||!height)return;
     event.preventDefault();view.focus({preventScroll:true});
     drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:frame.x,top:frame.y,width,height,
      sceneX:Number(view.dataset.sceneX),sceneY:Number(view.dataset.sceneY)};
     view.dataset.dragging='true';view.setPointerCapture?.(event.pointerId);
    });
    view.addEventListener('pointermove',event=>{
     if(!drag||drag.id!==event.pointerId||!canEdit())return;
     controls.edit({
      x:drag.left+(event.clientX-drag.x)*100/drag.width,
      y:drag.top+(event.clientY-drag.y)*100/drag.height,
     });
    });
    function endDrag(event){
     if(!drag||(event&&event.pointerId!==drag.id))return;
     const {id}=drag;drag=null;delete view.dataset.dragging;
     if(view.hasPointerCapture?.(id))view.releasePointerCapture(id);
     layoutOverflow();
    }
    for(const type of ['pointerup','pointercancel','lostpointercapture'])view.addEventListener(type,endDrag);
    async function commit(choice){
     if(!checkCurrent(current)||loading||saving||(stale&&choice!=='later')||(peeking()&&choice!=='later'))return;
     if(choice==='later'&&stale){advance();return;}
     endDrag();
     const review={media_id:mid,token:proposal.token,choice};
     if(choice==='manual'){
      review.frame={...frame};
      if(!review.frame.reference)delete review.frame.reference;
     }
     if(await mutate('save',{reviews:[review]}))advance();
    }
    exception={
     onKey(event){
      if(event.ctrlKey||event.altKey||event.metaKey||event.shiftKey||/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)||event.target.isContentEditable)return;
      const preset=treatments.get(event.key)?.button;
      const command=event.key==='Enter'&&event.target.tagName!=='BUTTON'?save:preset;
      if(command&&!command.disabled){
       event.preventDefault();
       if(!event.repeat){
        command.click();
        if(preset)view.focus({preventScroll:true});
       }
      }
      if(event.key===' '&&event.target.tagName!=='BUTTON'){
       event.preventDefault();
       if(!event.repeat&&!saving){peekHeld=true;changeView();}
      }
     },
     releaseSpace(){if(peekHeld){peekHeld=false;changeView();}},
     endPeek(){if(peeking()){peekHeld=peekLatched=false;changeView();}},
     peeking,
     dispose(){endDrag();controls.dispose();},
    };
    syncTreatment();changeView();
    loading=false;saveStatus();
   }catch(e){
    if(checkCurrent(current)){
     loading=false;status.textContent='';m.error.textContent=e.message||String(e);
     later.textContent='Next crop';editor.append(later);saveStatus();
    }
   }
  }
  function advance(){
   const mid=exceptionIds.shift();
   marked.delete(mid);if(mid===anchor)anchor=null;remember();
   if(exceptionIds.length)drawException();else exitEditor();
  }
  m.wrap.addEventListener('keydown',event=>exception?.onKey(event));
  m.wrap.addEventListener('keydown',event=>{if(saving&&event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();}},true);
  m.wrap.addEventListener('keyup',event=>{if(event.key===' ')exception?.releaseSpace();});
  m.wrap.addEventListener('focusout',event=>{if(!event.relatedTarget||!editor.contains(event.relatedTarget))exception?.endPeek();});
  window.addEventListener('blur',clearPeek);
  reload(true);
 };

 const libraryToolbar=root.getElementById('addMediaBtn')?.parentNode;
 if(libraryToolbar){
  const open=el('button','','Review card crops');open.type='button';
  open.onclick=()=>cards.reviewCrops(root.getElementById('characterSelect')?.value);libraryToolbar.append(open);
 }
 let saveQueue=Promise.resolve();
 cards.debugPanel=function(entry,owner,kind,onSaved,rows){
  const panel=el('section','naiCardDebugPanel'),mid=entry.preview_id||entry.captain_id||entry.images[0],names=new Map(cards.editionNames),owned=new Set(entry.edition_settings?.traits||[]),automatic=new Set(entry.automatic_editions||[]),frame=frameFor(owner,mid);
  panel.setAttribute('aria-label','Debug tools for '+entry.name);
  const filename=el('strong','naiDebugFilename',entry.name);filename.title=entry.name;
  const metadata=metaFor(owner,mid),automaticFrame=metadata?.mode==='auto',positioning=cards.framingStatus(owner,mid);
  const crop=el('span','naiDebugCrop',automaticFrame?'Auto-positioned · '+(metadata.checked?'Checked':'Unchecked'):custom(frame)?'Custom crop':'Default crop');
  crop.dataset.custom=String(custom(frame));crop.dataset.positioning=positioning;
  if(automaticFrame){
   const trim=metadata.review_reason||(metadata.vertical_crop_percent>0
    ?`Full width preserved · ${metadata.vertical_crop_percent.toFixed(2)}% hidden at top and bottom`
    :`Full height preserved · ${Number(metadata.side_crop_percent||0).toFixed(2)}% hidden on each side`);
   crop.title=trim+' · '+(metadata.checked?'Checked':'Unchecked');
  }else{
   crop.title=custom(frame)?`X ${frame.x||0} · Y ${frame.y||0} · Zoom ${frame.zoom??1} · ${frame.fit||'contain'}${frame.reference?' · Saved reference':''}`:'Centered · 1× zoom · Fit whole photo';
  }
  const message=el('p','naiDebugMessage');message.setAttribute('role','status');
  function button(text,action,label){const b=el('button','',text);b.type='button';if(label)b.setAttribute('aria-label',label);b.onclick=action;return b;}
  function run(action){
   const controls=[...panel.querySelectorAll('button,select')].map(e=>[e,e.disabled]);controls.forEach(([e])=>e.disabled=true);message.textContent='Saving…';
   const work=saveQueue.then(action);saveQueue=work.catch(()=>{});
   work.then(()=>{message.textContent='Saved';},e=>{message.textContent=e.message||String(e);}).finally(()=>controls.forEach(([e,disabled])=>e.disabled=disabled));
  }
  function saveEdition(payload){run(async()=>{const current=await cards.load(owner),saved=await root.naiOutfitRequest('/api/collection/edition',{character_id:owner,revision:current.collection.revision,entry_id:entry.id,kind,...payload});cards.cache.set(owner,saved);await onSaved();});}
  const actions=el('div','naiDebugRow');actions.append(crop,button('Position / crop',()=>cards.adjust(owner,mid,'image:'+mid,onSaved,{entry,rows}), 'Position crop for '+entry.name),button('Edit edition',()=>cards.editEdition(entry,owner,kind,onSaved),'Edit traits and edition for '+entry.name));
  const reviewActions=el('div','naiDebugRow');
  if(automaticFrame){
   const saveFrame=(action,extra={})=>run(async()=>{const current=await cards.load(owner),saved=await root.naiOutfitRequest('/api/collection/'+action,{character_id:owner,revision:current.collection.revision,media_id:mid,token:metadata.token,...extra});cards.cache.set(owner,saved);await onSaved();});
   reviewActions.append(button(metadata.checked?'Mark unchecked':'Mark checked',()=>saveFrame('frame-review',{checked:!metadata.checked})),button('Restore default',()=>saveFrame('frame-default'),'Restore default positioning for '+entry.name));
  }
  const traits=el('div','naiDebugTraits');traits.setAttribute('aria-label','Card traits');
  for(const id of entry.owned_editions||[]){const chip=el('span','naiDebugTrait',names.get(id)||id);if(automatic.has(id))chip.append(el('small','','Auto'));if(owned.has(id))chip.append(button('×',()=>saveEdition({remove_traits:[id]}),'Remove '+(names.get(id)||id)+' trait'));traits.append(chip);}
  for(const title of entry.titles||[])if(title.id==='team_captain')traits.append(el('span','naiDebugTrait','Captain · Auto'));
  if(!traits.childElementCount)traits.append(el('span','','No traits'));
  const field=(label,values,value)=>{const l=el('label','',label),select=el('select');select.setAttribute('aria-label',label+' for '+entry.name);for(const [id,name]of values){const o=el('option','',name);o.value=id;select.append(o)}select.value=value;l.append(select);return [l,select];};
  const [displayLabel,display]=field('Frame',[['auto','Automatic'],['none','Base card'],...cards.editionNames.filter(([id])=>entry.owned_editions?.includes(id))],entry.edition_settings?.choice||'auto');display.onchange=()=>saveEdition({choice:display.value});
  const additions=cards.editionNames.filter(([id])=>!entry.owned_editions?.includes(id));const [addLabel,add]=field('Add trait',[['','Choose trait…'],...additions],'');add.disabled=!additions.length;add.onchange=()=>{if(add.value)saveEdition({add_traits:[add.value]});};
  panel.append(filename,actions);if(automaticFrame)panel.append(reviewActions);panel.append(traits,displayLabel,addLabel,message);return panel;
 };
})();
