// Manual search and duplicate comparison share the same searchable library browser.
const manualFindButton=button('Search Sets / images',()=>task(()=>openManualBrowser()));manualFindButton.id='manualFind';$('export').before(manualFindButton);
const heldOption=el('option','Set Purgatory');heldOption.value='purgatory';$('setFilter').append(heldOption);
const heldLabel=el('label'),heldCheck=el('input');heldCheck.type='checkbox';heldCheck.id='setPurgatory';heldLabel.append(heldCheck,document.createTextNode(' Set Purgatory'));$('setFavoriteRow').after(heldLabel);
const searchOpenColors=openColors;openColors=function(target=''){searchOpenColors(target);heldLabel.hidden=!target;heldCheck.checked=!!data?.sets.find(g=>g.id===target)?.in_purgatory;};
function libraryImageURL(owner,id,original=false){return '/api/organizer/library-image?owner='+encodeURIComponent(owner)+'&id='+encodeURIComponent(id)+'&token='+TOKEN+(original?'':'&size=600');}
async function openManualBrowser(compare=null){
 await saveDraft();const dialog=el('dialog');dialog.id=compare?'duplicateCompare':'manualBrowser';dialog.style.cssText='width:min(1200px,96vw);height:auto;max-height:94vh;overflow:auto;padding:22px';document.body.append(dialog);dialog.showModal();
 const close=button('Close',()=>dialog.close()),status=el('p'),form=el('form'),query=el('input'),kind=el('select'),scope=el('select'),category=el('select'),placement=el('select'),grid=el('div'),pages=el('div');
 const option=(v,t)=>{const o=el('option',t);o.value=v;return o;};kind.append(option('sets','Sets'),option('images','Images'));scope.append(option('library','Current Media Library'),option('inventory','Saved folder inventory'));placement.append(option('all','All locations'),option('main','Normal Sets / Main'),option('purgatory','Purgatory'),option('unassigned','Images without a Set'));
 kind.setAttribute('aria-label','Search type');scope.setAttribute('aria-label','Search source');category.setAttribute('aria-label','Search category');placement.setAttribute('aria-label','Search placement');query.setAttribute('aria-label','Manual search');query.placeholder='Name, category or description…';query.type='search';query.style.flex='1';
 const run=button('Search',()=>{});run.type='submit';form.className='row';form.style.flexWrap='wrap';form.append(scope,kind,query,category,placement,run);grid.style.cssText='display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px';
 dialog.append(el('h2',compare?'Compare before importing':'Find a Set or image manually'),close,el('p',compare?'Choose a library image to compare. Similarity alone does not confirm a duplicate. Your choice is saved and applied with the import.':'Search independently of automatic suggestions. Use a Set as the destination, or add an image to your current selection.'),form,status,grid,pages);
 let compareSerial=0,scanOnly=false,offset=0,serial=0,result=null,owner=compare?.owner||'',sourceId=compare?.rows[0]?.id;
 const sourcePicker=el('select');sourcePicker.setAttribute('aria-label','Incoming image');
 if(compare){kind.value='images';kind.disabled=true;scope.disabled=true;for(const row of compare.rows)sourcePicker.append(option(row.id,row.name));form.before(sourcePicker);sourcePicker.onchange=()=>{sourceId=sourcePicker.value;compareSerial++;comparison.replaceChildren();load(true);};form.before(button('Show matches from saved duplicate scan',()=>{scanOnly=true;load(true);}),button('Search all library images',()=>{scanOnly=false;load(true);}));}
 const comparison=el('section');comparison.id='comparisonImages';if(compare)form.before(comparison);
 async function act(row){
  try{if(compare){await showComparison(row);return;}
   let ids=[row.id],target=kind.value==='sets'?row.id:null;
   if(scope.value==='library'){const attached=await api('attach-library',{job:data.job,character_id:owner,library_instance:result.library_instance,...(kind.value==='sets'?{set_id:row.id}:{media_ids:[row.id]})});ids=attached.ids;target=attached.target;await refresh();}
   if(kind.value==='sets'){$('target').value=target;targetChanged();}else{for(const id of ids)selection.add(id);await saveDraft();controls();renderCounts();if(view)await open(currentKind,currentId,offset,false);}
   dialog.close();toast(kind.value==='sets'?'Set selected as the destination. Save your selected images when ready.':'Image added to your selection. Name and save a Set when ready.');
  }catch(e){status.textContent=e.message;}
 }
 function zoom(url,name){const d=el('dialog'),im=el('img');d.style.cssText='width:96vw;height:92vh;background:#080b13;padding:8px';im.src=url;im.alt=name;im.style.cssText='width:100%;height:90%;object-fit:contain';d.append(button('Close original',()=>d.close()),im);document.body.append(d);d.onclose=()=>d.remove();d.showModal();}
 async function showComparison(row){
  const sequence=++compareSerial,source=sourceId,sourceInfo=await api('comparison-source',{job:data.job,id:source});if(sequence!==compareSerial||source!==sourceId||!dialog.open)return;comparison.replaceChildren(el('h3','Incoming image and library image'));
  const pair=el('div');pair.style.cssText='display:grid;grid-template-columns:1fr 1fr;gap:14px';
  const incoming='/api/organizer/original?id='+encodeURIComponent(source)+'&token='+TOKEN;
  for(const [url,title,full] of [[imageURL(source),sourcePicker.selectedOptions[0].textContent,incoming],[libraryImageURL(owner,row.id),row.name,libraryImageURL(owner,row.id,true)]]){const pane=el('div'),img=el('img');img.src=url;img.alt=title;img.style.cssText='width:100%;height:330px;object-fit:contain';pane.append(el('p',title),img,button('View original',()=>zoom(full,title)));pair.append(pane);}
  comparison.append(pair,el('p','Incoming: '+(sourceInfo.width||'?')+' × '+(sourceInfo.height||'?')+' · Library: '+(row.width||'?')+' × '+(row.height||'?')+' · '+row.placement+(row.sets.length?' · '+row.sets.map(g=>g.name).join(', '):'')));
  const choice=data.state.duplicate_choices?.[sourceInfo.sha||source];if(choice)comparison.append(el('p','Saved choice: '+choice.action+(choice.target_name?' · '+choice.target_name:'')));
  async function decide(action){try{if(action==='replace'&&!confirm('Replace the library image source with this incoming original when you apply the import? The library ID, ratings, crop and memberships stay attached. A checkpoint and retained original are saved.'))return;
    await api('duplicate-choice',{job:data.job,revision:data.state.revision,id:source,character_id:owner,action,target:row.id,target_sha:row.sha,library_instance:result.library_instance});await refresh();status.textContent='Saved: '+({keep:'reuse the existing library image',replace:'replace its source during import',separate:'import separately'})[action]+'. Reopen the import preview to apply.';await showComparison(row);
   }catch(e){status.textContent=e.message;}}
  comparison.append(button('Keep existing image',()=>decide('keep')),button('Replace existing source',()=>decide('replace')),button('Import separately',()=>decide('separate')));
 }
 async function load(reset=false){const seq=++serial;if(reset)offset=0;run.disabled=true;status.textContent='Searching…';
  try{const response=await api('manual-search',{job:data.job,character_id:owner,source:scope.value,kind:kind.value,query:query.value,category:category.value,placement:placement.value,offset,...(compare&&scanOnly?{duplicate_source:sourceId}:{})});if(seq!==serial||!dialog.open)return;
   if(response.choose_character){grid.replaceChildren();status.textContent='Choose the girl to search.';for(const c of response.choose_character)grid.append(button(c.name,()=>{owner=c.id;load(true);}));return;}
   result=response;owner=result.character_id||owner;const old=category.value;category.replaceChildren(option('','All categories'),option('__none','Uncategorized'),...result.categories.map(c=>option(c.id,c.name)));category.value=old||'';status.textContent=result.total+' results'+(scanOnly?' from the saved duplicate scan. No new scan was run; search all images if needed.':'');grid.replaceChildren();
   for(const row of result.rows){const card=el('article');card.className='card';card.append(el('strong',row.name),el('small',row.placement));if(row.cover){const img=el('img');img.src=scope.value==='library'?libraryImageURL(owner,row.cover):imageURL(row.cover,600);img.loading='lazy';img.alt=row.name;img.style.cssText='height:210px;width:100%;object-fit:contain';img.onclick=()=>zoom(scope.value==='library'?libraryImageURL(owner,row.cover,true):'/api/organizer/original?id='+encodeURIComponent(row.cover)+'&token='+TOKEN,row.name);card.append(img);}card.append(button(compare?'Compare':kind.value==='sets'?'Use this Set':'Add to selection',()=>act(row)));grid.append(card);}
   pages.replaceChildren();for(const [label,delta] of [['Previous',-60],['Next',60]]){const b=button(label,()=>{offset+=delta;load();});b.disabled=offset+delta<0||offset+delta>=result.total;pages.append(b);}
  }catch(e){status.textContent=e.message;}finally{if(seq===serial)run.disabled=false;}
 }
 form.onsubmit=e=>{e.preventDefault();load(true);};scope.onchange=kind.onchange=()=>{category.value='';load(true);};category.onchange=placement.onchange=()=>load(true);dialog.onclose=()=>{serial++;compareSerial++;dialog.remove();if(compare)task(()=>previewTransfer({keepScope:true}));};await load();query.focus();
}
const searchShowTransfer=showTransfer;showTransfer=async function(plan){await searchShowTransfer(plan);const rows=[...plan.imports];for(const [id,choice] of Object.entries(plan.duplicates||{}))if(!rows.some(r=>r.id===id))rows.push({id,name:images.get(id)?.name||choice.source_sha||id});
 if(rows.length){const compare=button('Compare duplicates before importing',()=>{transferDialog.close();task(()=>openManualBrowser({owner:plan.character_id,rows}));});compare.id='compareImportDuplicates';transferDialog.querySelector('h2').after(compare);}
 for(const choice of Object.values(plan.duplicates||{}))transferDialog.append(el('p',(choice.action==='replace'?'Replace source: ':'Reuse existing: ')+(choice.target_name||choice.target)));
};
