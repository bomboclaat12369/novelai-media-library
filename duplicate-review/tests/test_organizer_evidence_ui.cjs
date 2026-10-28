const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_organizer.py','--large'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1700,height:1100}}),errors=[],posts=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});page.setDefaultTimeout(20000);
 await page.goto(info.url);await page.waitForFunction(()=>data&&view);
 await page.locator('#filter').selectOption('large');
 assert.equal(await page.locator('#postList .post').count(),1);
 await page.locator('#postList .post').click();await page.waitForFunction(()=>!busy&&currentId==='post:dump');
 assert.equal(await page.getByLabel('Ignore as grouping evidence',{exact:true}).isChecked(),false);
 assert.equal(await page.locator('#grid .card').count(),60);
 assert.match(await page.locator('#position').textContent(),/Page 1 of 17.*1–60 \/ 1001 images/);
 await page.locator('#grid [data-pick]').first().click();
 await page.waitForFunction(()=>document.querySelector('#suggestions').textContent.includes('Connected original posts'));
 await page.getByRole('button',{name:'Next page →',exact:true}).click();await page.waitForFunction(()=>!busy&&offset===60);
 assert.match(await page.locator('#position').textContent(),/Page 2 of 17.*61–120/);
 assert.equal(await page.evaluate(()=>selection.size),1);
 await page.getByLabel('Ignore as grouping evidence',{exact:true}).check();
 await page.waitForFunction(()=>!busy&&data.posts.find(p=>p.id==='post:dump').mixed);
 assert.equal(await page.getByText('Connected original posts',{exact:true}).count(),0);
 assert.equal(await page.locator('#suggestions .card').count(),30); // visual matches remain
 assert.equal(await page.evaluate(()=>selection.size),1);
 await page.screenshot({path:'/tmp/organizer-evidence-desktop.png',fullPage:true});
 await page.reload();await page.waitForFunction(()=>data&&view);
 assert.equal(await page.getByLabel('Ignore as grouping evidence',{exact:true}).isChecked(),true);
 assert.equal(await page.evaluate(()=>selection.size),1);
 await page.locator('#filter').selectOption('ignored');assert.equal(await page.locator('#postList .post').count(),1);
 await page.locator('#undo').click();await page.waitForFunction(()=>!busy&&!data.posts.find(p=>p.id==='post:dump').mixed);
 assert.equal(await page.getByLabel('Ignore as grouping evidence',{exact:true}).isChecked(),false);
 assert.equal(await page.locator('#postList .post').count(),0);
 await page.getByText('Connected original posts',{exact:true}).waitFor();
 await page.locator('#filter').selectOption('large');
 await page.getByLabel('Ignore as grouping evidence',{exact:true}).check();await page.waitForFunction(()=>!busy&&data.posts.find(p=>p.id==='post:dump').mixed);
 await page.getByLabel('Ignore as grouping evidence',{exact:true}).uncheck();await page.waitForFunction(()=>!busy&&!data.posts.find(p=>p.id==='post:dump').mixed);
 await page.setViewportSize({width:1280,height:900});await page.screenshot({path:'/tmp/organizer-evidence-laptop.png',fullPage:true});
 assert(await page.locator('#ignorePostEvidence').isVisible());assert(await page.locator('#nextPage').isVisible());
 assert(!posts.some(p=>/\/api\/(scan|history\/inventory|bulk\/start|selection\/move|organizer\/index)/.test(p)),posts.join(','));
 assert.deepEqual(errors,[]);
 console.log('Evidence UI passed: large filter, paging, ignore/restore, visual suggestions, selection persistence, reload, Undo; no scan/move/analysis requests.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
