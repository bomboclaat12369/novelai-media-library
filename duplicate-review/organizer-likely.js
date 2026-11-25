// Each proposal stays local to this dialog until an explicit review decision.
const likelyDialog = el('dialog');
likelyDialog.id = 'likelyGroupsDialog';
likelyDialog.setAttribute('aria-label','Likely groups across posts');
const likelyStyle = el('style');
likelyStyle.textContent = `
 #likelyGroupsDialog{width:calc(100% - 16px);max-width:none;height:calc(100dvh - 16px);max-height:none;padding:0;--photo-size:230px}
 #likelyGroupsDialog[open]{display:flex;flex-direction:column}
 #likelyGroupsDialog h2,#likelyGroupsDialog h3{margin:0}
 #likelyGroupsDialog .match-body{flex:1;max-height:none;min-height:0;padding:8px 12px}
 #likelyGroupsDialog .match-body>p{margin:4px 0 8px}
 .likely-header,.likely-footer{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:7px 12px;flex:none}
 .likely-header{border-bottom:1px solid var(--line)}.likely-header h2{margin-right:auto!important}
 .likely-footer{border-top:1px solid var(--line)}.likely-footer .primary{margin-left:auto}
 #likelyGroupsDialog .likely-footer{padding-inline-end:max(5.5rem,calc(env(safe-area-inset-right) + 5rem))}
 .likely-tools{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:4px 0}
 .likely-footer .likely-error{color:#ffb7aa;font-weight:600}
 .likely-membership button{padding:2px 5px;margin-inline-start:5px;color:inherit;border-color:#8abbd0}
 .likely-discarding .match-photo:has(input:checked){border-color:#ee987f}
 .likely-status{margin:0;color:var(--muted);font-size:.92em}
 .likely-destination{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:5px}
 .likely-destination select,.likely-destination input{max-width:100%;min-width:150px}
 .likely-size{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;margin-inline-start:auto}
 .likely-destination .likely-size input{min-width:0;width:90px;padding:0;accent-color:var(--accent)}
 .likely-comparison,.likely-suggestions{min-width:0}
 .likely-comparison h3{font-size:1em;padding:2px 0 5px}
 .likely-photos{display:flex;flex-wrap:wrap;gap:6px;align-items:flex-start}
 .likely-photos .match-photo{--ratio:clamp(.4,var(--frame-ratio,.75),2.5);padding:3px;border-radius:6px;max-width:100%;
  flex:var(--ratio) 1 min(100%,calc(var(--photo-size) * 1.4 * var(--ratio)),calc(var(--photo-size) * 1.65))}
 .likely-photos .match-photo:has(input:checked){border-color:var(--accent)}
 .likely-photos .likely-enlarge{display:block;width:100%;padding:0;border:0;background:#0c1015}
 .likely-post-browser .match-photo.assigned{border:2px solid #78bbd7}
 .likely-post-browser .match-photo.located{outline:3px solid var(--accent);outline-offset:-3px}
 .likely-membership{display:block;margin:-2px -2px 3px;padding:3px 6px;border-radius:3px 3px 0 0;background:#294759;color:#eef9ff;font-size:.92em;font-weight:700;line-height:1.2;overflow-wrap:anywhere}
 .likely-photos .match-photo img{width:100%;height:auto;aspect-ratio:var(--ratio);max-height:min(70dvh,calc(var(--photo-size) * 1.8));object-fit:contain}
 .likely-photos label{display:flex;gap:6px;align-items:center;padding:4px 3px;cursor:pointer}
 .likely-photos input[type=checkbox]{width:18px;height:18px;flex:0 0 18px;margin:0;accent-color:var(--accent)}
 .likely-photos label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .likely-photos .likely-source{display:block;max-width:100%;padding:2px 4px;color:var(--accent);background:none;border:0;text-decoration:underline;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .likely-suggestions .match-examples{margin:0 0 8px}
 .likely-suggestions .match-examples img{max-width:none}
 .likely-post-browser{margin:8px 0;border:1px solid var(--line);border-radius:6px;padding:6px;min-width:0}
 .likely-post-browser summary{cursor:pointer;font-weight:600}
 .likely-post-controls{display:flex;gap:5px;align-items:center;flex-wrap:wrap;padding:6px 0}
 .likely-post-controls select{min-width:0;max-width:100%}
 .likely-post-columns{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
 .likely-post-columns input{width:88px;min-width:0;padding:0;accent-color:var(--accent)}
 .likely-post-columns output{min-width:2.2em;text-align:center}
 .likely-post-browser .likely-photos.fixed-columns{display:grid;grid-template-columns:repeat(var(--post-columns),minmax(0,1fr))}
 .likely-post-browser .fixed-columns .match-photo img{max-height:70dvh}
 .likely-post-controls [aria-pressed=true]{border-color:var(--accent);color:var(--accent)}
 .likely-post-merge-button{border-color:var(--accent);color:var(--accent)}
 .likely-merge-dialog{width:min(470px,94vw);max-height:85dvh;overflow:auto}
 .likely-merge-dialog h2{margin:0}
 .likely-merge-dialog ul{margin:8px 0;padding-inline-start:22px}
 .likely-merge-actions{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:8px;margin-top:14px}
 .likely-photos .unavailable{color:var(--muted);font-size:.8em}
 @media(min-width:960px) and (min-height:520px){
  #likelyGroupsDialog .match-body:has(.likely-post-browser[open]){display:flex;flex-direction:column;overflow:hidden}
  .likely-comparison:has(.likely-post-browser[open]){flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:10px}
  .likely-comparison:has(.likely-post-browser[open])>.likely-suggestions,.likely-comparison>.likely-post-browser[open]{overflow-y:auto;min-height:0;overscroll-behavior:contain}
  .likely-comparison>.likely-post-browser[open]{margin:0}
  .likely-post-browser[open] .likely-post-controls{position:sticky;top:0;z-index:1;background:var(--bg)}
 }
 @media(max-width:640px){
  #likelyGroupsDialog{width:100%;height:100dvh;border-radius:0}
  #likelyGroupsDialog .match-body,.likely-header,.likely-footer{padding:6px}
  .likely-header,.likely-footer{gap:4px}.likely-size{margin-inline-start:0}
 }
`;
document.head.append(likelyStyle);
document.body.append(likelyDialog);

