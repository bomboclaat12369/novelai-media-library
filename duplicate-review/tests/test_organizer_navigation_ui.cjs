const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['duplicate-review/tests/serve_organizer.py','--focus'],{env:process.env});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1700,height:1100}}),errors=[],posts=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname)});page.setDefaultTimeout(20000);
 await page.goto(info.url);await page.waitForFunction(()=>data&&view&&currentId==='post:1');
 await page.locator('#order').selectOption('original');await page.waitForFunction(()=>!busy&&view.order==='original');
 await page.locator(`#grid .card[data-id="${info.ids[2]}"] [data-pick]`).click();
 await page.locator('#suggestions .card[data-id="a-dump-anchor"] [data-pick]').click();
 const connected=page.locator('#suggestions .match').filter({hasText:'Mixed dump'});
 await connected.getByRole('button',{name:'Open',exact:true}).click();
 await page.waitForFunction(()=>!busy&&currentId==='post:dump'&&view.focus_id==='a-dump-anchor');
 assert.equal(await page.evaluate(()=>offset),960);
 assert.match(await page.locator('#position').textContent(),/Page 17 of 17/);
 const anchor=page.locator('#grid .connected-focus');assert.equal(await anchor.getAttribute('data-id'),'a-dump-anchor');
 await page.waitForFunction(()=>{const card=document.querySelector('#grid .connected-focus').getBoundingClientRect(),grid=document.querySelector('#grid').getBoundingClientRect();return card.top<grid.bottom&&card.bottom>grid.top});
 assert.equal(await page.evaluate(()=>selection.size),2);
 await page.waitForFunction(()=>document.querySelector('#grid .connected-focus img').naturalWidth>0);
 await page.screenshot({path:'/tmp/organizer-jump.png',fullPage:true});
 await page.locator('#back').click();await page.waitForFunction(()=>!busy&&currentId==='post:1');
 assert.equal(await page.locator('#order').inputValue(),'original');
 assert.equal(await page.evaluate(()=>selection.size),2);
 await page.locator('#setName').fill('blue and white outfit');await page.locator('#draftSetColors').click();
 await page.locator('#setColors').fill('black with gold, light blue');await page.locator('#saveSetColors').click();
 await page.waitForFunction(()=>!busy&&!document.querySelector('#colorDetails').open);await page.locator('#save').click();
 await page.waitForFunction(()=>!busy&&data.sets.some(s=>s.name==='Blue and White Outfit'));
 assert.deepEqual(await page.evaluate(()=>data.sets.find(s=>s.name==='Blue and White Outfit').colors),['Black with Gold','Light Blue']);
 await page.reload();await page.waitForFunction(()=>data&&view);assert(await page.evaluate(()=>data.sets.some(s=>s.name==='Blue and White Outfit')));
 assert(!posts.some(p=>/\/api\/(scan|history\/inventory|bulk\/start|selection\/move|organizer\/index)/.test(p)),posts.join(','));
 assert.deepEqual(errors,[]);console.log('Organizer navigation and title case UI passed: suggested image → final page anchor, scroll/highlight, Back, selection, saved names/colors and reload.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
