const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process'),readline=require('readline'),assert=require('assert'),fs=require('fs'),path=require('path');
(async()=>{
 const child=spawn('python',['tests/serve_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 const lines=readline.createInterface({input:child.stdout});
 const f=await new Promise(resolve=>lines.once('line',l=>resolve(JSON.parse(l))));
 fs.copyFileSync(path.join(f.incoming,'Forum copy.jpg'),path.join(f.incoming,'Another copy.jpg'));
 const browser=await chromium.launch({executablePath:'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(f.url);await page.fill('#incoming',f.incoming);await page.fill('#reference',f.reference);await page.click('#scan');
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='Scan complete');
 await page.click('#exactBulk');await page.waitForFunction(()=>document.querySelector('#dialog').open);
 assert.equal(await page.textContent('#dialogTitle'),'Move 2 exact duplicates?');
 assert((await page.textContent('#dialogBody')).includes('KEEP: '+path.join(f.reference,'Original portrait.jpg')));
 await page.click('#dialogNo');assert(fs.existsSync(path.join(f.incoming,'Forum copy.jpg')));
 await page.click('#exactBulk');await page.waitForFunction(()=>document.querySelector('#dialog').open);await page.click('#dialogYes');
 await page.waitForFunction(()=>document.querySelector('#moved').textContent==='2'&&!document.querySelector('#undo').disabled);
 assert(!fs.existsSync(path.join(f.incoming,'Forum copy.jpg')));assert(fs.existsSync(path.join(f.reference,'Original portrait.jpg')));assert(fs.existsSync(path.join(f.incoming,'Smaller download.jpg')));
 await page.click('#undo');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0'&&document.querySelector('#status').textContent.startsWith('Restored 2'));
 await page.reload();await page.waitForFunction(()=>document.querySelector('#files').textContent==='6');
 await page.selectOption('#exactScope','folder');await page.click('#exactBulk');await page.waitForFunction(()=>document.querySelector('#dialog').open);
 assert.equal(await page.textContent('#dialogTitle'),'Move 1 exact duplicates?');await page.click('#dialogNo');
 assert.equal(errors.length,0,JSON.stringify(errors));console.log('Bulk UI passed: preview, cancel, protected keeper, exact-only batch, whole-batch undo, folder scope.');
 }finally{await browser.close();child.kill();lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
