// Automatic memberships are persisted in the same Set records as manual work.
const matchedDialog=el('dialog');
matchedDialog.id='matchedDialog';
matchedDialog.setAttribute('aria-label','Review matched photos');
const matchStyles=el('style');
matchStyles.textContent=`
 #matchedDialog{width:min(1050px,94vw);height:auto;max-height:88vh;padding:0}
 #matchedDialog h2,#matchedDialog h3{margin:0}
 .match-bar,.match-tools{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
 .match-bar{padding:16px 20px;border-bottom:1px solid var(--line);justify-content:space-between}
 .match-body{padding:14px 20px;overflow:auto;max-height:64vh}
 .match-tools{margin-bottom:12px}.match-tools select{max-width:100%}
 .match-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:12px}
 .match-photo{margin:0;padding:7px;border:1px solid var(--line);border-radius:8px;min-width:0}
 .match-photo>button:first-child{display:block;width:100%;padding:0;background:#0c1015;border:0}
 .match-photo img{display:block;width:100%;height:178px;object-fit:contain}
 .match-photo figcaption{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:6px 0}
 .match-actions{display:flex;flex-wrap:wrap;gap:4px}.match-examples{display:flex;gap:6px;margin:6px 0 12px}
 .match-examples img{height:72px;max-width:92px;object-fit:contain;display:block}
 .match-status{margin:8px 0;color:var(--muted)}
`;
document.head.append(matchStyles);document.body.append(matchedDialog);

async function openMatchReview(period='all'){
 const job=data.job;
 let target='',offset=0;
 let dirty=false,jumping=false;
 if(matchDialog.open)matchDialog.close();
 matchedDialog.replaceChildren();
 const bar=el('div',undefined,'match-bar'),title=el('h2','Review matched photos');
 const close=button('Close',()=>matchedDialog.close());
 bar.append(title,close);
 const body=el('div',undefined,'match-body'),status=el('p',undefined,'match-status');
 status.setAttribute('role','status');
 matchedDialog.append(bar,body,status);
 if(!matchedDialog.open)matchedDialog.showModal();
 matchedDialog.onclose=async()=>{
  if(!dirty||jumping||data.job!==job||!view)return;
  try{const saved=captureSession();await open(currentKind,currentId,view.offset||0,false);await related();await restoreScroll(saved)}
  catch(error){toast(error.message)}
 };
 async function render(){
  let page;
  try{page=await api('match-review',{job,period,target,offset})}catch(e){status.textContent=e.message;return}
  if(!matchedDialog.open)return;
  target=page.target||'';offset=page.offset;
  const tools=el('div',undefined,'match-tools'),which=el('select');
  which.setAttribute('aria-label','Match history');
  which.add(new Option('All matches','all'));which.add(new Option('Latest batch','latest'));which.value=period;
  which.onchange=()=>task(async()=>{period=which.value;target='';offset=0;await render()});
  tools.append(which);
  const undo=button('Undo last review',()=>task(async()=>{await mutate('undo');dirty=true;await render()}));
  if(data.state.undo?.match_review)tools.append(undo);
  body.replaceChildren(tools);
  if(!page.sets.length){status.textContent='No current matches in this view.';return}
  const picker=el('select');picker.setAttribute('aria-label','Destination Set');
  for(const s of page.sets)picker.add(new Option(s.name+' · '+s.count,s.id));
  picker.value=target;picker.onchange=()=>task(async()=>{target=picker.value;offset=0;await render()});
  tools.append(picker,button('Open full Set',()=>task(async()=>{jumping=true;matchedDialog.close();await open('set',target)})));
  const selected=page.sets.find(s=>s.id===target);
  body.append(el('h3',selected.name));
  const openPhoto=(photo,list)=>{
   for(const item of list)images.set(item.id,item);
   viewerIds=list.map(i=>i.id);viewerAt=viewerIds.indexOf(photo.id);drawViewer();$('viewer').showModal();
  };
  if(page.examples.length){
   body.append(el('small','Previously assigned photos','muted'));
   const examples=el('div',undefined,'match-examples');
   for(const item of page.examples){const b=button('',()=>openPhoto(item,page.examples)),im=el('img');im.src=imageURL(item.id,240);im.alt=item.name;b.append(im);examples.append(b)}
   body.append(examples);
  }
  async function decide(action,ids){
   try{await mutate(action,{target,ids,match_review:true});dirty=true;await render()}catch(e){status.textContent=e.message}
  }
  const grid=el('div',undefined,'match-grid');body.append(grid);
  for(const item of page.photos){
   const card=el('figure',undefined,'match-photo'),preview=button('',()=>openPhoto(item,page.photos));
   const im=el('img');im.loading='lazy';im.src=imageURL(item.id,600);im.alt=item.name;preview.append(im);
   const caption=el('figcaption',item.name);caption.title=item.name;
   const actions=el('div',undefined,'match-actions');
   if(item.reviewed)actions.append(el('small','Kept','muted'));
   else actions.append(button('Keep',()=>task(()=>decide('confirm_matches',[item.id]))));
   if(item.removable)actions.append(button(item.other_membership?'Remove from draft':'Return to unmatched',()=>task(()=>decide('remove',[item.id]))));
   else actions.append(el('small','In Library','muted'));
   card.append(preview,caption,actions);grid.append(card);
  }
  const footer=el('div',undefined,'match-tools');
  const pending=page.photos.filter(i=>!i.reviewed).map(i=>i.id);
  if(pending.length)footer.append(button('Keep all on this page',()=>task(()=>decide('confirm_matches',pending))));
  if(page.count>24){
   const prev=button('Previous page',()=>task(async()=>{offset-=24;await render()}));
   const next=button('Next page',()=>task(async()=>{offset+=24;await render()}));
   prev.disabled=!offset;next.disabled=offset+24>=page.count;footer.append(prev,el('small',Math.floor(offset/24)+1+' / '+Math.ceil(page.count/24)),next);
  }
  body.append(footer);
  status.textContent=selected.reviewed+' of '+selected.count+' reviewed in this Set · '+page.total+' matched photos across '+page.sets.length+' Sets';
 }
 await render();
}
