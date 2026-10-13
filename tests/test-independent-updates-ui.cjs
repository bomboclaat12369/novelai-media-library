// Two browser origins using the real local companion. Verify both update directions.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const baseVersion=config.version,parts=baseVersion.split('.').map(Number),nextVersion=[parts[0],parts[1],parts[2]+1].join('.'),lastVersion=[parts[0],parts[1],parts[2]+2].join('.');
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_efficiency_fixture.py'],{cwd:dir});let stderr='';server.stderr.on('data',b=>stderr+=b);
 let browser;
 try{
  await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{if(b.toString().includes('READY'))resolve();});server.on('exit',code=>reject(Error('Fixture failed '+code+' '+stderr)));});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
  const context=await browser.newContext({viewport:{width:1600,height:1000}}),errors=[];
  const overlay=await context.newPage();overlay.on('pageerror',e=>errors.push(e.message));overlay.on('dialog',d=>d.accept());
  await overlay.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body><textarea id="story"></textarea></body>'}));
  await overlay.exposeFunction('companionRequest',async o=>{const url=o.url.startsWith('https://raw.githubusercontent.com/')?'http://127.0.0.1:8765/test/release/'+o.url.split('/main/')[1]:o.url;const r=await fetch(url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
  await overlay.addInitScript(({payload,baseVersion})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=localStorage.getItem('nai-media-github-payload-version')||baseVersion;eval(localStorage.getItem('nai-media-github-payload')||payload);});
  },{payload,baseVersion});
  await overlay.goto('https://novelai.net/stories');await overlay.getByText('Local library connected',{exact:true}).waitFor();
  const standalone=await context.newPage();standalone.on('pageerror',e=>errors.push(e.message));standalone.on('dialog',d=>d.accept());
  await standalone.goto('http://127.0.0.1:8765/library/');await standalone.getByText('Local library connected',{exact:true}).waitFor();
  const ready=async(page,version)=>page.waitForFunction(v=>document.documentElement.dataset.naiMediaPayloadVersion===v,version);
  const requests=[];context.on('request',r=>requests.push(r.url()));
  await overlay.locator('#story').fill('Unfinished story text');
  await context.request.post('http://127.0.0.1:8765/test/advance',{data:{version:nextVersion}});
  await standalone.getByRole('button',{name:'Check updates',exact:true}).click();
  await standalone.locator('#naiUpdateStatus').getByText(new RegExp('v'+nextVersion+' available')).waitFor();
  await standalone.getByRole('button',{name:'Update',exact:true}).click();await ready(standalone,nextVersion);
  assert.equal(await overlay.locator('#story').inputValue(),'Unfinished story text');
  assert.equal(await overlay.evaluate(()=>document.documentElement.dataset.naiMediaPayloadVersion),baseVersion);
  await overlay.locator('#refreshBtn').click();
  await overlay.locator('#naiUpdateStatus').getByText(new RegExp('v'+nextVersion+' available')).waitFor();
  await overlay.getByRole('button',{name:'Update',exact:true}).click();await ready(overlay,nextVersion);
  await context.request.post('http://127.0.0.1:8765/test/advance',{data:{version:lastVersion}});
  await overlay.getByRole('button',{name:'Check updates',exact:true}).click();
  await overlay.locator('#naiUpdateStatus').getByText(new RegExp('v'+lastVersion+' available')).waitFor();
  await overlay.getByRole('button',{name:'Update',exact:true}).click();await ready(overlay,lastVersion);
  assert.equal(await standalone.evaluate(()=>document.documentElement.dataset.naiMediaPayloadVersion),nextVersion);
  assert(!requests.some(url=>url.includes('/api/ui-update/')));
  assert.deepEqual(errors,[]);
  console.log('PASS: both interfaces apply verified cached updates with one click; library Refresh detects updates; tabs update independently and preserve other-tab edits.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
