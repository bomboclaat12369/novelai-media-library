// Saved loops and source-frame matching. No duplicate-removal actions.
(() => {
 'use strict';
 const root=document.getElementById('nai-media-host')?.shadowRoot;if(!root)return;
 const API='http://127.0.0.1:8765';
 const request=(path,body)=>new Promise((resolve,reject)=>GM_xmlhttpRequest({method:body?'POST':'GET',url:API+path,
  headers:{'Content-Type':'application/json',Origin:'https://novelai.net'},data:body?JSON.stringify(body):null,timeout:240000,
  onload:r=>{try{const v=JSON.parse(r.responseText);if(r.status<200||r.status>=300)throw Error(v.error||'Video action failed');resolve(v)}catch(e){reject(e)}},
  onerror:()=>reject(Error('Start the companion and retry.')),ontimeout:()=>reject(Error('Video preparation timed out. Retry to reuse installed tools.'))}));
 const make=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e};
 const btn=(text,fn)=>{const b=make('button',text);b.type='button';b.onclick=fn;return b};
 const states=new WeakMap();
 const style=make('style');style.textContent=`.naiWorkflowOverlay{position:fixed;inset:0;background:#070a15dd;z-index:2147483600;display:flex;align-items:center;justify-content:center;padding:18px}.naiWorkflowPanel{background:#151a2c;border:1px solid #505a79;border-radius:14px;padding:20px;width:min(780px,95vw);max-height:94vh;overflow:auto;color:#eef0ff;font:14px system-ui}.naiWorkflowPanel video{width:100%;max-height:45vh;background:#080a12}.naiWorkflowPanel button{width:auto;padding:8px 12px;margin:4px}.naiWorkflowPanel input{width:120px;background:#0b1120;color:inherit;border:1px solid #56607d;border-radius:6px;padding:8px}.naiWorkflowPanel .nwRow{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}.naiWorkflowPanel .nwEndpoints{display:grid;grid-template-columns:1fr 1fr;gap:14px}.naiWorkflowPanel .nwEndpoints img{display:block;max-width:100%;height:72px;object-fit:contain}.naiLoopRail{font-size:10px!important;min-height:28px!important}`;root.append(style);
 function stop(video){const old=states.get(video);if(old){old.active=false;if(old.callback&&video.cancelVideoFrameCallback)video.cancelVideoFrameCallback(old.callback);video.removeEventListener('timeupdate',old.check);video.removeEventListener('ended',old.check);states.delete(video)}}
 function playLoop(video,range){
  stop(video);const state={active:true,range,source:video.currentSrc||video.src};states.set(video,state);video.loop=false;
  state.check=()=>{if(!state.active)return;if(!video.isConnected||(video.currentSrc||video.src)!==state.source){stop(video);return}if(!video.seeking&&(video.currentTime>=range.end||video.currentTime<range.start-.025)){const ended=video.ended;video.currentTime=range.start;if(ended)video.play().catch(()=>{})}};
  const tick=()=>{if(!state.active)return;state.check();if(state.active)state.callback=video.requestVideoFrameCallback(tick)};
  video.addEventListener('timeupdate',state.check);video.addEventListener('ended',state.check);
  if(video.requestVideoFrameCallback)state.callback=video.requestVideoFrameCallback(tick);
  video.currentTime=range.start;return video.play();
 }
 function identity(video){
  const direct=(video.currentSrc||video.src||'').match(/\/api\/media\/([0-9a-f]+)\/original/);if(direct)return direct[1];
  const ids=root.naiSlotMediaIds?.()||[];
  const stage=video.closest('.stage');if(stage)return ids[stage.id==='stage2'?1:0];
  const pane=video.closest('.naiTriplePane');if(pane){const panes=[...pane.parentNode.children].filter(n=>n.classList.contains('naiTriplePane'));return ids[panes.indexOf(pane)]}
 }
 async function editor(original){
  const id=identity(original);if(!id)throw Error('Select a saved video first.');
  const library=root.naiGetLibrary?.()||await request('/api/library');let media=library.media.find(m=>m.id===id);if(!media)return;
  const overlay=make('div'),panel=make('section');overlay.className='naiWorkflowOverlay';panel.className='naiWorkflowPanel';overlay.append(panel);
  const title=make('h2','Video loop & matching frame'),note=make('p','Edit boundaries while paused. Play loop locks the range; Loop off returns to ordinary playback.'),status=make('p');status.setAttribute('role','status');
  const video=make('video');video.controls=true;video.playsInline=true;video.crossOrigin='anonymous';video.src=original.currentSrc||original.src;original.pause();
  let mode='edit',busy=false,range=media.video_loop?{...media.video_loop}:{start:original.currentTime||0,end:Math.min((original.currentTime||0)+1,original.duration||Infinity)};
  const row=make('div');row.className='nwRow';const endpoints=make('div');endpoints.className='nwEndpoints';const fields={},pictures={},buttons=[];
  function paint(){for(const key of ['start','end'])fields[key].value=Number(range[key]||0).toFixed(6);for(const b of buttons)b.disabled=busy||(mode==='play'&&b.dataset.edit==='1');status.textContent=busy?'Preparing local frame controls…':mode==='play'?'Playing locked loop':'Editing · use frame steps to choose exact source timestamps';}
  async function run(fn){if(busy)return;busy=true;paint();try{await fn()}catch(e){status.textContent=e.message}finally{busy=false;for(const b of buttons)b.disabled=mode==='play'&&b.dataset.edit==='1'}}
  function seek(seconds){return new Promise((resolve,reject)=>{video.pause();if(Math.abs(video.currentTime-seconds)<1e-7){resolve();return}const done=()=>{clearTimeout(timer);video.removeEventListener('seeked',done);resolve()};const timer=setTimeout(()=>{video.removeEventListener('seeked',done);reject(Error('Video seek timed out.'))},15000);video.addEventListener('seeked',done);video.currentTime=seconds})}
  function picture(key){try{const c=make('canvas');c.width=240;c.height=Math.max(1,Math.round(240*video.videoHeight/video.videoWidth));c.getContext('2d').drawImage(video,0,0,c.width,c.height);pictures[key].src=c.toDataURL('image/jpeg',.85)}catch{}}
  for(const key of ['start','end']){
   const box=make('div'),label=make('label',key==='start'?'Start (seconds)':'End (seconds)'),input=make('input'),img=make('img');img.alt=key+' frame';input.type='number';input.min='0';input.step='0.000001';input.setAttribute('aria-label',label.textContent);fields[key]=input;pictures[key]=img;label.append(input);
   input.onchange=()=>{if(mode==='play'){paint();return}range[key]=Number(input.value)};
   const lock=btn('Set '+key,()=>run(async()=>{stop(video);video.pause();const result=await request('/api/media/'+id+'/video-step',{seconds:video.currentTime,direction:0});await seek(result.seconds);range[key]=result.seconds;picture(key);paint()}));lock.dataset.edit='1';buttons.push(lock);
   box.append(label,lock,img);endpoints.append(box);
  }
  for(const [label,direction] of [['← Frame',-1],['Frame →',1]]){const b=btn(label,()=>run(async()=>{stop(video);const r=await request('/api/media/'+id+'/video-step',{seconds:video.currentTime,direction});await seek(r.seconds);status.textContent='Source frame at '+r.seconds.toFixed(6)+' s'}));b.dataset.edit='1';buttons.push(b);row.append(b)}
  async function save(){range={start:Number(fields.start.value),end:Number(fields.end.value)};if(!Number.isFinite(range.start)||!Number.isFinite(range.end)||range.start<0||range.end<=range.start||range.end>video.duration+.001)throw Error('Choose an end after the start and within the clip.');media=await request('/api/media/'+id+'/video-loop',{loop:range});root.naiApplyMediaUpdate?.(media)}
  const saveButton=btn('Save loop',()=>run(async()=>{await save();status.textContent='Loop saved.'}));saveButton.dataset.edit='1';
  const play=btn('Play loop',()=>run(async()=>{await save();mode='play';for(const f of Object.values(fields))f.disabled=true;await playLoop(video,range);paint()}));
  const edit=btn('Edit loop',()=>{mode='edit';stop(video);video.pause();for(const f of Object.values(fields))f.disabled=false;paint()});
  const off=btn('Loop off',()=>{stop(video);stop(original);mode='edit';for(const f of Object.values(fields))f.disabled=false;paint();status.textContent='Loop off. Saved boundaries retained.'});
  const clear=btn('Clear saved loop',()=>run(async()=>{stop(video);stop(original);media=await request('/api/media/'+id+'/video-loop',{loop:null});root.naiApplyMediaUpdate?.(media);status.textContent='Saved loop cleared.'}));clear.dataset.edit='1';
  const match=btn('Use frame to find sets',()=>run(async()=>{
   mode='edit';stop(video);video.pause();media=await request('/api/media/'+id+'/video-frame',{seconds:video.currentTime});root.naiApplyMediaUpdate?.(media);
   const blob=await new Promise((resolve,reject)=>GM_xmlhttpRequest({method:'GET',url:API+'/api/media/'+id+'/matching-frame',responseType:'blob',onload:r=>r.status===200?resolve(r.response):reject(Error('Frame unavailable')),onerror:()=>reject(Error('Frame unavailable'))}));
   const url=URL.createObjectURL(blob);close(false);
   await root.naiFindMatchingSets({queries:[{...media,url,video_frame_id:id}],chooseLabel:'Add video to this set',onChoose:async sid=>{
    const latest=await request('/api/library');const other=latest.sets.filter(s=>s.id!==sid&&s.media_ids.includes(id));
    if(other.length&&!confirm('Move this video out of '+other.map(s=>s.name).join(', ')+' into the selected set?'))throw Error('No change made.');
    await request('/api/sets/'+sid,{add_media_ids:[id],preserve_placement:true});await root.naiReloadLibrary?.();
   }});
   // The matching modal owns this URL while open. Revoke when it disappears.
   const watcher=new MutationObserver(()=>{if(!root.querySelector('.naiMatchWrap')){URL.revokeObjectURL(url);watcher.disconnect()}});watcher.observe(root,{childList:true,subtree:true});
  }));match.dataset.edit='1';match.hidden=typeof root.naiFindMatchingSets!=='function';
  buttons.push(saveButton,play,edit,off,clear,match);row.append(saveButton,play,edit,off,clear);
  function close(resume=true){stop(video);video.pause();if(resume&&mode==='play')playLoop(original,range).catch(()=>{});else original.currentTime=video.currentTime;video.removeAttribute('src');video.load();overlay.remove();document.removeEventListener('keydown',escape,true)}
  const escape=e=>{if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();close()}};
  panel.append(title,note,video,endpoints,row,match,status,btn('Close',()=>close()));
  (root.fullscreenElement||root).append(overlay);document.addEventListener('keydown',escape,true);
  video.addEventListener('loadedmetadata',()=>{video.currentTime=original.currentTime||0},{once:true});paint();
 }
 let queued=false;
 function mount(){queued=false;for(const rail of root.querySelectorAll('#videoTools,.naiFullscreenMarkerRail')){
  if(rail.querySelector('[data-nai-loop]'))continue;
  const button=btn('Loop',()=>{const video=rail.closest('.stage,.naiTriplePane,.naiThirdMedia')?.querySelector('video');if(video)editor(video).catch(e=>alert(e.message))});button.className='naiLoopRail';button.dataset.naiLoop='1';button.title='Edit loop or select a matching frame';rail.append(button);
 }}
 const observer=new MutationObserver(()=>{if(!queued){queued=true;queueMicrotask(mount)}});observer.observe(root,{childList:true,subtree:true});mount();
 root.naiVideoWorkflow={editor,playLoop,stop,identity};
})();
