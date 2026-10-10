// Two browser origins using the real local companion. Verify both update directions.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python',['tests/serve_efficiency_fixture.py'],{cwd:dir});let stderr='';server.stderr.on('data',b=>stderr+=b);
 let browser;
 try{
  await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{if(b.toString().includes('READY'))resolve();});server.on('exit',code=>reject(Error('Fixture failed '+code+' '+stderr)));});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
  const context=await browser.newContext({viewport:{width:1600,height:1000}}),errors=[];
  const overlay=await context.newPage();overlay.on('pageerror',e=>errors.push(e.message));overlay.on('dialog',d=>d.accept());
  await overlay.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body><textarea id="story"></textarea></body>'}));
  await overlay.exposeFunction('companionRequest',async o=>{const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
  await overlay.addInitScript(({payload})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=localStorage.getItem('nai-media-github-payload-version')||'2.8.68';eval(localStorage.getItem('nai-media-github-payload')||payload);});
  },{payload});
  await overlay.goto('https://novelai.net/stories');await overlay.getByText('Local library connected',{exact:true}).waitFor();
  const standalone=await context.newPage();standalone.on('pageerror',e=>errors.push(e.message));standalone.on('dialog',d=>d.accept());
  await standalone.goto('http://127.0.0.1:8765/library/');await standalone.getByText('Local library connected',{exact:true}).waitFor();
  const ready=async(page,version)=>page.waitForFunction(v=>document.documentElement.dataset.naiMediaPayloadVersion===v,version);
  await standalone.locator('#naiCharacterStats').click();
  await standalone.getByText('3 unique saved files · 1 Set · 1 image needs replacement',{exact:true}).waitFor();
  assert.match(await standalone.locator('#naiStatsCounts').textContent(),/Inside Sets2/);
  await standalone.locator('#naiQualityMP').fill('0.4');await standalone.locator('#naiQualitySave').click();
  await standalone.getByText('Saved. New imports use this setting. Scan existing files to apply it to them.',{exact:true}).waitFor();
  await standalone.locator('#naiQualityScan').click();await standalone.getByText('Scan complete. Resolution flags and storage totals updated.',{exact:true}).waitFor();
  await standalone.locator('.modal').screenshot({path:'/tmp/nai68-stats.png'});
  // Overlay requests .69. Standalone defers while statistics/settings modal is open.
  await context.request.post('http://127.0.0.1:8765/test/advance',{data:{version:'2.8.69'}});
  await overlay.getByRole('button',{name:'Check updates',exact:true}).click();
  await overlay.locator('#naiUpdateStatus').getByText(/v2.8.69 ready/).waitFor();
  await overlay.getByRole('button',{name:'Update both',exact:true}).click();await ready(overlay,'2.8.69');
  await standalone.locator('#naiUpdateStatus').getByText(/Close the editor to update/).waitFor();
  assert.equal(await standalone.evaluate(()=>document.documentElement.dataset.naiMediaPayloadVersion),'2.8.68');
  await standalone.locator('.modal [data-close]').click();await ready(standalone,'2.8.69');
  await overlay.getByText('Local library connected',{exact:true}).waitFor();
  // Standalone requests .70. Edited NovelAI text must survive the remote update.
  await overlay.locator('#story').fill('Unfinished story text');
  await context.request.post('http://127.0.0.1:8765/test/advance',{data:{version:'2.8.70'}});
  await standalone.getByRole('button',{name:'Check updates',exact:true}).click();
  await standalone.locator('#naiUpdateStatus').getByText(/v2.8.70 ready/).waitFor();
  await standalone.getByRole('button',{name:'Update both',exact:true}).click();await ready(standalone,'2.8.70');
  await overlay.locator('#naiUpdateStatus').getByText(/Story edited/).waitFor();assert.equal(await overlay.locator('#story').inputValue(),'Unfinished story text');
  await overlay.getByRole('button',{name:'Update both',exact:true}).click();await ready(overlay,'2.8.70');
  assert.deepEqual(errors,[]);
  console.log('PASS: real statistics/settings/scan UI; both update directions; modal and story protection; verified loader cache applied.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
