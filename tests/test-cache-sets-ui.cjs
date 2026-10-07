// Focused browser check for session caching, assignment search and mixed Rapid Review.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG || 'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{const browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM || '/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});try{
const page=await browser.newPage({viewport:{width:1700,height:1000}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
await page.route('http://127.0.0.1:8765/**',r=>r.fulfill({status:404,body:''}));
await page.goto('https://novelai.net/stories');
await page.evaluate(()=>{
 const media=Array.from({length:220},(_,i)=>({id:'img'+i,character_id:'c',media_type:'image',original_name:`Image ${i}.png`,sha256:'source'+i,thumb_rel:'thumb'+i,categories:[],in_all:true,in_review:false,width:64,height:96,file_bytes:1000,created_at:new Date(1700000000000+i*1000).toISOString()}));
 window.lib={characters:[{id:'c',name:'Fixture',categories:[]}],media,sets:[{id:'beach',character_id:'c',kind:'set',name:'Beach',media_ids:[]},{id:'dress',character_id:'c',kind:'set',name:'Dress',media_ids:[]},{id:'conn',character_id:'c',kind:'connection',name:'Pink bikini',media_ids:[]}]};
 window.requests=[];window.alerts=[];window.alert=m=>alerts.push(m);window.confirm=()=>true;
 window.GM_xmlhttpRequest=o=>{const route=new URL(o.url).pathname,method=o.method||'GET';requests.push({route,method,url:o.url,background:!!o.naiBackground});let canceled=false;
 setTimeout(()=>{if(canceled)return;try{let value={};
 if(route==='/api/health')value={ok:true,version:9,mixed_collections:true,video_set_only:true,featured_flags:true};
 else if(route==='/api/library')value=lib;
 else if(route.endsWith('/quality'))value={width:64,height:96,file_bytes:1000};
 else if(route==='/api/import/file'){const f=o.data.get('file');value={item:{id:'saved'+lib.media.length,character_id:'c',media_type:f.type.startsWith('video/')?'video':'image',original_name:f.name,sha256:f.name,thumb_rel:'thumb',categories:[],in_all:true,in_videos:true},duplicate:false};lib.media.push(value.item);}
 else if(route.startsWith('/api/media/') && method==='POST'){
 const m=lib.media.find(m=>m.id===route.split('/')[3]);if(!m)throw Error('Unknown media');
 if(route.endsWith('/replace')){m.original_name=o.data.get('file').name;m.sha256='replacement';m.thumb_rel='newthumb';}
 else Object.assign(m,JSON.parse(o.data));value=m;
 }else if(route==='/api/sets' && method==='POST'){value={id:'newset'+lib.sets.length,...JSON.parse(o.data)};lib.sets.push(value);}
 else if(route.startsWith('/api/sets/') && method==='POST'){value=lib.sets.find(s=>s.id===route.split('/')[3]);const body=JSON.parse(o.data);if(body.add_media_ids)body.media_ids=[...new Set([...value.media_ids,...body.add_media_ids])];Object.assign(value,body);if(!body.preserve_placement)for(const id of value.media_ids){const m=lib.media.find(m=>m.id===id);if(!m.categories.length)m[m.media_type==='video'?'in_videos':'in_all']=false;}}
 else if(o.responseType==='blob'){const replacement=o.url.includes('replacement');o.onload({status:200,response:new Blob([`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="96"><rect width="64" height="96" fill="${replacement?'blue':'red'}"/></svg>`],{type:'image/svg+xml'})});return;}
 o.onload({status:200,responseText:JSON.stringify(value)});
 }catch(e){alerts.push(e.message);o.onerror?.(e);}},5);return {abort(){canceled=true;o.onabort?.({})}};};
});
await page.evaluate(payload);await page.getByText('Local library connected',{exact:true}).waitFor();
const rootEval=fn=>page.evaluate(fn);
await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#grid img')?.src.startsWith('blob:'));
await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia('img0'));
await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia('img1'));
await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia('img0'));
assert.equal(await page.evaluate(()=>requests.filter(r=>r.route==='/api/media/img0/original').length),1,'recent viewer original reused');
// Loading >90 distinct thumbnails must retain the first one without refetching.
await page.evaluate(async()=>{const r=document.getElementById('nai-media-host').shadowRoot;for(let i=0;i<130;i++){const img=document.createElement('img');r.appendChild(img);await r.naiLoadThumbnail('img'+i,img);img.remove();}});
const before=await page.evaluate(()=>requests.filter(r=>r.route==='/api/media/img0/thumb').length);
await page.evaluate(async()=>{const r=document.getElementById('nai-media-host').shadowRoot,img=document.createElement('img');r.appendChild(img);await r.naiLoadThumbnail('img0',img);img.remove();});
assert.equal(await page.evaluate(()=>requests.filter(r=>r.route==='/api/media/img0/thumb').length),before);
await page.locator('#editBtn').click();
const oldSrc=await page.locator('#stage1 img').getAttribute('src');
await page.evaluate(()=>{const b=document.getElementById('nai-media-host').shadowRoot.getElementById('replaceSourceBtn'),data=new DataTransfer();data.items.add(new File(['replacement'],'new.png',{type:'image/png'}));b.dispatchEvent(new DragEvent('drop',{dataTransfer:data,bubbles:true,composed:true,cancelable:true}));});
await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.getElementById('selectedName').textContent==='new.png');
assert.notEqual(await page.locator('#stage1 img').getAttribute('src'),oldSrc);
assert.ok(await page.evaluate(()=>requests.some(r=>r.route==='/api/media/img0/original'&&r.url.includes('source=replacement'))));
// Assignment search filters both collection types and handles no results.
await page.locator('#naiConnectMedia').click();await page.locator('#naiAssignSearch').fill('pink');
assert.deepEqual(await page.locator('#naiAssignExisting option').allTextContents(),['Pink bikini']);
await page.locator('#naiAssignKind').selectOption('set');await page.locator('#naiAssignSearch').fill('dre');
assert.deepEqual(await page.locator('#naiAssignExisting option').allTextContents(),['Dress']);
await page.locator('#naiAssignSearch').fill('no match');assert.ok(await page.locator('#naiAssignAdd').isDisabled());
await page.locator('#modalRoot [data-close]').click();
// Review contains both file types; opening/searching/creating a set imports nothing.
await page.locator('#addMediaBtn').click();

