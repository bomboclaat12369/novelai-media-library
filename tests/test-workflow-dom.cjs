// Behavior tests for the new controls, using the complete production assembly.
const {test}=require('node:test');
const {createRequire}=require('node:module');
const canvasRequire=process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?createRequire(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/package.json'):require;
const {createCanvas}=canvasRequire('@napi-rs/canvas');
const assert=require('node:assert/strict');
const {fixture,waitFor,delay}=require('./ui-fixture.cjs');
const click=(root,text)=>{const b=[...root.querySelectorAll('button')].find(b=>b.textContent===text);assert.ok(b,'Missing '+text);b.click();return b};
const image={id:'photo',character_id:'character',media_type:'image',original_name:'Original.png',categories:[],in_all:true};

test('Studio is reachable, uses originals and production cards, and leaves saved metadata alone',async()=>{
 const originals=[];const f=await fixture({media:[{...image}],configure:w=>{const canvases=new WeakMap();w.HTMLCanvasElement.prototype.getContext=function(){let c=canvases.get(this);if(!c){c=createCanvas(this.width,this.height);canvases.set(this,c)}c.width=this.width;c.height=this.height;return c.getContext('2d')};const normal=w.GM_xmlhttpRequest;w.GM_xmlhttpRequest=o=>{if(o.url.includes('/original'))originals.push(o.url);return normal(o)}}});
 try{click(f.root,'Card Studio');await waitFor(()=>f.root.querySelectorAll('.naiWorkflowPanel article').length===14,f.errors);
 const panel=f.root.querySelector('.naiWorkflowPanel');assert.ok(originals.some(p=>p.includes('/photo/original')));
 assert.ok([...panel.querySelectorAll('article img.naiFramedSource')].every(i=>i.src.startsWith('blob:')));
 const size=panel.querySelector('select[aria-label="Size"]');size.value='700';size.dispatchEvent(new f.w.Event('change'));await delay(30);
 assert.equal(panel.querySelectorAll('article').length,14);assert.ok(panel.textContent.includes('actual production card renderer'));assert.equal(f.writes.length,0);
 const count=f.revoked.length;click(panel,'Close');assert.equal(f.root.querySelector('.naiWorkflowPanel'),null);assert.ok(f.revoked.length>count,'original URL released on Close');assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

function videoFixture(){let saved={start:2,end:3};const calls=[];
 return fixture({media:[{id:'abcdef',character_id:'character',media_type:'video',original_name:'Clip.mp4',categories:[],in_all:false,video_loop:saved}],configure:w=>{
 const times=new WeakMap();Object.defineProperties(w.HTMLMediaElement.prototype,{duration:{get:()=>10},currentTime:{get(){return times.get(this)||0},set(v){times.set(this,v);queueMicrotask(()=>this.dispatchEvent(new w.Event('seeked')))}},paused:{get(){return !this._playing}}});
 w.HTMLMediaElement.prototype.play=function(){this._playing=true;return Promise.resolve()};w.HTMLMediaElement.prototype.pause=function(){this._playing=false};w.HTMLMediaElement.prototype.load=function(){};
 const normal=w.GM_xmlhttpRequest;w.GM_xmlhttpRequest=o=>{const route=new URL(o.url).pathname,b=JSON.parse(o.data||'{}');
 if(/\/video-(loop|step|frame)$/.test(route)){calls.push({route,body:b});let value;if(route.endsWith('video-step'))value={seconds:Math.round((b.seconds+b.direction*.1)*10)/10};else {if(route.endsWith('video-loop'))saved=b.loop;value={id:'abcdef',character_id:'character',media_type:'video',video_loop:saved,video_match_frame:{seconds:b.seconds||2}};}
 queueMicrotask(()=>o.onload({status:200,responseText:JSON.stringify(value)}));return {abort(){}};}return normal(o)};
 }}).then(f=>({...f,calls}));
}

test('loop editor steps source frames, locks Play, saves boundaries and retains them when Off',async()=>{
 const f=await videoFixture();try{await f.root.naiSelectMedia('abcdef');await delay(30);const original=f.root.querySelector('.stage video');assert.ok(original);original.currentTime=2;
 await f.root.naiVideoWorkflow.editor(original);const panel=f.root.querySelector('.naiWorkflowPanel');const preview=panel.querySelector('video');preview.currentTime=2;
 click(panel,'Frame →');await waitFor(()=>preview.currentTime===2.1,f.errors);await delay(10);click(panel,'Set start');await delay(20);
 const start=panel.querySelector('[aria-label="Start (seconds)"]'),end=panel.querySelector('[aria-label="End (seconds)"]');assert.equal(Number(start.value),2.1);end.value='3.2';end.dispatchEvent(new f.w.Event('change'));click(panel,'Play loop');await delay(20);
 assert.ok(start.disabled);assert.ok(f.calls.some(c=>c.route.endsWith('/video-loop')&&c.body.loop.start===2.1&&c.body.loop.end===3.2));
 preview.currentTime=3.3;preview.dispatchEvent(new f.w.Event('timeupdate'));assert.equal(preview.currentTime,2.1);
 click(panel,'Loop off');assert.equal(start.disabled,false);preview.currentTime=4;preview.dispatchEvent(new f.w.Event('timeupdate'));assert.equal(preview.currentTime,4);assert.equal(Number(start.value),2.1);
 click(panel,'Close');assert.equal(f.root.querySelector('.naiWorkflowPanel'),null);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('loop playback stops on source changes and restarts when the source ends',async()=>{
 const f=await videoFixture();try{const v=f.w.document.createElement('video');f.root.append(v);v.src='http://127.0.0.1:8765/api/media/abcdef/original';
 await f.root.naiVideoWorkflow.playLoop(v,{start:1,end:2});v.currentTime=2.2;Object.defineProperty(v,'ended',{value:true,configurable:true});v._playing=false;v.dispatchEvent(new f.w.Event('ended'));assert.equal(v.currentTime,1);assert.equal(v._playing,true);
 v.src='http://127.0.0.1:8765/api/media/bbb/original';v.currentTime=5;v.dispatchEvent(new f.w.Event('timeupdate'));assert.equal(v.currentTime,5);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('selected video frame opens matching with video identity and a retained timestamp',async()=>{
 const f=await videoFixture();try{await f.root.naiSelectMedia('abcdef');await delay(20);let query;
 f.root.naiFindMatchingSets=async options=>{query=options.queries[0];const e=f.w.document.createElement('div');e.className='naiMatchWrap';f.root.append(e)};
 await f.root.naiVideoWorkflow.editor(f.root.querySelector('.stage video'));const panel=f.root.querySelector('.naiWorkflowPanel');panel.querySelector('video').currentTime=4.5;click(panel,'Use frame to find sets');await waitFor(()=>query,f.errors);
 assert.equal(query.video_frame_id,'abcdef');assert.equal(query.video_match_frame.seconds,4.5);assert.ok(query.url.startsWith('blob:'));await delay(20);const count=f.revoked.length;f.root.querySelector('.naiMatchWrap').remove();await delay(10);assert.ok(f.revoked.length>count);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('checkpoint controls show missing media and keep Restore disabled',async()=>{
 const f=await fixture({configure:w=>{const normal=w.GM_xmlhttpRequest;w.GM_xmlhttpRequest=o=>{const route=new URL(o.url).pathname;let value;
 if(route==='/api/checkpoints')value={checkpoints:[{id:'cp',at:'Today',label:'Saved'}]};else if(route==='/api/checkpoints/preview')value={token:'token',current:{media:2,sets:1},restore:{media:3,sets:2},missing_media:['missing.jpg']};else return normal(o);
 queueMicrotask(()=>o.onload({status:200,responseText:JSON.stringify(value)}));return {abort(){}};}}});
 try{click(f.root,'Project tools');await waitFor(()=>[...f.root.querySelectorAll('button')].some(b=>b.textContent==='Preview restore'),f.errors);click(f.root,'Preview restore');await delay(20);
 const panel=f.root.querySelector('.naiWorkflowPanel');assert.ok(panel.textContent.includes('missing.jpg'));assert.ok([...panel.querySelectorAll('button')].find(b=>b.textContent==='Restore checkpoint').disabled);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});


test('Missing file finder is reachable from Project tools and Escape closes only the finder',async()=>{
 const f=await fixture({configure:w=>{const normal=w.GM_xmlhttpRequest;w.GM_xmlhttpRequest=o=>{const route=new URL(o.url).pathname;let value;
 if(route==='/api/checkpoints')value={checkpoints:[]};else if(route==='/api/missing-files/status')value={id:'scan',running:false,phase:'Scan complete',checked:0,total:0,missing:0,recoverable:0,total_issues:0,issues:[]};else return normal(o);
 queueMicrotask(()=>o.onload({status:200,responseText:JSON.stringify(value)}));return {abort(){}};}}});
 try{click(f.root,'Project tools');await delay(20);click(f.root,'Missing file finder');await waitFor(()=>f.root.querySelector('.naiMissingPanel'),f.errors);
 f.w.document.dispatchEvent(new f.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await waitFor(()=>!f.root.querySelector('.naiMissingPanel'),f.errors);assert.ok(f.root.querySelector('.naiWorkflowPanel'));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('manual search works independently of automatic matching and assigns a chosen Set',async()=>{
 const calls=[];let chosen;
 const f=await fixture({media:[{...image}],configure:w=>{const normal=w.GM_xmlhttpRequest;w.GM_xmlhttpRequest=o=>{if(o.url.endsWith('/api/sets/manual-search')){const b=JSON.parse(o.data);calls.push(b);queueMicrotask(()=>o.onload({status:200,responseText:JSON.stringify({rows:[{id:'held',name:'White Dress',in_purgatory:true,placement:'Set Purgatory',sets:[],count:1,cover:'photo'}],total:1,categories:[{id:'beach',name:'Beach'}]})}));return {abort(){}};}return normal(o)};}});
 try{await f.root.naiManualSearch({query:image,onChoose:async(id,q)=>chosen={id,q}});const panel=f.root.querySelector('.naiManualSearchWrap');assert.ok(panel.textContent.includes('White Dress'));const cat=panel.querySelector('[aria-label="Search category"]');cat.value='beach';cat.dispatchEvent(new f.w.Event('change'));await waitFor(()=>calls.length===2,f.errors);assert.equal(calls.at(-1).category,'beach');assert.equal(calls.at(-1).character_id,'character');click(panel,'Use this Set');await waitFor(()=>chosen,f.errors);assert.equal(chosen.id,'held');assert.equal(chosen.q.id,'photo');await waitFor(()=>!f.root.querySelector('.naiManualSearchWrap'),f.errors);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('Set Purgatory is separate from normal sets and restores the same set',async()=>{
 const f=await fixture({media:[{...image}]});try{
  const held={id:'abc123',character_id:'character',name:'Held Set',kind:'set',media_ids:['photo'],cover_media_id:'photo',in_purgatory:true,categories:[]};const normal={...held,id:'def123',name:'Good Set',in_purgatory:false};f.library.sets.push(held,normal);f.root.naiSetsApplyLibrary216(f.library);
  f.root.getElementById('naiSetsCat').click();await waitFor(()=>f.root.querySelector('.naiSetTile[data-set-id="def123"]'),f.errors);assert.equal(f.root.querySelector('.naiSetTile[data-set-id="abc123"]'),null);
  f.root.getElementById('naiSetPurgatoryCat').click();await waitFor(()=>f.root.querySelector('.naiSetTile[data-set-id="abc123"]'),f.errors);assert.equal(f.root.querySelector('.naiSetTile[data-set-id="def123"]'),null);
  f.root.getElementById('naiSelectSets').click();await delay(30);const tile=f.root.querySelector('.naiSetTile[data-set-id="abc123"]');tile.click();await delay(30);f.root.getElementById('naiBulkSetPurgatory').click();await waitFor(()=>held.in_purgatory===false,f.errors);assert.deepEqual(held.media_ids,['photo']);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});
