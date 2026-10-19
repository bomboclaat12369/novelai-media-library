const fs=require('fs'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',c=>reject(Error(stderr+c)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1700,height:1100}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const loaded=new Set();page.on('response',r=>{if(r.url().includes('/thumb?size='))loaded.add(new URL(r.url()).origin+new URL(r.url()).pathname+'?size='+new URL(r.url()).searchParams.get('size'))});
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiBattlesBtn').click();
  assert.equal(await page.getByLabel('Session',{exact:true}).inputValue(),'0');await page.locator('#naiBattleStart').click();
  const ready=()=>page.waitForFunction(()=>{const b=document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleChoose');return b&&!b.disabled});await ready();
  await page.locator('#naiBattleLeaderboard').click();assert.equal(await page.locator('.naiBattleRankCard').count(),16);assert.equal(await page.locator('.naiBattleRankCard [data-tier=Grandmaster]').count(),1);
  assert(await page.locator('.naiBattleGalleryVisual').first().evaluate(e=>e.clientHeight>240));
  await page.getByLabel('Search leaderboard').fill('Image 1');assert.equal(await page.locator('.naiBattleRankCard').count(),7);assert.equal(await page.getByLabel('Search leaderboard').evaluate(e=>e.getRootNode().activeElement===e),true);await page.getByLabel('Search leaderboard').fill('');
  await page.getByLabel('Rank filter').selectOption('Grandmaster');assert.equal(await page.locator('.naiBattleRankCard').count(),1);await page.getByLabel('Rank filter').selectOption('all');
  await page.getByLabel('Leaderboard image size').fill('320');await page.screenshot({path:'/tmp/battle-gallery-wide.png'});
  await page.locator('.naiBattleGalleryVisual').first().click();await page.keyboard.press('ArrowRight');assert((await page.locator('.naiBattleLight .naiBattleBrowse').textContent()).includes('#2'));await page.getByRole('button',{name:'Close image',exact:true}).click();
  await page.setViewportSize({width:1000,height:800});await page.getByLabel('Leaderboard image size').fill('160');assert(await page.locator('.naiBattleBoard').evaluate(e=>e.scrollWidth<=e.clientWidth+2));await page.screenshot({path:'/tmp/battle-gallery-compact.png'});
  await page.locator('.naiGalleryFocus').first().click();await ready();assert((await page.locator('.naiBattleStatus').textContent()).includes('Focusing'));await page.getByRole('button',{name:'End focus',exact:true}).click();await ready();assert((await page.locator('.naiBattleStatus').textContent()).includes('Continuous'));
  await page.getByLabel('Battle type',{exact:true}).selectOption('sets');await page.locator('#naiBattleStart').click();await ready();
  assert.equal(await page.locator('.naiBattleSetImage').count(),11);await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleSetImage').length===11);
  const originalPair=await page.locator('.naiBattleCard').evaluateAll(e=>e.map(x=>x.dataset.entryId));await page.locator('.naiBattleChoose').first().click();await ready();assert.equal(await page.locator('.naiBattleSetImage').count(),11);
  await page.locator('#naiBattleLeaderboard').click();assert.equal(await page.locator('.naiBattleRankCard').count(),3);assert.equal(await page.getByLabel('Leaderboard image size').inputValue(),'160');await page.screenshot({path:'/tmp/battle-gallery-sets.png'});
  await page.locator('#naiBattleLeaderboard').click();await page.getByLabel('Minimum set images',{exact:true}).fill('1');await page.locator('#naiBattleStart').click();await ready();
  const library=await (await page.request.get('http://127.0.0.1:8765/api/library')).json();const state=await (await page.request.post('http://127.0.0.1:8765/api/battles/state',{data:{character_id:library.characters[0].id,kind:'sets'}})).json();
  const pair=state.session.pair,upcoming=state.preload_entries.filter(id=>id!==pair.left&&id!==pair.right);assert(upcoming.length>0);
  const expected=upcoming.flatMap(id=>{const e=state.entries.find(x=>x.id===id),size=e.images.length<=2?1024:e.images.length<=6?768:512;return e.images.map(mid=>'http://127.0.0.1:8765/api/media/'+mid+'/thumb?size='+size)});
  await new Promise((resolve,reject)=>{let timer;const check=()=>{if(expected.every(url=>loaded.has(url))){clearTimeout(timer);page.off('response',check);resolve()}};timer=setTimeout(()=>{page.off('response',check);reject(Error('Upcoming set previews were not preloaded'))},5000);page.on('response',check);check()});
  assert.deepEqual(errors,[]);console.log('Gallery UI passed: large cards, filters, typing focus, fullscreen rank navigation, remembered size, compact layout, focus/end focus, continuous play and set grids.');
 }finally{await browser?.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
