const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process'),readline=require('readline'),assert=require('assert/strict'),fs=require('fs'),path=require('path');
(async()=>{
 const child=spawn('python',['tests/serve_groups.py','--visual'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 const lines=readline.createInterface({input:child.stdout});let browser;
 try{
  const f=await new Promise((resolve,reject)=>{lines.once('line',l=>resolve(JSON.parse(l)));child.once('exit',c=>reject(Error('Fixture exited: '+c)));});
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:1600,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(f.url);await page.fill('#incoming',f.incoming);await page.selectOption('#mode','broad');await page.click('#scan');
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Scan complete'&&document.querySelectorAll('#grid .card').length);
  await page.getByRole('button',{name:'Quarantine verified visual copies',exact:true}).click();
  await page.waitForFunction(()=>Number(document.querySelector('#moved').textContent)===1&&!document.querySelector('#undo').disabled);
  assert.equal(await page.locator('dialog[open]').count(),0);
  assert(fs.existsSync(path.join(f.new,'newest.png')),'Leftmost equal-MP keeper survives');
  assert(fs.existsSync(path.join(f.new,'different.jpg')),'Other photograph retains its own keeper');
  assert(fs.existsSync(path.join(f.old,'exact.png')));assert(fs.existsSync(path.join(f.old,'older.png')));assert(!fs.existsSync(path.join(f.old,'smaller.jpg')));
  await page.click('#undo');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0'&&document.querySelector('#groupCount').textContent==='2');
  for(const file of ['older.png','exact.png','smaller.jpg','different-copy.jpg'])assert(fs.existsSync(path.join(f.old,file)));
  assert.deepEqual(errors,[]);console.log('PASS: one-click auto quarantine through real HTTP, keeper order, distinct photographs retained, full batch Undo.');
  fs.rmSync(f.base,{recursive:true,force:true});
 }finally{if(browser)await browser.close();child.kill();lines.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
