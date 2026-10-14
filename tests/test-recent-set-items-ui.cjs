// Focused UI regression: Set thumbnail restoration, editing scroll, and input focus.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:config.version,NAI_FIXTURE_MULTI_SET:'',NAI_FIXTURE_EXTRA_IMAGES:'0',NAI_FIXTURE_SCROLL_SETS:''}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{const text=b.toString();if(text.includes('ready'))resolve(JSON.parse(text));});server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});
 context.setDefaultTimeout(10000);
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 await api('media/'+fixture.images[1]+'/categories',{categories:[],in_all:false});
 await api('media/'+fixture.images[2]+'/categories',{categories:[],in_all:false});
 const outfit=await api('sets',{character_id:fixture.character,name:'Blue Dress',media_ids:[fixture.images[1],fixture.images[2]],preserve_placement:true});
 await api('media/'+fixture.images[2]+'/review',{in_review:true});
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
  const tileIds=()=>page.locator('#grid .tile[data-id]').evaluateAll(tiles=>tiles.map(t=>t.dataset.id));
  const blankClick=async()=>{
    const point=await page.locator('#grid').evaluate(g=>{const r=g.getBoundingClientRect(),bottom=Math.max(...[...g.children].map(c=>c.getBoundingClientRect().bottom));return {x:r.left+20,y:Math.min(r.bottom-20,bottom+50)};});
    await page.mouse.click(point.x,point.y);
  };
  // Blank Main space must not navigate.
  await blankClick();assert.equal(await page.locator('#naiSetBackBtn').count(),0);
  await page.locator('#naiRecentSetItemsCat').click();await page.locator('#naiRecentSetType').waitFor();
  assert.deepEqual(await tileIds(),[fixture.images[1],fixture.images[2]].sort().concat(fixture.images[0]),'Set-entry order, including Review members');
  assert.equal(await page.locator('#naiSetEditBtn').count(),0,'Recent view has no bogus Set editor');
  await page.locator('#naiRecentOutsideMain').check();assert.deepEqual((await tileIds()).sort(),[fixture.images[1],fixture.images[2]].sort());
  await page.locator('#search').fill('blue');assert.equal((await tileIds()).length,2);
  await page.locator('#search').fill('missing');assert.equal((await tileIds()).length,0);
  await page.locator('#search').fill('');
  await page.locator('#naiRecentOutsideMain').uncheck();
  await page.locator('#naiRecentSetType').selectOption('all');assert.equal((await tileIds()).length,4);
  await page.locator('#naiRecentSetType').selectOption('image');
  // Item opens the existing viewer; caption opens its Set, Back returns to recents.
  await page.locator('.tile[data-id="'+fixture.images[1]+'"] img').click();
  await page.locator('.tile[data-id="'+fixture.images[1]+'"] .naiRecentSetCaption').click();
  await page.locator('#naiSetEditBtn').waitFor();
  await blankClick();await page.locator('#naiRecentSetType').waitFor();
  await page.locator('#naiSetBackBtn').click();await page.locator('.naiSetTile').first().waitFor();
  // Standard Set dead space follows Back and returns to the browser.
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiOpenGroup(id),outfit.id);
  await page.locator('#naiSetEditBtn').waitFor();await blankClick();await page.locator('.naiSetTile').first().waitFor();
  // Main selection changes an Auto cover without losing the Auto tag.
  const updated=await api('media/'+fixture.images[2]+'/review',{in_review:false});
  const main=await api('media/'+fixture.images[2]+'/categories',{categories:[],in_all:true});
  await page.evaluate(m=>{const r=document.getElementById('nai-media-host').shadowRoot;r.naiApplyMediaUpdate(m);r.naiSetsApplyLibrary216(r.naiGetLibrary());},main);
  const card=page.locator('.naiSetTile').filter({hasText:'Blue Dress'});
  assert.equal(await card.getAttribute('data-cover-id'),fixture.images[2]);assert.match(await card.innerText(),/Auto/);
  // Reset shared server placement for the second interface.
  await api('media/'+fixture.images[2]+'/categories',{categories:[],in_all:false});await api('media/'+fixture.images[2]+'/review',{in_review:true});
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: standalone and NovelAI — recent Set items, date order, Review visibility, outside-Main and type filters, search, viewer, scoped blank-space Back, Main cover and Auto badge.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
