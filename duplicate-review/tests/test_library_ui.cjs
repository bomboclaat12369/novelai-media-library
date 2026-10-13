const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process'),readline=require('readline'),assert=require('assert'),path=require('path'),fs=require('fs');
(async()=>{
 const child=spawn('python3',['tests/serve_library_ui.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 const lines=readline.createInterface({input:child.stdout});const f=await new Promise(resolve=>lines.once('line',l=>resolve(JSON.parse(l))));
 const browser=await chromium.launch({executablePath:'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
 const page=await browser.newPage({viewport:{width:1660,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(f.url);
 await page.waitForFunction(()=>document.querySelectorAll('#grid .card').length===4&&!document.querySelector('#scan').disabled);
 assert((await page.textContent('#libraryStatus')).includes('Connected'));
 assert.equal(await page.inputValue('#libraryCharacter'),f.character);
 const imported=page.locator('#grid .card').filter({hasText:'In library'});assert((await imported.textContent()).includes('Blue Dress'));
 assert((await page.textContent('#finishGroup')).includes('keep 1, move 3'));
 // Select the different pose and its exact copy in one action.
 const different=page.locator('#grid .card').filter({has:page.locator('h3',{hasText:/^different.png$/})});
 await different.getByRole('button',{name:'Different image',exact:true}).click();
 assert.equal(await page.locator('#splitGrid input:checked').count(),2);
 await page.click('#applySplit');await page.waitForFunction(()=>document.querySelector('#groupCount').textContent==='2'&&!document.querySelector('#scan').disabled);
 assert.equal(await page.locator('#grid .card').count(),2);
 const better=page.locator('#grid .card').filter({has:page.locator('h3',{hasText:/^better.png$/})});
 await better.getByRole('button',{name:'Replace library copy',exact:true}).click();
 assert.equal(await page.locator('#replaceGrid input:checked').count(),1);
 assert((await page.textContent('#replaceGrid')).includes('Blue Dress'));
 await page.screenshot({path:'/tmp/duplicate-review-140-replace.png',fullPage:true});
 await page.click('#applyReplace');await page.waitForFunction(()=>!document.querySelector('#replaceDialog').open&&document.querySelector('#moved').textContent==='1'&&!document.querySelector('#scan').disabled);
 assert(!fs.existsSync(path.join(f.incoming,'better.png')));
 await page.click('#undo');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0'&&!document.querySelector('#scan').disabled);
 assert(fs.existsSync(path.join(f.incoming,'better.png')));
 // The marked new pose stays while its extra copy is quarantined.
 const list=page.locator('#groupList button');const texts=await list.allTextContents();const index=texts.findIndex(t=>t.includes('different'));
 await list.nth(index).click();await page.waitForFunction(()=>[...document.querySelectorAll('#grid h3')].every(e=>e.textContent.includes('different'))&&!document.querySelector('#scan').disabled);
 const cards=page.locator('#grid .card');await cards.first().getByRole('button',{name:'Keep',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#finishGroup').textContent.includes('keep 1, move 1')&&!document.querySelector('#finishGroup').disabled);
 await page.screenshot({path:'/tmp/duplicate-review-140-groups.png',fullPage:true});
 await page.click('#finishGroup');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='1'&&!document.querySelector('#scan').disabled);
 assert.equal([fs.existsSync(path.join(f.incoming,'different.png')),fs.existsSync(path.join(f.incoming,'different-copy.png'))].filter(Boolean).length,1);
 assert.equal(errors.length,0,JSON.stringify(errors));console.log('Library UI passed: connection, live Set labels, split two-copy pose, targeted replacement, quarantine, undo, Keep and Finish group.');
 }finally{await browser.close();child.kill();lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
