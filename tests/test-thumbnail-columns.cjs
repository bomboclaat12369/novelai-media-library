// Thumbnail density is shared by both interfaces and remains virtualized.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:config.version,NAI_FIXTURE_EXTRA_IMAGES:'400'}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{if(b.toString().includes('ready'))resolve();});server.on('exit',c=>reject(Error(stderr+c)));});
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
  const columns=page.locator('#naiThumbColumns');
  await columns.waitFor({state:'visible'});assert.equal(await columns.inputValue(),'5');
  assert.deepEqual(await columns.locator('option').evaluateAll(opts=>opts.map(o=>o.value)),['4','5','6','7','8']);
  for(let mode=0;mode<2;mode++){
    for(const n of [4,5,6,7,8]){
      await columns.selectOption(String(n));
      assert.equal(await page.locator('#grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),n);
      await page.locator('#grid').evaluate(el=>el.scrollTop=el.scrollHeight);
      await page.waitForFunction(()=>{const r=document.getElementById('nai-media-host').shadowRoot;return !!r.querySelector('#grid .tile[title="Grid 399.jpg"]');});
      const ids=await page.locator('#grid .tile').evaluateAll(tiles=>tiles.map(t=>t.dataset.id));
      assert.equal(ids.length,new Set(ids).size);assert(ids.length<406,'grid remains virtualized');
    }
    await page.locator('#splitBtn').click();
  }
  await columns.selectOption('7');await page.reload();await page.getByText('Local library connected',{exact:true}).waitFor();assert.equal(await columns.inputValue(),'7');
  assert.equal(await page.locator('#grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),7);
  await page.locator('#naiSetsCat').click();assert.equal(await columns.inputValue(),'7');await page.locator('.naiSetTile').waitFor();
  await columns.selectOption('4');assert.equal(await page.locator('#grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),4);
  await page.locator('.right .toolbar').screenshot({path:'/tmp/nai71-columns-'+(standalone?'standalone':'overlay')+'.png'});
  assert.deepEqual(errors,[]);assert.deepEqual(alerts,[]);await page.close();
 }
 console.log('PASS: 4–8 columns in both interfaces and both viewer modes; virtual scrolling, persistence, and Sets.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
