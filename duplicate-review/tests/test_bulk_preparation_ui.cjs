const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{const server=spawn('python3',['duplicate-review/tests/serve_bulk_fixture.py'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
try{
 const info=await new Promise((resolve,reject)=>{let output='';server.stdout.on('data',b=>{output+=b;if(output.includes('\n'))resolve(JSON.parse(output.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/bulk-chromium',headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});const page=await browser.newPage({viewport:{width:1600,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
 await page.goto(info.url+'/bulk');await page.locator('#phase').filter({hasText:'Ready'}).waitFor();await page.locator('#roots').fill(info.incoming);await page.locator('#start').click();await page.locator('#phase').filter({hasText:'Evaluation ready'}).waitFor();assert.equal(await page.locator('.group').count(),2);
 assert.equal(await page.request.get(info.url+'/api/bulk/export').then(r=>r.status()),403);
 assert.equal(await page.request.post(info.url+'/api/bulk/start',{data:{roots:[info.incoming]}}).then(r=>r.status()),403);
 await page.locator('.group').first().click();await page.waitForFunction(()=>document.querySelectorAll('#grid .tile').length===4);assert.equal(await page.locator('#grid .tile').count(),4);await page.locator('#grid img').first().waitFor();await page.waitForFunction(()=>[...document.querySelectorAll('#grid img')].every(im=>im.complete&&im.naturalWidth));
 assert.equal(await page.locator('#selected').textContent(),'4 selected');await page.locator('#grid img').first().click();assert(await page.locator('#light').isVisible());await page.getByRole('button',{name:'Close image',exact:true}).click();
 await page.locator('#grid .tile').first().getByRole('button',{name:'Details',exact:true}).click();assert(await page.locator('#evidence').innerText().then(t=>t.includes('Post 3672997')));await page.locator('#closeInspect').click();
 await page.locator('#setName').fill('Blue outfit');await page.locator('#colors').fill('blue, navy');assert(await page.locator('.footer').evaluate(e=>e.getBoundingClientRect().bottom<=innerHeight+1));await page.screenshot({path:'/tmp/bulk-review-pilot.png'});await page.locator('#accept').click();await page.waitForFunction(()=>document.querySelectorAll('.group').length===1);await page.waitForFunction(()=>document.querySelector('#selected').textContent==='4 selected');assert.equal(await page.locator('.group').count(),1);
 await page.locator('#none').click();assert(await page.locator('#accept').isDisabled());await page.locator('#grid input[type=checkbox]').nth(0).check();await page.locator('#grid input[type=checkbox]').nth(1).check();await page.locator('#split').click();await page.waitForFunction(()=>document.querySelectorAll('#grid .tile').length===2);assert.equal(await page.locator('.group').count(),2);await page.locator('#skip').click();await page.waitForFunction(()=>document.querySelectorAll('.group').length===1);
 await page.reload();await page.locator('#phase').filter({hasText:'Evaluation ready'}).waitFor();await page.locator('#filter').selectOption('accepted');assert.equal(await page.locator('.group').count(),1);await page.locator('.group').first().click();await page.waitForFunction(()=>document.querySelector('#setName').value==='Blue outfit');assert.equal(await page.locator('#setName').inputValue(),'Blue outfit');assert.equal(await page.locator('#colors').inputValue(),'blue, navy');
 const download=page.waitForEvent('download');await page.locator('#export').click();const file=await download;assert(file.suggestedFilename().startsWith('set-evaluation-'));const stream=await file.createReadStream();let text='';for await(const b of stream)text+=b;const report=JSON.parse(text);assert.equal(report.evaluation.accepted,1);assert.equal(report.evaluation.splits,1);assert.equal(report.inventory.files,79);assert.equal(report.inventory.unique_survivors,78);assert(report.notice.includes('No files were moved'));
 // Reproduce the crowded unassigned page: rows must keep image height and scroll.
 await page.locator('#unassigned').click();await page.waitForFunction(()=>document.querySelectorAll('#grid .tile').length===60);
 for(const size of [{width:1600,height:1050},{width:2560,height:1440},{width:1000,height:760}]){
  await page.setViewportSize(size);assert(await page.locator('#grid').evaluate(grid=>grid.scrollHeight>grid.clientHeight));
  assert(await page.locator('#grid .tile').first().evaluate(tile=>tile.clientHeight>=tile.querySelector('img').clientHeight+20));
  assert(await page.locator('.footer').evaluate(e=>e.getBoundingClientRect().bottom<=innerHeight+1));
 }
 await page.getByRole('button',{name:'Next page',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('#grid .tile').length===10);
 await page.waitForFunction(()=>[...document.querySelectorAll('#grid img')].slice(0,3).every(im=>im.complete&&im.naturalWidth));await page.screenshot({path:'/tmp/bulk-unassigned-fixed.png'});
 // A rerun uses the same cohort, preserves the original decisions, and starts a fresh review.
 const oldId=await page.locator('#jobs').inputValue();await page.locator('#reevaluate').click();
 await page.waitForFunction(old=>document.querySelector('#jobs').value!==old,oldId);
 await page.locator('#phase').filter({hasText:'Evaluation ready'}).waitFor();assert.equal(await page.locator('.group').count(),2);
 assert(await page.locator('#stats').innerText().then(t=>t.includes('Same 78 images')));
 await page.locator('#jobs').selectOption(oldId);await page.waitForFunction(()=>document.querySelector('#stats').textContent.includes('1accepted'));
 await page.locator('#filter').selectOption('accepted');assert.equal(await page.locator('.group').count(),1);
 await page.setViewportSize({width:1000,height:760});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.goto(info.url+'/');await page.getByRole('link',{name:/Bulk set preparation/}).waitFor();assert.deepEqual(errors,[]);
 console.log('Pilot browser checks passed: scanning, grouping, source details, fullscreen, draft acceptance/splitting, refresh persistence, export, crowded unassigned layout, cohort replay, original-review preservation, duplicate-review navigation and token protection.');
}finally{await browser?.close();server.kill()}})().catch(e=>{console.error(e);process.exitCode=1});
