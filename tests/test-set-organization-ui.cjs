// Focused release integration: Set organization, main placement, and search fields.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:config.version,NAI_FIXTURE_MULTI_SET:''}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{const text=b.toString();if(text.includes('ready'))resolve(JSON.parse(text));});server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});
 context.setDefaultTimeout(10000);
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 await api('media/'+fixture.images[5]+'/review',{in_review:true});
 const blue=await api('sets',{character_id:fixture.character,name:'Blue Dress',media_ids:[fixture.images[1],fixture.images[2]],preserve_placement:false});
 const orange=await api('sets',{character_id:fixture.character,name:'Orange Bikini',media_ids:[],preserve_placement:true});
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
  await api('sets/'+blue.id,{remove_media_ids:[fixture.images[3]]});
  await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiReloadLibrary());
  const suffix=standalone?' standalone':' NovelAI';
  await page.locator('#naiManageSetsBtn').click();
  await page.locator('#naiManageCategories').click();
  await page.locator('#naiNewCategoryName').fill('Outfits'+suffix);
  await page.locator('#naiCreateCategory').click();
  await page.locator('.naiCategoryManageRow input').first().waitFor();
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiSetDialogStatus').textContent==='Saved');
  let lib=await api('library'),cat=lib.characters[0].set_categories.find(c=>c.name==='Outfits'+suffix);
  assert(cat);
  await page.locator('.naiCategoryManageRow[data-category-id="'+cat.id+'"] input').fill('Clothes'+suffix);
  await page.locator('.naiCategoryManageRow[data-category-id="'+cat.id+'"] button').filter({hasText:'Rename category'}).click();
  await page.waitForFunction(id=>document.getElementById('nai-media-host').shadowRoot.naiGetLibrary().characters[0].set_categories.find(c=>c.id===id)?.name.startsWith('Clothes'),cat.id);
  await page.locator('#modalRoot .modalFoot [data-close]').click();
  await page.locator('.naiSetTile[data-set-id="'+blue.id+'"] .naiSetCardEdit').click();
  assert.equal(await page.locator('#naiSetGallery').count(),0,'quick edits do not open picker');
  await page.locator('#naiQuickSetName').fill('Blue renamed'+suffix);
  if(standalone)await page.screenshot({path:'/tmp/nai-set-edit.png'});
  await page.locator('input[data-set-category="'+cat.id+'"]').check();
  await page.locator('#modalRoot [data-save]').click();await page.locator('#naiQuickSetName').waitFor({state:'detached'});
  lib=await api('library');assert.equal(lib.sets.find(s=>s.id===blue.id).name,'Blue renamed'+suffix);assert(lib.sets.find(s=>s.id===blue.id).categories.includes(cat.id));
  await page.locator('#naiSelectSets').click();
  for(const id of [blue.id,orange.id])await page.locator('.naiSetTile[data-set-id="'+id+'"] .naiSetSelect').check();
  await page.locator('#naiBulkSetCategories').click();
  await page.locator('input[data-set-category="'+cat.id+'"]').check();await page.locator('#modalRoot [data-save]').click();
  await page.locator('#naiBulkCategoryAction').waitFor({state:'detached'});
  lib=await api('library');assert(lib.sets.find(s=>s.id===orange.id).categories.includes(cat.id));
  await page.locator('#naiSelectSets').click();
  for(const id of [blue.id,orange.id])await page.locator('.naiSetTile[data-set-id="'+id+'"] .naiSetSelect').check();
  await page.locator('#naiBulkSetCategories').click();await page.locator('#naiBulkCategoryAction').selectOption('remove');
  await page.locator('input[data-set-category="'+cat.id+'"]').check();await page.locator('#modalRoot [data-save]').click();
  await page.locator('#naiBulkCategoryAction').waitFor({state:'detached'});
  lib=await api('library');assert(!lib.sets.find(s=>s.id===blue.id).categories.includes(cat.id));
  await page.locator('.naiSetTile[data-set-id="'+blue.id+'"]').click();await page.locator('#naiSetEditBtn').click();
  await page.locator('#naiSetGallery .naiSetPick[data-media-id="'+fixture.images[1]+'"]').waitFor();
  assert.equal(await page.locator('#naiSetGallery .naiSetPick[data-media-id="'+fixture.images[0]+'"]').count(),0,'other Set media hidden');
  await page.locator('#naiShowOtherSetMedia').check();
  await page.locator('#naiSetGallery .naiSetPick[data-media-id="'+fixture.images[0]+'"]').waitFor();
  assert.equal(await page.locator('#naiGroupSearch').getAttribute('autocomplete'),'off');
  assert.equal(await page.locator('#naiGroupSearch').getAttribute('list'),'naiEmptySearchSuggestions');
  assert.equal(await page.locator('#naiSetUploadBtn').count(),1);
  await page.locator('#naiShowOtherSetMedia').uncheck();
  await page.locator('#naiSetGallery .naiSetPick[data-media-id="'+fixture.images[3]+'"]').click();
  await page.locator('#naiSaveSetBtn').click();await page.locator('#naiSaveSetBtn').waitFor({state:'detached'});
  assert((await api('library')).sets.find(s=>s.id===blue.id).media_ids.includes(fixture.images[3]));
  // Reopen and cancel must not lose existing contents or show other Sets.
  await page.locator('#naiSetEditBtn').click();await page.locator('#naiShowOtherSetMedia').waitFor();
  assert(!(await page.locator('#naiShowOtherSetMedia').isChecked()));
  await page.locator('#modalRoot').getByRole('button',{name:'Cancel',exact:true}).click();
  await page.locator('#naiSetBackBtn').click();await page.locator('#naiCreateSet').click();
  await page.locator('#naiSetNameInput').fill('New Set'+suffix);
  assert.equal(await page.locator('#naiSetUploadBtn').count(),1);
  assert.equal(await page.locator('#naiSetGallery .naiSetPick[data-media-id="'+fixture.images[0]+'"]').count(),0);
  await page.locator('#naiSaveSetBtn').click();await page.locator('#naiSaveSetBtn').waitFor({state:'detached'});
  assert((await api('library')).sets.some(s=>s.name==='New Set'+suffix));
  // A real category assignment from Purgatory exits it and sorts by Main entry.
  await api('media/'+fixture.images[1]+'/purgatory',{in_purgatory:true});
  await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiReloadLibrary());
  await page.locator('.cat[data-cat="purgatory"]').click();
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia(id),fixture.images[1]);
  await page.locator('#editBtn').click();
  await page.locator('#editMediaCats input').first().check();
  await page.locator('#saveMediaCats').click();
  await page.waitForFunction(id=>!document.getElementById('nai-media-host').shadowRoot.naiGetLibrary().media.find(m=>m.id===id).in_purgatory,fixture.images[1]);
  await page.locator('#saveMediaCats').waitFor({state:'detached'});
  await page.locator('.cat[data-cat="all"]').click();
  await page.locator('#sortSelect').selectOption('main_added');
  await page.waitForFunction(id=>document.getElementById('nai-media-host').shadowRoot.querySelector('#grid .tile[data-id]')?.dataset.id===id,fixture.images[1]);
  lib=await api('library');assert(lib.media.find(m=>m.id===fixture.images[1]).created_at.startsWith('2020-'));
  assert.equal(await page.locator('#search').getAttribute('autocomplete'),'off');
  await page.locator('#naiSetsCat').click();
  await page.screenshot({path:'/tmp/nai-sets-'+(standalone?'standalone':'novelai')+'.png'});
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: both interfaces — quick rename/categories, bulk add/remove, category management, Set picker visibility, creation, Purgatory exit and Main-entry sorting.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
