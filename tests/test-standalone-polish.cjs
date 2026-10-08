// Focused checks for the standalone footer, density, adaptive previews, and video selection.
const assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python',['tests/serve_standalone_fixture.py'],{env:{...process.env,NAI_UI_VERSION:'2.8.65',NAI_FIXTURE_EXTRA_IMAGES:'100'}});
 server.stderr.on('data',d=>process.stderr.write(d));let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',d=>{out+=d;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]));});server.on('exit',code=>reject(Error('Fixture exited '+code)));});
 browser=await chromium.launch({executablePath:'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const page=await browser.newPage({viewport:{width:2560,height:1440}}),errors=[],thumbRequests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/thumb?'))thumbRequests.push(r.url());});
 await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();
 const rootEval=fn=>page.evaluate(fn);
 const footer=()=>rootEval(()=>{const r=document.getElementById('nai-media-host').shadowRoot;const box=id=>{const b=r.getElementById(id).getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height}};return {footer:box('naiCompactFooter'),stage:box('stage1'),meta:box('selectedName'),quality:box('qualityInfo'),connect:box('naiConnectMedia')};});
 const tile=id=>page.locator(`#grid .tile[data-id="${id}"]`);
 await tile(fixture.images[0]).click();await page.locator('#stage1 img').waitFor();
 let before=await footer();assert.equal(before.footer.h,63);assert(before.meta.y<before.footer.y+28);assert(Math.abs(before.connect.y-before.meta.y)<12);
 // Adaptive preview is based on the square tile's short edge, rather than its portrait height.
 await page.locator('#splitBtn').click();await page.locator('#naiThumbColumns').selectOption('4');
 await page.waitForFunction(id=>{const i=document.getElementById('nai-media-host').shadowRoot.querySelector(`#grid .tile[data-id="${id}"] img`);return i?.naturalWidth>=512;},fixture.images[0],{timeout:10000});
 assert(thumbRequests.some(u=>u.includes('size=512')));
 const originalSrc=await tile(fixture.images[0]).locator('img').getAttribute('src');
 await page.locator('#naiThumbColumns').selectOption('8');await page.locator('#naiThumbColumns').selectOption('4');
 assert.equal(await tile(fixture.images[0]).locator('img').getAttribute('src'),originalSrc,'reuse the sharper cached preview');
 for(const n of [4,5,6,7,8]){
   await page.locator('#naiThumbColumns').selectOption(String(n));
   assert.equal(await page.locator('#grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),n);
   await page.locator('#grid').evaluate(el=>el.scrollTop=el.scrollHeight);
   await page.waitForFunction(()=>{const r=document.getElementById('nai-media-host').shadowRoot,lib=r.naiGetLibrary();const last=lib.media.filter(m=>m.media_type==='image').at(-1);return !!r.querySelector(`#grid .tile[data-id="${last.id}"]`);});
   const ids=await page.locator('#grid .tile').evaluateAll(tiles=>tiles.map(t=>t.dataset.id));assert.equal(ids.length,new Set(ids).size);assert(ids.length<106,'grid stays virtualized');
 }
 await page.locator('#grid').evaluate(el=>el.scrollTop=0);await page.locator('#naiThumbColumns').selectOption('5');
 await page.locator('#splitBtn').click();await page.locator('#naiStandaloneSlot2').click();await page.locator('#videosModeBtn').click();await tile(fixture.video).click();
 await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#stage2 video')?.readyState>=2);
 const video=page.locator('#stage2 video');await video.evaluate(v=>v.pause());
 await page.locator('#stage1 img').click();const imageBox=await footer();
 await video.click({position:{x:180,y:180}});assert(await video.evaluate(v=>v.paused),'selecting inactive video must not play it');
 const videoBox=await footer();assert.equal(imageBox.stage.h,videoBox.stage.h);assert.equal(imageBox.footer.h,videoBox.footer.h);assert.equal(imageBox.meta.y,videoBox.meta.y);
 await video.click({position:{x:180,y:180}});assert(!(await video.evaluate(v=>v.paused)),'active click plays');
 await page.locator('#stage1 img').click();await video.click({position:{x:180,y:180}});assert(!(await video.evaluate(v=>v.paused)),'selecting playing video must not pause');
 await video.click({position:{x:180,y:180}});assert(await video.evaluate(v=>v.paused),'active click pauses');
 await page.screenshot({path:'/tmp/nai65-dual.png'});
 await page.locator('#naiStandaloneSlot1').click();await page.locator('#splitBtn').click();
 await page.setViewportSize({width:1800,height:1050});
 await page.screenshot({path:'/tmp/nai65-single.png'});
 let b=await footer();assert.equal(b.footer.h,63);assert(b.connect.x+b.connect.w<=600,'Connect remains accessible in single mode');
 await page.locator('#naiThumbColumns').selectOption('6');await page.reload();await page.getByText('Local library connected',{exact:true}).waitFor();assert.equal(await page.locator('#naiThumbColumns').inputValue(),'6');assert.equal(await page.locator('#nai-media-host').getAttribute('data-dual'),'true');
 assert.deepEqual(errors,[]);console.log('PASS: sharp previews/reuse, 4–8 virtual columns, persisted density, stable 63px footer, inactive video selection preserves playback.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
