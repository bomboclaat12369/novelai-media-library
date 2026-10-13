// Focused regression: confirmed Set removal, search scope, and source-replacement Undo.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:config.version,NAI_FIXTURE_MULTI_SET:'1'}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{const text=b.toString();if(text.includes('ready'))resolve(JSON.parse(text));});server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});
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
  await api('sets/'+blue.id,{add_media_ids:[fixture.images[1],fixture.images[2]]});
  await api('media/'+fixture.images[1]+'/categories',{categories:[],in_all:false});
  await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiReloadLibrary());
  await page.locator('#naiSetsCat').click();
  await page.locator('#search').fill('Blue');
  await page.locator('.naiSetTile[data-set-id="'+orange.id+'"]').waitFor({state:'detached'});
  await page.locator('.cat[data-cat="all"]').click();
  assert.equal(await page.locator('#search').inputValue(),'');
  await page.locator('#naiSetsCat').click();
  assert.equal(await page.locator('#search').inputValue(),'Blue');
  await page.locator('.naiSetTile[data-set-id="'+blue.id+'"]').click();
  await page.locator('.tile[data-id="'+fixture.images[1]+'"]').waitFor();
  assert.equal(await page.locator('.naiRemoveSetMember').count(),0);
  await page.locator('#search').fill('Portrait');
  await page.locator('.cat[data-cat="all"]').click();
  assert.equal(await page.locator('#search').inputValue(),'');
  await page.locator('#naiSetsCat').click();
  assert.equal(await page.locator('#search').inputValue(),'Blue');
  await page.locator('.naiSetTile[data-set-id="'+blue.id+'"]').click();
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia(id),fixture.images[1]);
  await page.locator('#naiMemberships .naiRemoveMembership').click();
  await page.locator('#naiConfirmRemoveSet').waitFor();
  assert((await api('library')).sets.find(s=>s.id===blue.id).media_ids.includes(fixture.images[1]));
  await page.locator('#modalRoot').getByRole('button',{name:'Cancel',exact:true}).click();
  assert((await api('library')).sets.find(s=>s.id===blue.id).media_ids.includes(fixture.images[1]));
  await page.locator('#naiMemberships .naiRemoveMembership').click();
  await page.locator('#naiConfirmRemoveSet').click();
  await page.locator('#naiConfirmRemoveSet').waitFor({state:'detached'});
  let library=await api('library');
  assert(!library.sets.find(s=>s.id===blue.id).media_ids.includes(fixture.images[1]));
  assert(library.media.find(m=>m.id===fixture.images[1]).in_all);
  await page.locator('.cat[data-cat="all"]').click();
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia(id),fixture.images[4]);
  assert.equal(await page.locator('#naiMemberships .naiRemoveMembership').count(),1);
  await page.locator('#naiMemberships .naiRemoveMembership').click();
  await page.locator('#naiRemoveSetChoice').waitFor();
  assert(await page.locator('#naiConfirmRemoveSet').isDisabled());
  const overlap=library.sets.find(s=>s.name==='Overlap One');
  await page.locator('#naiRemoveSetChoice').selectOption(overlap.id);
  assert(!(await page.locator('#naiConfirmRemoveSet').isDisabled()));
  if(standalone){await page.locator('#modalRoot').getByRole('button',{name:'Cancel',exact:true}).click();}
  else{
   await page.locator('#naiConfirmRemoveSet').click();
   await page.locator('#naiConfirmRemoveSet').waitFor({state:'detached'});
   library=await api('library');
   assert(!library.sets.find(s=>s.id===overlap.id).media_ids.includes(fixture.images[4]));
   assert(library.sets.find(s=>s.name==='Overlap Two').media_ids.includes(fixture.images[4]));
  }
  const before=(await api('library')).media.find(m=>m.id===fixture.images[3]);
  const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=17;c.height=23;c.getContext('2d').fillRect(0,0,17,23);return c.toDataURL().split(',')[1];});
  const replaced=await context.request.post('http://127.0.0.1:8765/api/media/'+before.id+'/replace',{multipart:{file:{name:before.original_name,mimeType:'image/png',buffer:Buffer.from(png,'base64')}}});
  assert.equal(replaced.status(),200,await replaced.text());
  await page.evaluate(async id=>{const r=document.getElementById('nai-media-host').shadowRoot;await r.naiReloadLibrary();r.naiSelectMedia(id);},before.id);
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#stage1 img')?.naturalWidth===17);
  await page.locator('#undoBtn').click();
  await page.locator('#undoLatestBtn').waitFor();
  assert((await page.locator('[data-history-list] li').first().innerText()).includes('Replace image source'));
  await page.locator('#undoLatestBtn').click();
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('[data-history-status]').textContent.includes('Keeps the last') && !document.getElementById('nai-media-host').shadowRoot.querySelector('[data-history-list] li')?.textContent.includes('Replace image source'));
  assert.equal((await api('library')).media.find(m=>m.id===before.id).sha256,before.sha256);
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#stage1 img')?.naturalWidth===1000);
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: standalone and NovelAI confirmed Set removal, multiple-Set choice, Set search isolation, replacement Undo.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
