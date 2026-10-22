const assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',c=>reject(Error(stderr+c)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1600,height:1000}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const ready=()=>page.waitForFunction(()=>{const r=document.getElementById('nai-media-host').shadowRoot;return r.querySelectorAll('.naiBattleChoose').length===2&&[...r.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled)});
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiBattlesBtn').click();await page.locator('#naiBattleStart').click();await ready();
  const pair=await page.locator('.naiBattleCard').evaluateAll(es=>es.map(e=>e.dataset.entryId));
  await page.locator('.naiBattleTools').getByRole('button',{name:'Collection HQ',exact:true}).click();await page.locator('[data-collection-hq] .naiCollectionMap').waitFor();
  assert(await page.locator('.naiBattleWrap').evaluate(e=>e.inert));await page.locator('[data-collection-hq] .naiCollectionHeader').getByRole('button',{name:'Close',exact:true}).click();
  assert.equal(await page.locator('.naiBattleWrap').count(),1);assert.equal(await page.locator('.naiBattleWrap').evaluate(e=>e.inert),false);assert.deepEqual(await page.locator('.naiBattleCard').evaluateAll(es=>es.map(e=>e.dataset.entryId)),pair);
  // Vote still saves once, and the next pair is usable after returning from HQ.
  const response=page.waitForResponse(r=>r.url().endsWith('/api/battles/vote'));await page.locator('.naiBattlePhoto').first().click();const saved=await (await response).json();await ready();assert(saved.session.pair);assert.equal(saved.votes,161);
  await page.locator('#naiBattleLeaderboard').click();
  const appearance=await page.locator('.naiBattleRankCard .naiCardShell').evaluateAll(es=>es.map(e=>({rank:e.dataset.rank,metal:getComputedStyle(e).getPropertyValue('--metal-mid'),asset:e.querySelector('.naiCardOrnament').style.backgroundImage,nodes:e.querySelector('.naiCardOrnament').childElementCount})));
  assert(new Set(appearance.map(e=>e.metal)).size>=4);assert(appearance.every(e=>e.asset.includes('data:image/svg+xml')&&e.nodes===0));
  assert.equal(await page.locator('.naiBattleRankCard').first().evaluate(e=>getComputedStyle(e).contentVisibility),'auto');
  // Check every rank theme and unchanged percentile mapping without writing user data.
  const themes=await page.evaluate(()=>{const r=document.getElementById('nai-media-host').shadowRoot,rows=Array.from({length:30},(_,i)=>({id:String(i),images:[String(i)],rating:1000+i*10,played:20,provisional:false,rating_status:'Established'}));return {scores:rows.map(e=>r.naiCards.ovr(e,rows)),colors:['Bronze','Silver','Gold','Platinum','Diamond','Master','Grandmaster'].map(tier=>{const card=r.naiCards.lightCard({...rows[10],tier},rows,'',document.createElement('img'));return card.style.getPropertyValue('--metal-mid')})}});
  assert.equal(new Set(themes.colors).size,7);assert.equal(themes.scores[0],60);assert.equal(themes.scores.at(-1),99);assert(themes.scores.every((x,i,a)=>!i||x>=a[i-1]));
  const board=page.locator('.naiBattleBoard');await board.evaluate(e=>e.scrollTop=300);const scroll=await board.evaluate(e=>e.scrollTop);
  const first=page.locator('.naiBattleGalleryVisual').first();await first.evaluate(e=>e.click());await page.locator('.naiBattleLight .naiExpandedCard img').waitFor();await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleLight img')?.naturalWidth>0);
  assert.equal(await page.locator('.naiBattleLight .naiCardOrnament').count(),1);assert.equal(await page.locator('.naiBattleLight .naiCardRail').count(),1);
  const before=await page.locator('.naiBattleLight img').getAttribute('data-media-id');await page.keyboard.press('ArrowRight');await page.waitForFunction(id=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleLight img')?.dataset.mediaId!==id,before);
  // Clicking the photo stays open; clicking the blank area closes it.
  await page.locator('.naiBattleLight img').click();assert.equal(await page.locator('.naiBattleLight').count(),1);
  await page.screenshot({path:(process.env.NAI_CARD_SHOTS||'/tmp')+'/card-expanded-rank.png'});
  await page.locator('.naiCardLightStage').click({position:{x:4,y:4}});assert.equal(await page.locator('.naiBattleLight').count(),0);assert.equal(await page.locator('.naiBattleBoard').evaluate(e=>e.scrollTop),scroll);
  await page.locator('.naiBattleGalleryVisual').first().click();await page.keyboard.press('Escape');assert.equal(await page.locator('.naiBattleLight').count(),0);
  await page.locator('.naiBattleTools').getByRole('button',{name:'Collection HQ',exact:true}).click();await page.locator('[data-collection-hq] .naiCollectionMap').waitFor();await page.keyboard.press('Escape');assert.equal(await page.locator('.naiBattleWrap').count(),1);assert(await board.isVisible());
  // Launching a specific task from HQ must replace, not duplicate, the old battle.
  await page.locator('.naiBattleTools').getByRole('button',{name:'Collection HQ',exact:true}).click();await page.locator('[data-collection-hq] .naiCollectionMap').waitFor();await page.locator('[data-collection-hq]').getByRole('button',{name:'Strengthen ratings',exact:true}).first().click();await ready();assert.equal(await page.locator('.naiBattleWrap').count(),1);assert.equal(await page.locator('[data-collection-hq]').count(),0);
  await page.getByLabel('Show MMR',{exact:true}).uncheck();assert.equal(await page.locator('.naiCardStage .naiCardRail').count(),0);assert.deepEqual(await page.locator('.naiCardStage .naiCardShell').evaluateAll(es=>es.map(e=>e.dataset.rank)),['Unranked','Unranked']);
  assert.deepEqual(errors,[]);console.log('Rank themes, OVR, shared art, HQ return/launch, vote persistence, expanded-card navigation/backdrop/scroll and blind mode passed.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
