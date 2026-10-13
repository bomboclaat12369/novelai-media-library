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
  await page.locator('#naiSetsCat').click();await page.locator('.naiSetTile[data-set-id="'+blue.id+'"]').click();
  const first=page.locator('.tile[data-id="'+fixture.images[1]+'"]');
  await first.getByRole('button',{name:'Remove from Set',exact:true}).click();
  await first.waitFor({state:'detached'});
  let library=await api('library');
  assert(!library.sets.find(s=>s.id===blue.id).media_ids.includes(fixture.images[1]));
  assert(library.media.find(m=>m.id===fixture.images[1]).in_all);
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia(id),fixture.images[2]);
  await page.locator('#naiMemberships .naiRemoveMembership').click();
  await page.locator('#naiMemberships .naiRemoveMembership').waitFor({state:'detached'});
  library=await api('library');assert.equal(library.sets.find(s=>s.id===blue.id).media_ids.length,0);
  assert(library.media.some(m=>m.id===fixture.images[2]));
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: explicit Set tile and viewer removal controls in NovelAI and standalone; files retained; Set-only image returns to Main.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
