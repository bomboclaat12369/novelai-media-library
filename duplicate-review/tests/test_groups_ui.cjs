const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process'),readline=require('readline'),assert=require('assert'),fs=require('fs'),path=require('path');
(async()=>{
 const child=spawn('python',['tests/serve_groups.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 const lines=readline.createInterface({input:child.stdout});const f=await new Promise(resolve=>lines.once('line',l=>resolve(JSON.parse(l))));
 const browser=await chromium.launch({executablePath:'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
 const page=await browser.newPage({viewport:{width:1600,height:1050}});const errors=[];let previews=0;page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/api/preview'))previews++});
 await page.goto(f.url);await page.fill('#incoming',f.incoming);await page.click('#scan');
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='Scan complete'&&document.querySelectorAll('#grid .card').length===4);
 assert.equal(await page.textContent('#groupCount'),'2');assert((await page.textContent('#groupTitle')).startsWith('4 copies'));assert((await page.locator('#grid .card').first().textContent()).includes('2025-08-03'));
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('#grid img')).every(i=>i.complete&&i.naturalWidth>0));
 const oldPreviews=previews;
 await page.click('#autoPixels');await page.waitForFunction(()=>document.querySelector('#selectionCount').textContent==='3 selected to move');
 assert.equal(await page.locator('#grid input:checked').count(),2);assert(!(await page.locator('#grid .card').first().locator('input').isChecked()));
 assert.equal(previews,oldPreviews,'Auto-select must not reload previews');
 await page.screenshot({path:'/tmp/duplicate-groups-ui.png',fullPage:true});
 await page.click('#moveSelected');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='3'&&!document.querySelector('#undo').disabled);
 assert.equal(await page.locator('dialog[open]').count(),0,'No movement confirmation popup');
 assert(fs.existsSync(path.join(f.new,'newest.png')));assert(!fs.existsSync(path.join(f.old,'older.png')));assert(fs.existsSync(path.join(f.old,'smaller.jpg')));
 await page.click('#undo');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0'&&document.querySelectorAll('#grid .card').length===4);
 await page.selectOption('#sort','fewest');await page.waitForFunction(()=>document.querySelectorAll('#grid .card').length===2);
 await page.selectOption('#sort','most');await page.waitForFunction(()=>document.querySelectorAll('#grid .card').length===4);
 await page.click('#compare');await page.waitForFunction(()=>document.querySelector('#leftImage').naturalWidth>0);await page.selectOption('#zoom','150');assert(await page.locator('#leftArea').evaluate(e=>e.classList.contains('zoomed')));await page.click('#closeCompare');
 await page.locator('#grid .card').first().getByRole('button',{name:'Keep only this'}).click();
 await page.waitForFunction(()=>document.querySelector('#moved').textContent==='3'&&!document.querySelector('#undo').disabled);assert.equal(await page.locator('dialog[open]').count(),0);
 await page.click('#undo');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0'&&document.querySelectorAll('#grid .card').length===4);
 await page.click('#keepGroup');await page.waitForFunction(()=>document.querySelector('#groupCount').textContent==='1');assert.equal(await page.locator('dialog[open]').count(),0);
 assert.equal(errors.length,0,JSON.stringify(errors));console.log('Groups UI passed: grouping, count sorting, automatic selection, newest keeper, no reload on selection, popup-free keep/move, batch undo, large comparison.');
 }finally{await browser.close();child.kill();lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
