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
 for(const standalone of [false]){
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
  await api('sets',{character_id:fixture.character,name:'White Bikini 1',media_ids:[fixture.images[1]],preserve_placement:true});
  await api('sets',{character_id:fixture.character,name:'White Bikini 2',media_ids:[fixture.images[2]],preserve_placement:true});
  await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiReloadLibrary());
  for(const query of ['white bikini','white']){
   await page.locator('#search').fill(query);await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelectorAll('#grid .tile[data-id]').length===2);
   assert.deepEqual((await page.locator('#grid .tile[data-id]').evaluateAll(es=>es.map(e=>e.dataset.id))).sort(),[fixture.images[1],fixture.images[2]].sort());
  }
  await page.locator('.naiSearchField').filter({has:page.locator('#search')}).getByRole('button',{name:'Clear search',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelectorAll('#grid .tile[data-id]').length===6);
  await page.locator('#naiProfileBtn').click();const profile=page.getByRole('dialog',{name:'Person profile',exact:true});await profile.getByRole('button',{name:'Edit profile',exact:true}).click();await profile.getByLabel('Eye color',{exact:true}).fill('Blue');await profile.getByLabel('Hair color',{exact:true}).fill('Brown');await profile.getByRole('button',{name:'Save profile',exact:true}).click();await profile.getByText('Blue',{exact:true}).waitFor();assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Passed: NovelAI overlay main search by associated set name and substring, search clearing, profile colors.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
