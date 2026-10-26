// Historical duplicate review shares the normal cards, comparison viewer and
// Keep controls. Only confirmation differs: record origins, never move files.
let historyData=null,historyState=null,historyConfig={},historyKeeper=null;
let historyPage=0,historyTarget=null,historyLoadedJob=null,historyListOffset=0;
const historyHidden=new Map();
function historyModeActive(){return $('reviewQueue').value==='history'}
function reviewPreview(r,size){return (historyModeActive()?'/api/bulk/image?id='+encodeURIComponent(r.origin_id):'/api/preview?id='+r.id)+'&size='+size+'&token='+token}
function openReviewFile(r,reveal=false){return api(historyModeActive()?'/api/history/'+(reveal?'reveal':'open'):'/api/'+(reveal?'reveal':'open'),{id:historyModeActive()?r.origin_id:r.id})}
function historyLabel(s){return ({pending:'Unresolved',deferred:'Deferred',discarded:'Intentionally discarded',no_counterpart:'Previously marked no counterpart — unresolved'})[s]||s}
function historyControls(){
 const running=!!historyState?.running||!!snapshot?.status.running,locked=busy||running;
 for(const id of ['scan','scanKind','workers','incoming','reference','mode','addIncoming','addReference','reset','resumeCleanup','resumeReplacement'])$(id).disabled=true;
 for(const id of ['historyRefresh','historyPick','historyRoots','historyMode','historyFilter','historySearch','historySearchButton','connectLibrary','libraryCharacter','reviewQueue'])$(id).disabled=locked;
 $('historyStop').classList.toggle('hidden',!historyState?.running);$('historyStop').disabled=busy;
 $('undo').textContent='Undo last connection';$('undo').disabled=locked||!historyData?.can_undo;
 $('finishGroup').textContent='Finish group · save keeper connection';$('finishGroup').disabled=locked||!historyKeeper;
 $('keepGroup').textContent='Defer / next';$('keepGroup').disabled=locked||!historyData?.image;
 for(const id of ['historyDiscard','historyPending'])$(id).disabled=locked||!historyData?.image;
 $('prev').disabled=locked||!historyData?.offset;$('next').disabled=locked||!historyData||historyData.offset+1>=historyData.total;
 $('compare').disabled=locked||!members.length;
 $('historyCandidatePrev').disabled=locked||historyPage===0;
 $('historyCandidateNext').disabled=locked||!historyData||(historyPage+1)*24>=historyData.candidate_count;
 $('listPrev').disabled=locked||historyListOffset===0;
 $('listNext').disabled=locked||historyListOffset+50>=(historyData?.entries.length||0);
 document.querySelectorAll('#grid button,#grid input,#groupList button').forEach(e=>e.disabled=locked||e.dataset.protected==='1');
 if($('compareDialog').open)historyCompareControls();
}
function adaptHistoryCard(r,bottom){
 const meta=bottom.querySelector('.metadata');bottom.replaceChildren(meta);
 if(r.unavailable){const warning=document.createElement('p');warning.className='note';warning.textContent='File unavailable: '+r.unavailable;bottom.append(warning)}
 if(r.quarantined){const note=document.createElement('p');note.className='note';note.textContent=historyData.copy_count+' quarantined file(s) represented. Choose the same photograph among the surviving copies.';bottom.append(note)}
 else {const keep=button(r.keep?'✓ Keep':'Keep',()=>selectHistoryKeeper(r),r.keep?'primary':'keep-choice');keep.dataset.protected=r.unavailable?'1':'0';bottom.append(keep);const confirm=button('Keep only this',()=>confirmHistoryKeeper(r),'primary');confirm.dataset.protected=r.unavailable?'1':'0';bottom.append(confirm)}
 const actions=document.createElement('div');actions.className='row row-actions';actions.append(button('Open original',()=>task(()=>openReviewFile(r))),button('Show in folder',()=>task(()=>openReviewFile(r,true))));bottom.append(actions);
 const origins=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('div');summary.textContent='Original locations';text.style.overflowWrap='anywhere';text.textContent=(r.quarantined?historyData.origins:r.origins||[]).map(o=>o.original_path||o.path).join('\n');text.style.whiteSpace='pre-wrap';origins.append(summary,text);bottom.append(origins);
}
function selectHistoryKeeper(r){
 if(busy||historyState?.running||r.quarantined||r.unavailable)return;
 historyKeeper=historyKeeper===r.origin_id?null:r.origin_id;
 members.forEach(m=>m.keep=m.origin_id===historyKeeper);renderCards();controls();
 if($('compareDialog').open){refreshComparisonResolution();historyCompareControls()}
}
function historyCompareControls(){
 for(const side of ['left','right']){
  const r=members.find(m=>m.id===Number($(side+'Choice').value));
  const row=$(side+'Details').parentElement;
  row.querySelectorAll('button').forEach(b=>b.classList.toggle('hidden',!['keep'+side[0].toUpperCase()+side.slice(1),'open'+side[0].toUpperCase()+side.slice(1),side+'KeepChoice'].includes(b.id)));
  const disabled=busy||!r||r.quarantined||!!r.unavailable;
  $(side+'KeepChoice').disabled=disabled;
  const keep=$('keep'+side[0].toUpperCase()+side.slice(1));keep.disabled=disabled;keep.textContent='Keep only this';
 }
}
async function confirmHistoryKeeper(r,fromCompare=false){
 if(!r||r.quarantined||r.unavailable||busy)return;
 // Candidate grids contain suggestions, not a claim that every candidate is a duplicate.
 return task(async()=>{
  await api('/api/bulk/confirm-origin',{job:historyData.job,target:historyData.image.id,keeper:r.origin_id});
  if(fromCompare)closeCompare();historyTarget=null;historyPage=0;await loadHistory();
  toast('Keeper connection saved. All original locations retained; no files moved.');
 });
}
async function markHistory(status){
 if(!historyData?.image)return;
 await api('/api/bulk/mark-origin',{job:historyData.job,target:historyData.image.id,status});
 const offset=historyData.offset;
 historyTarget=null;historyPage=0;
 await loadHistory($('historyFilter').value==='all'?Math.min(offset+1,historyData.total-1):offset);
}
function renderHistoryList(){
 $('groupList').replaceChildren();const entries=historyData?.entries||[];
 entries.slice(historyListOffset,historyListOffset+50).forEach(entry=>{
  const b=button('',()=>task(async()=>{historyTarget=entry.digest;historyPage=0;await loadHistory()}),'group-button'+(entry.digest===historyData.digest?' active':''));
  const title=document.createElement('strong'),file=document.createElement('small');title.textContent=entry.count+' quarantined file(s) · '+historyLabel(entry.status);file.textContent=entry.name;b.append(title,file);$('groupList').append(b);
 });
 $('listRange').textContent=entries.length?(historyListOffset+1)+'–'+Math.min(entries.length,historyListOffset+50):'';
}
async function loadHistory(offset=null){
 const params=new URLSearchParams({mode:$('historyMode').value,filter:$('historyFilter').value,q:$('historySearch').value,page:historyPage});
 if(offset!==null)params.set('offset',offset);else if(historyTarget)params.set('target',historyTarget);
 const data=await api('/api/bulk/origin-audit?'+params);
 if(!historyModeActive())return;
 historyData=data;historyLoadedJob=data.job;historyTarget=data.digest||null;historyKeeper=null;
 historyListOffset=Math.floor((data.offset||0)/50)*50;
 members=data.image?[data.image,...data.candidates].map((r,i)=>({...r,origin_id:r.id,id:i+1,quarantined:i===0,keep:false})):[];
 $('files').textContent=data.inventory.readable||0;$('groupCount').textContent=data.total;
 $('groupCount').nextElementSibling.textContent='history entries';$('moved').textContent=data.total_files;$('movedLabel').textContent='unlinked quarantine files';
 $('review').classList.toggle('hidden',!data.image);$('empty').classList.toggle('hidden',!!data.image);
 $('empty').querySelector('h2').textContent=data.total_files?'No entries in this filter':'No unresolved quarantine entries';
 $('empty').querySelector('p').textContent=data.total_files?'Choose All unresolved to see deferred and discarded entries.':'Check the inventory coverage and Issues above before considering history complete.';
 $('groupTitle').textContent=data.image?data.copy_count+' quarantined file(s) · choose surviving copy':'';
 $('groupKind').textContent=data.image?historyLabel(data.review_status):'';
 $('position').textContent=data.total?(data.offset+1)+' / '+data.total:'';
 $('reviewHelp').textContent='First card: already quarantined. The other cards are possible matches, not confirmed duplicates. Mark the matching survivor Keep, then Finish group. Defer if unsure; no files move.';
 $('historyOrigins').textContent=(data.origins||[]).map(o=>'Original: '+(o.original_path||o.path)+(o.quarantine_path?'\nQuarantine: '+o.quarantine_path:'')).join('\n\n');
 $('historyCandidateCount').textContent=data.candidate_count?((historyPage*24+1)+'–'+Math.min((historyPage+1)*24,data.candidate_count)+' of '+data.candidate_count+' candidates'):'No convincing candidates. Search or browse all survivors; this does not mean the copy is gone.';
 const c=data.counts;$('status').textContent='Duplicate history · '+data.total_files+' unlinked files · '+c.pending+' pending · '+c.deferred+' deferred · '+(c.discarded||0)+' intentionally discarded'+(c.no_counterpart?' · '+c.no_counterpart+' previously marked no counterpart':'');
 $('coverage').textContent=(data.complete_inventory?'Full inventory available. ':'Inventory incomplete — refresh before relying on totals. ')+data.regular_groups+' regular duplicate groups remain. Exact, verified visual and saved keeper links are excluded. '+(data.issues.length?data.issues.length+' file issues need inspection.':'');
 $('errors').classList.toggle('hidden',!data.issues.length);$('progress').classList.add('hidden');
 renderHistoryList();renderCards();controls();
}
async function refreshHistory(force=false){
 if(polling||closed)return;polling=true;
 try{
  const state=await api('/api/bulk/state');if(!historyModeActive())return;
  historyState=state;
  if(state.running){$('status').textContent=state.phase;$('progress').classList.remove('hidden');$('progress').max=state.total||1;$('progress').value=state.done;$('review').classList.add('hidden');$('empty').classList.remove('hidden');$('empty').querySelector('h2').textContent='Refreshing full duplicate history';$('empty').querySelector('p').textContent='Reading survivors and quarantine; no set grouping and no files moved.'}
  else if(!state.id||state.error||state.interrupted||(!state.inventory&&!state.complete)){
   historyData=null;members=[];$('review').classList.add('hidden');$('empty').classList.remove('hidden');$('progress').classList.add('hidden');
   $('status').textContent=state.error||state.phase;$('empty').querySelector('h2').textContent='Refresh duplicate history to begin';$('empty').querySelector('p').textContent='Use your full collection folder, including quarantine. No need to build proposed sets.';
  }else if(force||historyLoadedJob!==state.id)await loadHistory();
  controls();
 }catch(e){toast(e.message,true)}finally{polling=false}
}
async function switchReviewQueue(){
 closeCompare();selected.clear();historyKeeper=null;
 const active=historyModeActive();$('historySetup').classList.toggle('hidden',!active);
 const ids=['autoToolbar','autoInfo','selectionCount','moveSelected','clearSelection','sort','quarantineGroup','viewVerified','cancel'];
 const nodes=[...ids.map($),document.querySelector('label[for="sort"]')];
 if(active){
  for(const el of nodes){historyHidden.set(el,el.classList.contains('hidden'));el.classList.add('hidden')}
  historyState=await api('/api/bulk/state');historyConfig=historyState.config||{};
  if(!$('historyRoots').value)$('historyRoots').value=(historyConfig.roots||[...paths('incoming'),...paths('reference')]).join('\n');
  historyLoadedJob=null;historyTarget=null;historyPage=0;
  await refreshHistory(true);
 }else{
  historyHidden.forEach((hidden,el)=>el.classList.toggle('hidden',hidden));historyHidden.clear();
  $('undo').textContent='Undo last action';$('keepGroup').textContent='Keep all / dismiss group';$('groupCount').nextElementSibling.textContent='groups to review';
  document.querySelectorAll('#compareDialog .row button').forEach(b=>b.classList.remove('hidden'));
  $('reviewQueue').disabled=false;seenRevision=-1;await refresh(true);
 }
}
$('reviewQueue').onchange=()=>task(switchReviewQueue);
$('historyPick').onclick=()=>task(async()=>{const r=await api('/api/pick',{});if(r.path)$('historyRoots').value=[...new Set([...paths('historyRoots'),r.path])].join('\n')});
$('historyRefresh').onclick=()=>task(async()=>{
 const config={...historyConfig,roots:paths('historyRoots'),limit:0};
 // Retain the saved collection's companion choice; newly connected choices are explicit.
 if($('libraryCharacter').value)config.character_id=$('libraryCharacter').value;
 historyState=await api('/api/history/inventory',config);historyData=null;historyLoadedJob=null;historyTarget=null;historyPage=0;await refreshHistory(true);
});
$('historyStop').onclick=()=>task(()=>api('/api/bulk/cancel',{}));
for(const id of ['historyMode','historyFilter'])$(id).onchange=()=>task(async()=>{historyPage=0;historyTarget=null;await loadHistory()});
$('historySearchButton').onclick=()=>task(async()=>{historyPage=0;await loadHistory()});
$('historySearch').onkeydown=e=>{if(e.key==='Enter')$('historySearchButton').click()};
$('historyCandidatePrev').onclick=()=>task(async()=>{historyPage=Math.max(0,historyPage-1);await loadHistory()});
$('historyCandidateNext').onclick=()=>task(async()=>{historyPage++;await loadHistory()});
$('historyPending').onclick=()=>task(()=>markHistory('pending'));
$('historyDiscard').onclick=()=>dialog('Mark intentionally discarded?','Use this only if you recognize this as a photo you intentionally discarded. If unsure, use Defer. This keeps all files and original paths; it does not create a keeper connection.',()=>task(()=>markHistory('discarded')));
// Preserve the regular handlers; historical confirmation never calls move/restore.
for(const [id,action] of Object.entries({
 finishGroup:()=>confirmHistoryKeeper(members.find(r=>r.origin_id===historyKeeper)),
 keepGroup:()=>task(()=>markHistory('deferred')),
 undo:()=>task(async()=>{await api('/api/bulk/undo-origin',{job:historyData.job});historyTarget=null;await loadHistory()}),
 prev:()=>task(async()=>{historyPage=0;await loadHistory(historyData.offset-1)}),
 next:()=>task(async()=>{historyPage=0;await loadHistory(historyData.offset+1)}),
 listPrev:()=>{historyListOffset=Math.max(0,historyListOffset-50);renderHistoryList();controls()},
 listNext:()=>{historyListOffset+=50;renderHistoryList();controls()},
 errors:()=>dialog('Inventory issues',(historyData?.issues||historyState?.issues||[]).map(e=>e.path+'\n'+e.message).join('\n\n'))
})){
 const regular=$(id).onclick;$(id).onclick=e=>historyModeActive()?action():regular(e);
}
