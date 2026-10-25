const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_bulk_fixture.py'],{env:{...process.env,RECOVERY_FIXTURE:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1400,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(20000);
 await page.goto(info.url+'/bulk');await page.locator('#phase').filter({hasText:'Ready'}).waitFor();await page.locator('#roots').fill(info.incoming);await page.locator('#start').click();await page.locator('#phase').filter({hasText:'Evaluation ready'}).waitFor();
 await page.locator('#originAudit').click();await page.locator('#audit[open]').waitFor();assert((await page.locator('#auditSummary').innerText()).includes('2 unresolved files'));
 assert.equal(await page.locator('#auditCandidates .tile').count(),0);assert((await page.locator('#auditPaths').innerText()).includes('Post 90'));
 await page.locator('#auditNext').click();await page.waitForFunction(()=>auditData.offset===1);const digest=await page.evaluate(()=>auditData.digest);
 await page.locator('#closeAudit').click();await page.locator('#originAudit').click();await page.locator('#audit[open]').waitFor();assert.equal(await page.evaluate(()=>auditData.digest),digest);
 await page.locator('#auditDefer').click();await page.waitForFunction(()=>auditData.review_status==='deferred');await page.locator('#auditFilter').selectOption('deferred');await page.waitForFunction(()=>auditData.total===1);
 await page.locator('#auditMode').selectOption('all');await page.waitForFunction(()=>auditData.candidate_count===78);assert.equal(await page.locator('#auditCandidates .tile').count(),24);
 await page.locator('#candidateNext').click();await page.waitForFunction(()=>auditData.page===1);
 await page.locator('#auditSearch').fill('A0.png');await page.locator('#auditSearchButton').click();await page.waitForFunction(()=>auditData.candidate_count===1);
 page.once('dialog',d=>d.accept());await page.locator('#auditCandidates').getByRole('button',{name:'Confirm same photo'}).click();await page.waitForFunction(()=>auditData.total===0);
 await page.locator('#undoOrigin').click();await page.waitForFunction(()=>auditData.total===1);
 await page.locator('#closeAudit').click();await page.reload();await page.locator('#originAudit').click();await page.locator('#audit[open]').waitFor();assert.equal(await page.evaluate(()=>auditData.digest),digest);
 assert.deepEqual(errors,[]);console.log('Recovery UI passed: origins, non-padded suggestions, persisted cursor/status, all-survivor pagination, search, confirm and undo.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
