// Durable workflow controls. This file extends the existing organizer functions.
const upNextButton=button('★ Up next · 0',()=>task(()=>open('up_next','up_next')));
upNextButton.id='upNext';$('unsorted').before(upNextButton);
const laterButton=button('Later · 0',()=>{tab='posts';$('filter').value='deferred';limit=80;renderList();scheduleSession()});
laterButton.id='laterQueue';upNextButton.after(laterButton);
const returnButton=button('Return to queue',()=>task(async()=>{await mutate('post',{id:currentId,status:'pending'});workflowControls();toast('Post returned to the active queue.')}));
returnButton.id='returnToQueue';$('defer').after(returnButton);
const viewerStar=button('☆ Up next',()=>task(()=>togglePin(viewerIds[viewerAt])));
viewerStar.id='viewerStar';$('viewerReference').before(viewerStar);

function workflowControls(){
 if(!data)return;
 upNextButton.textContent='★ Up next · '+(data.up_next||[]).length;
 laterButton.textContent='Later · '+(data.later_count||0);
 returnButton.classList.toggle('hidden',currentKind!=='post'||data.posts.find(p=>p.id===currentId)?.status!=='deferred');
 returnButton.disabled=busy;
 document.querySelectorAll('[data-star]').forEach(b=>{
  const pinned=(data.up_next||[]).includes(b.dataset.star);
  b.textContent=pinned?'★':'☆';b.setAttribute('aria-pressed',String(pinned));
  b.title=pinned?'Remove from Up next':'Save to Up next';b.setAttribute('aria-label',b.title);b.disabled=busy;
 });
 const id=viewerIds[viewerAt],i=images.get(id);
 viewerStar.disabled=busy||!i||i.quarantined||i.discarded;
 viewerStar.textContent=(data.up_next||[]).includes(id)?'★ Saved for next':'☆ Up next';
}
async function togglePin(id){
 await mutate('pin',{id,pinned:!(data.up_next||[]).includes(id)});
 if(currentKind==='up_next')await open('up_next','up_next',offset,false);
 workflowControls();
}
const workflowCard=card;
card=function(i,suggestion=false){
 const c=workflowCard(i,suggestion);
 if(!i.quarantined&&!i.discarded){
  const star=button((data?.up_next||[]).includes(i.id)?'★':'☆',()=>task(()=>togglePin(i.id)),'small quiet');
  star.dataset.star=i.id;star.title='Save to Up next';star.setAttribute('aria-label','Save to Up next');
  c.querySelector('footer').prepend(star);
  if(currentKind==='up_next'&&!suggestion){
   c.querySelector('footer').append(button('Start here',()=>task(async()=>{
    await saveDraft();const source=i.sources.find(s=>data.posts.some(p=>p.id===s));
    if(source)await open('post',source,0,true,i.id);
    else toast('Source post unavailable; this image can still guide suggestions.');
    if(suggestionReference!==i.id)await pinSuggestion(i.id);
   }),'small'));
  }
 }
 return c;
};
const workflowCount=renderCounts;renderCounts=function(){workflowCount();workflowControls()};
const workflowControl=controls;controls=function(){workflowControl();workflowControls()};
const workflowViewer=drawViewer;drawViewer=function(){workflowViewer();workflowControls()};
mark=async function(status){
 const old=currentId;await mutate('post',{id:old,status});
 const next=filtered().find(p=>p.id!==old&&p.status==='pending');
 if(next)await open('post',next.id);
 else toast(status==='deferred'?'Saved in Later. All active posts in this view are finished.':'Post updated.');
 workflowControls();
};

