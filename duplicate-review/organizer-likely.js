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
 .likely-photos .omitted{opacity:.56}
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
 tier.onchange=()=>task(async()=>{breadth=tier.value;session='';choices.clear();await load()});
 header.append(el('h2','Likely groups across posts'),tier,prev,next,close);
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
  status.textContent='Finding cross-post groups…';
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
   status.textContent='No pending cross-post groups.';
   body.append(el('p',breadth==='closest'?'Choose More from post order to look for additional groups.':'Other unmatched photos are available in Review unmatched photos.'));
   return;
  }
  status.textContent='Group '+(index+1)+' of '+page.total+' · '+page.photos_left+' suggested photos left';
  const state=choices.get(page.key)||{selected:new Set(page.photos.map(p=>p.id)),target:page.destination};
  if(!state.named)state.name=page.new_name;
  choices.set(page.key,state);
  const destination=el('div',undefined,'likely-destination'), label=el('label','Destination Set');
  const picker=el('select');picker.setAttribute('aria-label','Destination Set');
  picker.add(new Option('New draft Set',''));
  const candidates=new Set([page.proposed_target,...page.alternatives]);
  for(const set of data.sets.filter(s=>!s.in_purgatory).sort((a,b)=>Number(candidates.has(b.id))-Number(candidates.has(a.id))||a.name.localeCompare(b.name))){
   const note=set.id===page.proposed_target?' · suggested':candidates.has(set.id)?' · possible match':'';
   picker.add(new Option(set.name+note,set.id));
  }
  picker.value=state.target;
  picker.onchange=()=>task(async()=>{state.target=picker.value;await load(index,state.target)});
  destination.append(label,picker);
  if(!state.target){
   const name=el('input');name.value=state.name;name.setAttribute('aria-label','New Set name');
   name.maxLength=250;name.oninput=()=>{state.name=name.value;state.named=!!name.value.trim()};destination.append(name);
  }
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
    body.append(heading,grid);sections.set(photo.source_key,grid);
   }
   const figure=el('figure',undefined,'match-photo'), check=el('input');
   check.type='checkbox';check.checked=state.selected.has(photo.id);
   const caption=el('label'), text=el('span',(photo.source_position?'#'+photo.source_position+' · ':'')+photo.name);
   text.title=photo.name;caption.append(check,text);
   check.setAttribute('aria-label','Include '+photo.name);
   figure.classList.toggle('omitted',!check.checked);
   check.onchange=()=>{
    if(check.checked)state.selected.add(photo.id);else state.selected.delete(photo.id);
    figure.classList.toggle('omitted',!check.checked);updateApprove();
   };
   figure.append(photoButton(photo,page.photos,600),caption);sections.get(photo.source_key).append(figure);
  }
  const dismiss=button('Dismiss group',()=>task(()=>decide('dismiss_likely')));
  const approve=button('Approve group',()=>task(()=>decide('approve_likely')),'primary');
  footer.append(dismiss,approve);
  function updateApprove(){
   const count=state.selected.size;
   approve.textContent=count===page.photos.length?'Approve group ('+count+')':'Approve selected ('+count+')';
   approve.disabled=count<(state.target?1:2);
  }
  updateApprove();
  const explanation=el('details'),cal=page.training;
  explanation.append(el('summary','How suggestions are ranked'));
  const wording=cal.adapted?'Workbench tuned outfit and setting weights using confirmed Sets. On '+cal.held_out_sets+
   ' separate Sets, the first cross-post reference matched the shoot '+Math.round(100*cal.baseline)+'% before tuning and '+
   Math.round(100*cal.candidate)+'% after tuning, averaged per Set.':'Workbench is using the standard outfit and setting weights. It checks possible adjustments using confirmed Sets from different posts.';
  explanation.append(el('p',wording));body.append(explanation);
  async function decide(action){
   try{
    const result=await mutate(action,{session,key:page.key,ids:[...state.selected],target:state.target,name:state.name});
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
