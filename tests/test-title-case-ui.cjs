const assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{env:{...process.env,NAI_UI_VERSION:'2.9.7'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
 const info=await new Promise((resolve,reject)=>{let out='';server.stdout.on('data',b=>{out+=b;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]))});server.on('exit',c=>reject(Error(stderr+c)))});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1700,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(20000);
 const library=async()=>{const r=await page.request.get('http://127.0.0.1:8765/api/library');assert.equal(r.status(),200);return r.json()};
 await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();
 await page.locator('#naiSetsCat').click();await page.locator('#naiCreateSet').click();await page.locator('#naiSetNameInput').fill('blue and white outfit');
 await page.locator(`.naiSetPick[data-media-id="${info.images[1]}"]`).click();assert.equal(await page.locator('#naiSetNameInput').getAttribute('autocomplete'),'off');await page.locator('#naiSaveSetBtn').click();await page.locator('#naiSaveSetBtn').waitFor({state:'detached'});
 let group=(await library()).sets.find(s=>s.name==='Blue and White Outfit');assert(group,'Created name must be title case');
 await page.locator(`.naiSetTile[data-set-id="${group.id}"]`).click();await page.locator('#naiSetRenameBtn').click();
 await page.locator('#naiQuickSetName').fill('red or blue with gold');await page.locator('#naiSetColors').fill('black with gold, light blue, Light Blue');
 assert.equal(await page.locator('#naiQuickSetName').getAttribute('autocomplete'),'off');assert.equal(await page.locator('#naiSetColors').getAttribute('autocomplete'),'off');await page.locator('[data-save]').click();await page.locator('#naiQuickSetName').waitFor({state:'detached'});
 group=(await library()).sets.find(s=>s.id===group.id);assert.equal(group.name,'Red or Blue with Gold');assert.deepEqual(group.colors,['Black with Gold','Light Blue']);
 await page.locator('#naiSetRenameBtn').click();assert.equal(await page.locator('#naiQuickSetName').inputValue(),'Red or Blue with Gold');assert.equal(await page.locator('#naiSetColors').inputValue(),'Black with Gold, Light Blue');
 await page.locator('.naiSetQuick').screenshot({path:'/tmp/library-title-case.png'});
 assert.deepEqual(errors,[]);console.log('Media Library UI passed: lowercase Set creation, lowercase name/color edit, deduplication and reopening with saved title case.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
