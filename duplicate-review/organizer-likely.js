// Each proposal stays local to this dialog until an explicit review decision.
const likelyDialog = el('dialog');
likelyDialog.id = 'likelyGroupsDialog';
likelyDialog.setAttribute('aria-label','Likely groups across posts');
const likelyStyle = el('style');
likelyStyle.textContent = `
 #likelyGroupsDialog{width:min(1080px,95vw);height:auto;max-height:92vh;padding:0}
 #likelyGroupsDialog[open]{display:flex;flex-direction:column}
 #likelyGroupsDialog h2,#likelyGroupsDialog h3{margin:0}
 #likelyGroupsDialog .match-body{max-height:none;min-height:0}
 .likely-header,.likely-footer{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:12px 18px;flex:none}
 .likely-header{border-bottom:1px solid var(--line)}.likely-header h2{margin-right:auto!important}
 .likely-footer{border-top:1px solid var(--line)}.likely-footer .primary{margin-left:auto}
 .likely-status{margin:0;color:var(--muted);font-size:.92em}
 .likely-destination{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
 .likely-destination select,.likely-destination input{max-width:100%;min-width:150px}
 .likely-source{margin:14px 0 6px;font-size:1em;overflow-wrap:anywhere}
 .likely-photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(146px,100%),1fr));gap:8px}
 .likely-photos .match-photo img{height:145px}
 .likely-photos label{display:flex;gap:6px;align-items:center;padding-top:5px;cursor:pointer}
 .likely-photos label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .likely-photos .omitted{opacity:.65}
 .likely-post-browser{margin:16px 0;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
 .likely-post-browser summary{cursor:pointer;font-weight:600}
 .likely-post-controls,.likely-post-caption{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:.65em 0}
 .likely-post-controls select{min-width:0;max-width:100%}.likely-source button{margin-left:.6em}
 .likely-photos .unavailable{color:var(--muted);font-size:.8em}
 @media(max-width:640px){.likely-photos{grid-template-columns:repeat(2,minmax(0,1fr))}.likely-header,.likely-footer{padding:8px}.likely-photos .match-photo img{height:108px}}
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
 function photoButton(photo,list,size){
  const b=button('',()=>preview(photo,list)),im=el('img');
  b.setAttribute('aria-label','Enlarge '+photo.name);
  im.loading='lazy';im.src=imageURL(photo.id,size);im.alt=photo.name;b.append(im);
  return b;
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
  body.append(destination);
  body.append(el('p','Uncheck any photos that don’t belong. Approving saves the checked photos to your Workbench draft.','muted'));
  if(page.source_reason)body.append(el('p',page.source_reason));
  if(page.references.length){
   body.append(el('small','Already in the destination Set','muted'));
   const refs=el('div',undefined,'match-examples');
   for(const photo of page.references)refs.append(photoButton(photo,page.references,240));
   body.append(refs);
  }
  const sections=new Map();
  for(const photo of page.photos){
   if(!sections.has(photo.source_key)){
    const heading=el('h3',photo.source_label||'Source post','likely-source'),grid=el('div',undefined,'likely-photos');
    if(page.source_posts?.some(post=>post.id===photo.source_key)){
     const viewPost=button('View post',()=>openPost(photo.source_key),'small');
     viewPost.setAttribute('aria-label','View post '+photo.source_label);heading.append(viewPost);
    }
    body.append(heading,grid);sections.set(photo.source_key,grid);
   }
   sections.get(photo.source_key).append(photoChoice(photo,page.photos));
  }
  function photoChoice(photo,list){
   const figure=el('figure',undefined,'match-photo'), check=el('input');
   check.type='checkbox';check.checked=state.selected.has(photo.id);check.disabled=!!photo.unavailable_reason;
   const caption=el('label'), text=el('span',(photo.source_position?'#'+photo.source_position+' · ':'')+(photo.display_name||photo.name));
   text.title=photo.display_name||photo.name;caption.append(check,text);
   check.setAttribute('aria-label','Include '+photo.name);
   figure.classList.toggle('omitted',!check.checked);
   check.onchange=()=>{
    if(check.checked)state.selected.add(photo.id);else state.selected.delete(photo.id);
    figure.classList.toggle('omitted',!check.checked);updateApprove();
   };
   figure.append(photoButton(photo,list,600),caption);
   if(photo.unavailable_reason)figure.append(el('small',photo.unavailable_reason,'unavailable'));
   return figure;
  }
  const browser=el('details',undefined,'likely-post-browser'), postPicker=el('select');
  const controls=el('div',undefined,'likely-post-controls'), postStatus=el('span'), extraGrid=el('div',undefined,'likely-photos');
  const posts=page.source_posts||[], groupKey=page.key;
  let request=0, displayed='', currentPage=null;
  postPicker.setAttribute('aria-label','Matching post');
  for(const post of posts)postPicker.add(new Option(post.label,post.id));
  if(!posts.some(p=>p.id===state.post))state.post=posts[0]?.id;
  postPicker.value=state.post||'';
  const back=button('Previous photos',()=>showPost(currentPage.offset-currentPage.limit),'small');
  const more=button('Next photos',()=>showPost(currentPage.offset+currentPage.limit),'small');
  postStatus.setAttribute('role','status');controls.append(postPicker,back,more,postStatus);
  browser.append(el('summary','Browse matching posts'),controls,extraGrid);
  if(posts.length)body.append(browser);
  async function showPost(at){
   const source=postPicker.value, serial=++request;
   state.post=source;state.postOffset=at;displayed=source;
   back.disabled=more.disabled=true;extraGrid.replaceChildren();postStatus.textContent='Loading photos…';
   try{
    const result=await api('likely-groups',{job,session,key:groupKey,source_post:source,post_offset:at});
    if(serial!==request||!browser.isConnected||closed)return;
    currentPage=result;state.postOffset=result.offset;
    postStatus.textContent=result.total?(result.offset+1)+'–'+(result.offset+result.photos.length)+' of '+result.total+' other photos':'No other photos in this post.';
    back.disabled=!result.offset;more.disabled=result.offset+result.limit>=result.total;
    for(const photo of result.photos)extraGrid.append(photoChoice(photo,result.photos));
   }catch(error){if(serial===request&&browser.isConnected){postStatus.textContent=error.message;displayed='';extraGrid.append(button('Retry',()=>showPost(at)))}}
  }
  function openPost(source){
   const changed=state.post!==source;
   postPicker.value=source;browser.open=true;
   if(changed||!displayed)showPost(changed?0:state.postOffset||0);
   browser.scrollIntoView({block:'nearest'});postPicker.focus();
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
  function updateApprove(){
   const count=state.selected.size;
   const entireGroup=count===page.photos.length&&page.photos.every(photo=>state.selected.has(photo.id));
   approve.textContent=(entireGroup?'Approve group (':'Approve selected (')+count+')';
   hold.disabled=approve.disabled=count<(state.target?1:2);
  }
  updateApprove();
  const explanation=el('details'),cal=page.training;
  explanation.append(el('summary','How suggestions are ranked'));
  const wording=breadth==='partial'?'Suggestions come from a single post with photos already in the same Set. Each suggested photo has at least two visual matches in that Set.':cal.adapted?'Workbench tuned outfit and setting weights using confirmed Sets. On '+cal.held_out_sets+
   ' separate Sets, the first cross-post reference matched the shoot '+Math.round(100*cal.baseline)+'% before tuning and '+
   Math.round(100*cal.candidate)+'% after tuning, averaged per Set.':'Workbench is using the standard outfit and setting weights. It checks possible adjustments using confirmed Sets from different posts.';
  explanation.append(el('p',wording));body.append(explanation);
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
