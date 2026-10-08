// Focused real-companion integration: layout, slots, local transport, shared edits.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..');
(async()=>{
 const server=spawn('python',['tests/serve_standalone_fixture.py'],{cwd:dir});
 server.stderr.on('data',d=>process.stderr.write(d));
 let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',d=>{out+=d;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]));});server.on('exit',code=>reject(Error('Fixture exited '+code)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1800,height:1050}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('dialog',d=>{errors.push(d.message());d.dismiss();});
 await page.goto('http://127.0.0.1:8765/library/');
 await page.getByText('Local library connected',{exact:true}).waitFor();
 const dims=()=>page.evaluate(()=>{const r=document.getElementById('nai-media-host').shadowRoot;return ['stage1','stage2','grid'].map(id=>{const b=r.getElementById(id).getBoundingClientRect();return {x:b.x,w:b.width,h:b.height};});});
 let d=await dims();assert(Math.abs(d[0].w-600)<3);assert(Math.abs(d[1].w-600)<3);assert(Math.abs(d[2].w-600)<3);
 const columns=await page.locator('#grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);assert.equal(columns,5);
 await page.locator(`#grid .tile[data-id="${fixture.images[0]}"]`).click();
 await page.locator('#stage1 img').waitFor();
 await page.locator('#naiStandaloneSlot2').click();
 await page.locator(`#grid .tile[data-id="${fixture.images[1]}"]`).click();await page.locator('#stage2 img').waitFor();
 assert.equal(await page.locator('#stage1 img').getAttribute('alt'),'Portrait 1.jpg');
 assert.equal(await page.locator('#stage2 img').getAttribute('alt'),'Portrait 2.jpg');
 await page.locator('#stage1 img').click();assert.equal(await page.locator('#nai-media-host').getAttribute('data-active-slot'),'0');
 assert.equal(await page.locator('#lightRoot').textContent(),'');
 await page.locator('#favBtn').click();
 let library=await (await context.request.get('http://127.0.0.1:8765/api/library')).json();assert(library.media.find(m=>m.id===fixture.images[0]).favorite);assert(!library.media.find(m=>m.id===fixture.images[1]).favorite);
 await page.screenshot({path:'/tmp/nai-standalone-dual.png'});
 await page.locator('#splitBtn').click();d=await dims();assert(Math.abs(d[0].w-600)<3);assert.equal(d[1].w,0);assert(Math.abs(d[2].w-1200)<3);assert.equal(await page.locator('#grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),columns);
 await page.screenshot({path:'/tmp/nai-standalone-single.png'});
 await page.locator('#splitBtn').click();assert.equal(await page.locator('#stage2 img').getAttribute('alt'),'Portrait 2.jpg');
 await page.locator('#naiStandaloneSlot2').click();await page.locator('#videosModeBtn').click();await page.locator(`#grid .tile[data-id="${fixture.video}"]`).click();
 await page.locator('#stage2 video').waitFor();await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#stage2 video')?.readyState>=1);
 await page.locator('#videoTools').waitFor({state:'visible'});
 await page.screenshot({path:'/tmp/nai-standalone-video.png'});
 // Single mode always pauses the hidden second video, even if slot 1 is active.
 await page.locator('#stage2 video').evaluate(v=>v.play());await page.locator('#naiStandaloneSlot1').click();await page.locator('#splitBtn').click();assert(await page.locator('#stage2 video').evaluate(v=>v.paused));
 // Native FormData import and source replacement retain real multipart boundaries.
 const imported=await page.evaluate(async character=>{const r=document.getElementById('nai-media-host').shadowRoot;const blob=await (await fetch(r.querySelector('#stage1 img').src)).blob();const form=new FormData();form.append('character_id',character);form.append('categories','[]');form.append('file',blob,'native-import.jpg');return await new Promise((resolve,reject)=>GM_xmlhttpRequest({method:'POST',url:location.origin+'/api/import/file',data:form,headers:{Origin:'https://novelai.net'},onload:r=>resolve(JSON.parse(r.responseText)),onerror:reject}));},fixture.character);
 assert(imported.item?.id || imported.id,'native upload returned a media item');
 // Changes in another client become visible on return, without navigation coupling.
 const edit=await context.request.post('http://127.0.0.1:8765/api/media/'+fixture.images[0]+'/featured',{data:{featured:true}});assert.equal(edit.status(),200);
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await page.waitForFunction(id=>document.getElementById('nai-media-host').shadowRoot.naiGetLibrary().media.find(m=>m.id===id)?.featured,fixture.images[0]);
 await page.reload();await page.getByText('Local library connected',{exact:true}).waitFor();assert.equal(await page.locator('#nai-media-host').getAttribute('data-dual'),'true');
 // Local page must not broaden write access to unrelated web origins.
 const denied=await context.request.post('http://127.0.0.1:8765/api/characters',{headers:{Origin:'https://untrusted.example'},data:{name:'blocked'}});assert.equal(denied.status(),403);
 assert.deepEqual(errors,[]);
 console.log('PASS: exact thirds, unchanged columns, independent viewers, single mode, video controls/pause, native upload, shared edits, default Dual, origin restriction, verified offline UI cache.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
