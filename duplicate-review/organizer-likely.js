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
 .likely-post-controls [aria-pressed=true]{border-color:var(--accent);color:var(--accent)}
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

async function openLikelyGroups(){
 const job = data.job, choices = new Map();
 let session='', index=0, page=null, dirty=false, closed=false, breadth='closest';
 matchDialog.close();
 const header=el('div',undefined,'likely-header'), body=el('div',undefined,'match-body');
 const footer=el('div',undefined,'likely-footer'), status=el('p','Finding cross-post groups…','likely-status');
 status.setAttribute('role','status');
 const prev=button('Previous group',()=>task(()=>load(index-1)));
 const next=button('Next group',()=>task(()=>load(index+1)));
 const close=button('Close',()=>likelyDialog.close());
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
 async function refreshPost(){
  if(data.job!==job||!view)return;
  try{const saved=captureSession();await open(currentKind,currentId,view.offset||0,false);await related();await restoreScroll(saved)}
  catch(error){toast(error.message)}
 }
 likelyDialog.onclose=async()=>{closed=true;if(dirty)await refreshPost()};
 await saveDraft();

 function preview(photo,list){
  for(const p of list)images.set(p.id,p);
  viewerIds=list.map(p=>p.id);viewerAt=viewerIds.indexOf(photo.id);
  drawViewer();$('viewer').showModal();
 }
 function photoFigure(photo,list){
  const figure=el('figure',undefined,'match-photo'),b=button('',()=>preview(photo,list)),im=el('img');
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
  picker.onchange=()=>task(async()=>{state.target=picker.value;await load(index,state.target)});
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
  body.append(el('p','Check the photos that belong to this shoot. Your selection is saved when you approve.','muted'));
  if(page.source_reason)body.append(el('p',page.source_reason));
  const comparison=el('div',undefined,'likely-comparison'), suggestions=el('section',undefined,'likely-suggestions');
  comparison.append(suggestions);body.append(comparison);
  suggestions.append(el('h3','Suggested photos'));
  const proposed=el('div',undefined,'likely-photos');
  suggestions.append(proposed);
  for(const photo of page.photos){
   const figure=photoChoice(photo,page.photos);
   if(page.source_posts?.some(post=>post.id===photo.source_key)){
    const label=photo.source_label||'Source post';
    const link=button(label,()=>openPost(photo.source_key),'small likely-source');
    link.title='View post '+label;link.setAttribute('aria-label',link.title);figure.append(link);
   }else if(photo.source_label)figure.append(el('small',photo.source_label));
   proposed.append(figure);
  }
  if(page.references.length){
   suggestions.append(el('h3','Already in the destination Set'));
   const refs=el('div',undefined,'match-examples likely-photos');
   for(const photo of page.references)refs.append(photoFigure(photo,page.references));
   suggestions.append(refs);
  }
  function photoChoice(photo,list){
   const figure=photoFigure(photo,list), check=el('input');
   check.type='checkbox';check.value=photo.id;check.checked=state.selected.has(photo.id);check.disabled=!!photo.unavailable_reason;
   const caption=el('label'), text=el('span',(photo.source_position?'#'+photo.source_position+' · ':'')+(photo.display_name||photo.name));
   text.title=photo.display_name||photo.name;caption.append(check,text);
   check.setAttribute('aria-label','Include '+photo.name);
   check.onchange=()=>{
    if(check.checked)state.selected.add(photo.id);else state.selected.delete(photo.id);
    updateSelection();
   };
   figure.append(caption);
   if(photo.unavailable_reason)figure.append(el('small',photo.unavailable_reason,'unavailable'));
   return figure;
  }
  const browser=el('details',undefined,'likely-post-browser'), postPicker=el('select');
  const controls=el('div',undefined,'likely-post-controls'), postStatus=el('span'), extraGrid=el('div',undefined,'likely-photos');
  const posts=page.source_posts||[], groupKey=page.key;
  let request=0, displayed='', currentPage=null, selectableIds=null;
  postPicker.setAttribute('aria-label','Matching post');
  for(const post of posts)postPicker.add(new Option(post.label,post.id));
  if(!posts.some(p=>p.id===state.post))state.post=posts[0]?.id;
  postPicker.value=state.post||'';
  const back=button('Previous photos',()=>showPost(currentPage.offset-currentPage.limit),'small');
  const more=button('Next photos',()=>showPost(currentPage.offset+currentPage.limit),'small');
  const similar=button('Group similar images',()=>{
   state.postOrder=state.postOrder==='similar'?'original':'similar';
   showPost(0);
  },'small');
  similar.title='Toggle between visual grouping and original post order.';
  const bulkSelect=button('Select entire post',()=>{
   const remove=selectableIds.every(id=>state.selected.has(id));
   for(const id of selectableIds){
    if(remove)state.selected.delete(id);else state.selected.add(id);
   }
   updateSelection();
  },'small');
  bulkSelect.title='Change the selection for every available photo in this post, across all pages.';
  postStatus.setAttribute('role','status');controls.append(postPicker,similar,bulkSelect,back,more,postStatus);
  browser.append(el('summary','Browse matching posts'),controls,extraGrid);
  if(posts.length)comparison.append(browser);
  async function showPost(at){
   const source=postPicker.value, serial=++request;
   if(source!==displayed)selectableIds=null;
   state.post=source;state.postOffset=at;displayed=source;
   browser.scrollTop=0;
   currentPage=null;bulkSelect.disabled=back.disabled=more.disabled=true;
   similar.setAttribute('aria-pressed',String(state.postOrder==='similar'));
   extraGrid.replaceChildren();postStatus.textContent='Loading photos…';
   try{
    const result=await api('likely-groups',{job,session,key:groupKey,source_post:source,
     post_offset:at,post_order:state.postOrder||'original',include_selectable:selectableIds===null});
    if(serial!==request||!browser.isConnected||closed)return;
    if(result.selectable_ids)selectableIds=result.selectable_ids;
    currentPage=result;state.postOffset=result.offset;
    postStatus.textContent=result.total?(result.offset+1)+'–'+(result.offset+result.photos.length)+' of '+result.total+' other photos':'No other photos in this post.';
    back.disabled=!result.offset;more.disabled=result.offset+result.limit>=result.total;
    for(const photo of result.photos)extraGrid.append(photoChoice(photo,result.photos));
    updateSelection();
   }catch(error){if(serial===request&&browser.isConnected){postStatus.textContent=error.message;displayed='';extraGrid.append(button('Retry',()=>showPost(at)))}}
  }
  function openPost(source){
   const changed=state.post!==source;
   postPicker.value=source;browser.open=true;
   if(changed||!displayed)showPost(changed?0:state.postOffset||0);
   browser.querySelector('summary').scrollIntoView({block:'nearest'});postPicker.focus({preventScroll:true});
  }
  browser.ontoggle=()=>{
   state.browsing=browser.open;
   if(browser.open&&!displayed)showPost(state.postOffset||0);
  };
  postPicker.onchange=()=>showPost(0);
  if(state.browsing)browser.open=true;
  const dismiss=button('Dismiss group',()=>task(()=>decide('dismiss_likely')));
  const approve=button('Approve group',()=>task(()=>decide('approve_likely')),'primary');
  const hold=button('Approve and hold for review',()=>task(()=>decide('approve_likely',true)));
  hold.title='Save the checked photos to this Set and keep the Set in Workbench until promoted.';
  footer.append(dismiss,hold,approve);
  function updateSelection(){
   for(const check of comparison.querySelectorAll('input[type=checkbox]'))check.checked=state.selected.has(check.value);
   bulkSelect.disabled=!currentPage||!selectableIds?.length;
   const allInPost=selectableIds?.length&&selectableIds.every(id=>state.selected.has(id));
   bulkSelect.textContent=allInPost?'Deselect entire post':'Select entire post';
   const count=state.selected.size;
   const entireGroup=count===page.photos.length&&page.photos.every(photo=>state.selected.has(photo.id));
   approve.textContent=(entireGroup?'Approve group (':'Approve selected (')+count+')';
   hold.disabled=approve.disabled=count<(state.target?1:2);
  }
  updateSelection();
  const explanation=el('details'),cal=page.training;
  explanation.append(el('summary','How suggestions are ranked'));
  const wording=breadth==='partial'?'Suggestions come from a single post with photos already in the same Set. Each suggested photo has at least two visual matches in that Set.':cal.adapted?'Workbench tuned outfit and setting weights using confirmed Sets. On '+cal.held_out_sets+
   ' separate Sets, the first cross-post reference matched the shoot '+Math.round(100*cal.baseline)+'% before tuning and '+
   Math.round(100*cal.candidate)+'% after tuning, averaged per Set.':'Workbench is using the standard outfit and setting weights. It checks possible adjustments using confirmed Sets from different posts.';
  explanation.append(el('p',wording));suggestions.append(explanation);
  async function decide(action,holdForReview=false){
   try{
    const result=await mutate(action,{session,key:page.key,ids:[...state.selected],target:state.target,
     name:state.name,set_details:state.details.get(state.target),hold_for_review:holdForReview});
   if(!result)return;
    dirty=true;choices.delete(page.key);
    if(closed){await refreshPost();return}
    await load(index);
   }catch(e){
    if(closed)return;
    status.textContent=e.message;
    if(!footer.querySelector('[data-reload]')){
     const reload=button('Refresh groups',()=>task(restart));reload.dataset.reload='1';footer.prepend(reload);
    }
   }
  }
 }
 await load();
}
