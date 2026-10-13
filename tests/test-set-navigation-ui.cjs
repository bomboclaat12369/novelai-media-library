// Focused UI regression: Set thumbnail restoration, editing scroll, and input focus.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:config.version,NAI_FIXTURE_MULTI_SET:'',NAI_FIXTURE_EXTRA_IMAGES:'100',NAI_FIXTURE_SCROLL_SETS:'1'}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
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
  // Main search goes to Set names without a category click.
  assert.equal(await page.locator('#naiSearchScope').inputValue(),'sets');
  await page.locator('#search').fill('Scroll Set 050');
  await page.locator('.naiSetTile').waitFor();
  assert.equal(await page.locator('.naiSetTile').count(),1);
  await page.locator('#search').fill('');
  assert.equal(await page.locator('.naiSetCardEdit,.naiSetCardCategories').count(),0);
  const lib=await api('library'),target=lib.sets.find(s=>s.name==='Scroll Set 050'),large=lib.sets.find(s=>s.name==='Large Set');
  const scroll=async y=>page.evaluate(y=>{const r=document.getElementById('nai-media-host').shadowRoot;r.naiVirtualGrid.restoreScroll(y);return r.getElementById('grid').scrollTop;},y);
  const getScroll=()=>page.locator('#grid').evaluate(g=>g.scrollTop);
  const anchor=await scroll(1200);assert(anchor>800);
  await page.locator('#naiManageSetsBtn').click();
  await page.locator('#naiManageSetSearch').waitFor();
  assert.equal(await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.activeElement.id),'naiManageSetSearch');
  assert.equal(await getScroll(),anchor);
  await page.locator('#naiManageSetSearch').fill('Scroll Set 050');
  await page.locator('.naiSetToolsRow button').filter({hasText:'Rename'}).click();
  await page.locator('#naiQuickSetName').waitFor();
  assert.equal(await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.activeElement.id),'naiQuickSetName');
  await page.locator('#naiQuickSetName').fill('Renamed 050');
  await page.locator('#modalRoot [data-save]').click();await page.locator('#naiQuickSetName').waitFor({state:'detached'});
  assert(Math.abs(await getScroll()-anchor)<3,'rename preserves Set browser scroll');
  await page.locator('#naiManageSetsBtn').click();await page.locator('#naiManageSetSearch').fill('Large Set');
  await page.locator('.naiSetToolsRow button').filter({hasText:'Edit contents'}).click();
  await page.locator('#naiGroupSearch').waitFor();
  assert.equal(await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.activeElement.id),'naiGroupSearch');
  await page.locator('#naiSaveSetBtn').click();await page.locator('#naiSaveSetBtn').waitFor({state:'detached'});
  assert(Math.abs(await getScroll()-anchor)<3,'contents save preserves Set browser scroll');
  // Opening and returning from a Set restores the Set list position.
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiOpenGroup(id),large.id);
  await page.locator('#naiSetEditBtn').waitFor();
  const memberScroll=await scroll(900);assert(memberScroll>600);
  await page.locator('#naiManageSetsBtn').click();await page.locator('#naiManageSetSearch').fill('Large Set');
  await page.locator('.naiSetToolsRow button').filter({hasText:'Rename'}).click();await page.locator('#naiQuickSetName').fill('Large Set');
  await page.locator('#modalRoot [data-save]').click();await page.locator('#naiQuickSetName').waitFor({state:'detached'});
  assert(Math.abs(await getScroll()-memberScroll)<3,'open Set member grid keeps its position');
  // The breadcrumb is above the scrolled viewport, so invoke it without auto-scrolling.
  await page.locator('#naiSetBackBtn').evaluate(b=>b.click());
  assert(Math.abs(await getScroll()-anchor)<3,'Back restores Set browser position');
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiAssignGroups([id]),fixture.images[3]);
  await page.locator('#naiAssignSearch').waitFor();
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.activeElement.id==='naiAssignSearch');
  await page.locator('#modalRoot [data-close]').click();
  await page.locator('#naiManageSetsBtn').click();await page.locator('#naiToolsNewSet').click();
  await page.locator('#naiSetNameInput').waitFor();
  assert.equal(await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.activeElement.id),'naiSetNameInput');
  await page.locator('#modalRoot .naiSetManagerFoot [data-close]').click();
  await page.locator('#naiManageSetsBtn').click();await page.locator('#naiToolsCategories').click();
  await page.locator('#naiNewCategoryName').waitFor();
  assert.equal(await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.activeElement.id),'naiNewCategoryName');
  await page.locator('#modalRoot .modalFoot [data-close]').click();
  await page.locator('.cat[data-cat="all"]').click();
  assert.equal(await page.locator('#naiSearchScope').inputValue(),'sets');
  assert.equal(await page.locator('#search').inputValue(),'');
  await page.locator('#naiSearchScope').selectOption('files');await page.locator('#search').fill('Portrait 4');
  await page.locator('.tile[data-id="'+fixture.images[3]+'"]').waitFor();
  assert.equal(await page.locator('#grid .tile').count(),1,'explicit filename search still works');
  await page.locator('.cat[data-cat="purgatory"]').click();
  assert.equal(await page.locator('#naiSearchScope').inputValue(),'sets');
  await api('sets/'+target.id,{name:'Scroll Set 050'});
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: both interfaces — classic cards, management menu, edit/back scroll retention, default Set search, explicit file search, and automatic field focus.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
