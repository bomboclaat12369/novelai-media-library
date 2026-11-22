// Membership and the decision to import a Set have separate controls.
let applyPendingSetDetails=null;
(()=>{
 const filter=$('setFilter'),reviewOption=new Option('Sets under review','under_review');
 filter.add(reviewOption,1);
 if(localStorage.getItem('organizer-setFilter')==='under_review')filter.value='under_review';

 const saveHeld=button('Save for review',()=>task(async()=>{
  const target=$('target').value;
  const result=await mutate('save',{ids:[...selection],target,hold_for_review:true,
   name:target?'':$('setName').value,...(target?{}:{colors:draftColors,categories:draftCategories,favorite:draftFavorite})});
  if(!result)return;
  $('setName').value='';$('target').value='';targetChanged(false);
  if(view)await open(currentKind,currentId,offset);
  await related();
  toast(result.save_result.saved+' selected images saved in Sets under review.'+
   (result.save_result.skipped?' '+result.save_result.skipped+' already-assigned photos skipped.':''));
 }));
 saveHeld.id='saveForReview';
 saveHeld.title='Keep this shoot together in Workbench until you promote it';
 $('save').after(saveHeld);

 const change=button('Confirm Set and hold for review',()=>task(async()=>{
  const group=data.sets.find(g=>g.id===currentId);if(!group)return;
  await mutate('set_review',{target:group.id,under_review:!group.under_review});
  await open('set',group.id,offset,false);
  toast(group.under_review?'Promoted. This Set is eligible for Import to library.':'Set confirmed. Find it in Sets → Sets under review.');
 }));
 change.id='setReviewStatus';change.classList.add('hidden');$('editSetColors').before(change);
 const previousControls=controls;
 controls=function(){
  previousControls();saveHeld.disabled=$('save').disabled;
  const group=currentKind==='set'&&data?.sets.find(g=>g.id===currentId);
  change.classList.toggle('hidden',!group);change.disabled=busy||!view;
  change.textContent=group?.under_review?'Promote to regular Set':'Confirm Set and hold for review';
  change.title=group?.library_id?'Applies to this Workbench draft. Previously imported photos keep their Library placement.':'Sets under review stay in Workbench until promoted.';
 };
 const previousRenderSets=renderSets;
 renderSets=function(target){
  previousRenderSets(target);
  const held=new Set(data.sets.filter(g=>g.under_review).map(g=>g.id));
  for(const option of $('target').options)if(held.has(option.value))option.textContent+=' · under review';
 };
 const previousFiltered=filtered;
 filtered=function(){
  if(tab!=='sets')return previousFiltered();
  if(filter.value!=='under_review')return previousFiltered().filter(g=>!g.under_review);
  const search=$('search').value.trim().toLowerCase(),mode=$('setSort').value;
  const rows=data.sets.filter(g=>g.under_review&&[g.name,...(g.colors||[])].join(' ').toLowerCase().includes(search));
  const byName=(a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true,sensitivity:'base'});
  if(mode==='nameAsc'||mode==='nameDesc')rows.sort((a,b)=>(mode==='nameAsc'?1:-1)*byName(a,b));
  else if(['createdAsc','createdDesc','updatedDesc'].includes(mode)){
   const field=mode==='updatedDesc'?'updated':'created',direction=mode==='createdAsc'?1:-1;
   rows.sort((a,b)=>{const x=Number(a[field])||0,y=Number(b[field])||0;return !x||!y?(!!y-!!x)||byName(a,b):direction*(x-y)||byName(a,b)});
  }
  return rows;
 };

 const previousRestore=restoreSession;
 restoreSession=function(){
  const ui=previousRestore(),address=new URL(location.href);
  if(address.searchParams.get('setList')!=='under_review')return ui;
  $('search').value='';$('setsTab').click();filter.value='under_review';
  filter.dispatchEvent(new Event('change',{bubbles:true}));
  const first=filtered()[0];if(first){currentKind='set';currentId=first.id;offset=0}
  address.searchParams.delete('setList');history.replaceState(null,'',address);
  return {...ui,gridScroll:0,navScroll:0};
 };

 // The same details editor can stage fields for a likely group until approval.
 const originalOpen=openColors,originalSave=$('saveSetColors').onclick;
 openColors=function(target=''){applyPendingSetDetails=null;originalOpen(target)};
 $('colorDetails').addEventListener('close',()=>{applyPendingSetDetails=null});
 $('saveSetColors').onclick=event=>{
  if(!applyPendingSetDetails)return originalSave(event);
  return task(async()=>{
   const name=$('setEditName').value.trim();
   if(!name||name.length>250)throw Error('Give the Set a name (up to 250 characters).');
   const colors=[...new Set($('setColors').value.split(',').map(s=>s.trim()).filter(Boolean))];
   if(colors.length>50||colors.some(c=>c.length>150))throw Error('Use up to 50 color descriptors, each at most 150 characters.');
   const details={name,colors,categories:chosenCategories(),favorite:$('setFavorite').checked};
   if(colorTarget)details.in_purgatory=$('setPurgatory').checked;
   applyPendingSetDetails(details);$('colorDetails').close();
  });
 };
})();
