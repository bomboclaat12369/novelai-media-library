const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_organizer.py','--collections'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1800,height:1100}}),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')requests.push(new URL(r.url()).pathname)});page.setDefaultTimeout(15000);
 await page.goto(info.url);await page.waitForFunction(()=>data&&view);
 assert.deepEqual(await page.locator('#collectionPicker option').allTextContents(),['Alice','Mikayla']);
 await page.locator('#setsTab').click();await page.locator('#postList .post').filter({hasText:'Mikayla Shoot'}).click();await page.waitForFunction(()=>!busy&&currentKind==='set');
 assert(await page.locator('#setInstagram').isVisible());
 const card=page.locator('#grid .card').first();await card.locator('[data-pick]').click();await page.locator('#setName').fill('Unfinished Mikayla');
 await page.waitForFunction(()=>document.querySelectorAll('#suggestions .card').length>3);
 const measures=()=>page.locator('.suggest-grid').first().evaluate(g=>({columns:getComputedStyle(g).gridTemplateColumns.split(' ').length,width:g.querySelector('.card').getBoundingClientRect().width,height:g.querySelector('img').getBoundingClientRect().height}));
 const before=await measures();const handle=await page.locator('#sidebarResize').boundingBox();
 await page.mouse.move(handle.x+handle.width/2,handle.y+100);await page.mouse.down();await page.mouse.move(handle.x-400,handle.y+100,{steps:15});await page.mouse.up();
 const after=await measures();assert(after.columns>before.columns);assert(await page.locator('.basket').evaluate(e=>e.scrollWidth<=e.clientWidth));assert.equal(after.width,before.width);assert.equal(after.height,before.height);
 await page.screenshot({path:'/tmp/organizer-collections-wide.png',fullPage:true});
 await page.locator('#collectionPicker').selectOption('alice-job');await page.waitForFunction(()=>data?.job==='alice-job'&&view);
 assert(!await page.locator('#postList').textContent().then(s=>s.includes('Mikayla Shoot')));
 await page.locator('#postList .post').filter({hasText:'Alice Shoot'}).click();await page.waitForFunction(()=>!busy&&currentKind==='set');
 assert(!await page.locator('#setInstagram').isVisible());assert.equal(await page.locator('#setName').inputValue(),'');
 await page.locator('#grid [data-pick]').first().click();await page.locator('#setName').fill('Unfinished Alice');
 await page.locator('#collectionPicker').selectOption('fixture-job');await page.waitForFunction(()=>data?.job==='fixture-job'&&view);
 assert.equal(await page.locator('#setName').inputValue(),'Unfinished Mikayla');assert.equal(await page.evaluate(()=>selection.size),1);assert.match(await page.locator('#title').textContent(),/Mikayla Shoot/);
 assert(await page.locator('#setInstagram').isVisible());await page.reload();await page.waitForFunction(()=>data?.job==='fixture-job'&&view);
 assert.equal(await page.locator('#setName').inputValue(),'Unfinished Mikayla');
 await page.locator('#collectionPicker').selectOption('alice-job');await page.waitForFunction(()=>data?.job==='alice-job'&&view);
 assert.equal(await page.locator('#setName').inputValue(),'Unfinished Alice');assert.equal(await page.evaluate(()=>selection.size),1);
 assert(!requests.some(p=>/\/api\/(scan|history\/inventory|bulk\/start|selection\/move|organizer\/index)/.test(p)));assert.deepEqual(errors,[]);
 console.log('Collections UI passed: named switching, saved drafts/views/selections, reload, Instagram tags, fixed thumbnail dimensions with more columns; no scans or analysis.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
