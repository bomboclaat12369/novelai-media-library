const assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1',NAI_CARD_FEATURES_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',c=>reject(Error(stderr+c)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1600,height:1000}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE',e.message)});
  const ready=()=>page.waitForFunction(()=>{const r=document.getElementById('nai-media-host').shadowRoot;return r.querySelectorAll('.naiBattleChoose').length===2&&[...r.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled)});
  const board=page.locator('.naiBattleBoard'),cards=page.locator('.naiBattleRankCard');
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiBattlesBtn').click();await page.locator('#naiBattleLeaderboard').click();await cards.first().waitFor().catch(async e=>{console.error(await page.locator('.naiBattleWrap').innerText());await page.screenshot({path:'/tmp/card-feature-error.png'});throw e});
  const library=await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiGetLibrary());const owner=library.characters[0].id;
  assert(await cards.count()<65);assert.equal(await page.getByRole('button',{name:'Show more',exact:true}).count(),0);
  const frontIds=await cards.evaluateAll(es=>es.map(e=>e.dataset.entryId));await board.evaluate(e=>e.scrollTop=e.scrollHeight);await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleRankCard')].some(e=>e.dataset.entryId==='card-fixture-359'));
  assert(await cards.count()<65);assert(!(await cards.evaluateAll(es=>es.map(e=>e.dataset.entryId))).includes(frontIds[0]));await board.evaluate(e=>e.scrollTop=0);await page.waitForFunction(id=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleRankCard')?.dataset.entryId===id,frontIds[0]);
  assert(await page.locator('.naiCardTitleArt[alt="Captain"]').count()>0);assert(await page.locator('.naiCardTitleArt[alt="Former #1"]').count()>0);
  await cards.nth(1).locator('.naiBattleGalleryVisual').click();await page.locator('.naiExpandedCard .naiCardPhotoWindow img').waitFor();
  await page.locator('.naiExpandedCard .naiCardPhotoWindow img').click();await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiFlipCard')?.dataset.flipped==='true');
  await page.locator('.naiCardUtilities > summary').click();await page.getByLabel('Featured title',{exact:true}).waitFor();assert(await page.locator('.naiCardBackBody').textContent().then(s=>s.includes('Former #1')));
  await page.locator('.naiFlipCard').evaluate(e=>Promise.all(e.getAnimations({subtree:true}).map(a=>a.finished)));
  await page.screenshot({path:(process.env.NAI_CARD_SHOTS||'/tmp')+'/card-feature-back.png'});
  await page.locator('.naiCardBackBody h2').click();assert.equal(await page.locator('.naiFlipCard').getAttribute('data-flipped'),'false');
  await page.locator('.naiFlipCard').evaluate(e=>Promise.all(e.getAnimations({subtree:true}).map(a=>a.finished)));
  await page.screenshot({path:(process.env.NAI_CARD_SHOTS||'/tmp')+'/card-feature-title.png'});
  await page.locator('.naiExpandedCard .naiCardPhotoWindow img').click();const titleSaved=page.waitForResponse(r=>r.url().endsWith('/api/collection/title'));await page.getByLabel('Featured title',{exact:true}).selectOption('none');assert.equal((await titleSaved).status(),200);await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiFlipCard')?.dataset.flipped==='true'&&!document.getElementById('nai-media-host').shadowRoot.querySelector('.naiExpandedCard .naiCardTitleArt'));
  await page.locator('.naiBattleLight').getByRole('button',{name:'Close image',exact:true}).click();await cards.first().waitFor();
  // Direct challenge chooses two exact cards, saves only a single normal vote.
  await cards.first().locator('.naiBattleGalleryVisual').click();await page.locator('.naiBattleLight').getByRole('button',{name:'Challenge…',exact:true}).click();await page.getByLabel('Find an opponent').fill('Image 1.png');await page.locator('.naiChallengePanel .naiUnfoldTile').first().click();await ready();assert((await page.locator('.naiBattleStatus').textContent()).includes('Direct challenge'));
  const voted=page.waitForResponse(r=>r.url().endsWith('/api/battles/vote'));await page.locator('.naiBattlePhoto').first().click();const result=await (await voted).json();await ready();assert.equal(result.votes,161);
  // Focus is available outside the enlarged card.
  await page.locator('#naiBattleLeaderboard').click();await cards.first().waitFor();await cards.first().locator('.naiBattleGalleryVisual').click();await page.locator('.naiBattleLight').getByRole('button',{name:'Focus comparisons',exact:true}).click();await ready();assert((await page.locator('.naiBattleStatus').textContent()).includes('Focusing'));
  // New arrivals clear unread status after viewing, but stay unfinished.
  await page.request.post('http://127.0.0.1:8765/test/card-arrival',{data:{}});await page.locator('.naiBattleTools').getByRole('button',{name:'Refresh',exact:true}).click();await ready();await page.locator('.naiBattleTools').getByRole('button',{name:'New arrivals · 1',exact:true}).click();await page.locator('.naiBattleRankCard[data-entry-id="new-arrival"]').waitFor();await page.locator('.naiBattleTools').getByRole('button',{name:'New arrivals',exact:true}).waitFor();await page.locator('.naiBattleTools').getByRole('button',{name:/^Needs placement/}).click();await page.locator('.naiBattleRankCard[data-entry-id="new-arrival"]').waitFor();
  // Set captain remains independent of its library cover and uses a single portrait.
  await page.getByLabel('Battle type',{exact:true}).selectOption('sets');await cards.first().waitFor();assert.equal(await cards.first().locator('.naiBattleGalleryVisual img').count(),1);await cards.first().locator('.naiBattleGalleryVisual').click();await page.locator('.naiSetUnfold .naiUnfoldTile').first().waitFor();
  const initial=await page.locator('.naiSetUnfold .naiUnfoldTile[data-captain=true] img').getAttribute('src');await page.locator('.naiSetUnfold').getByRole('button',{name:'Choose captain',exact:true}).click();const chosen=page.locator('.naiSetUnfold .naiUnfoldTile').nth(1);const save=page.waitForResponse(r=>r.url().endsWith('/api/collection/captain'));await chosen.click();assert.equal((await save).status(),200);await page.locator('.naiSetUnfold').getByRole('button',{name:'Choose captain',exact:true}).waitFor();assert.equal(await page.locator('.naiSetUnfold .naiUnfoldTile[data-captain=true]').count(),1);
  await page.locator('.naiSetUnfold').getByRole('button',{name:'Close set',exact:true}).click();await cards.first().waitFor();assert.equal(await page.locator('.naiBattleRankCard .naiCardTitleArt').count(),0);
  await cards.first().locator('.naiBattleGalleryVisual').click();await page.locator('.naiSetUnfold .naiUnfoldTile').first().click();await page.locator('.naiFlipCard').waitFor();await page.locator('.naiBattleLight').getByRole('button',{name:'Close image',exact:true}).click();await page.locator('.naiSetUnfold').waitFor();
  await page.screenshot({path:(process.env.NAI_CARD_SHOTS||'/tmp')+'/card-feature-unfold.png'});await page.keyboard.press('Escape');assert.equal(await page.locator('.naiBattleLight').count(),0);
  await page.setViewportSize({width:1000,height:760});await page.locator('.naiBattleBoard').evaluate(e=>e.scrollTop=0);await cards.first().waitFor();assert(await board.evaluate(e=>e.scrollWidth<=e.clientWidth+2));
  assert.deepEqual(errors,[]);console.log('360-card virtual scrolling, graphic titles, flip/persistence, challenges/votes, fullscreen focus, arrivals/placement and set captain/unfold flows passed.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
