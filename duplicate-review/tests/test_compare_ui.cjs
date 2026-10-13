const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const {spawn}=require('child_process'),readline=require('readline'),assert=require('assert'),path=require('path'),fs=require('fs');
(async()=>{
 const child=spawn('python',['tests/serve_groups.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
 const lines=readline.createInterface({input:child.stdout});const f=await new Promise(resolve=>lines.once('line',l=>resolve(JSON.parse(l))));
 const browser=await chromium.launch({executablePath:'/tmp/duplicate-review-chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
 const page=await browser.newPage({viewport:{width:1600,height:1050}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(f.url);await page.fill('#incoming',f.incoming);await page.click('#scan');
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='Scan complete'&&document.querySelectorAll('#grid .card').length===4);
 assert.equal(await page.locator('#grid .highest-resolution').count(),3);
 assert.equal(await page.locator('#grid .resolution-badge').count(),3);
 // Equal-resolution group has no highlighting.
 await page.selectOption('#sort','fewest');await page.waitForFunction(()=>document.querySelectorAll('#grid .card').length===2);
 assert.equal(await page.locator('#grid .highest-resolution').count(),0);
 await page.selectOption('#sort','most');await page.waitForFunction(()=>document.querySelectorAll('#grid .card').length===4);
 await page.click('#compare');await page.waitForFunction(()=>document.querySelector('#leftImage').naturalWidth>0&&document.querySelector('#rightImage').naturalWidth>0);
 assert.equal(await page.locator('#compareDialog .higher-resolution').count(),0);
 const small=await page.locator('#rightChoice option').evaluateAll(opts=>opts.find(o=>o.textContent.includes('smaller.jpg')).value);
 await page.selectOption('#rightChoice',small);await page.waitForFunction(()=>document.querySelector('#rightImage').naturalWidth===320);
 assert(await page.locator('#leftArea').evaluate(e=>e.classList.contains('higher-resolution')));
 assert(!(await page.locator('#rightArea').evaluate(e=>e.classList.contains('higher-resolution'))));
 assert((await page.textContent('#leftDetails')).includes('0.54 MP'));
 assert((await page.textContent('#rightDetails')).includes('0.13 MP'));
 await page.screenshot({path:'/tmp/duplicate-review-130-compare.png',fullPage:true});
 // Image content and controls do not dismiss.
 await page.locator('#leftImage').click();assert(await page.locator('#compareDialog').evaluate(e=>e.open));
 await page.selectOption('#zoom','150');assert(await page.locator('#compareDialog').evaluate(e=>e.open));
 await page.selectOption('#zoom','fit');
 // Click in object-fit letterboxing; it belongs to the img element, but not image content.
 const letterbox=await page.locator('#leftImage').evaluate(im=>{const r=im.getBoundingClientRect(),s=Math.min(r.width/im.naturalWidth,r.height/im.naturalHeight),w=im.naturalWidth*s,h=im.naturalHeight*s;return r.width-w>10?{x:r.left+3,y:r.top+r.height/2}:{x:r.left+r.width/2,y:r.top+3}});
 await page.mouse.click(letterbox.x,letterbox.y);await page.waitForFunction(()=>!document.querySelector('#compareDialog').open);
 await page.click('#compare');await page.mouse.click(8,8);await page.waitForFunction(()=>!document.querySelector('#compareDialog').open);
 await page.click('#compare');await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#compareDialog').open);
 assert.equal(await page.locator('#leftImage').getAttribute('src'),null);
 await page.click('#compare');await page.click('#keepLeft');
 await page.waitForFunction(()=>!document.querySelector('#compareDialog').open&&document.querySelector('#moved').textContent==='3'&&!document.querySelector('#undo').disabled);
 assert(fs.existsSync(path.join(f.new,'newest.png')));
 assert(!fs.existsSync(path.join(f.old,'smaller.jpg')));
 await page.click('#undo');await page.waitForFunction(()=>document.querySelector('#moved').textContent==='0'&&document.querySelectorAll('#grid .card').length===4);
 assert.equal(errors.length,0,JSON.stringify(errors));console.log('Compare UI passed: MP highlights/ties/equality, live comparison labels, backdrop and letterbox closing, image/control clicks retained, Escape cleanup, keep from compare and batch undo.');
 }finally{await browser.close();child.kill();lines.close()}
})().catch(e=>{console.error(e);process.exit(1)});
