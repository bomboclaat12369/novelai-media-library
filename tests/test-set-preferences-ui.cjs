// Real companion API: set preference workflows on both interfaces.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python',['tests/serve_efficiency_fixture.py'],{cwd:dir});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{if(b.toString().includes('READY'))resolve();});server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1000}});
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200);return r.json();};
 for(const standalone of [false,true]){
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
  const lib=await api('library'),base=lib.sets[0];
  // Start with an automatic cover for each interface's test.
  await api('sets/'+base.id,{cover_source:'auto',cover_media_id:base.media_ids[0],favorite:false});
  await page.locator('#refreshBtn').click();await page.locator('#naiSetsCat').click();
  const tile=page.locator(`.naiSetTile[data-set-id="${base.id}"]`);
  await tile.locator('.naiSetCoverStatus').getByText('Auto',{exact:true}).waitFor();
  await tile.screenshot({path:'/tmp/nai70-auto-'+(standalone?'standalone':'overlay')+'.png'});
  await tile.locator('.naiSetFavorite').click();await page.locator('#naiFavoriteSetsCat').getByText('★ Favorite Sets 1',{exact:true}).waitFor();
  await page.locator('#naiFavoriteSetsCat').click();assert.equal(await page.locator('.naiSetTile').count(),1);
  assert.equal(await page.locator('#naiFavoriteSetsCat').evaluate(e=>e.classList.contains('active')),true);
  await tile.click();await page.locator('#naiSetBackBtn').waitFor();
  await page.locator(`.tile[data-id="${base.media_ids[0]}"] .naiSetCover216`).click();
  await page.locator(`.tile[data-id="${base.media_ids[0]}"] .naiSetCover216[title="Current set thumbnail"]`).waitFor();
  await page.locator('#naiSetBackBtn').click();await tile.waitFor();assert.equal(await tile.locator('.naiSetCoverStatus').count(),0);
  assert.equal(await page.locator('#naiFavoriteSetsCat').evaluate(e=>e.classList.contains('active')),true);
  await page.reload();await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiFavoriteSetsCat').click();await tile.waitFor();assert.equal(await tile.locator('.naiSetCoverStatus').count(),0);
  const after=await api('library');assert.equal(after.media.filter(m=>m.favorite).length,0,'set favorites must not favorite their contents');
  await tile.locator('.naiSetFavorite').click();await page.getByText('No favorite sets match this view. Use the star on a set to add it.',{exact:true}).waitFor();
  // Saving the default cover through Manage Sets does not mark it manually chosen.
  await page.locator('#naiManageSetsBtn').click();await page.locator('#naiNewSetBtn').click();await page.locator('#naiSetNameInput').fill(base.name);
  await page.locator('#naiSaveSetBtn').click();await page.locator('.naiSetEditor').waitFor({state:'detached'});
  let saved=(await api('library')).sets;const name=standalone?base.name+' 2':base.name+' 1';assert(saved.some(s=>s.name===name));
  await page.locator('#naiSetsCat').click();await page.locator('#grid').screenshot({path:'/tmp/nai70-sets-'+(standalone?'standalone':'overlay')+'.png'});
  assert.deepEqual(errors,[]);assert.deepEqual(alerts,[]);await page.close();
 }
 console.log('PASS: both interfaces: automatic cover badge, manual pin, separate set favorites, persistence, back navigation, collision numbering and no media favorite changes.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
