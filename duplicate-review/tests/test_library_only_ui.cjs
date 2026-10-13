const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process'),readline=require('readline'),assert=require('assert/strict'),path=require('path');
(async()=>{
 const child=spawn('python3',['tests/serve_library_only_ui.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 let browser;
 try{
 const lines=readline.createInterface({input:child.stdout});const f=await new Promise((resolve,reject)=>{lines.once('line',l=>resolve(JSON.parse(l)));child.once('exit',c=>reject(Error('Fixture exited '+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1660,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(f.url);
 await page.waitForFunction(()=>!document.querySelector('#scan').disabled&&document.querySelector('#libraryStatus').textContent.includes('Connected'));
 await page.selectOption('#scanKind','library');assert.equal(await page.locator('#incomingSection').isVisible(),false);
 await page.selectOption('#libraryCharacter','*');await page.click('#scan');
 await page.waitForFunction(()=>document.querySelectorAll('#grid .card').length===3&&!document.querySelector('#scan').disabled);
 assert.equal(await page.locator('#autoToolbar').isVisible(),false);
 assert.match(await page.locator('#coverage').textContent(),/3 \/ 3 library files/);
 const keeper=page.locator('#grid .card').filter({has:page.locator('h3',{hasText:/^full.png$/})});
 await keeper.getByRole('button',{name:'Keep',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#finishGroup').textContent.includes('keep 1, remove 2')&&!document.querySelector('#scan').disabled);
 await page.screenshot({path:'/tmp/library-duplicate-mode.png',fullPage:true});
 await page.click('#finishGroup');
 await page.waitForFunction(()=>document.querySelector('#moved').textContent==='2'&&!document.querySelector('#scan').disabled);
 assert.equal(await page.locator('#grid .card').count(),0);
 await page.click('#undo');
 await page.waitForFunction(()=>document.querySelectorAll('#grid .card').length===3&&!document.querySelector('#scan').disabled);
 assert.equal(await page.locator('#moved').textContent(),'0');assert.deepEqual(errors,[]);
 console.log('PASS: library-only mode, no folder requirement, all-character coverage, explicit keep/remove, and Undo through the browser.');
 }finally{if(browser)await browser.close();child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
