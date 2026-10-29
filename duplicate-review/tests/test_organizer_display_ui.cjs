const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_organizer.py'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1700,height:1100}}),errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(new URL(r.url()).pathname));page.setDefaultTimeout(15000);
 await page.goto(info.url);await page.waitForFunction(()=>data?.images===18&&view);
 assert.match(await page.locator('#totals').textContent(),/^16 \/ 18 unassigned/);
 const id=info.ids[2],card=page.locator(`#grid .card[data-id="${id}"]`);
 await page.locator('#highlightUnassigned').click();assert.equal(await page.locator('#highlightUnassigned').getAttribute('aria-pressed'),'true');
 assert.equal(await card.locator('.unassigned-label').isVisible(),true);
 assert.equal(await page.locator(`#grid .card[data-id="${info.ids[0]}"] .unassigned-label`).isVisible(),false);
 assert.equal(await page.locator('#grid .card').filter({hasText:'Unresolved'}).locator('.unassigned-label').isVisible(),false);
 await card.locator('[data-pick]').click();await page.waitForFunction(()=>document.querySelector('#suggestions .card'));
 assert.equal(await card.evaluate(c=>getComputedStyle(c).borderTopColor),'rgb(230, 198, 139)');
 assert.equal(await card.locator('footer').evaluate(c=>getComputedStyle(c).backgroundColor),'rgb(80, 37, 45)');
 assert.equal(await page.locator(`#suggestions .card[data-id="${info.ids[3]}"] .unassigned-label`).isVisible(),true);
 // Both card and viewer controls toggle the same reference without changing selection.
 await card.locator('[data-reference]').click();await page.waitForFunction(()=>!busy&&suggestionReference);
 await card.locator('[data-reference]').click();await page.waitForFunction(()=>!busy&&!suggestionReference);
 assert.equal(await page.evaluate(()=>selection.size),1);
 await card.locator('img').click();await page.locator('#viewerReference').click();await page.waitForFunction(()=>!busy&&suggestionReference);
 await page.locator('#viewerReference').click();await page.waitForFunction(()=>!busy&&!suggestionReference);await page.locator('#viewerClose').click();
 // Dragging makes both the panel and its suggestion images larger.
 const side=page.locator('#relatedSidebar'),handle=page.locator('#sidebarResize');const original=await side.boundingBox(),oldImage=await page.locator('#suggestions .card img').first().boundingBox();
 const bounds=await handle.boundingBox();await page.mouse.move(bounds.x+bounds.width/2,bounds.y+300);await page.mouse.down();await page.mouse.move(bounds.x-195,bounds.y+300,{steps:8});await page.mouse.up();
 const widened=await side.boundingBox();assert(widened.width>original.width+180);assert((await page.locator('#suggestions .card img').first().boundingBox()).height>oldImage.height);
 await handle.focus();await page.keyboard.press('ArrowLeft');assert((await side.boundingBox()).width>widened.width);
 const savedWidth=(await side.boundingBox()).width;
 await page.locator('#draftSetColors').click();await page.locator('#setFavorite').check();await page.locator('#saveSetColors').click();await page.waitForFunction(()=>!busy&&!document.querySelector('#colorDetails').open);
 await page.locator('#setName').fill('favorite test');await page.locator('#save').click();await page.waitForFunction(()=>!busy&&data.sets.some(g=>g.name==='Favorite Test'));
 const target=await page.evaluate(()=>data.sets.find(g=>g.name==='Favorite Test').id);assert.equal(await page.evaluate(id=>data.sets.find(g=>g.id===id).favorite,target),true);
 assert.match(await page.locator('#totals').textContent(),/^15 \/ 18 unassigned/);assert.equal(await card.locator('.unassigned-label').isVisible(),false);
 await page.locator('#setsTab').click();await page.locator('#setFilter').selectOption('favorites');assert.equal(await page.locator('#postList .post').count(),1);assert.match(await page.locator('#postList strong').textContent(),/^★ Favorite Test$/);
 await page.locator('#postList .post').click();await page.waitForFunction(()=>!busy&&currentKind==='set');await page.locator('#editSetColors').click();assert.equal(await page.locator('#setFavorite').isChecked(),true);await page.locator('#setFavorite').uncheck();await page.locator('#saveSetColors').click();await page.waitForFunction(()=>!busy&&!document.querySelector('#colorDetails').open);assert.equal(await page.locator('#postList .post').count(),0);
 await page.locator('#undo').click();await page.waitForFunction(()=>!busy&&data.sets.some(g=>g.favorite));assert.equal(await page.locator('#postList .post').count(),1);
 await page.reload();await page.waitForFunction(()=>view&&data);assert.equal((await side.boundingBox()).width,savedWidth);assert.equal(await page.locator('#highlightUnassigned').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#postList .post').count(),1);
 await page.locator('#highlightUnassigned').click();assert.equal(await page.locator('#highlightUnassigned').getAttribute('aria-pressed'),'false');
 await page.setViewportSize({width:2400,height:1100});await handle.focus();await page.keyboard.press('ArrowLeft');assert((await side.boundingBox()).width>savedWidth);await page.keyboard.press('Home');assert.equal((await side.boundingBox()).width,410);
 await page.setViewportSize({width:1000,height:900});await page.locator('#relatedToggle').click();await handle.focus();await page.keyboard.press('ArrowLeft');assert((await side.boundingBox()).width<=440);
 await page.setViewportSize({width:700,height:900});assert.equal(await handle.isVisible(),false);assert.equal(await side.isVisible(),true);
 await page.setViewportSize({width:1700,height:1100});await page.locator('#postsTab').click();await page.locator('#postList .post').first().click();await page.waitForFunction(()=>!busy&&currentKind==='post');await page.locator('#highlightUnassigned').click();await page.screenshot({path:'/tmp/organizer-display-2015.png'});
 assert(!requests.includes('/api/scan'));assert(!requests.includes('/api/organizer/index'));assert.deepEqual(errors,[]);
 console.log('Organizer display UI passed: unassigned highlights/count, gold selection, reference toggles, pointer/keyboard/responsive resizing, favorite draft/edit/filter/undo/reload; no scan.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
