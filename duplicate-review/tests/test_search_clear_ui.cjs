const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_organizer.py'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1700,height:1100}}),errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(new URL(r.url()).pathname));page.setDefaultTimeout(15000);
 await page.goto(info.url);await page.waitForFunction(()=>data?.images===18&&view);
 const count=await page.locator('#postList .post').count();assert(count>0);
 await page.locator('#search').fill('no-matching-post-zzzz');
 const clear=page.locator('.naiSearchField').filter({has:page.locator('#search')}).getByRole('button',{name:'Clear search',exact:true});
 await clear.waitFor();const a=await page.locator('#search').boundingBox(),b=await clear.boundingBox();assert(b.x>a.x+a.width/2&&b.x+b.width<=a.x+a.width+1);
 assert.equal(await page.locator('#postList .post').count(),0);await clear.click();assert.equal(await page.locator('#search').inputValue(),'');assert.equal(await page.locator('#postList .post').count(),count);assert.equal(await page.locator('#search').evaluate(e=>e===document.activeElement),true);assert.deepEqual(errors,[]);assert(!requests.some(p=>/\/api\/(scan|bulk\/start|organizer\/index)/.test(p)));
 console.log('Passed: local organizer search clears, restores results and focus, button fits at far right, no scans.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
