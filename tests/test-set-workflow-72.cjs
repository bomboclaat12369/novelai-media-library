// Focused release check: only the changed Set flows and standalone fullscreen.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:config.version}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{const text=b.toString();if(text.includes('ready'))resolve(JSON.parse(text));});server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 await api('media/'+fixture.images[5]+'/review',{in_review:true});
 const blue=await api('sets',{character_id:fixture.character,name:'Blue Dress',media_ids:[fixture.images[1]],preserve_placement:true});
 const orange=await api('sets',{character_id:fixture.character,name:'Orange Bikini',media_ids:[fixture.images[2]],preserve_placement:true});
 for(const standalone of [true,false]){
  const page=await context.newPage(),errors=[],alerts=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{alerts.push(d.message());d.accept();});
  if(!standalone){
   await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
   await page.exposeFunction('companionRequest',async o=>{const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
   await page.addInitScript(({payload,version})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
   },{payload,version:config.version});
  }
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');await page.getByText('Local library connected',{exact:true}).waitFor();
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia(id),fixture.images[0]);
  if(standalone){
   await page.locator('#stage1 .naiStandaloneFullscreen').click();await page.locator('#lightRoot .lightbox img').waitFor();await page.locator('#lightRoot .lightClose').click();
   await page.evaluate(async id=>{const r=document.getElementById('nai-media-host').shadowRoot;await r.naiSetActiveSlot(1);await r.naiSelectMedia(id);await r.naiSetActiveSlot(0);},fixture.images[1]);
   await page.locator('#stage2 .naiStandaloneFullscreen').click();await page.locator('#lightRoot .lightbox img').waitFor();assert.equal(await page.locator('#lightRoot img').getAttribute('alt'),'Portrait 2.jpg');await page.keyboard.press('Escape');
  }else assert.equal(await page.locator('.naiStandaloneFullscreen').count(),0);
  await page.locator('#naiSetsCat').click();await page.locator('#search').fill('Blue');await page.locator('.naiSetTile').waitFor();
  assert.equal(await page.locator('.naiSetTile').count(),1);
  await page.locator('#naiReviewCat270').click();await page.locator('#naiReviewClose270').click();await page.locator('#naiSetsCat').click();assert.equal(await page.locator('#search').inputValue(),'Blue');assert.equal(await page.locator('.naiSetTile').count(),1);
  await page.locator('.naiSetTile').click();await page.locator('#naiSetsCat').click();assert.equal(await page.locator('#search').inputValue(),'Blue');
  await page.locator('#search').fill('');
  await api('sets/'+blue.id,{name:'Blue Dress edited'});
  await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiReloadLibrary());
  await page.locator('#naiSetsCat').click();await page.locator('#naiSetSort').selectOption('updated');
  assert.equal(await page.locator('.naiSetTile').first().getAttribute('data-set-id'),blue.id);
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiAssignGroups([id]),fixture.images[3]);
  await page.locator('#naiAssignSearch').fill('Dress Blue');assert.deepEqual(await page.locator('#naiAssignExisting option').allTextContents(),['Choose a set…','Blue Dress edited']);assert.equal(await page.locator('#naiAssignExisting').getAttribute('size'),'6');
  await page.locator('#naiAssignExisting').selectOption(blue.id);
  await page.waitForFunction(()=>{const r=document.getElementById('nai-media-host').shadowRoot;return r.querySelector('.naiSetPreviewGrid img')?.naturalWidth>0;});
  await page.locator('#naiAssignSearch').fill('nonexistent');assert(await page.locator('#naiAssignAdd').isDisabled());assert.equal(await page.locator('.naiSetPreviewGrid img').count(),0);
  await page.locator('#modalRoot [data-close]').click();
  if(standalone){
   // Use real saved Purgatory images to check the assignment endpoint and main placement.
   const library=await api('library'),cat=library.characters[0].categories[0].id;
   await api('media/'+fixture.images[3]+'/categories',{categories:[]});await api('media/'+fixture.images[3]+'/purgatory',{in_purgatory:true});
   await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiAssignGroups([id]),fixture.images[3]);await page.locator('#naiAssignExisting').selectOption(orange.id);await page.locator('#naiAssignAdd').click();await page.locator('#naiAssignAdd').waitFor({state:'detached'});
   let m=(await api('library')).media.find(m=>m.id===fixture.images[3]);assert.equal(m.in_purgatory,false);assert.equal(m.in_all,false);
   await api('media/'+fixture.images[4]+'/purgatory',{in_purgatory:true});await api('sets',{character_id:fixture.character,name:'From Purgatory',media_ids:[fixture.images[4]],preserve_placement:true});
   m=(await api('library')).media.find(m=>m.id===fixture.images[4]);assert.equal(m.in_purgatory,false);assert.equal(m.in_all,true);assert(m.categories.includes(cat));
   // Opening assignment starts unchecked; select all / unselect all do not save files.
   await page.locator('#addMediaBtn').click();
   const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aH1cAAAAASUVORK5CYII=','base64');
   await page.locator('#fileInput').setInputFiles([{name:'First.png',mimeType:'image/png',buffer:png},{name:'Second.png',mimeType:'image/png',buffer:png}]);
   await page.locator('#importReview').click();await page.locator('#naiQueueSets270').click();await page.locator('.naiSetQueueCard270').first().waitFor();
   assert.equal(await page.locator('.naiSetQueueCard270 input:checked').count(),0);
   await page.locator('#naiSetQueueAll270').click();assert.equal(await page.locator('.naiSetQueueCard270 input:checked').count(),2);
   await page.locator('#naiSetQueueNone270').click();assert.equal(await page.locator('.naiSetQueueCard270 input:checked').count(),0);
   await page.locator('#naiSetQueueSearch270').fill('blue');await page.locator('#naiSetQueueExisting270').selectOption(blue.id);
   await page.waitForFunction(()=>{const r=document.getElementById('nai-media-host').shadowRoot;return r.querySelector('.naiSetQueueWrap270 .naiSetPreviewGrid img')?.naturalWidth>0;});
   await page.locator('.naiSetQueueWrap270').screenshot({path:'/tmp/nai72-rapid-sets.png'});
   await page.locator('#naiSetQueueCancel270').click();await page.locator('#naiReviewClose270').click();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(alerts,[]);await page.close();
 }
 console.log('PASS: standalone fullscreen; live Set results/previews in both interfaces; remembered search; updated sort; Purgatory assignment and category placement; unchecked Rapid Review selection and selection controls.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
