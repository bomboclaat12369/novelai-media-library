// Real companion integration for persistent Rapid Review and Set organization.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:config.version,NAI_FIXTURE_MULTI_SET:'',NAI_FIXTURE_EXTRA_IMAGES:'0',NAI_FIXTURE_SCROLL_SETS:'',NAI_FIXTURE_PENDING:'80'}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{const text=b.toString();if(text.includes('ready'))resolve(JSON.parse(text));});server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});
 context.setDefaultTimeout(10000);
 await context.route(/^https?:\/\/(?!127\.0\.0\.1(?::|\/)|novelai\.net(?:\/|$))/,r=>r.abort());
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 const sourceBytes=await (await context.request.get('http://127.0.0.1:8765/api/media/'+fixture.images[3]+'/original')).body();
 const blue=await api('sets',{character_id:fixture.character,name:'Blue Dress',media_ids:[fixture.images[1],fixture.images[2]],preserve_placement:true});
 for(const standalone of [true,false]){
  let promptAnswer='Outfits';const page=await context.newPage(),errors=[],alerts=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept(d.type()==='prompt' ? promptAnswer : undefined));
  if(!standalone){
   await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
   await page.exposeFunction('companionRequest',async o=>{if(new URL(o.url).hostname!=='127.0.0.1')return {status:503,text:''};const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
   await page.addInitScript(({payload,version})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
   },{payload,version:config.version});
  }
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');await page.getByText('Local library connected',{exact:true}).waitFor();
  await page.locator('#naiResumeRapid').waitFor();await page.locator('#naiResumeRapid').click();await page.locator('#naiRapidBulkReview').waitFor();
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('#naiQueueStrip270 img')].slice(0,56).every(img=>img.naturalWidth>0));
  if(standalone)await page.screenshot({path:'/tmp/rapid-review82.png'});
  let queue=await api('rapid-review?character_id='+fixture.character);
  assert.equal(await page.locator('#naiQueueStrip270 input:checked').count(),queue.items.length,'queue initially selected');
  const visible=await page.locator('#naiQueueStrip270').evaluate(g=>{const r=g.getBoundingClientRect();return [...g.children].filter(c=>{const b=c.getBoundingClientRect();return b.top>=r.top&&b.bottom<=r.bottom;}).length;});assert(visible>14,'large grid shows more than 14');
  await page.locator('#naiRapidUnselectAll').click();
  const first=queue.items[0].id,second=queue.items[1].id;
  await page.locator('.naiQueueThumb270[data-id="'+first+'"] input').check();await page.locator('.naiQueueThumb270[data-id="'+second+'"] input').check();
  await page.locator('#naiRapidNewSet').click();await page.locator('#naiSetQueueNew270').fill('New '+standalone);await page.locator('#naiQueueSetColors').fill('Blue, White');
  assert.equal(await page.locator('#naiSetQueueGallery270 input:checked').count(),2);
  await page.locator('#naiSetQueueNew270').press('Enter');await page.locator('#naiSetQueueNew270').waitFor({state:'detached'});
  let lib=await api('library'),created=lib.sets.find(s=>s.name==='New '+standalone);assert(created);assert.deepEqual(created.media_ids,[first,second]);assert.deepEqual(created.colors,['Blue','White']);
  queue=await api('rapid-review?character_id='+fixture.character);const reviewId=queue.items[0].id;
  await page.locator('#naiRapidUnselectAll').click();await page.locator('.naiQueueThumb270[data-id="'+reviewId+'"] input').check();await page.locator('#naiRapidBulkReview').click();
  await page.locator('.naiQueueThumb270[data-id="'+reviewId+'"]').waitFor({state:'detached'});lib=await api('library');assert(lib.media.find(m=>m.id===reviewId).in_review);
  await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop=500);
  await page.locator('#naiReviewClose270').click();await page.locator('#naiReviewClose270').waitFor({state:'detached'});
  const remaining=(await api('rapid-review?character_id='+fixture.character)).items.length;
  await page.reload();await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiResumeRapid').click();await page.locator('#naiRapidBulkReview').waitFor();
  assert.equal(await page.locator('#naiQueueStrip270 .naiQueueThumb270').count(),remaining);assert((await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop))>200,'scroll survives reload');
  await page.locator('#naiRapidExpand').click();assert(await page.locator('.naiReviewVisual270').isHidden());await page.locator('#naiRapidExpand').click();
  await page.locator('#naiReviewClose270').click();await page.locator('#naiReviewClose270').waitFor({state:'detached'});
  // Actual user import path appends to the existing durable queue.
  await page.locator('#addMediaBtn').click();await page.locator('#fileInput').setInputFiles([{name:'Append '+standalone+'.jpg',mimeType:'image/jpeg',buffer:Buffer.concat([sourceBytes,Buffer.from('append-'+standalone)])}]);
  await page.locator('#importReview').click();await page.locator('#naiRapidBulkReview').waitFor();
  assert.equal((await api('rapid-review?character_id='+fixture.character)).items.length,remaining+1);
  await page.locator('#naiReviewClose270').click();await page.locator('#naiReviewClose270').waitFor({state:'detached'});
  // Main Set view: cover targets Viewer 2; details and arrangement remain reachable.
  await page.evaluate(id=>{const r=document.getElementById('nai-media-host').shadowRoot;r.naiSetActiveSlot(0);return r.naiSelectMedia(id);},fixture.images[3]);
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiOpenGroup(id),blue.id);await page.locator('#naiArrangeSet').waitFor();
  const state=await page.evaluate(()=>JSON.parse(localStorage.getItem('nai-media-v1-ui')));
  if(state.splitView){assert.equal(state.slotMediaIds[1],blue.cover_media_id);assert.equal(state.slotMediaIds[0],fixture.images[3]);}
  assert.equal(await page.locator('#grid .tile[draggable="true"]').count(),0);
  await page.locator('#naiSetRenameBtn').click();await page.locator('#naiSetAliases').fill('Ocean outfit, Pool look');await page.locator('#naiSetNotes').fill('White straps');await page.locator('#naiSetColors').fill('Blue, White');await page.locator('#modalRoot [data-save]').click();await page.locator('#naiSetAliases').waitFor({state:'detached'});
  await page.locator('#naiArrangeSet').click();assert.equal(await page.locator('#grid .tile[draggable="true"]').count(),2);
  const original=(await api('library')).sets.find(s=>s.id===blue.id).media_ids;
  await page.locator('#grid .tile[data-id="'+original[1]+'"] button[title="Move earlier"]').click();
  await page.waitForFunction(()=>!document.getElementById('nai-media-host').shadowRoot.getElementById('naiArrangeSet').disabled);
  assert.deepEqual((await api('library')).sets.find(s=>s.id===blue.id).media_ids,[original[1],original[0]]);
  await page.locator('#naiArrangeSet').click();assert.equal(await page.locator('#grid .tile[draggable="true"]').count(),0);
  await page.locator('#naiFindMissingMembers').click();await page.getByText('Find missing Set images',{exact:true}).waitFor();assert.match(await page.locator('.naiScanWrap').innerText(),/all searchable images in this Set/);await page.locator('.naiScanWrap button').filter({hasText:'Close'}).click();
  await page.locator('#search').fill('Ocean outfit');await page.locator('.naiSetTile').waitFor();assert.equal(await page.locator('.naiSetTile').count(),1);
  // Category ordering is saved within Edit Media.
  const category=await api('categories',{character_id:fixture.character,name:'Bikini '+standalone,media_type:'image'});
  await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiReloadLibrary());
  await page.locator('#editBtn').click();await page.locator('#naiCategoryOrder').waitFor();
  await page.locator('[data-order-category="'+category.id+'"] button[title="Move category up"]').click();
  await page.waitForFunction(id=>{const cats=document.getElementById('nai-media-host').shadowRoot.naiGetLibrary().characters[0].categories;return cats.findIndex(c=>c.id===id)===cats.length-2;},category.id);
  await page.locator('#modalRoot [data-close]').first().click();
  if(!standalone){await page.locator('#naiResumeRapid').click();await page.locator('#naiRapidDiscard').click();await page.locator('#naiReviewClose270').waitFor({state:'detached'});assert.equal((await api('rapid-review?character_id='+fixture.character)).items.length,0);assert((await api('library')).media.some(m=>m.id===first));}
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: standalone and NovelAI — persistent grid queue, bulk Set creation/Review, append imports, close/reload/discard, details, order toggle, Viewer 2 cover, category order, reverse-search entry.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
