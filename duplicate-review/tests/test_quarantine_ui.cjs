const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process'),readline=require('readline'),assert=require('assert'),fs=require('fs'),path=require('path');
(async()=>{
 const child=spawn('python',['tests/serve_groups.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 const lines=readline.createInterface({input:child.stdout});
 let browser;
 try{
 const f=await new Promise(resolve=>lines.once('line',l=>resolve(JSON.parse(l))));
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1600,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(f.url);await page.fill('#incoming',f.incoming);await page.click('#scan');
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='Scan complete'&&document.querySelectorAll('#grid .card').length===4);
 await page.locator('#grid .card').first().getByRole('button',{name:'Keep',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#finishGroup').textContent.includes('keep 1'));
 await page.getByRole('button',{name:'Quarantine all incoming',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#moved').textContent==='4'&&!document.querySelector('#undo').disabled&&document.querySelector('#groupCount').textContent==='1');
 assert.equal(await page.locator('dialog[open]').count(),0);
 for(const p of [path.join(f.old,'older.png'),path.join(f.old,'exact.png'),path.join(f.old,'smaller.jpg'),path.join(f.new,'newest.png')])assert(!fs.existsSync(p));
 assert(fs.existsSync(path.join(f.new,'different.jpg')),'Other groups stay untouched');
 await page.click('#undo');
 await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0'&&document.querySelector('#groupCount').textContent==='2');
 for(const p of [path.join(f.old,'older.png'),path.join(f.old,'exact.png'),path.join(f.old,'smaller.jpg'),path.join(f.new,'newest.png')])assert(fs.existsSync(p));
 assert.deepEqual(errors,[]);
 console.log('Quarantine group UI passed: moves all four incoming copies including Keep, leaves other group intact, batch Undo restores all.');
 }finally{if(browser)await browser.close();child.kill();lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
