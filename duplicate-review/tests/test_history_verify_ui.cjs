const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const high=!!process.env.HIGH_CONFIDENCE_FIXTURE,all=!!process.env.ACCEPT_ALL_FIXTURE,remaining=all?1:2;
 const server=spawn('python3',['duplicate-review/tests/serve_history_verify.py'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[],posts=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});page.setDefaultTimeout(15000);
 await page.goto(info.url+'/#history');await page.waitForFunction(()=>historyData?.total_files===4&&!busy);
 await page.locator('#historyFilter').selectOption('uncertain');await page.waitForFunction(()=>historyData.total===0&&!busy);
 assert.match(await page.locator('#empty').textContent(),/run Verify saved matches first/);
 assert.equal(posts.filter(p=>p==='/api/history/verify').length,0);
 await page.locator(all?'#historyAcceptAll':high?'#historyHighConfidence':'#historyVerify').click();await page.waitForFunction(n=>historyData?.total_files===n&&!historyState.running&&!busy,remaining);
 assert.equal(await page.evaluate(()=>historyData.total),remaining);
 assert.match(await page.locator('#historyVerification').textContent(),all?/3 files connected/:/2 files connected/);
 assert.equal(await page.locator('#undo').textContent(),all?'Undo accepted suggestions':high?'Undo high-confidence connections':'Undo automatic connections');
 await page.locator('#historyFilter').selectOption('no_matches');await page.waitForFunction(()=>historyData.total===1&&!busy);
 assert.equal(await page.locator('#grid .card').count(),1);
 await page.reload();await page.waitForFunction(n=>historyData?.total_files===n&&!busy,remaining);
 assert.equal(await page.evaluate(()=>historyData.job),'saved-alice');
 assert.equal(posts.filter(p=>p==='/api/history/verify').length,1);
 assert.equal(await page.evaluate(()=>historyData.verification.policy),all?'accept_suggestions':high?'high_confidence':'strict');
 await page.locator('#undo').click();await page.waitForFunction(()=>historyData?.total_files===4&&!busy);
 assert.equal(await page.evaluate(()=>historyData.total),3);
 await page.locator('#reviewQueue').selectOption('regular');await page.waitForFunction(()=>!busy&&!historyModeActive());
 assert.equal(await page.locator('#scan').isEnabled(),true);
 await page.locator('#reviewQueue').selectOption('history');await page.waitForFunction(()=>historyData?.total_files===4&&!busy);
 assert.equal(await page.locator('#historyVerify').isEnabled(),true);
 assert.deepEqual(errors,[]);
 assert(!posts.some(p=>['/api/history/inventory','/api/scan','/api/selection','/api/group'].includes(p)),posts.join(','));
 console.log('Saved-history UI passed: verification, filters, batch undo after reload, regular-mode return, no scan or inventory requests.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