function confirmMatchingPostMerge(plan){
 const dialog=el('dialog',undefined,'likely-merge-dialog');
 const title=el('h2','Merge into one Set');
 dialog.setAttribute('aria-label',title.textContent);
 const total=el('p');total.append(el('strong',plan.name+' · '+plan.count+' photos after merging in this collection'));
 const counts=el('ul');counts.append(el('li',plan.from_post+' from '+plan.post));
 if(plan.checked_elsewhere)counts.append(el('li',plan.checked_elsewhere+' checked from other matching posts'));
 if(plan.other_members)counts.append(el('li',plan.other_members+' additional photos already in the Sets being kept together'));
 dialog.append(title,total,counts);
 if(plan.sets.length){
  const sets=el('ul');
  for(const group of plan.sets){
   sets.append(el('li',(group.id===plan.target?'Keep ':'Merge in ')+group.name+' ('+group.count+')'));
  }
  dialog.append(sets);
 }else dialog.append(el('p','This creates a new Workbench Set.'));
 if(plan.skipped)dialog.append(el('p',plan.skipped+' unavailable photos from the post will stay out.'));
 const hold=el('input'),label=el('label');
 hold.type='checkbox';hold.checked=hold.disabled=plan.under_review;
 label.append(hold,document.createTextNode(' Keep merged Set under review'));
 const actions=el('div',undefined,'likely-merge-actions');
 const cancel=button('Cancel',()=>dialog.close());
 actions.append(cancel,button('Merge into '+plan.name,()=>dialog.close('merge'),'primary'));
 dialog.append(label,actions);document.body.append(dialog);
 return new Promise(resolve=>{
  dialog.onclose=()=>{const result=dialog.returnValue==='merge'?hold.checked:null;dialog.remove();resolve(result)};
  dialog.showModal();cancel.focus();
 });
}

