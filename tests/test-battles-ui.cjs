const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,'release-userscript.json'))),payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{cwd:dir});let stderr='',browser;server.stderr.on('data',b=>stderr+=b);
 try{
 await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});context.setDefaultTimeout(15000);
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 const lib=await api('library'),owner=lib.characters[0].id,main=new Set(lib.media.filter(m=>m.in_all).map(m=>m.id));
 const state=kind=>api('battles/state',{character_id:owner,kind});
 for(const standalone of [true,false]){
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  if(!standalone){
   await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
   await page.exposeFunction('companionRequest',async o=>{const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
   await page.addInitScript(({payload,version})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
   },{payload,version:config.version});
  }
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');
  await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiBattlesBtn').click();
  await page.getByLabel('Mode',{exact:true}).selectOption('winner');await page.getByLabel('Round',{exact:true}).selectOption('10');await page.locator('#naiBattleStart').click();
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].length===2&&[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled));
  const ids=await page.locator('.naiBattleCard').evaluateAll(cards=>cards.map(c=>c.dataset.entryId));assert(ids.every(id=>main.has(id)));
  const before=await state('images');assert.equal(before.entries.length,4);
  await page.locator('.naiBattleChoose').first().click();await page.waitForFunction(n=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.includes(n+' saved votes'),before.votes+1);
  const after=await state('images');assert.equal(after.votes,before.votes+1);assert([after.session.pair.left,after.session.pair.right].includes(ids[0]));
  await page.locator('#naiBattleUndo').click();await page.waitForFunction(n=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.includes(n+' saved votes'),before.votes);
  await page.getByRole('button',{name:'Close',exact:true}).click();await page.locator('#naiBattlesBtn').click();await page.locator('.naiBattleCard').first().waitFor();
  assert.deepEqual((await state('images')).session.pair,before.session.pair);
  await page.getByLabel('Battle type',{exact:true}).selectOption('sets');await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.startsWith('2 eligible sets'));
  await page.getByLabel('Minimum set images',{exact:true}).fill('5');await page.getByLabel('Similar-size opponents',{exact:true}).check();await page.locator('#naiBattleStart').click();
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].length===2&&[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled));
  assert.equal(await page.locator('.naiBattleSamples button').count(),8);assert.equal(await page.getByRole('heading',{name:'Small set',exact:true}).count(),0);
  await page.locator('.naiBattleCard').first().getByRole('button',{name:'→',exact:true}).click();
  await page.locator('.naiBattleCard').first().getByRole('button',{name:'View full image',exact:true}).click();await page.locator('.naiBattleLight').waitFor();await page.getByRole('button',{name:'Close image',exact:true}).click();
  if(standalone)await page.screenshot({path:'/tmp/battles-sets.png'});
  const setBefore=await state('sets');await page.locator('.naiBattleChoose').last().click();await page.waitForFunction(n=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.includes(n+' saved votes'),setBefore.votes+1);
  await page.locator('#naiBattleLeaderboard').click();assert.equal(await page.locator('.naiBattleRow').count(),3);assert((await page.locator('.naiBattleBoard').textContent()).includes('Provisional'));
  assert.equal((await state('images')).votes,before.votes);await page.locator('#naiBattleUndo').click();
  await page.getByRole('button',{name:'Close',exact:true}).click();assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Battles UI passed in standalone and NovelAI: Main-only images, Winner Stays, resume, undo, set minimum, equal samples, browsing and separate leaderboards.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
