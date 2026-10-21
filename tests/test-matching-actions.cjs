// Focused reference zoom and single-upload discard checks against the real queue API.
const path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{cwd:dir,env:{...process.env,NAI_RAPID_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',x=>stderr+=x);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',()=>reject(Error(stderr)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/matching-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1366,height:900}});page.setDefaultTimeout(12000);const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{errors.push(d.message());d.accept()});
  const api=async(route,body)=>{const r=await page.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json()};
  const initial=await api('library'),owner=initial.characters[0].id,queued=await api('rapid-review?character_id='+owner),ids=queued.items.slice(0,3).map(m=>m.id);
  await api('rapid-review/resolve',{character_id:owner,action:'discard',media_ids:queued.items.slice(3).map(m=>m.id)});
  let delaySearch=false,releaseSearch,searchStarted,cancelledSearch;
  const started=new Promise(resolve=>searchStarted=resolve),cancelled=new Promise(resolve=>cancelledSearch=resolve);
  await page.route('**/api/sets/find-matches',async route=>{if(delaySearch){await new Promise(resolve=>{releaseSearch=resolve;searchStarted()})}return route.fulfill({contentType:'application/json',body:JSON.stringify({id:'fixture',running:delaySearch,phase:'Finished',results:[],individual_results:[],total:0,done:0})})});
  await page.route('**/api/sets/match-cancel',route=>{cancelledSearch();return route.fulfill({contentType:'application/json',body:'{"id":"fixture","cancel_requested":true}'})});
  let failDiscard=true;
  await page.route('**/api/rapid-review/resolve',route=>{if(failDiscard){failDiscard=false;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Temporary discard failure'})})}return route.continue()});
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();
  // Saved-library matching gets original-resolution zoom, but no upload-discard action.
  await page.evaluate(q=>{document.getElementById('nai-media-host').shadowRoot.naiFindMatchingSets({queries:[q],onChoose:()=>{}})},initial.media[0]);
  await page.locator('.naiMatchStatus').filter({hasText:'Finished'}).waitFor();assert(await page.locator('.naiMatchDiscard').isHidden());
  await page.getByRole('button',{name:'View reference image fullscreen'}).click();await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiMatchZoom img')?.naturalWidth>=1600);
  await page.keyboard.press('Escape');assert.equal(await page.locator('.naiMatchZoom').count(),0);assert.equal(await page.locator('.naiMatchWrap').count(),1);await page.locator('.naiMatchHead button').click();
  await page.locator('#naiResumeRapid').click();await page.locator('#naiRapidSelectedCount').filter({hasText:'3 selected'}).waitFor();
  const open=async()=>{await page.locator('#naiReviewFindMatches').click();await page.locator('.naiMatchStatus').filter({hasText:'Finished'}).waitFor()};
  await open();await page.getByRole('button',{name:'View reference image fullscreen'}).click();await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiMatchZoom img')?.naturalWidth===200);await page.keyboard.press('Escape');
  await page.locator('.naiMatchDiscard').click();await page.locator('.naiMatchStatus').filter({hasText:'Temporary discard failure'}).waitFor();assert(await page.locator('.naiMatchDiscard').isEnabled());assert.equal((await api('rapid-review?character_id='+owner)).items.length,3);
  await page.locator('.naiMatchDiscard').click();await page.locator('.naiMatchWrap').waitFor({state:'detached'});assert.equal(await page.locator('.naiSetQueueWrap270').count(),0);
  assert.deepEqual((await api('rapid-review?character_id='+owner)).items.map(m=>m.id),ids.slice(1));assert.equal(await page.locator('.naiQueueThumb270.current').getAttribute('data-id'),ids[1]);
  // A different reference selected in the dialog must discard that image alone.
  await open();await page.getByRole('combobox',{name:'Image to match',exact:true}).selectOption('1');await page.locator('.naiMatchDiscard').click();await page.locator('.naiMatchWrap').waitFor({state:'detached'});
  assert.deepEqual((await api('rapid-review?character_id='+owner)).items.map(m=>m.id),[ids[1]]);assert.equal(await page.locator('.naiQueueThumb270.current').getAttribute('data-id'),ids[1]);
  delaySearch=true;await page.locator('#naiReviewFindMatches').click();await started;
  await page.locator('.naiMatchDiscard').click();await page.locator('.naiMatchWrap').waitFor({state:'detached'});releaseSearch();await Promise.race([cancelled,new Promise((_,reject)=>setTimeout(()=>reject(Error('Late search was not cancelled')),5000))]);
  assert.equal(await page.locator('[data-nai-review-v270],.naiSetQueueWrap270').count(),0);assert.equal((await api('rapid-review?character_id='+owner)).items.length,0);
  const after=await api('library');assert.deepEqual(after.media,initial.media);assert.deepEqual(after.sets,initial.sets);
  await page.locator('#naiSetsCat').click();await page.locator('.naiSetTile').first().waitFor();
  await page.evaluate(({owner,sets})=>{const r=document.getElementById('nai-media-host').shadowRoot;r.naiRankingsChanged({character_id:owner,kind:'sets',entries:sets.map(s=>({id:s.id,tier:'Gold',rating:1308,played:5,rd:100,provisional:false}))})},{owner,sets:initial.sets});
  await page.locator('.naiSetTile .naiLibraryRank').first().waitFor();
  for(const width of [95,150]){
   const tile=page.locator('.naiSetTile').first();await tile.evaluate((e,w)=>{e.style.width=w+'px';e.style.height=w+'px'},width);
   const rank=await tile.locator('.naiLibraryRank').boundingBox(),count=await tile.locator('.naiSetCount').boundingBox();assert(rank.y+rank.height<=count.y-2,JSON.stringify({width,rank,count}));
  }
  await page.locator('.naiSetTile').first().screenshot({path:'/tmp/set-rank-spacing.png'});assert.deepEqual(errors,[]);
  console.log('Reference originals/zoom, Escape, discard retry, current-image-only discard, next/last queue navigation, saved-library safety and badge spacing passed.');
 }finally{if(browser)await browser.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
