// Compare and resolve two shoots without leaving the post underneath.
async function openSplitReview(start='',afterChange=null){
 const job=data.job,dialog=el('dialog'),title=el('h2','Review split Sets'),body=el('div'),status=el('p');
 dialog.id='splitReview';dialog.setAttribute('aria-label','Review split Sets');
 dialog.style.cssText='width:min(1050px,94vw);max-height:90vh;overflow:auto;padding:18px';
 status.setAttribute('role','status');
 const header=el('div',undefined,'match-bar');header.append(title,button('Close',()=>dialog.close()));
 dialog.append(header,status,body);document.body.append(dialog);dialog.showModal();
 let offset=0,left='',right='',leftPage=0,rightPage=0,serial=0,dirty=false,saving=false,notice='';
 const position=captureSession();
 dialog.onclose=async()=>{
  ++serial;dialog.remove();if(!dirty||job!==data?.job)return;
  try{
   if(view){
    if(currentKind==='set'&&!data.sets.some(g=>g.id===currentId)){
     const successor=data.sets.find(g=>g.merged_sources?.includes(currentId));
     if(successor)currentId=successor.id;
    }
    await open(currentKind,currentId,view.offset||0,false);await related();await restoreScroll(position);
   }
   if(afterChange)await afterChange();
  }catch(e){toast(e.message)}
 };
 function resetPages(){leftPage=0;rightPage=0}
 async function render(){
  const request=++serial;status.textContent='Comparing Sets…';
  let p;
  try{p=await api('split-review',{job,offset,left,right,focus:start,left_page:leftPage,right_page:rightPage})}
  catch(e){if(request===serial)status.textContent=e.message;return}
  if(!dialog.open||request!==serial)return;
  offset=p.offset;body.replaceChildren();status.textContent=notice;notice='';
  const list=el('div',undefined,'match-tools');
  const compare=el('details'),summary=el('summary','Choose two Sets');
  const pickA=el('select'),pickB=el('select');
  pickA.setAttribute('aria-label','First Set');pickB.setAttribute('aria-label','Second Set');
  for(const control of [pickA,pickB]){
   control.add(new Option('Choose a Set',''));
   for(const g of p.choices)control.add(new Option(g.name+' · '+g.count,g.id));
  }
  pickA.value=left||start||p.left?.id||'';pickB.value=right||p.right?.id||'';
  const pick=button('Compare Sets',()=>task(async()=>{
   if(!pickA.value||!pickB.value||pickA.value===pickB.value){status.textContent='Choose two different Sets.';return}
   left=pickA.value;right=pickB.value;offset=0;resetPages();await render();
  }));
  const fields=el('div',undefined,'match-tools');fields.append(pickA,pickB,pick);compare.append(summary,fields);
  compare.open=!!start&&!left||!p.total;list.append(compare);
  if(left){list.append(button('Back to possible splits',()=>task(async()=>{left=right=start='';offset=0;resetPages();await render()})))}
  else if(p.total){const prev=button('Previous',()=>task(async()=>{offset--;resetPages();await render()}));
   const next=button('Next',()=>task(async()=>{offset++;resetPages();await render()}));
   prev.disabled=offset===0;next.disabled=offset+1>=p.total;list.append(prev,el('span',(offset+1)+' of '+p.total),next);}
  if(data.state.undo?.split_review)list.append(button('Undo last decision',()=>task(async()=>{
   if(saving)return;saving=true;
   try{await mutate('undo');dirty=true;left=right=start='';resetPages();notice='Decision undone.';await render()}catch(e){status.textContent=e.message}finally{saving=false}
  })));
  body.append(list);
  if(!p.left){body.append(el('p','No possible splits to review. You can choose two Sets to compare.'));return}
  if(p.reason)body.append(el('p',p.reason));
  if(p.fragment)body.append(el('p','The second group is still unassigned. You can add it to this shoot or save it as its own Set.'));
  const columns=el('div');columns.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:16px';
  function pane(side,isLeft){
   const area=el('section');area.append(el('h3',side.name+' · '+side.count+' photos'));
   const photos=el('div',undefined,'match-grid');photos.style.gridTemplateColumns='repeat(auto-fill,minmax(100px,1fr))';
   for(const photo of side.photos){
    const im=el('img');im.src=imageURL(photo.id,400);im.alt=photo.name;im.loading='lazy';im.style.cssText='width:100%;height:130px;object-fit:contain';
    const zoom=button('',()=>{for(const i of side.photos)images.set(i.id,i);viewerIds=side.photos.map(i=>i.id);viewerAt=viewerIds.indexOf(photo.id);drawViewer();$('viewer').showModal()});
    zoom.title=photo.name;zoom.append(im);photos.append(zoom);
   }
   area.append(photos);
   if(side.count>24){const change=async delta=>{if(isLeft)leftPage+=delta;else rightPage+=delta;await render()};
    const back=button('Previous photos',()=>task(()=>change(-24))),more=button('Next photos',()=>task(()=>change(24)));
    back.disabled=!side.offset;more.disabled=side.offset+24>=side.count;area.append(back,more);}
   return area;
  }
  columns.append(pane(p.left,true),pane(p.right,false));body.append(columns);
  const actions=el('div',undefined,'match-tools'),keep=el('select'),label=el('label','Keep the name ');
  keep.setAttribute('aria-label','Set to keep');
  if(p.right.can_retire)keep.add(new Option(p.left.name,p.left.id));
  if(!p.fragment&&p.left.can_retire)keep.add(new Option(p.right.name,p.right.id));
  keep.value=p.keep;label.append(keep);
  const holdLabel=el('label'),hold=el('input');hold.type='checkbox';
  holdLabel.append(hold,document.createTextNode(p.fragment?' Hold resulting Set for review':' Hold resulting Set(s) for review'));
  holdLabel.title=p.fragment?'Applies to the Set you create or add to.':'Keeping the shoots separate holds both Sets. Combining them holds the combined Set.';
  async function decide(action){
   if(saving)return;saving=true;for(const b of actions.querySelectorAll('button'))b.disabled=true;
   try{
    if(data.state.revision!==p.revision)throw Error('The collection changed. Reopen this comparison.');
    const chosen=keep.selectedOptions[0]?.textContent;
    await mutate(action,{left:p.left.id,right:p.right.id,keep:keep.value,stamp:p.stamp,hold_for_review:hold.checked});
    dirty=true;left=right=start='';resetPages();
    notice=action==='combine_split'?'Combined in '+chosen+'.':'Saved as separate shoots.';
    await render();
   }catch(e){status.textContent=e.message}finally{saving=false;for(const b of actions.querySelectorAll('button'))b.disabled=false}
  }
  actions.append(label,holdLabel,button(p.fragment?'Add group to Set':'Combine Sets',()=>task(()=>decide('combine_split')),'primary'),
                 button(p.fragment?'Create separate Set':'Keep separate',()=>task(()=>decide('separate_split'))));
  body.append(actions);
 }
 await render();
}
