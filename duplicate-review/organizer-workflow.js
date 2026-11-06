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

const applyDrafts=button('Import to library',()=>task(previewTransfer),'primary');
applyDrafts.id='applyDrafts';$('export').before(applyDrafts);
const transferDialog=el('dialog');transferDialog.id='transferDialog';
transferDialog.style.cssText='width:min(740px,94vw);height:auto;max-height:88vh;overflow:auto;padding:24px';
document.body.append(transferDialog);
let transferIncludeSets=true,transferIncludeIndividuals=true,transferOwner='';
async function previewTransfer(options={}){
 await saveDraft();
 if(!options.keepScope){transferIncludeIndividuals=true;transferIncludeSets=!(data.individuals||[]).length;transferOwner='';}
 let result=await api('transfer-preview',{job:data.job,revision:data.state.revision,include_sets:transferIncludeSets,include_individuals:transferIncludeIndividuals,character_id:transferOwner});
 if(result.choose_character){
  transferDialog.replaceChildren(el('h2','Choose the destination girl'));
  for(const c of result.choose_character)transferDialog.append(button(c.name,()=>task(async()=>{transferOwner=c.id;await previewTransfer({keepScope:true});})));
  transferDialog.append(button('Cancel',()=>transferDialog.close()));if(!transferDialog.open)transferDialog.showModal();return;
 }
 await showTransfer(result);
}
async function showTransfer(plan){
 const individuals=plan.individuals||[];
 transferDialog.replaceChildren(el('h2','Import to library'),el('p',individuals.length+' individual images · '+plan.sets.length+' sets · '+plan.imports.length+' new imports · '+plan.existing_count+' already imported or queued.'));
 const scope=el('div');scope.className='row';
 for(const [labelText,value,change] of [['Include individual images',transferIncludeIndividuals,v=>transferIncludeIndividuals=v],['Include saved set drafts',transferIncludeSets,v=>transferIncludeSets=v]]){
  const label=el('label'),input=el('input');input.type='checkbox';input.checked=value;input.onchange=()=>task(async()=>{change(input.checked);await previewTransfer({keepScope:true})});label.append(input,document.createTextNode(' '+labelText));scope.append(label);
 }
 transferDialog.append(scope);
 const list=el('div');list.style.cssText='max-height:40vh;overflow:auto';
 for(const g of plan.sets)list.append(el('p',g.name+' — '+g.action+' · '+g.count+' items'));
 const names={main:'Main',categories:'Selected categories',review:'Review first',purgatory:'Purgatory'};
 for(const destination of Object.keys(names)){
  const rows=individuals.filter(i=>i.options.destination===destination);if(rows.length)list.append(el('p',names[destination]+' · '+rows.length+' images'));
 }
 const pending=individuals.filter(i=>i.status==='already_in_review').length;
 if(pending)list.append(el('p',pending+' already in Rapid Review. Their saved review choices will be kept.','muted'));
 if(individuals.some(i=>i.status==='existing'&&['review','purgatory'].includes(i.options.destination)))list.append(el('p','Images already in the library keep their placement; Review/Purgatory stages new images only.','muted'));
 for(const c of plan.conflicts)list.append(el('p',c.name+': move from '+c.from.join(', ')+' to '+c.to,'muted'));
 for(const issue of plan.issues)list.append(el('p',issue,'error'));
 transferDialog.append(list,el('p','Copies originals without resizing. Exact existing images are reused. Ratings, framing and existing metadata stay attached. Changes are applied together after the final check.','muted'));
 const status=el('p'),cancel=button('Cancel',()=>transferDialog.close()),stop=button('Stop after current file',()=>{stopping=true;stop.disabled=true;status.textContent='Stopping after the current file…'});let stopping=false;
 stop.hidden=true;
 transferDialog.oncancel=event=>{if(applying){event.preventDefault();stopping=true;stop.disabled=true;}};let applying=false;
 async function apply(mode){
  applying=true;stopping=false;for(const control of transferDialog.querySelectorAll('button,input'))control.disabled=true;
  stop.hidden=false;stop.disabled=false;
  try{
   for(let n=0;n<plan.imports.length;n++){
    if(stopping)break;
    status.textContent='Copying '+(n+1)+' / '+plan.imports.length+' · '+plan.imports[n].name;
    await api('transfer-import',{job:data.job,token:plan.token,id:plan.imports[n].id});
   }
   if(stopping){status.textContent='Stopped. Your queue and copied originals are saved. Reopen Import to library to resume.';cancel.disabled=false;return;}
   stop.disabled=true;status.textContent='Checking and applying imports…';
   const result=await api('transfer-apply',{job:data.job,revision:data.state.revision,token:plan.token,conflicts:mode});
   await refresh();if(view)await open(currentKind,currentId,offset,false);
   const outcomes=Object.values(result.individuals||{}),review=outcomes.filter(i=>i.destination==='review').length;
   transferDialog.replaceChildren(el('h2','Import complete'),el('p',outcomes.length+' individual images processed · '+result.sets+' sets applied.'));
   if(review)transferDialog.append(el('p',review+' images are in the library’s persistent Rapid Review queue. Select this girl in the library and choose Resume Rapid Review for crops, categories, favorites, flags and individual or bulk decisions.'));
   if(result.library_url){const link=el('a','Open Media Library');link.href=result.library_url;link.target='_blank';link.rel='noopener';transferDialog.append(link);}
   transferDialog.append(el('p','Original source files remain in place. A checkpoint was created before applying changes.','muted'),button('Close',()=>transferDialog.close()));
  }catch(e){status.textContent=e.message+' Reopen the preview to resume safely.';cancel.disabled=false;throw e;}
  finally{applying=false;stop.disabled=true;}
 }
 const confirm=button(plan.conflicts.length?'Apply and move memberships':'Apply changes',()=>task(()=>apply('move')),'primary');
 confirm.disabled=!!plan.issues.length||(!plan.sets.length&&!individuals.length);
 transferDialog.append(status,confirm,stop);
 if(plan.conflicts.length){const skip=button('Skip conflicting set images',()=>task(()=>apply('skip')));skip.disabled=!!plan.issues.length;transferDialog.append(skip)}
 transferDialog.append(cancel);if(!transferDialog.open)transferDialog.showModal();
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

// Individual imports use the same source inventory, viewer and persistent selection.
const allImagesButton=button('All images',()=>task(()=>open('all_images','all_images')));
allImagesButton.id='allImages';upNextButton.before(allImagesButton);
const individualQueueButton=button('Import queue · 0',()=>task(()=>open('imports','imports')));
individualQueueButton.id='individualQueue';allImagesButton.after(individualQueueButton);
const queueIndividuals=button('Save individual images…',()=>task(()=>editIndividualImports()),'primary');
queueIndividuals.id='queueIndividuals';$('save').before(queueIndividuals);
const removeIndividuals=button('Remove from import queue',()=>task(async()=>{await mutate('remove_individuals',{ids:[...selection]});await open('imports','imports',offset,false);}));
removeIndividuals.id='removeIndividuals';queueIndividuals.after(removeIndividuals);
const individualControls=controls;
controls=function(){individualControls();const rows=data?.individuals||[],byId=new Map(rows.map(r=>[r.id,r]));individualQueueButton.textContent='Import queue · '+rows.length;
 queueIndividuals.disabled=busy||!selection.size||!!data?.inventory_running;
 removeIndividuals.classList.toggle('hidden',currentKind!=='imports');removeIndividuals.disabled=busy||!selection.size;
 for(const c of document.querySelectorAll('.card')){
  let badge=c.querySelector('.individualBadge');const entry=byId.get(c.dataset.id);
  if(entry){if(!badge){badge=el('div',undefined,'individualBadge muted');c.append(badge)}badge.textContent='Queued → '+({main:'Main',review:'Review first',categories:'Categories',purgatory:'Purgatory'}[entry.options.destination]);}
  else badge?.remove();
 }
};
async function editIndividualImports(owner=''){
 const ids=[...selection];if(!ids.length)return;
 const catalog=await api('import-catalog',{job:data.job,character_id:owner});
 const dialog=el('dialog');dialog.id='individualImportDialog';dialog.style.cssText='width:min(660px,94vw);height:auto;max-height:90vh;overflow:auto;padding:24px';document.body.append(dialog);
 dialog.addEventListener('close',()=>dialog.remove(),{once:true});
 if(catalog.choose_character){dialog.append(el('h2','Choose the destination girl'));for(const c of catalog.choose_character)dialog.append(button(c.name,()=>task(async()=>{dialog.close();await editIndividualImports(c.id)})));dialog.append(button('Cancel',()=>dialog.close()));dialog.showModal();return;}
 const existing=(data.individuals||[]).filter(r=>ids.includes(r.id)),preset=existing.length===ids.length&&existing.every(r=>JSON.stringify(r.options)===JSON.stringify(existing[0].options))?existing[0].options:{};
 dialog.append(el('h2','Save '+ids.length+' individual images · '+catalog.name),el('p','No set is required. Existing set memberships are kept. These choices are saved locally until you use Import to library.'));
 const destination=el('select');destination.id='individualDestination';destination.setAttribute('aria-label','Individual import destination');
 for(const [value,label]of [['main','Main'],['review','Review first · full Rapid Review tools'],['categories','Selected categories · respect ghost categories'],['purgatory','Purgatory']])destination.append(new Option(label,value));destination.value=preset.destination||'main';
 const categoryList=el('div');categoryList.id='individualCategories';categoryList.style.cssText='display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0';
 for(const category of catalog.categories){const label=el('label'),input=el('input');input.type='checkbox';input.value=category.id;input.checked=(preset.categories||[]).includes(category.id);label.append(input,document.createTextNode(' '+category.name+(category.ghost?' (ghost)':'')));categoryList.append(label)}
 if(!catalog.categories.length)categoryList.append(el('p','No image categories yet. You can assign them later in the library.','muted'));
 const flags=el('div');flags.className='row';const fields={};
 for(const [key,name] of [['favorite','Favorite'],['featured','Featured'],['needs_replacement','Needs replacement']]){const label=el('label'),input=el('input');input.type='checkbox';input.checked=!!preset[key];input.setAttribute('aria-label',name);fields[key]=input;label.append(input,document.createTextNode(' '+name));flags.append(label)}
 dialog.append(destination,el('h3','Image categories'),categoryList,flags,el('p','For existing library images, categories and checked flags are added; unchecked flags do not clear saved metadata. Review first and Purgatory only stage new images.','muted'));
 const createRow=el('div'),categoryName=el('input');createRow.className='row';categoryName.placeholder='New image category';categoryName.maxLength=100;categoryName.setAttribute('aria-label','New image category');
 const createCategory=button('Create category',()=>task(async()=>{
  if(!categoryName.value.trim())return;createCategory.disabled=true;
  try{const category=await api('import-category-create',{job:data.job,character_id:catalog.character_id,name:categoryName.value.trim()});
   if(![...categoryList.querySelectorAll('input')].some(i=>i.value===category.id)){categoryList.querySelector('p')?.remove();const label=el('label'),input=el('input');input.type='checkbox';input.value=category.id;input.checked=true;label.append(input,document.createTextNode(' '+category.name));categoryList.append(label);}categoryName.value='';
  }finally{createCategory.disabled=false;}
 }));createRow.append(categoryName,createCategory);dialog.append(createRow);
 const save=button('Save to import queue',()=>task(async()=>{
  const options={destination:destination.value,categories:[...categoryList.querySelectorAll('input:checked')].map(i=>i.value)};for(const [key,input]of Object.entries(fields))options[key]=input.checked;
  if(options.destination==='categories'&&!options.categories.length){toast('Choose a category or use Main.');return;}
  save.disabled=true;try{await mutate('queue_individuals',{ids,character_id:catalog.character_id,library_instance:catalog.library_instance,options});dialog.close();await open('imports','imports',0,false);toast(ids.length+' images saved in the import queue.');}finally{save.disabled=false}
 }),'primary');save.id='saveIndividualImports';dialog.append(save,button('Cancel',()=>dialog.close()));dialog.showModal();
}
// Shift selects a range in the visible grid; browsing and zooming remain separate.
let rangeAnchor='';const individualCard=card;
card=function(i,suggestion=false){const c=individualCard(i,suggestion),pick=c.querySelector('[data-pick]');
 if(pick){pick.title='Select image · Shift-click selects a range on this page';pick.onclick=event=>{
  if(!suggestion&&event.shiftKey&&view?.images.some(r=>r.id===rangeAnchor)){
   const ids=view.images.filter(r=>!r.quarantined&&!r.discarded).map(r=>r.id),a=ids.indexOf(rangeAnchor),b=ids.indexOf(i.id);
   if(a>=0&&b>=0){for(const id of ids.slice(Math.min(a,b),Math.max(a,b)+1))selection.add(id);updateSelection();return;}
  }
  rangeAnchor=i.id;toggle(i);
 };}return c;
};
const originalQuality=button('Original quality',()=>{const i=images.get(viewerIds[viewerAt]);if(!i||i.media_type==='video')return;$('largeImage').src='/api/organizer/original?'+new URLSearchParams({id:i.id,token:TOKEN});originalQuality.disabled=true;originalQuality.textContent='Original quality selected';});
originalQuality.id='originalQuality';$('viewerOriginal').before(originalQuality);
const individualViewer=drawViewer;drawViewer=function(){individualViewer();const i=images.get(viewerIds[viewerAt]);originalQuality.disabled=i?.media_type==='video';originalQuality.textContent='Original quality';};

const missingQueued=button('Remove unavailable queue entries',()=>task(async()=>{
 const rows=(data.individuals||[]).filter(r=>!r.id);if(!rows.length)return;
 if(!confirm('Remove '+rows.length+' unavailable entries from the import queue? Source files and library images are kept.'))return;
 await mutate('remove_individuals',{keys:rows.map(r=>r.key),ids:[]});await open('imports','imports',offset,false);
}));missingQueued.id='removeUnavailableImports';removeIndividuals.after(missingQueued);
const availableImportControls=controls;controls=function(){availableImportControls();const count=(data?.individuals||[]).filter(r=>!r.id).length;missingQueued.classList.toggle('hidden',currentKind!=='imports'||!count);missingQueued.disabled=busy;missingQueued.textContent='Remove '+count+' unavailable queue entries';};
