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
 .naiCropToolbar{position:sticky;top:0;z-index:3;background:#111923;padding:8px 0;display:flex;flex-wrap:wrap;align-items:center;gap:.6rem;margin:0 0 1rem}
 .naiCropGrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,235px),1fr));gap:16px}
 .naiCropTile{min-width:0}.naiCropTile .naiPortraitCard{width:100%;height:auto;max-width:none}
 .naiCropTile .naiCropPreview{aspect-ratio:7/10}.naiCropTile .naiCropActions{display:flex;align-items:center;gap:6px;margin-top:5px}
 .naiCropActions label{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 `;
 cards.reviewCrops=function(owner,onClose){
  const excluded=new Set(),urls=new Set(),pageSize=12;
  let generation=0,page=0,snapshot,rows=[],queue=[],visible=[],saving=false,pending=0,stale=false,changed=false;
  const release=()=>{generation++;for(const url of urls)URL.revokeObjectURL(url);urls.clear();};
  const m=cards.modal('Review card crops',()=>{release();if(changed)onClose?.();});
  if(!owner){m.body.textContent='Choose a character to review card crops.';return;}
  const button=(name,click)=>{const b=el('button','',name);b.type='button';b.onclick=click;return b;};
  const toolbar=el('div','naiCropToolbar'),status=el('span'),grid=el('div','naiCropGrid');
  status.setAttribute('role','status');
  const previous=button('Previous',()=>{page--;draw();}),next=button('Next',()=>{page++;draw();});
  const refresh=button('Refresh',reload),approve=button('Approve selected',save);
  toolbar.append(approve,previous,next,refresh,status);
  m.body.append(el('p','','Uncheck crops to leave them for later. Adjust opens the full-size original and marks that crop reviewed when it loads.'),toolbar,grid);
  function sync(){
   const count=visible.filter(v=>v.ready&&v.check.checked).length;
   approve.textContent='Approve selected ('+count+')';
   approve.disabled=saving||stale||pending>0||!count;
   previous.disabled=saving||stale||page===0;next.disabled=saving||stale||(page+1)*pageSize>=queue.length;
   refresh.disabled=saving;
   for(const v of visible){v.check.disabled=saving||stale||!v.ready;v.adjust.disabled=saving||!v.ready;}
  }
  function use(data){
   snapshot=data;stale=false;rows=data.boards.find(b=>b.kind==='images').entries;
   const libraryMedia=new Map((root.naiGetLibrary?.()?.media||[]).map(m=>[m.id,m]));
   const seen=new Set();queue=[];
   for(const entry of rows){
    if(entry.flagged_for_removal)continue;
    for(const [side,mid] of entry.images.entries()){
     const meta=data.collection.frame_meta?.['image:'+mid];
     const photo=libraryMedia.get(mid);
     if(seen.has(mid)||meta?.mode!=='auto'||meta.checked||photo?.in_all===false||
        photo?.in_review||photo?.in_purgatory||photo?.flagged_for_removal)continue;
     seen.add(mid);
     queue.push({mid,token:meta.token,name:photo?.original_name||entry.name,entry:entry.duo_side?{...entry,duo_side:side?'back':'front'}:entry});
    }
   }
   page=Math.min(page,Math.max(0,Math.ceil(queue.length/pageSize)-1));draw();
  }
  async function reload(){
   release();const current=generation;stale=true;visible=[];grid.replaceChildren();
   status.textContent='Loading card crops…';m.error.textContent='';sync();
   try{const data=await cards.load(owner);if(current===generation)use(data);}
   catch(e){if(current===generation){status.textContent='';m.error.textContent=e.message||String(e);}}
  }
  function draw(){
   release();const current=generation;grid.replaceChildren();m.error.textContent='';
   const start=page*pageSize,slice=queue.slice(start,start+pageSize);
   status.textContent=slice.length?(start+1)+'–'+(start+slice.length)+' of '+queue.length+' unchecked crops':'No automatic crops are waiting for review.';
   visible=slice.map(item=>{
    const tile=el('article','naiCropTile'),preview=el('div','naiCropPreview','Loading original…'),actions=el('div','naiCropActions');
    const filename=item.entry.duo_side?item.name+' · '+item.entry.duo_side:item.name;
    const label=el('label'),check=el('input');check.type='checkbox';label.title=filename;
    check.onchange=()=>{if(check.checked)excluded.delete(item.token);else excluded.add(item.token);sync();};
    label.append(check,document.createTextNode(filename));
    const adjust=button('Adjust',()=>cards.adjust(owner,item.mid,'image:'+item.mid,()=>{changed=true;reload();},{entry:item.entry,rows}));
    adjust.setAttribute('aria-label','Adjust crop for '+filename);
    actions.append(label,adjust);tile.append(preview,actions);grid.append(tile);
    return {...item,preview,check,adjust,ready:false,filename};
   });
   pending=visible.length;sync();
   const work=visible.values();
   async function worker(){
    for(const v of work){
     if(current!==generation)return;
     let url;
     try{
      const original=await root.naiOutfitOriginal(v.mid);
      if(current!==generation)return;
      url=URL.createObjectURL(original);urls.add(url);
      const im=el('img');im.alt=v.filename;im.src=url;await im.decode();
      if(current!==generation)return;
      v.preview.replaceChildren(cards.lightCard(v.entry,rows,owner,im,true,v.mid));
      cards.applyFrame(im,snapshot.collection.frames['image:'+v.mid]);
      v.ready=true;v.check.checked=!excluded.has(v.token);
     }catch(e){
      if(current!==generation)return;
      if(url&&urls.delete(url))URL.revokeObjectURL(url);
      v.preview.textContent='Preview unavailable. Refresh to retry.';v.preview.title=e.message||String(e);
     }finally{if(current===generation){pending--;sync();}}
    }
   }
   for(let n=0;n<Math.min(3,pending);n++)worker();
  }
  async function save(){
   if(approve.disabled)return;
   const reviews=visible.filter(v=>v.ready&&v.check.checked).map(v=>({media_id:v.mid,token:v.token}));
   saving=true;sync();
   await m.run(async()=>{
    try{
     const saved=await root.naiOutfitRequest('/api/collection/frame-review-batch',{character_id:owner,revision:snapshot.collection.revision,reviews});
     cards.cache.set(owner,saved);changed=true;use(saved);
    }catch(e){stale=true;throw Error((e.message||String(e))+' Refresh this sheet before approving again.');}
   });
   saving=false;sync();
  }
  reload();
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
   const trim=metadata.vertical_crop_percent>0
    ?`Full width preserved · ${metadata.vertical_crop_percent.toFixed(2)}% hidden at top and bottom`
    :`Full height preserved · ${Number(metadata.side_crop_percent).toFixed(2)}% hidden on each side`;
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
