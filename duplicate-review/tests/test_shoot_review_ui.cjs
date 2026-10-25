const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_bulk_fixture.py'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:1400,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
  // Exercise the new display contract using a marked member in a real draft.
  await page.route('**/api/bulk/group?*',async route=>{const response=await route.fetch();const data=await response.json();if(data.members?.length&&data.evidence?.[data.members[0]]){const ev=data.evidence[data.members[0]];Object.assign(ev,{tentative:true,review_hint:'Check addition',reason:'Likely member based on matching views and the shoots established in this post.'})}await route.fulfill({response,json:data})});
  await page.goto(info.url+'/bulk');await page.locator('#phase').filter({hasText:'Ready'}).waitFor();await page.locator('#roots').fill(info.incoming);await page.locator('#start').click();await page.locator('#phase').filter({hasText:'Evaluation ready'}).waitFor();
  await page.locator('.group').first().click();await page.locator('#grid .chip').filter({hasText:'Check addition'}).waitFor();
  await page.locator('#folderContext').click();await page.locator('#folders[open]').waitFor();
  assert((await page.locator('#folderNotice').innerText()).includes('Full readable inventory'));
  assert.equal(await page.locator('#folderGrid .tile').count(),4);
  await page.locator('#relatedDrafts').getByRole('button',{name:'Inspect',exact:true}).first().click();
  await page.locator('#inspect[open]').waitFor();assert.equal(await page.locator('#alternatives .tile').count(),4);await page.locator('#closeInspect').click();
  page.once('dialog',d=>d.accept());await page.locator('#relatedDrafts').getByRole('button',{name:'Combine into current draft'}).first().click();
  await page.waitForFunction(()=>current.members.length===8);await page.locator('#closeFolders').click();
  await page.locator('#undoReview').click();await page.waitForFunction(()=>current.members.length===4);
  await page.locator('#originAudit').click();await page.locator('#audit[open]').waitFor();assert((await page.locator('#auditNotice').innerText()).includes('No entries in this filter'));await page.locator('#closeAudit').click();
  const tile=page.locator('#grid .tile').first();const removed=await tile.getAttribute('data-id');
  await tile.getByRole('button',{name:'Details',exact:true}).click();assert((await page.locator('#evidence').innerText()).includes('Uncheck this image if it does not belong.'));await page.locator('#closeInspect').click();
  await tile.getByRole('checkbox',{name:'Include image'}).uncheck();assert.equal(await page.locator('#selected').textContent(),'3 selected');await page.locator('#accept').click();
  await page.waitForFunction(()=>document.querySelector('#stats').textContent.includes('1accepted'));
  const data=await page.evaluate(()=>api('bulk/export'));const accepted=data.proposals.find(g=>g.review==='accepted');assert.equal(accepted.members.length,3);assert(!accepted.members.includes(removed));assert(data.unassigned.includes(removed));await page.locator('#unassigned').click();await page.locator('#recheckRemaining').waitFor();
  await page.locator('#fileDetails').check();const files=page.locator('#grid .file-details').first();const visibleId=await page.locator('#grid .tile').first().getAttribute('data-id');await files.waitFor({state:'visible'});
  assert((await files.innerText()).includes('ID '+visibleId.slice(0,12)));assert(await files.locator('span').first().getAttribute('title'));
  await page.reload();await page.locator('#unassigned').click();assert(await page.locator('#fileDetails').isChecked());await page.locator('#grid .file-details').first().waitFor({state:'visible'});
  await page.locator('#recheckRemaining').click();await page.waitForFunction(()=>state.recheck_remaining&&!state.running&&state.complete);
  const replay=await page.evaluate(()=>api('bulk/export'));assert.equal(replay.recheck_remaining,true);assert(replay.review_exclusions[removed]);
  assert.deepEqual(errors,[]);
  console.log('Shoot review UI passed: tentative badge, explanation, deselection, persisted review exclusion, file details, and remaining-image recheck.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
