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
  let promptAnswer='Outfits';const page=await context.newPage(),errors=[],alerts=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept(d.type()==='prompt' ? promptAnswer : undefined));
  if(!standalone){
   await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
   await page.exposeFunction('companionRequest',async o=>{const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
   await page.addInitScript(({payload,version})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
   },{payload,version:config.version});
  }
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');await page.getByText('Local library connected',{exact:true}).waitFor();
  await page.locator('#naiManageSetsBtn').click();
  await page.locator('#naiExistingSets button').filter({hasText:'Blue Dress'}).click();
  await page.locator('#naiNewSetCategory').click();
  await page.locator('#naiSetCategoryAssignments label').filter({hasText:'Outfits'}).waitFor();
  assert.equal(await page.locator('#naiSetCategoryAssignments input:checked').count(),1);
  await page.locator('#naiSaveSetBtn').click();await page.locator('#naiSaveSetBtn').waitFor({state:'detached'});
  const lib=await api('library'),category=lib.characters[0].set_categories.find(c=>c.name==='Outfits');
  assert.deepEqual(lib.sets.find(s=>s.id===blue.id).categories,[category.id]);
  assert(!lib.characters[0].categories.some(c=>c.id===category.id));
  await page.locator('#naiSetsCat').click();await page.locator('#naiSetCategoryFilter').selectOption(category.id);
  assert.deepEqual(await page.locator('.naiSetTile').evaluateAll(es=>es.map(e=>e.dataset.setId)),[blue.id]);
  await page.locator('.naiSetFavorite').click();
  await page.locator('#naiFavoriteSetsCat').click();assert.equal(await page.locator('.naiSetTile').count(),1);
  await page.locator('#naiSetsCat').click();await page.locator('#naiSetCategoryFilter').selectOption('__none');
  assert(!(await page.locator('.naiSetTile').evaluateAll(es=>es.map(e=>e.dataset.setId))).includes(blue.id));
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiAssignGroups([id]),fixture.images[3]);
  await page.locator('.naiSetPickerCategory').selectOption(category.id);
  assert.deepEqual(await page.locator('#naiAssignExisting option').allTextContents(),['Choose a set…','Blue Dress']);
  await page.locator('#modalRoot [data-close]').click();
  await page.locator('#naiManageSetsBtn').click();await page.locator('#naiManagerSetCategory').selectOption(category.id);
  assert.equal(await page.locator('#naiExistingSets button').count(),1);
  await page.locator('#naiExistingSets button').click();promptAnswer='Clothing';
  await page.locator('#naiRenameSetCategory').click();await page.locator('#naiSetCategoryAssignments label').filter({hasText:'Clothing'}).waitFor();
  assert.equal(await page.locator('#naiSetCategoryAssignments input:checked').count(),1);
  await page.locator('.modal').screenshot({path:'/tmp/set-categories-'+(standalone?'standalone':'novelai')+'.png'});
  await page.locator('#naiDeleteSetCategory').click();await page.getByText('Create categories to organize your Sets.',{exact:true}).waitFor();
  assert.equal((await api('library')).sets.find(s=>s.id===blue.id).categories.length,0);
  await page.locator('#modalRoot [data-close]').first().click();
  await api('sets/'+blue.id,{favorite:false});
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: both interfaces create, assign, filter, rename and delete Set categories; Favorite Sets and assignment picker filters; media categories unchanged.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
