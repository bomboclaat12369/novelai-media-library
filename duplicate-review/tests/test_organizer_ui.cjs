const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_organizer.py'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1700,height:1100}}),errors=[],posts=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});page.setDefaultTimeout(15000);
 await page.goto(info.url);await page.waitForFunction(()=>data?.images===18&&view?.images.length>0);
 assert.equal(await page.locator('#grid .card').count(),7);
 assert.equal(await page.locator('#grid .card').filter({hasText:'Unresolved'}).getByRole('button',{name:'Select',exact:true}).isEnabled(),false);
 const id=info.ids[2];await page.locator(`#grid .card[data-id="${id}"] [data-pick]`).click();
 await page.waitForFunction(()=>document.querySelectorAll('#suggestions .card').length>0);
 assert.match(await page.locator('#selectionCount').textContent(),/1 selected/);
 await page.locator(`#grid .card[data-id="${id}"] img`).click();await page.waitForFunction(()=>document.querySelector('#largeImage').naturalWidth>0);
 assert.equal(await page.locator('#viewer').evaluate(e=>e.open),true);
 await page.keyboard.press('ArrowRight');await page.keyboard.press(' ');assert.equal(await page.evaluate(()=>selection.size),2);
 await page.locator('#viewerDetails').click();assert.equal(await page.locator('#locations').isVisible(),true);
 await page.locator('#viewerClose').click();
 await page.locator('#setName').fill('Saved shoot');await page.locator('#save').click();await page.waitForFunction(()=>!busy&&data.sets.some(g=>g.name==='Saved shoot'));
 assert.equal(await page.evaluate(()=>selection.size),0);
 const saved=await page.evaluate(()=>data.sets.find(g=>g.name==='Saved shoot').id);
 await page.locator('#setsTab').click();await page.locator('#postList button').filter({hasText:'Saved shoot'}).click();await page.waitForFunction(()=>currentKind==='set'&&!busy);
 assert.equal(await page.locator('#grid .card').count(),2);
 await page.reload();await page.waitForFunction(()=>data?.sets.some(g=>g.name==='Saved shoot')&&view);
 assert.equal(await page.evaluate(()=>currentId),saved);
 await page.locator('#undo').click();await page.waitForFunction(()=>!busy&&!data.sets.some(g=>g.name==='Saved shoot'));
 assert.equal(await page.evaluate(()=>selection.size),2);
 // Reopen a surviving post after undo removed the viewed draft.
 await page.locator('#postsTab').click();await page.locator('#postList button').first().click();await page.waitForFunction(()=>currentKind==='post'&&!busy);
 await page.locator('#columns').fill('4');await page.locator('#columns').dispatchEvent('input');
 assert.equal(await page.locator('#grid').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),4);
 assert.equal(await page.locator('#grid img').first().evaluate(e=>getComputedStyle(e).objectFit),'contain');
 assert.equal(await page.locator('#grid .card').first().evaluate(c=>c.querySelector('footer').getBoundingClientRect().bottom<=c.getBoundingClientRect().bottom),true);
 await page.screenshot({path:'/tmp/organizer-desktop.png',fullPage:true});
 await page.locator('#programUpdate').click();await page.getByRole('heading',{name:'Program updates'}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Check for updates',exact:true}).isVisible(),true);
 await page.getByRole('button',{name:'Close',exact:true}).last().click();
 assert(!posts.some(p=>/\/api\/(scan|history\/inventory|bulk\/start|selection\/move)/.test(p)),posts.join(','));
 assert.deepEqual(errors,[]);
 console.log('Organizer UI passed: saved inventory, selection/suggestions, keyboard viewer, drafts/reload/undo, columns, uncropped images, update dialog; no scan or move requests.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
