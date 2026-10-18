const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process'),readline=require('readline'),assert=require('assert'),path=require('path'),fs=require('fs');
(async()=>{
 const child=spawn('python',['tests/serve_groups.py','--visual'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 const lines=readline.createInterface({input:child.stdout});let browser;
 try{
  const f=await new Promise(resolve=>lines.once('line',l=>resolve(JSON.parse(l))));
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||undefined,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:1600,height:1050}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(f.url);await page.fill('#incoming',f.incoming);await page.click('#scan');
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Scan complete'&&document.querySelectorAll('#grid .card').length===4);
  await page.click('#previewVerified');await page.waitForFunction(()=>document.querySelector('#verifiedDialog').open);
  const plan=await page.evaluate(()=>verifiedPreview),count=plan.moves.length;
  assert.equal(count,1);assert(plan.moves.every(m=>m.proof==='same_photo'));assert.equal(await page.textContent('#moved'),'0');
  for(const m of plan.moves){assert(fs.existsSync(m.target.path));assert(fs.existsSync(m.keeper.path))}
  assert((await page.locator('#verifiedKeeperImage').getAttribute('src')).includes('id='+plan.moves[0].keeper.id+'&'));
  assert((await page.locator('#verifiedTargetImage').getAttribute('src')).includes('id='+plan.moves[0].target.id+'&'));
  await page.click('#verifiedNone');assert(await page.locator('#applyVerified').isDisabled());
  await page.click('#verifiedAll');await page.uncheck('#verifiedInclude');
  assert(await page.locator('#verifiedNext').isDisabled());assert(await page.locator('#verifiedPrev').isDisabled());
  await page.selectOption('#verifiedZoom','100');await page.selectOption('#verifiedZoom','fit');
  await page.screenshot({path:'/tmp/verified-preview.png'});
  await page.click('#closeVerified');assert.equal(await page.textContent('#moved'),'0');
  assert(await page.locator('#review').isVisible());
  await page.click('#viewVerified');assert(!(await page.locator('#verifiedInclude').isChecked()));
  await page.check('#verifiedInclude');
  await page.click('#applyVerified');assert(await page.locator('#dialog').evaluate(e=>e.open));
  assert.equal(await page.textContent('#moved'),'0');await page.click('#dialogYes');
  await page.waitForFunction(n=>document.querySelector('#moved').textContent===String(n)&&!document.querySelector('#undo').disabled,count);
  assert(!fs.existsSync(plan.moves[0].target.path));
  for(const file of ['older.png','exact.png','different-copy.jpg'])assert(fs.existsSync(path.join(f.old,file)));
  for(const m of plan.moves){assert(fs.existsSync(m.keeper.path))}
  await page.click('#undo');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0');
  for(const m of plan.moves)assert(fs.existsSync(m.target.path));
  assert.deepEqual(errors,[]);console.log('Preview UI passed: no initial moves, correct pair IDs, exclusions/navigation/close/reopen, explicit approval subset, keepers retained and Undo.');
 }finally{if(browser)await browser.close();child.kill();lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
