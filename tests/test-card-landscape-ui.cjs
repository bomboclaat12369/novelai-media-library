const assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1',NAI_CARD_FEATURES_DEMO:'1',NAI_LANDSCAPE_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',c=>reject(Error(stderr+c)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu']});const page=await browser.newPage({viewport:{width:1600,height:1000}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();await page.locator('#naiBattlesBtn').click();await page.locator('#naiBattleLeaderboard').click();
  const board=page.locator('.naiBattleBoard'),cards=page.locator('.naiBattleRankCard');await cards.first().waitFor();
  const ids=await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiGetLibrary().media.slice(0,4).map(m=>m.id));
  const land=page.locator('.naiBattleRankCard[data-entry-id="'+ids[1]+'"]'),portrait=page.locator('.naiBattleRankCard[data-entry-id="'+ids[0]+'"]');
  await page.waitForFunction(id=>{const im=document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleRankCard[data-entry-id="'+id+'"] img[data-media-id]');return im?.complete&&im.naturalWidth>0;},ids[1]);
  assert.equal(await land.locator('.naiTradingCard').getAttribute('data-orientation'),'landscape');
  const ratio=loc=>loc.evaluate(e=>e.clientWidth/e.clientHeight);
  assert(Math.abs(await ratio(land.locator('.naiTradingCard'))-1.5)<.01);assert(Math.abs(await ratio(portrait.locator('.naiTradingCard'))-2/3)<.01);
  assert(await land.evaluate(e=>e.clientWidth)>1.8*await portrait.evaluate(e=>e.clientWidth));
  assert.match(await land.locator('.naiCardName small').textContent(),/^#\d+$/);
  const geometry=loc=>loc.evaluate(e=>{const r=e.getBoundingClientRect(),p=e.querySelector('.naiCardPhotoWindow,.naiBattleGalleryVisual').getBoundingClientRect(),n=e.querySelector('.naiCardName').getBoundingClientRect(),t=e.querySelector('.naiCardTitleArt')?.getBoundingClientRect();return {photo:p.height/r.height,footerTop:(n.top-r.top)/r.height,footerHeight:n.height/r.height,title:t?t.width/r.width:null};});
  const base=await geometry(land.locator('.naiTradingCard'));assert(Math.abs(base.photo-.84)<.003);assert(Math.abs(base.footerTop-.878)<.003);assert(Math.abs(base.footerHeight-.077)<.003);
  // Large mixed collection stays virtual, ordered, and free of overlapping cells.
  const checkGrid=async()=>{await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));assert(await cards.count()<65);assert(await cards.evaluateAll(nodes=>{const boxes=nodes.map(e=>e.getBoundingClientRect());return boxes.every((a,i)=>boxes.slice(i+1).every(b=>a.right<=b.left+1||b.right<=a.left+1||a.bottom<=b.top+1||b.bottom<=a.top+1));}));};
  await checkGrid();await page.screenshot({path:'/tmp/card-landscape-board.png'});
  await board.evaluate(e=>e.scrollTop=e.scrollHeight);await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiCardPosition')].some(e=>e.textContent.startsWith('#360')));await checkGrid();await board.evaluate(e=>e.scrollTop=0);await land.waitFor();await checkGrid();
  await land.locator('.naiBattleGalleryVisual').click();const front=page.locator('.naiExpandedCard'),flipper=page.locator('.naiFlipCard');await page.waitForFunction(()=>{const im=document.getElementById('nai-media-host').shadowRoot.querySelector('.naiExpandedCard img[data-media-id]');return im?.complete&&im.naturalWidth>0;});
  assert(Math.abs(await ratio(flipper)-1.5)<.01);assert.equal(await page.locator('.naiCardBack').getAttribute('data-orientation'),'landscape');
  const full=await geometry(front);for(const k of ['photo','footerTop','footerHeight','title'])assert(Math.abs(full[k]-base[k])<.006,k);await page.screenshot({path:'/tmp/card-landscape-full.png'});
  await page.locator('.naiBattleLight').getByRole('button',{name:'Position card',exact:true}).click();const editor=page.getByRole('dialog',{name:'Position card image',exact:true}),preview=editor.locator('.naiCardEditPreview');await preview.waitFor();assert(Math.abs(await ratio(preview)-1.5)<.01);assert(await preview.locator('.naiCardPhotoWindow img').evaluate(im=>im.naturalWidth===2400&&im.naturalHeight===1601));
  for(const k of ['photo','footerTop','footerHeight','title'])assert(Math.abs((await geometry(preview))[k]-base[k])<.006,'position '+k);
  await editor.getByLabel('Zoom',{exact:true}).fill('1.75');await editor.getByLabel('Horizontal position',{exact:true}).fill('-14');await page.screenshot({path:'/tmp/card-landscape-position.png'});await editor.getByRole('button',{name:'Save framing',exact:true}).click();await editor.waitFor({state:'detached'});assert(await front.locator('.naiCardPhotoWindow img').evaluate(im=>im.style.transform.includes('scale(1.75)')));
  // Reused fullscreen image must change orientation as navigation changes the source.
  await page.locator('.naiBattleBrowse').getByRole('button',{name:'←',exact:true}).click();await front.locator('img[data-media-id="'+ids[0]+'"]').waitFor();assert(Math.abs(await ratio(flipper)-2/3)<.01);
  await page.locator('.naiBattleBrowse').getByRole('button',{name:'→',exact:true}).click();await front.locator('img[data-media-id="'+ids[1]+'"]').waitFor();assert(Math.abs(await ratio(flipper)-1.5)<.01);
  await page.locator('.naiBattleLight').getByRole('button',{name:'Focus comparisons',exact:true}).click();const battle=page.locator('.naiBattleCard[data-entry-id="'+ids[1]+'"] .naiTradingCard');await battle.waitFor();await page.waitForFunction(id=>{const e=document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleCard[data-entry-id="'+id+'"] .naiTradingCard');return e&&Math.abs(e.clientWidth/e.clientHeight-1.5)<.01;},ids[1]);assert(await battle.locator('.naiCardPhotoWindow img').evaluate(im=>im.naturalWidth===2400));await page.screenshot({path:'/tmp/card-landscape-battle.png'});
  await page.locator('#naiBattleLeaderboard').click();await cards.first().waitFor();const exif=page.locator('.naiBattleRankCard[data-entry-id="'+ids[3]+'"]');await exif.locator('.naiBattleGalleryVisual').click();await page.waitForFunction(()=>{const im=document.getElementById('nai-media-host').shadowRoot.querySelector('.naiExpandedCard .naiCardPhotoWindow img');return im?.complete&&im.naturalWidth===1600;});assert(await front.locator('.naiCardPhotoWindow img').evaluate(im=>im.naturalWidth===1600&&im.naturalHeight===2403));assert(Math.abs(await ratio(flipper)-2/3)<.01);
  await page.locator('.naiBattleLight').getByRole('button',{name:'Close image',exact:true}).click();await page.setViewportSize({width:700,height:760});await checkGrid();await page.setViewportSize({width:2560,height:1440});await checkGrid();assert.deepEqual(errors,[]);
  console.log('Portrait/landscape proportions, number-only labels, bounded mixed-grid scrolling, fullscreen navigation, original-resolution positioning and saved framing, battle sizing, EXIF rotation, and responsive layouts passed.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