const applyDrafts=button('Apply drafts to library',()=>task(previewTransfer),'primary');
applyDrafts.id='applyDrafts';$('export').before(applyDrafts);
const transferDialog=el('dialog');transferDialog.id='transferDialog';
transferDialog.style.cssText='width:min(740px,94vw);height:auto;max-height:88vh;overflow:auto;padding:24px';
document.body.append(transferDialog);
async function previewTransfer(){
 await saveDraft();
 let result=await api('transfer-preview',{job:data.job,revision:data.state.revision});
 if(result.choose_character){
  transferDialog.replaceChildren(el('h2','Choose the destination collection'));
  for(const c of result.choose_character)transferDialog.append(button(c.name,()=>task(async()=>{
   transferDialog.close();await showTransfer(await api('transfer-preview',{job:data.job,revision:data.state.revision,character_id:c.id}));
  })));
  transferDialog.append(button('Cancel',()=>transferDialog.close()));transferDialog.showModal();return;
 }
 await showTransfer(result);
}
async function showTransfer(plan){
 transferDialog.replaceChildren(el('h2','Apply organizer drafts'),el('p',plan.sets.length+' sets · '+plan.imports.length+' new imports · '+plan.existing_count+' already imported.'));
 const list=el('div');list.style.cssText='max-height:45vh;overflow:auto';
 for(const g of plan.sets)list.append(el('p',g.name+' — '+g.action+' · '+g.count+' items'));
 for(const c of plan.conflicts)list.append(el('p',c.name+': move from '+c.from.join(', ')+' to '+c.to,'muted'));
 for(const issue of plan.issues)list.append(el('p',issue,'error'));
 transferDialog.append(list,el('p','Imports are copied and resumable. Set changes are applied together after a final check. Originals stay in place.','muted'));
 const status=el('p'),cancel=button('Cancel',()=>transferDialog.close());
 async function apply(mode){
  for(const b of transferDialog.querySelectorAll('button'))b.disabled=true;
  try{
   for(let n=0;n<plan.imports.length;n++){
    status.textContent='Importing '+(n+1)+' / '+plan.imports.length+'…';
    await api('transfer-import',{job:data.job,token:plan.token,id:plan.imports[n].id});
   }
   status.textContent='Checking and applying sets…';
   const result=await api('transfer-apply',{job:data.job,revision:data.state.revision,token:plan.token,conflicts:mode});
   await refresh();if(view)await open(currentKind,currentId,offset,false);
   transferDialog.close();toast(result.sets+' sets applied. A checkpoint was created before the changes.');
  }catch(e){status.textContent=e.message+' Reopen the preview to resume safely.';cancel.disabled=false;throw e;}
 }
 const confirm=button(plan.conflicts.length?'Apply and move memberships':'Apply changes',()=>task(()=>apply('move')),'primary');
 confirm.disabled=!!plan.issues.length||!plan.sets.length;
 transferDialog.append(status,confirm);
 if(plan.conflicts.length){const skip=button('Skip conflicting images',()=>task(()=>apply('skip')));skip.disabled=!!plan.issues.length;transferDialog.append(skip)}
 transferDialog.append(cancel);transferDialog.showModal();
}

const videoQueueButton=button('Video set matching',()=>task(openVideoQueue));
$('export').before(videoQueueButton);
async function openVideoQueue(){
 await saveDraft();const result=await api('videos');
 const dialog=el('dialog');dialog.style.cssText='width:min(900px,94vw);height:auto;max-height:90vh;overflow:auto;padding:24px';
 const list=el('div'),status=el('p'),video=el('video');video.controls=true;video.style.cssText='width:100%;max-height:42vh';
 const row=el('div');row.className='row';let chosen=null;
 const controls=[];
 const step=direction=>task(async()=>{if(!chosen)return;controls.forEach(b=>b.disabled=true);status.textContent='Reading source frame timestamps…';try{video.pause();const r=await api('video-step',{job:data.job,id:chosen.id,seconds:video.currentTime,direction});video.currentTime=r.seconds;status.textContent='Frame at '+r.seconds.toFixed(6)+' seconds'}finally{controls.forEach(b=>b.disabled=false)}});
 controls.push(button('← Frame',()=>step(-1)),button('Frame →',()=>step(1)));
 const choose=button('Use frame for suggestions',()=>task(async()=>{
  if(!chosen)return;controls.forEach(b=>b.disabled=true);status.textContent='Saving the full frame for set matching…';video.pause();
  try{
   const r=await api('video-frame',{job:data.job,id:chosen.id,seconds:video.currentTime});
   dialog.close();await refresh(true);referenceImage=data.reference_image;if(referenceImage)images.set(referenceImage.id,referenceImage);
   const source=referenceImage?.sources.find(s=>data.posts.some(p=>p.id===s));if(source)await open('post',source,0,true,r.id);
   const p=await api('index',{ids:[r.id]});progress(p);schedulePoll();await related();
   toast('Video frame saved. Matching uses this reference; saving a set attaches the video.');
  }finally{controls.forEach(b=>b.disabled=false)}
 }),'primary');controls.push(choose);row.append(...controls);
 const filter=el('label'),all=el('input');all.type='checkbox';filter.append(all,document.createTextNode(' Show assigned videos too'));
 function render(){list.replaceChildren();for(const item of result.videos.filter(i=>all.checked||!i.assigned)){
  const b=button(item.name+(item.frame_seconds!=null?' · frame '+item.frame_seconds.toFixed(3)+' s':''),()=>{chosen=item;video.src='/api/organizer/video-file?'+new URLSearchParams({id:item.id,token:TOKEN});video.onloadedmetadata=()=>{video.currentTime=item.frame_seconds||0};status.textContent=item.source||item.name;controls.forEach(b=>b.disabled=false)});
  b.style.cssText='display:block;width:100%;text-align:left;margin:4px 0';list.append(b);
 }if(!list.children.length)list.append(el('p','No unassigned videos were found in this collection’s source folders.'))}
 all.onchange=render;list.style.cssText='max-height:22vh;overflow:auto';render();controls.forEach(b=>b.disabled=true);
 dialog.append(el('h2','Videos awaiting set assignment'),filter,list,video,row,status,button('Close',()=>dialog.close()));
 dialog.addEventListener('close',()=>{video.pause();video.removeAttribute('src');video.load();dialog.remove()},{once:true});document.body.append(dialog);dialog.showModal();
}

