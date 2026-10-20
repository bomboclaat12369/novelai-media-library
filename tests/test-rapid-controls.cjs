const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{cwd:dir,env:{...process.env,NAI_RAPID_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',x=>stderr+=x);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',()=>reject(Error(stderr)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/battle-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1700,height:1050}});page.setDefaultTimeout(12000);const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{errors.push(d.message());d.accept()});
  const api=async(route,body)=>{const r=await page.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json()};
  const initial=await api('library'),owner=initial.characters[0].id;let searches=0;
  await page.route('**/api/sets/find-matches',route=>{searches++;return route.fulfill({contentType:'application/json',body:JSON.stringify({id:'fixture',running:false,phase:'Finished',results:[],total:0,done:0})})});
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiResumeRapid').click();await page.locator('#naiRapidSelectedCount').filter({hasText:'60 selected'}).waitFor();
  assert.equal(await page.locator('#carryCats,#reviewAddCat,#naiQueueSets270').count(),0);
  assert.deepEqual(await page.locator('.naiRapidPrimary button').evaluateAll(bs=>bs.map(b=>b.id)),['naiRapidNewSet','naiReviewFindMatches','naiRapidBulkReview']);
  assert(await page.locator('#naiRapidBulkSet').evaluate(b=>!!b.closest('.naiReviewActions270')));
  for(const viewport of [{width:1700,height:1050},{width:1366,height:768}]){
   await page.setViewportSize(viewport);
   const layout=await page.locator('.naiRapidGridPanel').evaluate(p=>{const q=p.querySelector('#naiQueueStrip270'),cmd=p.querySelector('.naiRapidCommandArea');return {grid:q.clientHeight,panel:p.clientHeight,command:cmd.clientHeight,overflow:cmd.scrollHeight-cmd.clientHeight,width:p.scrollWidth-p.clientWidth}});
   assert(layout.grid>=layout.panel*.43,JSON.stringify(layout));assert(layout.overflow<3,JSON.stringify(layout));assert(layout.width<3,JSON.stringify(layout));
   await page.screenshot({path:'/tmp/rapid-controls-'+viewport.width+'.png'});
  }
  await page.setViewportSize({width:1700,height:1050});
  await page.locator('#naiRapidSize').evaluate(e=>{e.value='165';e.dispatchEvent(new Event('input'))});await page.locator('#naiQueueStrip270').evaluate(e=>{e.scrollTop=500;e.dispatchEvent(new Event('scroll'))});
  const before=await page.locator('#naiQueueStrip270').evaluate(e=>e.scrollTop);await page.locator('.naiQueueThumb270').nth(20).locator('img').click();await page.waitForFunction(before=>Math.abs(document.getElementById('nai-media-host').shadowRoot.querySelector('#naiQueueStrip270').scrollTop-before)<10,before).catch(async e=>{console.error({before,after:await page.locator('#naiQueueStrip270').evaluate(e=>e.scrollTop)});throw e});
  await page.locator('#naiRapidUnselectAll').click();assert(await page.locator('#naiRapidNewSet').isDisabled());assert(await page.locator('#naiRapidBulkSet').isDisabled());assert(await page.locator('#naiRapidBulkReview').isDisabled());assert(await page.locator('#naiReviewFindMatches').isEnabled());
  const matched=page.waitForResponse(r=>r.url().includes('/api/sets/find-matches'));await page.locator('#naiReviewFindMatches').click();await page.locator('.naiMatchWrap').waitFor();await matched;assert.equal(searches,1);await page.locator('.naiMatchHead button').click();await page.locator('#naiSetQueueCancel270').click();
  const choose=async count=>{await page.locator('#naiRapidUnselectAll').click();for(let i=0;i<count;i++)await page.locator('.naiQueueThumb270 input').nth(i).check()};
  await choose(2);await page.locator('#naiRapidNewSet').click();await page.locator('#naiSetQueueNew270').fill('Rapid layout set');await page.locator('#naiSetQueueCreate270').click();await page.locator('#naiRapidRemaining').filter({hasText:'58 remaining'}).waitFor();
  let lib=await api('library'),group=lib.sets.find(s=>s.name==='Rapid layout set');assert.equal(group.media_ids.length,2);assert(lib.media.filter(m=>group.media_ids.includes(m.id)).every(m=>!m.in_all&&!m.in_review&&!m.in_purgatory));
  await choose(2);await page.locator('#naiRapidBulkSet').click();await page.locator('#naiSetQueueExisting270').selectOption(group.id);await page.locator('#naiSetQueueSave270').click();await page.locator('#naiRapidRemaining').filter({hasText:'56 remaining'}).waitFor();assert.equal((await api('library')).sets.find(s=>s.id===group.id).media_ids.length,4);
  await choose(1);await page.locator('#naiRapidBulkReview').click();await page.locator('#naiRapidRemaining').filter({hasText:'55 remaining'}).waitFor();const held=(await api('library')).media.find(m=>m.in_review);assert(held);
  await page.locator('#naiReviewClose270').click();await page.locator('#naiReviewCat270').click();await page.locator('#naiReviewHold270').waitFor();assert(await page.locator('#naiReviewHold270').isChecked());await page.locator('#reviewCats input[data-catid="old"]').check();assert(!(await page.locator('#naiReviewHold270').isChecked()));await page.locator('#naiReviewNext270').click();await page.locator('[data-nai-review-v270]').waitFor({state:'detached'});
  const released=(await api('library')).media.find(m=>m.id===held.id);assert(!released.in_review&&!released.in_purgatory&&!released.in_all);assert(released.categories.includes('old'));
  await page.locator('#naiResumeRapid').click();assert.equal(await page.locator('#naiRapidSize').inputValue(),'165');assert.equal(await page.locator('.naiQueueThumb270').count(),55);assert.deepEqual(errors,[]);
  console.log('Rapid review controls, compact layout, matching entry, bulk set/review actions, category release, scroll and size retention passed.');
 }finally{if(browser)await browser.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
