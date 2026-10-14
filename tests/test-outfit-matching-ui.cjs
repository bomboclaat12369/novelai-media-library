// Real model, real companion; only requested matching flows in both interfaces.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,'release-userscript.json'))),payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_FIXTURE_SCROLL_SETS:'1'}});let stderr='',browser;server.stderr.on('data',b=>stderr+=b);
 try{
 const fixture=await new Promise((resolve,reject)=>{server.stdout.once('data',b=>resolve(JSON.parse(b)));server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});context.setDefaultTimeout(20000);
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 for(const standalone of [true,false]){
  const page=await context.newPage(),errors=[],alerts=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{alerts.push(d.message());await d.accept();});
  if(!standalone){
   await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
   await page.exposeFunction('companionRequest',async o=>{const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
   await page.addInitScript(({payload,version})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
   },{payload,version:config.version});
  }
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');await page.getByText('Local library connected',{exact:true}).waitFor();
  // Realistic long Set list: rows must not shrink or run underneath the footer.
  await page.locator('#naiManageSetsBtn').click();await page.locator('#naiSetToolsList').waitFor();
  await page.locator('#naiSetToolsList').evaluate(el=>{el.scrollTop=el.scrollHeight;});
  const lastRow=page.locator('.naiSetToolsRow').last();await lastRow.scrollIntoViewIfNeeded();
  const rowBounds=await lastRow.boundingBox(),listBounds=await page.locator('#naiSetToolsList').boundingBox();
  assert(rowBounds.height>=50);assert(rowBounds.y+rowBounds.height<=listBounds.y+listBounds.height+1);
  await page.screenshot({path:'/tmp/set-manager-'+(standalone?'standalone':'novelai')+'.png'});
  await page.setViewportSize({width:600,height:800});
  assert(await page.locator('.naiSetToolsDialog').evaluate(el=>el.scrollWidth<=el.clientWidth));
  await page.setViewportSize({width:1700,height:1100});
  await page.locator('.naiSetToolsDialog .modalFoot [data-close]').click();
  const before=await api('library');
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiAssignGroups([id]),fixture.images[3]);
  assert.equal(await page.locator('.naiMatchWrap').count(),0);
  await page.locator('.naiFindMatchingSets').click();await page.locator('.naiMatchCard').first().waitFor().catch(async e=>{console.error('MATCH STATUS',await page.locator('.naiMatchStatus').allTextContents(),'ERRORS',errors);throw e;});
  assert.equal(await page.locator('.naiMatchCard').count(),5);
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiMatchCard img')].every(img=>img.complete&&img.naturalWidth>0));
  await page.screenshot({path:'/tmp/outfit-results-'+(standalone?'standalone':'novelai')+'.png'});
  const warm=await api('sets/find-matches',{character_id:fixture.character,media_id:fixture.images[3]});
  let warmed=warm;while(warmed.running){await new Promise(r=>setTimeout(r,100));warmed=await api('sets/match-status?id='+warm.id);}
  assert(!warmed.error);assert.equal(warmed.new_images,0);assert.equal(warmed.cached_images,6);console.log('Warm search',warmed.elapsed_seconds+'s',warmed.cached_images+' cached');
  await page.getByRole('button',{name:'Focus on outfit',exact:true}).click();const cropCanvas=page.locator('.naiMatchCrop canvas');await cropCanvas.waitFor();
  const box=await cropCanvas.boundingBox();await page.mouse.move(box.x+box.width*.2,box.y+box.height*.15);await page.mouse.down();await page.mouse.move(box.x+box.width*.8,box.y+box.height*.85,{steps:3});await page.mouse.up();
  await page.getByRole('button',{name:'Search this outfit',exact:true}).click();await page.locator('.naiMatchCard').first().waitFor();
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiMatchCard img')].every(img=>img.complete&&img.naturalWidth>0));
  assert(await page.getByRole('button',{name:'Use full image',exact:true}).isVisible());
  await page.getByRole('button',{name:/Show more matches/}).click();assert.equal(await page.locator('.naiMatchCard').count(),6);
  assert.deepEqual((await api('library')).sets,before.sets,'Search must not change membership');
  assert.equal((await api('library')).media.length,before.media.length);
  await page.locator('.naiMatchCard img').first().click();await page.locator('.naiMatchZoom').waitFor();await page.locator('.naiMatchZoom').click();
  const chosen=await page.locator('.naiMatchCard').first().getAttribute('data-set-id');
  await page.locator('.naiMatchCard').first().getByRole('button',{name:'Use this Set',exact:true}).click();
  assert.equal(await page.locator('#naiAssignExisting').inputValue(),chosen);
  await page.locator('#naiAssignAdd').click();await page.locator('#naiAssignAdd').waitFor({state:'detached'});
  assert((await api('library')).sets.find(s=>s.id===chosen).media_ids.includes(fixture.images[3]));
  // New Set editor lets a selected image search without saving the editor.
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiOpenGroupManager(null,[id]),fixture.images[2]);
  await page.locator('#naiEditorFindMatches').click();await page.locator('.naiMatchCard').first().waitFor().catch(async e=>{console.error('MATCH STATUS',await page.locator('.naiMatchStatus').allTextContents(),'ERRORS',errors);throw e;});
  const target=await page.locator('.naiMatchCard').first().getAttribute('data-set-id');
  await page.locator('.naiMatchCard').first().getByRole('button',{name:'Use Set in editor'}).click();
  const editor=await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiGroupManagerSelection());assert.equal(editor.setId,target);assert(editor.baseMediaIds.includes(fixture.images[2]));
  await page.locator('#modalRoot [data-close]').first().click();
  // Unsaved draft matching does not register an import or consume the queue.
  const count=(await api('library')).media.length;
  await page.locator('#addMediaBtn').click();
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAHgAAAC0CAIAAADQLH9KAAABoElEQVR4nO3QQRHAIADAMMDifKAKoVOx8liioNf57DP43rod8BdGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI68i6gCzZqgQDEAAAAASUVORK5CYII=','base64');
  await page.locator('#fileInput').setInputFiles([{name:'Query.png',mimeType:'image/png',buffer:png}]);await page.locator('#importReview').click();
  await page.locator('#naiReviewFindMatches').click();await page.locator('.naiMatchCard').first().waitFor().catch(async e=>{console.error('MATCH STATUS',await page.locator('.naiMatchStatus').allTextContents(),'ERRORS',errors);throw e;});
  assert.equal((await api('library')).media.length,count);
  assert.equal(await page.locator('.naiSetQueueCard270 input:checked').count(),1);
  await page.locator('.naiMatchCard').first().getByRole('button',{name:'Use this Set',exact:true}).click();
  assert(await page.locator('#naiSetQueueExisting270').inputValue());
  await page.locator('#naiSetQueueCancel270').click();await page.locator('#naiReviewClose270').click();
  assert.deepEqual(errors,[]);assert.deepEqual(alerts,[]);
  console.log('PASS outfit matching: '+(standalone?'standalone':'NovelAI')+' saved image, Set editor, unsaved Rapid Review, top five/show more, explicit assignment, no search mutations.');await page.close();
 }
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