async function openLikelyGroups(){
 const job = data.job, choices = new Map();
 let session='', index=0, page=null, dirty=false, closed=false, breadth='closest', saving=false;
 matchDialog.close();
 const header=el('div',undefined,'likely-header'), body=el('div',undefined,'match-body');
 const footer=el('div',undefined,'likely-footer'), status=el('p','Finding cross-post groups…','likely-status');
 status.setAttribute('role','status');
 const prev=button('Previous group',()=>task(()=>load(index-1)));
 const next=button('Next group',()=>task(()=>load(index+1)));
 const close=button('Close',()=>{if(!saving)likelyDialog.close()});
 const tier=el('select');tier.setAttribute('aria-label','Suggestion range');
 tier.add(new Option('Closest matches','closest'));tier.add(new Option('More from post order','broader'));
 tier.add(new Option('Finish partial Sets','partial'));
 tier.onchange=()=>task(async()=>{breadth=tier.value;session='';choices.clear();await load()});
 const heading=el('h2','Likely groups across posts');
 header.append(heading,tier,prev,next,close);
 prev.disabled=next.disabled=true;
 likelyDialog.replaceChildren(header,body,footer);
 footer.append(status);
 likelyDialog.showModal();
 const protectSave=event=>{if(saving){event.preventDefault();event.returnValue=''}};
 window.addEventListener('beforeunload',protectSave);
 likelyDialog.oncancel=event=>{if(saving)event.preventDefault()};
 async function refreshPost(){
  if(data.job!==job||!view)return;
  try{const saved=captureSession();await open(currentKind,currentId,view.offset||0,false);await related();await restoreScroll(saved)}
  catch(error){toast(error.message)}
 }
 likelyDialog.onclose=async()=>{closed=true;window.removeEventListener('beforeunload',protectSave);if(dirty)await refreshPost()};
 await saveDraft();

 function preview(photo,list){
  for(const p of list)images.set(p.id,p);
  viewerIds=list.map(p=>p.id);viewerAt=viewerIds.indexOf(photo.id);
  drawViewer();$('viewer').showModal();
 }
 function photoFigure(photo,list){
  const figure=el('figure',undefined,'match-photo'),b=button('',()=>preview(photo,list),'likely-enlarge'),im=el('img');
  function setFrame(width,height){
   if(width>0&&height>0)figure.style.setProperty('--frame-ratio',String(width/height));
  }
  if(photo.dimensions)setFrame(...photo.dimensions);
  else im.onload=()=>setFrame(im.naturalWidth,im.naturalHeight);
  b.setAttribute('aria-label','Enlarge '+photo.name);
  im.loading='lazy';im.decoding='async';im.src=imageURL(photo.id,1000);im.alt=photo.name;
  b.append(im);figure.append(b);return figure;
 }
 async function load(at=0, destination){
  heading.textContent=breadth==='partial'?'Finish partial Sets':'Likely groups across posts';
  likelyDialog.setAttribute('aria-label',heading.textContent);
  status.textContent=breadth==='partial'?'Looking for photos from the same post…':'Finding cross-post groups…';
  try{
   const result=await api('likely-groups',{job,session,breadth,offset:at,...(destination===undefined?{}:{destination})});
   if(closed||!likelyDialog.open)return;
   session=result.session;index=result.offset;page=result;
   if(page.destination_set?.id&&!data.sets.some(g=>g.id===page.destination_set.id))data.sets.push(page.destination_set);
   const saved=choices.get(page.key);
   if(destination===undefined&&saved&&saved.target!==page.destination){await load(index,saved.target);return}
   render();
  }catch(e){
   if(closed)return;
   status.textContent=e.message;
   body.replaceChildren();footer.replaceChildren(status,button('Refresh groups',()=>task(restart)));
   prev.disabled=next.disabled=true;
  }
 }
 async function restart(){
  await refresh();
  if(data.job!==job){likelyDialog.close();return}
  session='';choices.clear();await load();
 }
 async function analyze(){
  try{
   let progress=await api('index',{job,revision:data.state.revision,for_set_matching:true});
   while(progress.running&&!closed){
    status.textContent=progress.phase+' · '+progress.done+' / '+progress.total;
    await new Promise(resolve=>setTimeout(resolve,750));
    if(!closed)progress=await api('progress');
   }
   if(closed)return;
   if(progress.phase!=='Visual analysis saved'&&!progress.phase.startsWith('All saved images already indexed')){
    throw Error(progress.phase);
   }
   await restart();
  }catch(e){status.textContent=e.message}
 }
 function render(){
  body.replaceChildren();body.scrollTop=0;footer.replaceChildren(status);
  status.classList.remove('likely-error');
  prev.disabled=!index;next.disabled=index+1>=page.total;
  const missing=data.match_stills-data.match_analyzed;
  if(missing>0){
   footer.append(button('Analyze remaining photos ('+missing+')',()=>task(analyze)));
  }
  if(data.state.undo?.likely_review){
   footer.append(button('Undo last review',()=>task(async()=>{await mutate('undo');dirty=true;await restart()})));
  }
  if(!page.total){
   status.textContent=breadth==='partial'?'No partial Sets with suggested photos.':'No pending cross-post groups.';
   body.append(el('p',breadth==='closest'?'Choose More from post order to look for additional groups.':'Other unmatched photos are available in Review unmatched photos.'));
   return;
  }
  status.textContent='Group '+(index+1)+' of '+page.total+' · '+page.photos_left+' suggested photos left';
  const state=choices.get(page.key)||{selected:new Set(page.photos.map(p=>p.id)),target:page.destination,details:new Map()};
  if(!state.selected)state.selected=new Set(state.splitting&&page.photos.length>2?[]:page.photos.map(p=>p.id));
  const discarding=!!state.discards;
  body.classList.toggle('likely-discarding',discarding);
  if(!state.named)state.name=page.new_name;
  choices.set(page.key,state);
  const destination=el('div',undefined,'likely-destination'), label=el('label','Destination Set');
  const picker=el('select');picker.setAttribute('aria-label','Destination Set');
  picker.add(new Option('New draft Set',''));
  const candidates=new Set([page.proposed_target,...page.alternatives]);
  for(const set of data.sets.filter(s=>!s.in_purgatory).sort((a,b)=>Number(candidates.has(b.id))-Number(candidates.has(a.id))||a.name.localeCompare(b.name))){
   const note=set.id===page.proposed_target?' · suggested':candidates.has(set.id)?' · possible match':'';
   picker.add(new Option(set.name+note+(set.under_review?' · under review':''),set.id));
  }
  picker.value=state.target;
  async function chooseTarget(target,anchor){
   state.target=target;
   state.destinationAnchor=anchor;
   const scroll=browser.scrollTop;
   if(currentPage)state.postOffset=currentPage.offset;
   state.postScroll=scroll;
   await load(index,target);
  }
  picker.onchange=()=>task(()=>chooseTarget(picker.value));
  destination.append(label,picker);
  let name;
  if(!state.target){
   name=el('input');name.value=state.name;name.setAttribute('aria-label','New Set name');
   name.maxLength=250;name.oninput=()=>{state.name=name.value;state.named=true;if(state.details.has(''))state.details.get('').name=name.value};destination.append(name);
  }
  destination.append(button('Set details',()=>{
   const target=state.target, previous=state.details.get(target);
   openColors(target);
   if(!target)$('setEditName').value=state.name;
   if(previous){
    $('setEditName').value=previous.name;
    $('setColors').value=previous.colors.join(', ');
    renderCategoryChoices(previous.categories);
    $('setFavorite').checked=previous.favorite;
    if(target)$('setPurgatory').checked=previous.in_purgatory;
   }
   $('saveSetColors').textContent='Apply to group';
   applyPendingSetDetails=values=>{
    state.details.set(target,values);
    if(!target){state.named=true;state.name=values.name;name.value=values.name}
   };
  }));
  const sizeLabel=el('label','Photo size','likely-size'),size=el('input');
  size.type='range';size.min='150';size.max='420';size.step='10';
  size.value=localStorage.getItem('organizer-likely-photo-size')||'230';
  const applySize=()=>likelyDialog.style.setProperty('--photo-size',size.value+'px');
  size.oninput=applySize;
  size.onchange=()=>localStorage.setItem('organizer-likely-photo-size',size.value);
  applySize();sizeLabel.append(size);destination.append(sizeLabel);
  body.append(destination);
  const hint=discarding?'Check photos in either pane to send to Discard. You can restore them from Discarded.':
   state.splitting||page.remaining_group?'Check one shoot at a time. After saving, the remaining photos stay here.':
   'Check the photos that belong to this shoot. Your selection is saved when you approve.';
  body.append(el('p',hint,'muted'));
  if(page.source_reason)body.append(el('p',page.source_reason));
  const comparison=el('div',undefined,'likely-comparison'), suggestions=el('section',undefined,'likely-suggestions');
  comparison.append(suggestions);body.append(comparison);
  const suggestionTools=el('div',undefined,'likely-tools');
  suggestionTools.append(el('h3',page.remaining_group?'Remaining photos':'Suggested photos'));
  if(!discarding){
   const split=button('Split group',()=>task(async()=>{
    state.selected.clear();state.splitting=true;await chooseTarget('');
   }));
   split.title='Start with an empty selection and save each shoot separately.';
   if(page.photos.length>1&&!state.splitting)suggestionTools.append(split);
   suggestionTools.append(button('Select suggested',()=>{for(const p of page.photos)state.selected.add(p.id);updateSelection()}),
    button('Clear selection',()=>{state.selected.clear();updateSelection()}));
  }
  suggestions.append(suggestionTools);
  const proposed=el('div',undefined,'likely-photos');
  suggestions.append(proposed);
  for(const photo of page.photos){
   const figure=photoChoice(photo,page.photos);
   if(page.source_posts?.some(post=>post.id===photo.source_key)){
    const label=photo.source_label||'Source post';
    const link=button(label,()=>openPost(photo.source_key,photo.id),'small likely-source');
    link.title='View post '+label;link.setAttribute('aria-label',link.title);figure.append(link);
   }else if(photo.source_label)figure.append(el('small',photo.source_label));
   proposed.append(figure);
  }
  if(state.target){
   const refTools=el('div',undefined,'likely-tools');
   refTools.append(el('h3','Already in the destination Set'));
   if(!discarding)refTools.append(button('Use a separate Set',()=>task(async()=>{
    state.separateFrom=state.target;
    if(!state.named&&page.separate_name){state.name=page.separate_name;state.named=true}
    await chooseTarget('');
    const field=body.querySelector('[aria-label="New Set name"]');field?.focus();field?.select();
   })));
   suggestions.append(refTools);
   const refs=el('div',undefined,'match-examples likely-photos');
   for(const photo of page.references)refs.append(photoFigure(photo,page.references));
   suggestions.append(refs);
  }
  function photoChoice(photo,list){
   const figure=photoFigure(photo,list), check=el('input');
   const selected=discarding?state.discards:state.selected;
   check.type='checkbox';check.value=photo.id;check.checked=selected.has(photo.id);check.disabled=!discarding&&!!photo.unavailable_reason;
   const caption=el('label'), text=el('span',(photo.suggested?'Suggested · ':'')+(photo.source_position?'#'+photo.source_position+' · ':'')+(photo.display_name||photo.name));
   text.title=photo.display_name||photo.name;caption.append(check,text);
   check.setAttribute('aria-label',(discarding?'Discard ':'Include ')+photo.name);
   check.onchange=()=>{
    if(check.checked)selected.add(photo.id);else selected.delete(photo.id);
    updateSelection();
   };
   figure.append(caption);
   if(photo.set_names?.length){
    figure.classList.add('assigned');
    const band=el('div','In '+photo.set_names.join(', '),'likely-membership');
    if(!discarding)for(const [id,label] of Object.entries(photo.destination_sets||{})){
     if(id===state.target){band.append(document.createTextNode(' · Destination'));continue}
     const use=button('Use '+label,()=>task(()=>chooseTarget(id,photo.id)));
     use.setAttribute('aria-label','Use '+label+' as destination');band.append(use);
    }
    figure.prepend(band);
   }else if(photo.unavailable_reason)figure.append(el('small',photo.unavailable_reason,'unavailable'));
   return figure;
  }
  const browser=el('details',undefined,'likely-post-browser'), postPicker=el('select');
  const controls=el('div',undefined,'likely-post-controls'), postStatus=el('span'), extraGrid=el('div',undefined,'likely-photos');
  const posts=page.source_posts||[], groupKey=page.key;
  let request=0, displayed='', currentPage=null, selectableIds=null;
  postPicker.setAttribute('aria-label','Matching post');
  for(const post of posts)postPicker.add(new Option(post.label,post.id));
  if(!posts.some(p=>p.id===state.post))state.post=page.photos.find(p=>posts.some(post=>post.id===p.source_key))?.source_key||posts[0]?.id;
  postPicker.value=state.post||'';
  const back=button('Previous photos',()=>showPost(currentPage.offset-currentPage.limit),'small');
  const more=button('Next photos',()=>showPost(currentPage.offset+currentPage.limit),'small');
  const similar=button('Group similar images',()=>{
   state.postOrder=state.postOrder==='similar'?'original':'similar';
   showPost(undefined,state.anchor);
  },'small');
  similar.title='Toggle between visual grouping and original post order.';
  const bulkSelect=button('Select entire post',()=>{
   const remove=selectableIds.every(id=>state.selected.has(id));
   for(const id of selectableIds){
    if(remove)state.selected.delete(id);else state.selected.add(id);
   }
   updateSelection();
  },'small');
  bulkSelect.title='Select available photos across all pages. Choose a Set on an assigned photo to add only the checked photos to it.';
  const merge=button('Merge into one Set…',()=>task(mergePost),'small likely-post-merge-button');
  merge.title='Combine the whole open post and checked photos with their existing Sets.';
  const columnsLabel=el('label','Photos per row','likely-post-columns');
  const columns=el('input'), columnCount=el('output');
  columns.type='range';columns.min='0';columns.max='8';columns.step='1';
  columns.setAttribute('aria-label','Matching post photos per row');
  columns.title='Auto follows Photo size. Choose 1 to 8 for a fixed number per row.';
  columns.value=localStorage.getItem('organizer-likely-post-columns')||'0';
  function applyColumns(){
   const count=columns.valueAsNumber;
   extraGrid.classList.toggle('fixed-columns',count>0);
   extraGrid.style.setProperty('--post-columns',String(count||1));
   columnCount.textContent=count?String(count):'Auto';
   columns.setAttribute('aria-valuetext',count?String(count)+' per row':'Auto');
  }
  columns.oninput=applyColumns;
  columns.onchange=()=>localStorage.setItem('organizer-likely-post-columns',columns.value);
  applyColumns();columnsLabel.append(columns,columnCount);
  postStatus.setAttribute('role','status');controls.append(postPicker,similar,bulkSelect,merge,columnsLabel,back,more,postStatus);
  if(discarding){bulkSelect.hidden=true;merge.hidden=true}
  browser.append(el('summary','Browse matching posts'),controls,extraGrid);
  if(posts.length)comparison.append(browser);
  async function showPost(at,focusId){
   const source=postPicker.value, serial=++request;
   if(source!==displayed)selectableIds=null;
   state.post=source;state.postOffset=at;displayed=source;
   browser.scrollTop=0;
   currentPage=null;merge.disabled=bulkSelect.disabled=back.disabled=more.disabled=true;
   similar.setAttribute('aria-pressed',String(state.postOrder==='similar'));
   extraGrid.replaceChildren();postStatus.textContent='Loading photos…';
   try{
    const result=await api('likely-groups',{job,session,key:groupKey,source_post:source,
     post_context:true,focus_id:focusId,post_offset:at,post_order:state.postOrder||'original',include_selectable:selectableIds===null});
    if(serial!==request||!browser.isConnected||closed)return;
    if(result.selectable_ids)selectableIds=result.selectable_ids;
    currentPage=result;state.postOffset=at===undefined?undefined:result.offset;
    postStatus.textContent=result.total?(result.offset+1)+'–'+(result.offset+result.photos.length)+' of '+result.total+' photos':'No photos in this post.';
    if(at===undefined&&focusId&&result.focus_id!==focusId)postStatus.textContent+=' · Requested photo unavailable';
    else if(at===undefined&&result.total&&!result.focus_id)postStatus.textContent+=' · No visible match in this post';
    if(at===undefined)state.anchor=result.focus_id;
    back.disabled=!result.offset;more.disabled=result.offset+result.limit>=result.total;
    for(const photo of result.photos){
     const figure=photoChoice(photo,result.photos);extraGrid.append(figure);
     if(photo.id!==result.focus_id)continue;
     figure.classList.add('located');figure.tabIndex=-1;
     postStatus.textContent+=' · Located #'+photo.source_position;
     requestAnimationFrame(()=>{
      if(serial!==request||!browser.open||!figure.isConnected||closed)return;
      figure.scrollIntoView({block:'center',inline:'nearest'});figure.focus({preventScroll:true});
     });
    }
    if(state.postScroll!=null){browser.scrollTop=state.postScroll;delete state.postScroll}
    updateSelection();
   }catch(error){if(serial===request&&browser.isConnected){postStatus.textContent=error.message;displayed='';extraGrid.append(button('Retry',()=>showPost(at,focusId)))}}
  }
  function openPost(source,focusId){
   state.postOrder='original';
   postPicker.value=source;browser.open=true;
   showPost(undefined,focusId);
   browser.querySelector('summary').scrollIntoView({block:'nearest'});postPicker.focus({preventScroll:true});
  }
  browser.ontoggle=()=>{
   state.browsing=browser.open;
   if(browser.open&&!displayed)showPost(state.postOffset,state.anchor);
   if(!browser.open){request++;displayed='';state.postOffset=undefined;state.postOrder='original'}
  };
  postPicker.onchange=()=>{state.postOrder='original';showPost()};
  if(state.browsing)browser.open=true;
  function runDecision(action,hold=false){
   if(busy){if(!saving)status.textContent='Workbench is finishing the previous action. Try again in a moment.';return}
   return task(()=>decide(action,hold));
  }
  const dismiss=button('Dismiss group',()=>runDecision('dismiss_likely'));
  const approve=button('Approve group',()=>runDecision('approve_likely'),'primary');
  const hold=button('Approve and hold for review',()=>runDecision('approve_likely',true));
  hold.title='Save the checked photos to this Set and keep the Set in Workbench until promoted.';
  function discardMode(on){
   if(currentPage){state.postOffset=currentPage.offset;state.postScroll=browser.scrollTop}
   const scroll=body.scrollTop, within=suggestions.scrollTop;
   if(on)state.discards=new Set();else delete state.discards;
   render();body.scrollTop=scroll;body.querySelector('.likely-suggestions').scrollTop=within;
  }
  const discard=button('Discard photos…',()=>discardMode(true));
  const cancelDiscard=button('Cancel discard',()=>discardMode(false));
  const sendDiscard=button('Send to Discard',()=>runDecision('discard_likely'),'primary');
  if(discarding)footer.append(cancelDiscard,sendDiscard);
  else footer.append(dismiss,discard,hold,approve);
  function updateSelection(){
   for(const check of comparison.querySelectorAll('input[type=checkbox]'))check.checked=(discarding?state.discards:state.selected).has(check.value);
   bulkSelect.disabled=!currentPage||!selectableIds?.length;
   merge.disabled=!currentPage;
   const allInPost=selectableIds?.length&&selectableIds.every(id=>state.selected.has(id));
   bulkSelect.textContent=allInPost?'Deselect entire post':'Select entire post';
   const count=state.selected.size;
   const entireGroup=count===page.photos.length&&page.photos.every(photo=>state.selected.has(photo.id));
   approve.textContent=(entireGroup?'Approve group (':'Approve selected (')+count+')';
   hold.disabled=approve.disabled=count<(state.target?1:2);
   if(state.splitting)approve.textContent='Save Set ('+count+')';
   sendDiscard.textContent='Send to Discard ('+(state.discards?.size||0)+')';
   sendDiscard.disabled=!state.discards?.size;
  }
  updateSelection();
  const explanation=el('details'),cal=page.training;
  explanation.append(el('summary','How suggestions are ranked'));
  const wording=breadth==='partial'?'Suggestions come from a single post with photos already in the same Set. Each suggested photo has at least two visual matches in that Set.':cal.adapted?'Workbench tuned outfit and setting weights using confirmed Sets. On '+cal.held_out_sets+
   ' separate Sets, the first cross-post reference matched the shoot '+Math.round(100*cal.baseline)+'% before tuning and '+
   Math.round(100*cal.candidate)+'% after tuning, averaged per Set.':'Workbench is using the standard outfit and setting weights. It checks possible adjustments using confirmed Sets from different posts.';
  explanation.append(el('p',wording));suggestions.append(explanation);
  async function mergePost(){
   const serial=request, payload={session,key:groupKey,source_post:postPicker.value,ids:[...state.selected],
    target:state.target,name:state.name,set_details:state.details.get(state.target)};
   try{
    const plan=await api('post-merge-preview',{job,...payload});
    if(closed||!browser.isConnected||serial!==request)return;
    if(state.target!==payload.target||state.name!==payload.name||state.selected.size!==payload.ids.length||
       !payload.ids.every(id=>state.selected.has(id))){
     toast('Your selection changed. Open Merge into one Set again.');return;
    }
    const hold=await confirmMatchingPostMerge(plan);
    if(hold===null)return;
    await mutate('merge_likely_post',{...payload,stamp:plan.stamp,hold_for_review:hold});
    dirty=true;choices.delete(groupKey);
    for(const [key,saved] of choices){
     if(saved.target&&!data.sets.some(g=>g.id===saved.target&&!g.in_purgatory))choices.delete(key);
    }
    if(closed){await refreshPost();return}
    await load(index);toast('Merged into '+plan.name+' · '+plan.count+' photos');
   }catch(e){
    if(closed)return;
    postStatus.textContent=e.message;
    if(!footer.querySelector('[data-reload]')){
     const reload=button('Refresh groups',()=>task(restart));reload.dataset.reload='1';footer.prepend(reload);
    }
   }
  }
  async function decide(action,holdForReview=false){
   if(saving)return;
   const ids=[...(discarding?state.discards:state.selected)];
   const key=page.key, target=state.target;
   const name=state.details.get(target)?.name||data.sets.find(g=>g.id===target)?.name||state.name;
   saving=true;body.inert=header.inert=true;
   const buttons=[...footer.querySelectorAll('button:not(:disabled)')];for(const b of buttons)b.disabled=true;
   status.classList.remove('likely-error');
   status.textContent=discarding?'Sending photos to Discard…':action==='dismiss_likely'?'Dismissing group…':'Saving '+ids.length+' photos to '+name+'…';
   try{
    const result=await mutate(action,{session,key,ids,target,name:state.name,set_details:state.details.get(target),
     hold_for_review:holdForReview,keep_remaining:true,separate:!!(state.splitting||state.separateFrom),separate_from:state.separateFrom,
     destination_anchor:state.destinationAnchor,
     retain_ids:discarding?[...state.selected].filter(i=>!state.discards.has(i)):undefined});
    if(!result)return;
    dirty=true;choices.delete(key);
    const left=result.likely_result?.remaining_key;
    if(left){
     if(discarding){
      state.selected=new Set(result.likely_result.retained_ids);
      if(ids.includes(state.destinationAnchor))delete state.destinationAnchor;
      delete state.discards;
      if(currentPage){state.postOffset=currentPage.offset;state.postScroll=browser.scrollTop}
      choices.set(left,state);
     }else{
      choices.set(left,{selected:null,target:'',details:new Map(),splitting:state.splitting,
       post:state.post,postOrder:state.postOrder,browsing:state.browsing,postOffset:currentPage?.offset});
     }
    }
    if(closed){await refreshPost();return}
    await load(result.likely_result?.offset??index);
    const message=discarding?'Sent '+ids.length+' to Discard':action==='dismiss_likely'?'Group dismissed':'Saved '+ids.length+' to '+name;
    status.prepend(document.createTextNode(message+' · '));
   }catch(e){
    if(closed)return;
    status.classList.add('likely-error');
    status.textContent='Could not '+(discarding?'discard photos':action==='dismiss_likely'?'dismiss group':'approve group')+'. '+e.message;
    if(!footer.querySelector('[data-reload]')){
     const reload=button('Refresh groups',()=>task(restart));reload.dataset.reload='1';footer.prepend(reload);
    }
   }finally{saving=false;body.inert=header.inert=false;for(const b of buttons)b.disabled=false}
  }
 }
 await load();
}
