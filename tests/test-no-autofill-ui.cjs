// Autofill suppression must cover dynamic dialogs and stay inside the library.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:'2.9.7'}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{const text=b.toString();if(text.includes('ready'))resolve(JSON.parse(text));});server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 for(const standalone of [true,false]){
  const page=await context.newPage(),errors=[];page.setDefaultTimeout(15000);console.log('Checking',standalone?'standalone':'overlay');page.on('pageerror',e=>errors.push(e.message));
  if(!standalone){
   await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body><input id=novelaiField autocomplete=on>Fixture</body>'}));
   await page.exposeFunction('companionRequest',async o=>{const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
   await page.addInitScript(({payload,version})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
   },{payload,version:config.version});
  }
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');await page.getByText('Local library connected',{exact:true}).waitFor();
  if(standalone){await page.locator('#naiSetsCat').click();await page.locator('#naiCreateSet').click();assert.equal(await page.locator('#naiSetNameInput').getAttribute('autocomplete'),'off')}else{await page.evaluate(()=>{const form=document.createElement('form');form.innerHTML='<input id=autofillDynamicProbe autocomplete=on><textarea></textarea>';document.getElementById('nai-media-host').shadowRoot.append(form)});assert.equal(await page.locator('#autofillDynamicProbe').getAttribute('autocomplete'),'off')}
  const counts=await page.evaluate(()=>{const root=document.getElementById('nai-media-host').shadowRoot;return root.querySelectorAll('input:not([autocomplete="off"]),textarea:not([autocomplete="off"])').length});
  assert.equal(counts,0);
  if(!standalone)assert.equal(await page.locator('#novelaiField').getAttribute('autocomplete'),'on');
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Autofill checks passed for dynamic fields in standalone and NovelAI overlay; host page inputs untouched.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
