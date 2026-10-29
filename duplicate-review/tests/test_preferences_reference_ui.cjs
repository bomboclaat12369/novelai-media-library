const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_organizer.py'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}}),page=await context.newPage(),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(new URL(r.url()).pathname));page.setDefaultTimeout(15000);
 await page.route('**/api/library',r=>r.fulfill({json:{library_id:'fixture',characters:[{id:'alice',name:'Alice'},{id:'bob',name:'Bob'}]}}));
 const base=info.url.replace('/organizer','');await page.goto(base);await page.waitForFunction(()=>preferencesReady);
 await page.locator('#connectLibrary').click();await page.locator('#libraryCharacter option[value="alice"]').waitFor({state:'attached'});
 await page.locator('#incoming').fill('C:\\New images\nD:\\Another folder');await page.locator('#reference').fill('D:\\Reference');await page.locator('#libraryCharacter').selectOption('alice');
 await page.reload();await page.waitForFunction(()=>preferencesReady&&libraryConnection);
 assert.equal(await page.locator('#incoming').inputValue(),'C:\\New images\nD:\\Another folder');assert.equal(await page.locator('#reference').inputValue(),'D:\\Reference');assert.equal(await page.locator('#libraryCharacter').inputValue(),'alice');
 await page.locator('#incoming').fill('');await page.locator('#libraryCharacter').selectOption('');await page.goto(info.url);await page.waitForFunction(()=>data?.images===18&&view);
 assert.equal(await page.locator('input:not([autocomplete="off"]),textarea:not([autocomplete="off"])').count(),0);
 const first=info.ids[2];await page.locator(`#grid .card[data-id="${first}"] [data-pick]`).click();await page.locator('#target').selectOption('library:existing');await page.waitForFunction(()=>!busy);
 await page.locator(`#grid [data-reference="${first}"]`).click();await page.waitForFunction(()=>!busy&&referenceImage?.analyzed);
 assert.equal(await page.locator('#referencePanel').isVisible(),true);assert.equal(await page.evaluate(()=>selection.size),1);assert.equal(await page.locator('#target').inputValue(),'library:existing');
 assert.match(await page.locator('#referenceStatus').textContent(),/Only this image/);
 await page.reload();await page.waitForFunction(()=>view&&referenceImage?.analyzed);assert.equal(await page.evaluate(()=>suggestionReference),first);assert.equal(await page.evaluate(()=>selection.size),1);
 await page.locator('#clearReference').click();await page.waitForFunction(()=>!busy&&!suggestionReference);assert.equal(await page.locator('#referencePanel').isVisible(),false);
 await page.locator(`#grid .card[data-id="${first}"] img`).click();await page.locator('#viewerReference').click();await page.waitForFunction(()=>!busy&&suggestionReference);await page.locator('#viewerClose').click();
 await page.screenshot({path:'/tmp/organizer-reference.png'});
 await page.goto(base);await page.waitForFunction(()=>preferencesReady);assert.equal(await page.locator('#incoming').inputValue(),'');assert.equal(await page.locator('#libraryCharacter').inputValue(),'');assert.equal(await page.locator('#reference').inputValue(),'D:\\Reference');
 // A fresh browser context has no localStorage; preferences must come from SQLite.
 const fresh=await browser.newPage();await fresh.goto(base);await fresh.waitForFunction(()=>preferencesReady);assert.equal(await fresh.locator('#reference').inputValue(),'D:\\Reference');assert.equal(await fresh.locator('#incoming').inputValue(),'');
 assert.equal(await fresh.locator('input:not([autocomplete="off"]),textarea:not([autocomplete="off"])').count(),0);
 assert(!requests.includes('/api/scan'));assert.deepEqual(errors,[]);console.log('Preferences and reference UI passed: instant reload, empty choices, navigation, fresh session, pin/clear/viewer, retained selection and autofill suppression; no scan.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
