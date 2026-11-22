// The pilot saves confirmed shoots to the Folder Organizer's shared review list.
(()=>{
 const list=element('a','Sets under review');list.href='/organizer?setList=under_review';$('export').after(list);
 const action=element('button','Confirm and hold for review');action.id='reviewFolderSet';$('accept').before(action);
 const originalSelection=updateSelection;
 updateSelection=function(){
  originalSelection();
  const linked=current?.folder_set;
  action.hidden=!current||current.id==='unassigned';action.disabled=busy||(!linked&&selected.size<2);
  action.textContent=linked?.under_review?'Promote to regular Set':linked?'Hold Set for review':'Confirm and hold for review';
  if(linked)$('groupInfo').textContent=linked.name+' · '+(linked.under_review?'Set under review':'Regular Workbench Set');
 };
 action.onclick=async()=>{
  if(busy||!current||current.id==='unassigned')return;
  busy=true;updateSelection();
  try{
   const linked=current.folder_set;
   const payload={job:state.id,proposal:current.id,revision:current.organizer_revision,target:linked?.id||'',under_review:!linked?.under_review,
    ids:[...selected],name:$('setName').value,colors:$('colors').value.split(',').map(x=>x.trim()).filter(Boolean),
    categories:[...$('categories').selectedOptions].map(o=>o.value),notes:$('notes').value};
   let saved=await api('bulk/review-set',payload);
   if(saved.confirmation_required){
    const names=[...new Set(saved.conflicts.flatMap(row=>row.sets.map(s=>s.name)))].join(', ');
    if(!confirm('Move '+saved.conflicts.length+' already assigned photo(s) from '+names+' into '+saved.destination+'?'))return;
    saved=await api('bulk/review-set',{...payload,membership_confirmation:saved.membership_confirmation});
   }
   if(saved.confirmation_required)throw Error('Membership changed. Open the proposal again.');
   await openGroup(current.id);
  }catch(e){error(e)}finally{busy=false;updateSelection()}
 };
 updateSelection();
})();
