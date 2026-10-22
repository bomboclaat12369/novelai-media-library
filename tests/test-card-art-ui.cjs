const assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',c=>reject(Error(stderr+c)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1600,height:1000}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  // Optional local photo for visual inspection only; never included in the release.
  if(process.env.NAI_CARD_PHOTO)await page.route('**/api/media/*/*',async route=>{const url=new URL(route.request().url());if(url.pathname.endsWith('/original')||url.pathname.endsWith('/thumb'))await route.fulfill({path:process.env.NAI_CARD_PHOTO,contentType:'image/jpeg'});else await route.continue()});
  const shots=process.env.NAI_CARD_SHOTS||'/tmp';
  const ready=()=>page.waitForFunction(()=>{const r=document.getElementById('nai-media-host').shadowRoot;return r.querySelectorAll('.naiBattleChoose').length===2&&[...r.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled)});
  const screenshot=async name=>{await page.locator('.naiBattleGalleryVisual img,.naiProfileHero').evaluateAll(async ims=>{await Promise.allSettled(ims.filter(im=>im.src).map(im=>im.decode()));await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))});await page.screenshot({path:shots+'/card-art-'+name+'.png'});};
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiBattlesBtn').click();await page.locator('#naiBattleStart').click();await ready();
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiCardStage>.naiTradingCard').clientHeight>400);
  assert.equal(await page.locator('.naiBattleCard>.naiCardStage>.naiCardShell').count(),2);
  assert(await page.locator('.naiCardStage>.naiTradingCard').first().evaluate(e=>Math.abs(e.clientWidth/e.clientHeight-2/3)<.01));
  assert(await page.locator('.naiCardStage>.naiTradingCard').first().evaluate(e=>e.querySelector('.naiCardPhotoWindow').clientHeight/e.clientHeight>.8));
  assert.equal(await page.locator('.naiCardShell .naiBattleFooter').count(),0);await screenshot('battle');
  const before=await page.locator('.naiBattleStatus').textContent();await page.locator('.naiBattlePhoto').first().click();await ready();assert.notEqual(await page.locator('.naiBattleStatus').textContent(),before);
  await page.keyboard.press('ArrowRight');await ready();await page.locator('#naiBattleLeaderboard').click();
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleGalleryVisual img')].slice(0,4).every(im=>im.complete&&im.naturalWidth));
  assert(await page.locator('.naiBattleGalleryVisual img').first().evaluate(im=>im.clientHeight>150));assert.equal(await page.locator('.naiCardShell .naiGalleryInfo').count(),0);assert.equal(await page.locator('.naiCardDetails[open]').count(),0);assert.equal(await page.locator('.naiCardShell>.naiCardOrnament').count(),16);await screenshot('gallery');
  await page.locator('.naiGalleryInspect').first().click();await page.locator('.naiBattleLight').getByRole('button',{name:'Rating history',exact:true}).click();await page.keyboard.press('Escape');
  await page.locator('.naiBattleLight').getByRole('button',{name:'Position card',exact:true}).click();await page.getByLabel('Zoom',{exact:true}).fill('1.15');await page.getByRole('button',{name:'Save framing',exact:true}).click();
  await page.locator('.naiBattleLight').getByRole('button',{name:'Close image',exact:true}).click();await page.locator('.naiBattleGalleryVisual').first().click();await page.locator('.naiExpandedCard .naiCardPhotoWindow img').waitFor();await page.getByRole('button',{name:'Close image',exact:true}).click();
  await page.getByLabel('Battle type',{exact:true}).selectOption('sets');await page.locator('#naiBattleStart').click();await ready();assert.equal(await page.locator('.naiBattleSetImage').count(),11);await screenshot('sets');
  await page.setViewportSize({width:1000,height:760});await page.waitForFunction(()=>{const e=document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleMosaic');return e.clientHeight>180&&e.clientHeight<500});await screenshot('sets-compact');
  await page.getByLabel('Show MMR',{exact:true}).uncheck();assert.equal(await page.locator('.naiCardRail').count(),0);await page.getByLabel('Show MMR',{exact:true}).check();await page.getByLabel('Battle type',{exact:true}).selectOption('images');await ready();await screenshot('images-compact');
  assert(await page.locator('.naiCardStage>.naiTradingCard').first().evaluate(e=>Math.abs(e.clientWidth/e.clientHeight-2/3)<.01));await page.locator('.naiBattleHead').getByRole('button',{name:'Close',exact:true}).click();assert.equal(await page.locator('.naiCardShell').count(),0);
  await page.setViewportSize({width:1600,height:1000});await page.locator('#naiProfileBtn').click();await page.locator('.naiProfileCard .naiCardOrnament').waitFor();await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiProfileHero')?.naturalWidth>0);await screenshot('profile');assert.equal(await page.locator('.naiProfileCard .naiCardAttributes>div').count(),4);assert(await page.locator('.naiProfileCard').evaluate(e=>e.querySelector('.naiCardPhotoWindow').clientHeight/e.clientHeight>.65));
  await page.getByRole('button',{name:'Position image',exact:true}).click();await page.getByLabel('Horizontal position',{exact:true}).fill('5');await page.getByRole('button',{name:'Save framing',exact:true}).click();await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiProfileHero').style.transform.includes('5%'));
  await page.setViewportSize({width:1000,height:760});assert(await page.locator('.naiProfilePanel').evaluate(e=>e.scrollWidth<=e.clientWidth+2));await screenshot('profile-compact');assert.deepEqual(errors,[]);
  console.log('Card artwork passed: portrait sizing, >80% image window, external controls, gallery actions, fullscreen, saved framing, click/keyboard voting, set mosaics, blind mode, profile stats and compact layout.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
