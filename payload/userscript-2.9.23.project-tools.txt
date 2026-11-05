// Production-renderer Studio and local project diagnostics/checkpoints.
(() => {
 'use strict';
 const root=document.getElementById('nai-media-host')?.shadowRoot;
 if(!root||document.documentElement.dataset.naiStandalone!=='1')return;
 const request=root.naiOutfitRequest,make=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e};
 const button=(text,fn)=>{const b=make('button',text);b.type='button';b.onclick=fn;return b};
 function dialog(title){const wrap=make('div'),panel=make('section'),status=make('p'),cleanup=[];wrap.className='naiWorkflowOverlay';panel.className='naiWorkflowPanel';wrap.append(panel);panel.append(make('h2',title));
  const close=()=>{wrap.remove();document.removeEventListener('keydown',escape,true);for(const fn of cleanup)fn()};const escape=e=>{if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();close()}};
  panel.append(button('Close',close));root.append(wrap);document.addEventListener('keydown',escape,true);return {wrap,panel,status,close,cleanup};}
 function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=make('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 async function systemTools(){
  const {panel,status}=dialog('Project tools');panel.append(make('p','Create complete checkpoints from Media Workbench to include organizer and duplicate history. These library checkpoints cover sets, cards, loops and battles.'));
  const originals=make('input');originals.type='checkbox';const label=make('label',' Include original library media');label.prepend(originals);
  const list=make('div');const create=button('Create library checkpoint',async()=>{create.disabled=true;status.textContent='Creating checkpoint…';try{const result=await request('/api/checkpoints/create',{include_media:originals.checked});status.textContent='Saved '+result.id;await refresh()}catch(e){status.textContent=e.message}finally{create.disabled=false}});
  panel.append(label,create,button('Download diagnostics',async()=>{try{const d=await request('/api/diagnostics');d.interface_version=document.documentElement.dataset.naiMediaPayloadVersion;d.browser_timings=root.naiWorkflowTimings||{};download(d,'media-library-diagnostics.json');status.textContent='Diagnostics downloaded.'}catch(e){status.textContent=e.message}}),status,list);
  async function refresh(){const d=await request('/api/checkpoints');list.replaceChildren();for(const item of d.checkpoints){const row=make('p');row.append(make('span',item.at+' · '+item.label+' '),button('Preview restore',async()=>{try{
   const p=await request('/api/checkpoints/preview',{id:item.id});list.replaceChildren(make('h3','Restore preview'),make('p',p.current.media+' → '+p.restore.media+' media items; '+p.current.sets+' → '+p.restore.sets+' sets. Battle history will also return to this checkpoint.'));
   for(const name of p.missing_media.slice(0,20))list.append(make('p','Missing: '+name));
   const apply=button('Restore checkpoint',async()=>{apply.disabled=true;try{await request('/api/checkpoints/restore',{id:item.id,token:p.token});location.reload()}catch(e){status.textContent=e.message;apply.disabled=false}});apply.disabled=!!p.missing_media.length;list.append(apply,button('Back',()=>refresh().catch(e=>status.textContent=e.message)));
  }catch(e){status.textContent=e.message}}));list.append(row)}}
  await refresh();
 }
 async function studio(entry,rows,owner){
  const cards=root.naiCards,library=root.naiGetLibrary?.();if(!cards||!library)return;
  const media=library.media.filter(m=>m.media_type==='image');
  if(!media.length){alert('Import an image to preview card layouts.');return}
  let mid=entry?.preview_id||entry?.captain_id||entry?.images?.[0]||root.naiSlotMediaIds?.()[0]||media[0].id;
  if(!media.some(m=>m.id===mid))mid=media[0].id;
  owner=owner||media.find(m=>m.id===mid).character_id;await cards.load(owner);
  const {panel,status,cleanup}=dialog('Card Studio');panel.style.width='min(1450px,96vw)';
  let photoUrl=null,photoId=null;
  cleanup.push(()=>{serial++;if(photoUrl)URL.revokeObjectURL(photoUrl);photoUrl=null});
  panel.append(make('p','Previewing release '+document.documentElement.dataset.naiMediaPayloadVersion+' with the library’s current artwork and saved positioning. Preview controls do not edit cards.'));
  const fields=make('div');fields.className='nwRow';const inputs={};
  function select(label,options,value){const l=make('label',label+' '),s=make('select');s.style.cssText='width:auto;padding:7px;background:#0c1425;color:#eee';s.setAttribute('aria-label',label);for(const [key,name] of options){const o=make('option',name);o.value=key;s.append(o)}s.value=value;l.append(s);fields.append(l);inputs[label]=s;s.onchange=()=>render().catch(e=>status.textContent=e.message);return s}
  const source=select('Image',media.map(m=>[m.id,m.original_name]),mid);
  const tier=select('Rank',['Bronze','Silver','Gold','Platinum','Diamond','Master','Grandmaster'].map(s=>[s,s]),entry?.tier||'Grandmaster');
  const size=select('Size',[['190','Grid'],['280','Large grid'],['420','Detail'],['700','Full size']],'280');
  const fit=select('Position',[['saved','Saved'],['contain','FIT'],['fill','FILL']],'saved');
  const name=make('input'),overall=make('input'),number=make('input');name.value=library.characters.find(c=>c.id===owner)?.name||'Collection';name.style.width='210px';name.setAttribute('aria-label','Preview name');overall.type=number.type='number';overall.value=String(entry?cards.ovr(entry,rows||[entry])??99:99);overall.min='0';overall.max='99';number.value=String(entry?.position||7);number.min='1';number.max='99999';overall.setAttribute('aria-label','Preview overall');number.setAttribute('aria-label','Preview card number');
  fields.append(make('label','Name'),name,make('label','OVR'),overall,make('label','Number'),number);for(const input of [name,overall,number])input.onchange=()=>render().catch(e=>status.textContent=e.message);
  const grid=make('div');grid.style.cssText='display:grid;gap:18px;align-items:start;padding:12px 0';panel.append(fields,status,grid);
  let serial=0;
  async function render(){const seq=++serial;const selected=media.find(m=>m.id===source.value);if(!selected)return;owner=selected.character_id;status.textContent='Loading original image…';await cards.load(owner);
   if(photoId!==selected.id){const blob=await new Promise((resolve,reject)=>GM_xmlhttpRequest({method:'GET',url:'http://127.0.0.1:8765/api/media/'+encodeURIComponent(selected.id)+'/original',responseType:'blob',timeout:120000,onload:r=>r.status===200?resolve(r.response):reject(Error('Original image unavailable')),onerror:()=>reject(Error('Original image unavailable')),ontimeout:()=>reject(Error('Original image timed out'))}));if(seq!==serial||!panel.isConnected)return;if(photoUrl)URL.revokeObjectURL(photoUrl);photoUrl=URL.createObjectURL(blob);photoId=selected.id;}
   if(seq!==serial||!panel.isConnected)return;const started=performance.now();
   grid.replaceChildren();grid.style.gridTemplateColumns='repeat(auto-fit,minmax(min(100%,'+size.value+'px),'+size.value+'px))';
   for(const [id,label] of [['none','Base card'],...cards.editionNames]){
    const preview={...(entry||{}),id:selected.id,images:[selected.id],name:selected.original_name,count:1,tier:tier.value,rating:entry?.rating||1200,played:entry?.played||3,provisional:false,rating_status:'Developing',position:Math.max(1,Number(number.value)||1),preview_name:name.value,preview_ovr:Math.max(0,Math.min(99,Number(overall.value)||0)),edition_id:id==='none'?null:id,edition_settings:{...(entry?.edition_settings||{}),choice:id},titles:[]};
    const im=make('img');im.className='naiFramedSource';im.alt=selected.original_name;im.src=photoUrl;
    const tile=make('article'),card=cards.lightCard(preview,rows||[preview],owner,im,true,selected.id);card.style.width='100%';card.style.aspectRatio='3 / 4';
    if(fit.value!=='saved')cards.applyFrame(im,{fit:fit.value,x:0,y:0,zoom:1});
    tile.append(make('p',label),card);grid.append(tile);
   }
   root.naiWorkflowTimings={...(root.naiWorkflowTimings||{}),studio_build_ms:Math.round((performance.now()-started)*10)/10};status.textContent='14 layouts · actual production card renderer';
  }
  await render();
 }
 root.naiCardStudio=studio;
 if(root.naiCards?.debugPanel){const original=root.naiCards.debugPanel;root.naiCards.debugPanel=function(entry,owner,kind,onSaved,rows){const panel=original(entry,owner,kind,onSaved,rows);panel.append(button('Open in Card Studio',()=>studio(entry,rows,owner).catch(e=>alert(e.message))));return panel}}
 const toolbar=root.getElementById('addMediaBtn')?.parentNode;
 if(toolbar){toolbar.append(button('Card Studio',()=>studio().catch(e=>alert(e.message))),button('Project tools',()=>systemTools().catch(e=>alert(e.message))))}
})();
