// Real model, real companion; only requested matching flows in both interfaces.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,'release-userscript.json'))),payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_FIXTURE_OUTFIT_SCAN:'1'}});let stderr='',browser;server.stderr.on('data',b=>stderr+=b);
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
  // Reset only fixture memberships between interfaces.
  const previous=await api('library');
  for(const set of previous.sets){const remove=(set.media_ids||[]).filter(id=>fixture.ungrouped.includes(id));if(remove.length)await api('sets/'+set.id,{remove_media_ids:remove});}
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');await page.getByText('Local library connected',{exact:true}).waitFor();

  const before=await api('library');
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiAssignGroups([id],true),fixture.ungrouped[0]);
  await page.locator('.naiIndividualCard').first().waitFor();
  assert.equal(await page.locator('.naiIndividualCard').count(),5);
  assert.equal(await page.locator('.naiIndividualCard[data-media-id="'+fixture.ungrouped[0]+'"]').count(),0);
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiIndividualCard img')].every(img=>img.complete&&img.naturalWidth>0));
  assert.deepEqual((await api('library')).sets,before.sets,'Searching cannot assign or create');
  await page.screenshot({path:'/tmp/individual-matching-'+(standalone?'standalone':'novelai')+'.png'});
  await page.locator('.naiIndividualCard[data-media-id="'+fixture.ungrouped[1]+'"] input').check();
  const name='New pair '+(standalone?'standalone':'NovelAI');
  await page.getByLabel('New matching Set name',{exact:true}).fill(name);
  await page.getByRole('button',{name:'Create Set with selected images',exact:true}).click();
  await page.locator('.naiIndividualSection').waitFor({state:'detached'});
  const created=(await api('library')).sets.find(s=>s.name===name);assert(created);assert.deepEqual(new Set(created.media_ids),new Set(fixture.ungrouped.slice(0,2)));
  assert.equal(await page.locator('#naiAssignExisting').inputValue(),created.id);
  await page.locator('#modalRoot [data-close]').first().click();
  // Scan is read-only until an explicit per-image assignment.
  await page.locator('#naiManageSetsBtn').click();await page.locator('#naiToolsScanSets').click();
  const preScan=await api('library');await page.getByRole('button',{name:'Start scan',exact:true}).click();
  await page.getByRole('combobox',{name:'Scan result filter'}).waitFor();
  assert.equal(await page.getByRole('combobox',{name:'Scan result filter'}).inputValue(),'stronger');
  assert.deepEqual((await api('library')).sets,preScan.sets);
  await page.getByRole('combobox',{name:'Scan result filter'}).selectOption('all');
  await page.locator('.naiScanSuggestion').first().waitFor();
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiScanReview img')].every(img=>img.complete&&img.naturalWidth>0));
  await page.screenshot({path:'/tmp/set-scan-'+(standalone?'standalone':'novelai')+'.png'});
  const scannedId=await page.locator('.naiScanReview').getAttribute('data-media-id');
  assert(fixture.ungrouped.slice(2).includes(scannedId));
  const chosen=await page.locator('.naiScanSuggestion').first().getAttribute('data-set-id');
  await page.locator('.naiScanAssign').first().click();
  await page.waitForFunction(id=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiScanReview')?.dataset.mediaId!==id,scannedId);
  const after=await api('library');assert(after.sets.find(s=>s.id===chosen).media_ids.includes(scannedId));
  assert.equal(after.sets.filter(s=>s.media_ids.includes(scannedId)).length,1);
  await page.locator('.naiScanWrap').getByRole('button',{name:'Close',exact:true}).click();
  // New Set from an unsaved draft: only the explicitly chosen saved image is grouped.
  const count=(await api('library')).media.length;
  await page.locator('#addMediaBtn').click();
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAHgAAAC0CAIAAADQLH9KAAABoElEQVR4nO3QQRHAIADAMMDifKAKoVOx8liioNf57DP43rod8BdGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI4YHTE6YnTE6IjREaMjRkeMjhgdMTpidMToiNERoyNGR4yOGB0xOmJ0xOiI0RGjI0ZHjI68i6gCzZqgQDEAAAAASUVORK5CYII=','base64');

  await page.locator('#fileInput').setInputFiles([{name:'Pending query.png',mimeType:'image/png',buffer:png}]);await page.locator('#importReview').click();
  await page.locator('#naiReviewFindMatches').click();await page.locator('.naiIndividualCard').first().waitFor();
  const selectedIndividual=await page.locator('.naiIndividualCard').first().getAttribute('data-media-id');
  await page.locator('.naiIndividualCard input').first().check();
  const queuedName='For queue '+(standalone?'standalone':'NovelAI');await page.getByLabel('New matching Set name',{exact:true}).fill(queuedName);
  await page.getByRole('button',{name:'Create Set with selected images',exact:true}).click();await page.locator('.naiIndividualSection').waitFor({state:'detached'});
  const queued=(await api('library')).sets.find(s=>s.name===queuedName);assert(queued);assert.deepEqual(queued.media_ids,[selectedIndividual]);assert.equal((await api('library')).media.length,count);
  assert.equal(await page.locator('#naiSetQueueExisting270').inputValue(),queued.id);assert.equal(await page.locator('.naiSetQueueCard270 input:checked').count(),1);
  await page.locator('#naiSetQueueCancel270').click();await page.locator('#naiReviewClose270').click();
  assert.deepEqual(errors,[]);assert.deepEqual(alerts,[]);
  console.log('PASS individual matching and scan: '+(standalone?'standalone':'NovelAI')+' loaded previews, saved pair creation, scan review/manual assignment, queued image not imported.');await page.close();
 }
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
