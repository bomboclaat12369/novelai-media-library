// Historical duplicate review shares the normal cards, comparison viewer and
// Keep controls. Only confirmation differs: record origins, never move files.
let historyData=null,historyState=null,historyConfig={};
let historyPage=0,historyTarget=null,historyLoadedJob=null,historyListOffset=0,regularMatching=null;
const historyHidden=new Map();
function historyModeActive(){return $('reviewQueue').value==='history'}
function reviewPreview(r,size){return (historyModeActive()?'/api/bulk/image?id='+encodeURIComponent(r.origin_id):'/api/preview?id='+r.id)+'&size='+size+'&token='+token}
function openReviewFile(r,reveal=false){return api(historyModeActive()?'/api/history/'+(reveal?'reveal':'open'):'/api/'+(reveal?'reveal':'open'),{id:historyModeActive()?r.origin_id:r.id})}
function historyLabel(s){return ({pending:'Unresolved',deferred:'Deferred',discarded:'Intentionally discarded',no_counterpart:'Previously marked no counterpart — unresolved'})[s]||s}
function historyControls(){
 const running=!!historyState?.running||!!snapshot?.status.running,locked=busy||running;
 for(const id of ['scan','scanKind','incoming','reference','addIncoming','addReference','reset','resumeCleanup','resumeReplacement'])$(id).disabled=true;
 for(const id of ['mode','workers','historyRefresh','historyVerify','historyHighConfidence','historyPick','historyRoots','historyMode','historyFilter','historySearch','historySearchButton','connectLibrary','libraryCharacter','reviewQueue'])$(id).disabled=locked;
 $('historyVerify').disabled=locked||!historyData?.matching_ready;
 $('historyHighConfidence').disabled=locked||!historyData?.matching_ready;
 $('historyStop').classList.toggle('hidden',!historyState?.running);$('historyStop').disabled=busy;
 $('undo').textContent=historyData?.auto_undo?(historyData.auto_policy==='high_confidence'?'Undo high-confidence connections':'Undo automatic connections'):'Undo last connection';$('undo').disabled=locked||!historyData?.can_undo;
 $('finishGroup').disabled=true;
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
 if(r.match){const proof=document.createElement('p');proof.className='note';proof.textContent=r.match.kind+' · match score '+r.match.score;bottom.append(proof)}
 if(r.unavailable){const warning=document.createElement('p');warning.className='note';warning.textContent='File unavailable: '+r.unavailable;bottom.append(warning)}
 if(r.quarantined){const note=document.createElement('p');note.className='note';note.textContent=historyData.copy_count+' quarantined file(s) represented. Choose the same photograph among the surviving copies.';bottom.append(note)}
 else {const confirm=button('Keep & next',()=>confirmHistoryKeeper(r),'primary');confirm.title='Save this keeper connection and advance. Undo last connection reverses it.';confirm.dataset.protected=r.unavailable?'1':'0';bottom.append(confirm)}
 const actions=document.createElement('div');actions.className='row row-actions';actions.append(button('Open original',()=>task(()=>openReviewFile(r))),button('Show in folder',()=>task(()=>openReviewFile(r,true))));bottom.append(actions);
 const origins=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('div');summary.textContent='Original locations';text.style.overflowWrap='anywhere';text.textContent=(r.quarantined?historyData.origins:r.origins||[]).map(o=>o.original_path||o.path).join('\n');text.style.whiteSpace='pre-wrap';origins.append(summary,text);bottom.append(origins);
}
function selectHistoryKeeper(r){
 return confirmHistoryKeeper(r,$('compareDialog').open);
}
function historyCompareControls(){
 for(const side of ['left','right']){
  const r=members.find(m=>m.id===Number($(side+'Choice').value));
  const row=$(side+'Details').parentElement;
  row.querySelectorAll('button').forEach(b=>b.classList.toggle('hidden',!['keep'+side[0].toUpperCase()+side.slice(1),'open'+side[0].toUpperCase()+side.slice(1)].includes(b.id)));
  const disabled=busy||historyState?.running||snapshot?.status.running||!r||r.quarantined||!!r.unavailable;
  $(side+'KeepChoice').disabled=disabled;
  const keep=$('keep'+side[0].toUpperCase()+side.slice(1));keep.disabled=disabled;keep.textContent=r?.quarantined?'Already quarantined':'Keep & next';
 }
}
async function confirmHistoryKeeper(r,fromCompare=false){
 if(!r||r.quarantined||r.unavailable||busy||historyState?.running||snapshot?.status.running)return;
 // Candidate grids contain suggestions, not a claim that every candidate is a duplicate.
 return task(async()=>{
  const offset=historyData.offset;
  await api('/api/bulk/confirm-origin',{job:historyData.job,target:historyData.image.id,keeper:r.origin_id});
  if(fromCompare)closeCompare();historyTarget=null;historyPage=0;await loadHistory(offset);
  toast('Connection saved. Use Undo last connection to reverse it. No files moved.');
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
 historyData=data;historyLoadedJob=data.job;
 const verification=data.verification||{};
 $('historyVerification').textContent=verification.started?`${verification.policy==='high_confidence'?'High-confidence recovery':'Saved-match verification'}: ${verification.linked_files||0} files connected · ${verification.checked||0} entries checked. Remaining entries still need review; deferred/discarded entries are untouched.`:'Verify saved matches can reduce this queue without rebuilding the inventory. It checks saved candidates; scores alone never approve a connection. Accept high-confidence connections is a separate, optional recovery action.';
 historyTarget=data.digest||null;
 historyListOffset=Math.floor((data.offset||0)/50)*50;
 members=data.image?[data.image,...data.candidates].map((r,i)=>({...r,origin_id:r.id,id:i+1,quarantined:i===0,keep:false})):[];
 $('files').textContent=data.inventory.readable||0;$('groupCount').textContent=data.total;
 $('groupCount').nextElementSibling.textContent='history entries';$('moved').textContent=data.total_files;$('movedLabel').textContent='unlinked quarantine files';
 $('review').classList.toggle('hidden',!data.image);$('empty').classList.toggle('hidden',!!data.image);
 $('empty').querySelector('h2').textContent=data.total_files?'No entries in this filter':'No unresolved quarantine entries';
 $('empty').querySelector('p').textContent=data.total_files?'Choose All unresolved to see every remaining entry. Needs review after verification includes only checked, unresolved entries; run Verify saved matches first.':'Check the inventory coverage and Issues above before considering history complete.';
 $('groupTitle').textContent=data.image?data.copy_count+' quarantined file(s) · choose surviving copy':'';
 $('groupKind').textContent=data.image?historyLabel(data.review_status):'';
 $('position').textContent=data.total?(data.offset+1)+' / '+data.total:'';
 $('reviewHelp').textContent='First card: already quarantined. Click Keep & next on the matching survivor to save its connection and advance immediately. Undo last connection brings the comparison back. Defer if unsure; no files move.';
 $('historyOrigins').textContent=(data.origins||[]).map(o=>'Original: '+(o.original_path||o.path)+(o.quarantine_path?'\nQuarantine: '+o.quarantine_path:'')).join('\n\n');
 $('historyCandidateCount').textContent=data.candidate_count?((historyPage*24+1)+'–'+Math.min((historyPage+1)*24,data.candidate_count)+' of '+data.candidate_count+' candidates'):(data.matching_ready?'No matches at '+data.matching_mode+'. Try Broad and refresh, or search/browse manually. The entry remains unresolved.':'Refresh duplicate history to run the original duplicate matcher on this inventory.');
 const c=data.counts;$('status').textContent='Duplicate history · '+data.matching_mode+' matching · '+data.total_files+' unlinked files · '+c.pending+' pending · '+c.deferred+' deferred · '+(c.discarded||0)+' intentionally discarded'+(c.no_counterpart?' · '+c.no_counterpart+' previously marked no counterpart':'');
 $('coverage').textContent=(data.complete_inventory?'Full inventory available. '+(data.matching_ready?'Original duplicate matcher applied. ':'Refresh required for original duplicate matching. '):'Inventory incomplete — refresh before relying on totals. ')+data.regular_groups+' regular duplicate groups remain. Exact, verified visual and saved keeper links are excluded. '+(data.issues.length?data.issues.length+' file issues need inspection.':'');
 $('errors').classList.toggle('hidden',!data.issues.length);$('progress').classList.add('hidden');
 renderHistoryList();renderCards();controls();
}
async function refreshHistory(force=false){
 if(polling||closed)return;polling=true;
 try{
  const state=await api('/api/bulk/state');if(!historyModeActive())return;
  historyState=state;
  if(state.running){const eta=state.phase_eta_seconds;$('status').textContent=state.phase+' · '+(state.done||0).toLocaleString()+' / '+(state.total||0).toLocaleString()+' · '+Math.floor((state.phase_elapsed_seconds||0)/60)+'m elapsed'+(eta==null?' · estimating remaining time…':' · ~'+Math.ceil(eta/60)+'m remaining in this stage');$('progress').classList.remove('hidden');$('progress').max=state.total||1;$('progress').value=state.done;$('review').classList.add('hidden');$('empty').classList.remove('hidden');$('empty').querySelector('h2').textContent=state.history_verifying?(state.history_verification?.policy==='high_confidence'?'Checking high-confidence connections':'Verifying saved matches'):'Refreshing full duplicate history';$('empty').querySelector('p').textContent=state.history_verifying?'Checking saved candidates only. Connections and completed checks are saved as it runs. Stop and resume with the same verification button. No files move.':'Comparing unresolved quarantine copies against survivors with the original duplicate matcher. No set grouping or file moves.'}
  else if(!state.id||state.error||state.interrupted||(!state.inventory&&!state.complete)){
   historyData=null;members=[];$('review').classList.add('hidden');$('empty').classList.remove('hidden');$('progress').classList.add('hidden');
   $('status').textContent=state.error||state.phase;$('empty').querySelector('h2').textContent='Refresh duplicate history to begin';$('empty').querySelector('p').textContent='Use your full collection folder, including quarantine. No need to build proposed sets.';
  }else if(force||historyLoadedJob!==state.id)await loadHistory();
  controls();
 }catch(e){toast(e.message,true)}finally{polling=false}
}
async function switchReviewQueue(){
 closeCompare();selected.clear();
 const active=historyModeActive();$('historySetup').classList.toggle('hidden',!active);
 const ids=['autoToolbar','autoInfo','selectionCount','moveSelected','clearSelection','sort','quarantineGroup','viewVerified','cancel','finishGroup'];
 const nodes=[...ids.map($),document.querySelector('label[for="sort"]')];
 if(active){
  regularMatching={mode:$('mode').value,workers:$('workers').value};
  for(const el of nodes){historyHidden.set(el,el.classList.contains('hidden'));el.classList.add('hidden')}
  historyState=await api('/api/bulk/state');historyConfig=historyState.config||{};
  $('mode').value=historyConfig.duplicate_mode||regularMatching.mode;$('workers').value=String(historyConfig.workers||regularMatching.workers);
  if(!$('historyRoots').value)$('historyRoots').value=(historyConfig.roots||[...paths('incoming'),...paths('reference')]).join('\n');
  historyLoadedJob=null;historyTarget=null;historyPage=0;
  await refreshHistory(true);
 }else{
  historyHidden.forEach((hidden,el)=>el.classList.toggle('hidden',hidden));historyHidden.clear();
  if(regularMatching){$('mode').value=regularMatching.mode;$('workers').value=regularMatching.workers;}
  $('undo').textContent='Undo last action';$('keepGroup').textContent='Keep all / dismiss group';$('groupCount').nextElementSibling.textContent='groups to review';
  document.querySelectorAll('#compareDialog .row button').forEach(b=>b.classList.remove('hidden'));
  for(const side of ['Left','Right'])$('keep'+side).textContent='Keep only this';
  $('reviewQueue').disabled=false;seenRevision=-1;await refresh(true);
 }
}
$('reviewQueue').onchange=()=>task(switchReviewQueue);
$('historyPick').onclick=()=>task(async()=>{const r=await api('/api/pick',{});if(r.path)$('historyRoots').value=[...new Set([...paths('historyRoots'),r.path])].join('\n')});
$('historyRefresh').onclick=()=>task(async()=>{
 const config={...historyConfig,roots:paths('historyRoots'),limit:0,duplicate_mode:$('mode').value,workers:Number($('workers').value)};
 // Retain the saved collection's companion choice; newly connected choices are explicit.
 if($('libraryCharacter').value)config.character_id=$('libraryCharacter').value;
 historyState=await api('/api/history/inventory',config);historyData=null;historyLoadedJob=null;historyTarget=null;historyPage=0;await refreshHistory(true);
});
$('historyVerify').onclick=()=>task(async()=>{historyState=await api('/api/history/verify',{job:historyState.id});historyLoadedJob=null;historyTarget=null;historyPage=0;await refreshHistory(true)});
$('historyHighConfidence').onclick=()=>task(async()=>{historyState=await api('/api/history/verify',{job:historyState.id,policy:'high_confidence'});historyLoadedJob=null;historyTarget=null;historyPage=0;await refreshHistory(true)});
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
 finishGroup:()=>{},
 keepGroup:()=>task(()=>markHistory('deferred')),
 undo:()=>task(async()=>{const restored=await api('/api/bulk/undo-origin',{job:historyData.job});historyTarget=restored.restored_target;historyPage=0;$('historyFilter').value='all';await loadHistory();toast('Connection undone. The restored comparison is ready to review.')}),
 prev:()=>task(async()=>{historyPage=0;await loadHistory(historyData.offset-1)}),
 next:()=>task(async()=>{historyPage=0;await loadHistory(historyData.offset+1)}),
 listPrev:()=>{historyListOffset=Math.max(0,historyListOffset-50);renderHistoryList();controls()},
 listNext:()=>{historyListOffset+=50;renderHistoryList();controls()},
 errors:()=>dialog('Inventory issues',(historyData?.issues||historyState?.issues||[]).map(e=>e.path+'\n'+e.message).join('\n\n'))
})){
 const regular=$(id).onclick;$(id).onclick=e=>historyModeActive()?action():regular(e);
}