const checkpointButton=button('Checkpoints',()=>task(openCheckpoints));$('export').before(checkpointButton);
const diagnosticButton=button('Diagnostics',()=>task(async()=>{
 const report=await api('diagnostics');const a=el('a'),url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));a.href=url;a.download='media-project-diagnostics.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}));$('export').before(diagnosticButton);
async function openCheckpoints(){
 await saveDraft();const dialog=el('dialog');dialog.style.cssText='width:min(720px,94vw);height:auto;max-height:88vh;overflow:auto;padding:24px';
 const status=el('p'),list=el('div'),include=el('input'),label=el('label');include.type='checkbox';label.append(include,document.createTextNode(' Include original media and source files (can be large)'));
 const create=button('Create complete checkpoint',()=>task(async()=>{create.disabled=true;status.textContent='Saving library, battles, organizer and duplicate history…';try{const result=await api('checkpoint-create',{include_media:include.checked});status.textContent='Saved checkpoint '+result.id;await reload()}finally{create.disabled=false}}),'primary');
 async function reload(){const data=await api('checkpoints');list.replaceChildren();for(const item of data.checkpoints){const row=el('div');row.className='row';row.append(el('span',item.at+' · '+item.label),button('Preview restore',()=>task(async()=>{
  const plan=await api('checkpoint-preview',{id:item.id});const issues=[...plan.missing_files,...plan.changed_files,...plan.companion.missing_media];
  list.replaceChildren(el('h3','Restore preview'),el('p','Library: '+plan.companion.current.media+' → '+plan.companion.restore.media+' items; '+plan.companion.current.sets+' → '+plan.companion.restore.sets+' sets.'),el('p','Restores battle history, all organizer collections, stars, deferred posts, and duplicate decisions. A recovery checkpoint is made first.'));
  for(const issue of issues.slice(0,30))list.append(el('p','Unavailable or changed: '+issue,'error'));
  const confirm=button('Restore this checkpoint',()=>task(async()=>{confirm.disabled=true;status.textContent='Restoring…';try{await api('checkpoint-restore',{id:item.id,token:plan.token});dialog.close();location.reload()}finally{confirm.disabled=false}}),'primary');confirm.disabled=!!issues.length;
  list.append(confirm,button('Back',()=>task(reload)));
 })));list.append(row)}}
 dialog.append(el('h2','Complete project checkpoints'),el('p','Includes library metadata, cards, battle history, and Workbench databases. Original media is optional.'),label,create,status,list,button('Close',()=>dialog.close()));
 dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();await reload();
}

const missingFilesButton=button('Missing files',()=>window.naiOpenMissingFiles({host:document.body,request:(action,body)=>api('missing-'+action,body)}));$('export').before(missingFilesButton);
