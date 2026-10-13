const { chromium }=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process');
const readline=require('readline');
const assert=require('assert');
const path=require('path');
(async()=>{
 const child=spawn('python',['tests/serve_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 const lines=readline.createInterface({input:child.stdout});
 const fixture=await new Promise((resolve,reject)=>{lines.once('line',l=>resolve(JSON.parse(l)));child.once('exit',code=>reject(Error('Fixture exited '+code)))});
 const browser=await chromium.launch({executablePath:'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1050}});let errors=[];let external=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(!r.url().startsWith(fixture.url)&&!r.url().startsWith('data:'))external.push(r.url())});
 await page.goto(fixture.url);
 await page.fill('#incoming',fixture.incoming);await page.fill('#reference',fixture.reference);
 await page.click('#scan');
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='Scan complete');
 await page.waitForFunction(()=>document.querySelector('#leftImage').naturalWidth>0&&document.querySelector('#rightImage').naturalWidth>0);
 assert.equal(await page.textContent('#files'),'5');
 assert(await page.locator('#moveLeft').isDisabled(),'Reference move must be disabled');
 assert(!(await page.locator('#moveRight').isDisabled()));
 await page.screenshot({path:'/tmp/duplicate-review-ui.png',fullPage:true});
 // Confirming is required; cancel leaves the file and count intact.
 const before=Number(await page.textContent('#pairs'));
 await page.click('#moveRight');await page.click('#dialogNo');
 assert.equal(Number(await page.textContent('#pairs')),before);
 await page.click('#moveRight');await page.click('#dialogYes');
 await page.waitForFunction(()=>document.querySelector('#moved').textContent==='1');
 await page.click('#undo');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0');
 // Dismiss, reopen the page, then restore dismissed decisions.
 await page.click('#keep');
 await page.waitForFunction(n=>Number(document.querySelector('#pairs').textContent)<n,before);
 const after=Number(await page.textContent('#pairs'));
 await page.reload();await page.waitForFunction(n=>Number(document.querySelector('#pairs').textContent)===n,after);
 await page.click('#reset');await page.click('#dialogYes');
 await page.click('#scan');await page.waitForFunction(()=>document.querySelector('#status').textContent==='Scan complete');
 await page.waitForFunction(n=>Number(document.querySelector('#pairs').textContent)===n,before);
 await page.selectOption('#filter','visual');
 await page.waitForFunction(()=>document.querySelector('#matchType').textContent.startsWith('Visual'));
 await page.waitForFunction(()=>document.querySelector('#leftImage').naturalWidth>0&&document.querySelector('#rightImage').naturalWidth>0);
 await page.selectOption('#zoom','150');
 assert(await page.locator('#leftArea').evaluate(e=>e.classList.contains('zoomed')));
 await page.selectOption('#zoom','fit');
 await page.click('#history');await page.waitForFunction(()=>document.querySelector('#dialog').open&&document.querySelector('#dialogTitle').textContent==='Move history');assert((await page.textContent('#dialogBody')).includes('restored'));await page.click('#dialogNo');
 assert.equal(errors.length,0,JSON.stringify(errors));assert.equal(external.length,0,JSON.stringify(external));
 const noToken=await page.request.get(fixture.url+'api/state');assert.equal(noToken.status(),403);
 const origin=await page.request.get(fixture.url,{headers:{Origin:'https://malicious.example'}});assert.equal(origin.status(),403);
 const host=await page.request.get(fixture.url,{headers:{Host:'other.example'}});assert.equal(host.status(),403);
 console.log(JSON.stringify({ui:'passed',images:5,matches:before,referenceProtection:true,moveUndo:true,dismissPersistence:true,externalRequests:external.length,scriptErrors:errors.length}));
 }finally{await browser.close();child.kill();lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
