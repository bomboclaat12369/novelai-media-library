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
 await api('categories',{character_id:fixture.character,name:'Bikini',media_type:'image'});await api('categories',{character_id:fixture.character,name:'Lingerie',media_type:'image'});
 const blue=await api('sets',{character_id:fixture.character,name:'Blue Dress',media_ids:[fixture.images[1],fixture.images[4]],preserve_placement:true});
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

  await page.locator('#naiReviewCropBtnV254').waitFor();
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#reviewStage img')?.naturalWidth>0);
  assert.equal(await page.locator('#naiRapidAddAll').count(),0);assert.equal(await page.locator('#naiRapidExpand').count(),0);
  const first=(await api('rapid-review?character_id='+fixture.character)).items[0].id;
  await page.locator('#naiRapidMain').check();await page.locator('#naiReviewFavorite270').check();
  assert.equal(await page.locator('.naiQueueThumb270[data-id="'+first+'"] .naiRapidEdited').textContent(),'✎');
  for(const viewport of [{width:2048,height:1026},{width:1280,height:720}]){
    await page.setViewportSize(viewport);
    const layout=await page.evaluate(()=>{const r=document.getElementById('nai-media-host').shadowRoot,stage=r.querySelector('#reviewStage').getBoundingClientRect(),side=r.querySelector('.reviewSide'),panel=r.querySelector('.naiRapidGridPanel').getBoundingClientRect();return {stageHeight:stage.height,controlsRight:side.getBoundingClientRect().left>=stage.right,controlsScroll:side.scrollHeight>side.clientHeight+1,gridHeight:r.querySelector('#naiQueueStrip270').getBoundingClientRect().height,overflow:panel.bottom>innerHeight};});
    assert(layout.stageHeight>viewport.height*.75);assert(layout.controlsRight);assert(!layout.controlsScroll);assert(!layout.overflow);assert(layout.gridHeight>viewport.height*.35);
    for(const id of ['reviewAddCat','naiQueueSets270','naiReviewFindMatches','naiReviewCropBtnV254','carryCats','naiRapidNewSet','naiRapidBulkSet','naiRapidBulkReview','naiRapidSelectAll','naiRapidUnselectAll','naiRapidSize'])assert(await page.locator('#'+id).isVisible(),id+' remains visible');
  }
  await page.setViewportSize({width:2048,height:1026});
  await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop=220);
  const before=await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop);
  const selected=await page.locator('.naiQueueThumb270 input:checked').count();
  const image=await page.locator('#reviewStage img').elementHandle();
  await page.locator('#reviewStage img').click();await page.locator('.naiRapidFullscreen').waitFor();
  const full=await page.locator('#reviewStage').boundingBox();assert.equal(Math.round(full.width),2048);assert.equal(Math.round(full.height),1026);
  await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#reviewStage').getAttribute('data-nai-review-media-id'),first);
  await page.keyboard.press('Escape');await page.locator('.naiRapidFullscreen').waitFor({state:'detached'});
  assert(await image.evaluate(el=>el.isConnected));assert.equal(await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop),before);assert.equal(await page.locator('.naiQueueThumb270 input:checked').count(),selected);assert(await page.locator('#naiRapidMain').isChecked());
  await page.locator('#reviewStage img').click();await page.getByRole('button',{name:'Close fullscreen',exact:true}).click();assert.equal(await page.locator('.naiRapidFullscreen').count(),0);
  if(standalone)await page.screenshot({path:'/tmp/rapid-review84.png'});
  await page.locator('#naiRapidSize').fill('160');await page.locator('#naiRapidSize').dispatchEvent('input');
  await page.locator('#naiReviewClose270').click();await page.reload();await page.locator('#naiResumeRapid').click();await page.locator('#naiRapidBulkReview').waitFor();
  assert.equal(await page.locator('#naiRapidSize').inputValue(),'160');assert(await page.locator('#naiRapidMain').isChecked());
  await page.locator('#naiReviewNext270').click();await page.locator('.naiQueueThumb270[data-id="'+first+'"]').waitFor({state:'detached'});
  const saved=(await api('library')).media.find(m=>m.id===first);assert(saved.in_all);assert(saved.favorite);
  await page.locator('#naiReviewClose270').click();assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: Rapid Review layout at 2048×1026 and 1280×720, current/bulk tools, pencil badge, click fullscreen/Escape, queue selection/scroll persistence, All checkbox save, standalone and NovelAI.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