await page.locator('#fileInput').setInputFiles([{name:'Video 2.mp4',mimeType:'video/mp4',buffer:Buffer.from('video')},{name:'Image 1.png',mimeType:'image/png',buffer:Buffer.from('image')}]);
await page.locator('#importReview').click();await page.locator('#naiQueueSets270').click();
await page.locator('.naiSetQueueCard270').first().waitFor();
assert.equal(await page.locator('.naiSetQueueCard270').count(),2);
await page.locator('#naiSetQueueSearch270').fill('dre');assert.deepEqual(await page.locator('#naiSetQueueExisting270 option').allTextContents(),['Choose a set…','Dress']);
await page.locator('#naiSetQueueNew270').fill('New shoot');await page.locator('#naiSetQueueCreate270').click();
await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#naiSetQueueExisting270')?.value.startsWith('newset'));
assert.equal(await page.evaluate(()=>requests.filter(r=>r.route==='/api/import/file').length),0);
await page.locator('#naiSetQueueSave270').click();await page.locator('#naiSetQueueSave270').waitFor({state:'detached'});
assert.equal(await page.evaluate(()=>lib.media.length),222);
const saved=await page.evaluate(()=>lib.media.filter(m=>m.id.startsWith('saved')));
assert.equal(saved.find(m=>m.media_type==='video').in_videos,false);assert.equal(saved.find(m=>m.media_type==='image').in_all,false);
await page.locator('#videosModeBtn').click();assert.equal(await page.locator('#grid .tile').count(),0);
await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiOpenGroup(lib.sets.at(-1).id));
await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelectorAll('#grid .tile').length===2);
assert.deepEqual(await page.evaluate(()=>alerts),[]);assert.deepEqual(errors,[]);
console.log('PASS: thumbnail retention, original reuse/replacement invalidation, replacement drop, both search screens, mixed explicit-save review and set-only video filtering.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
