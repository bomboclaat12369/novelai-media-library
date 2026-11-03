const assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('exit',c=>reject(Error(stderr+c)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/chromium',headless:true,args:['--no-sandbox','--disable-gpu']});const p=await browser.newPage({viewport:{width:1700,height:1100}});p.setDefaultTimeout(20000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto('http://127.0.0.1:8765/library/');await p.getByText('Local library connected',{exact:true}).waitFor();
  const seed=await p.evaluate(async()=>{const r=document.getElementById('nai-media-host').shadowRoot,owner=r.naiGetLibrary().characters[0].id,board=await r.naiOutfitRequest('/api/battles/summary',{character_id:owner,kind:'images'}),e=board.entries[5];let current=await r.naiCards.load(owner);current=await r.naiOutfitRequest('/api/collection/edition',{character_id:owner,revision:current.collection.revision,entry_id:e.id,add_traits:['cosplay']});await r.naiOutfitRequest('/api/collection/frame',{character_id:owner,revision:current.collection.revision,key:'image:'+e.images[0],media_id:e.images[0],frame:{x:0,y:0,zoom:1,fit:'fill'}});return {id:e.id,name:e.name,owner,ratings:board.entries.map(e=>[e.id,e.rating])};});
  await p.locator('#naiBattlesBtn').click();await p.locator('#naiBattleLeaderboard').click();await p.getByLabel('Search leaderboard',{exact:true}).fill(seed.name);
  const card=()=>p.locator('.naiBattleRankCard[data-entry-id="'+seed.id+'"]');
  await card().locator('.naiEdition[data-edition=cosplay]').waitFor();assert.equal(await p.locator('.naiCardDebugPanel').count(),0);
  await p.getByLabel('Show special edition frames',{exact:true}).uncheck();await card().locator('.naiTradingCard:not(.naiEdition)').waitFor();
  await p.getByLabel('Debug mode',{exact:true}).check();await card().locator('.naiEdition[data-edition=cosplay]').waitFor();
  await card().getByText('Custom crop',{exact:true}).waitFor();assert(await card().locator('.naiFramedSource').evaluate(im=>getComputedStyle(im).boxShadow.includes('255, 38, 63')));
  await card().getByLabel('Add trait for '+seed.name,{exact:true}).selectOption('christmas');await card().getByRole('button',{name:'Remove Christmas trait',exact:true}).waitFor();
  await card().getByLabel('Frame for '+seed.name,{exact:true}).selectOption('christmas');await card().locator('.naiEdition[data-edition=christmas]').waitFor();
  await card().getByRole('button',{name:'Remove Cosplay trait',exact:true}).click();await p.waitForFunction(id=>!document.getElementById('nai-media-host').shadowRoot.querySelector(`[data-entry-id="${id}"] .naiDebugTraits`)?.textContent.includes('Cosplay'),seed.id);
  await card().getByRole('button',{name:'Edit traits and edition for '+seed.name,exact:true}).click();await p.getByLabel('Displayed frame',{exact:true}).waitFor();assert.equal(await p.getByLabel('Rating display',{exact:true}).count(),0);await p.locator('.naiCollectionOverlay').getByRole('button',{name:'Close',exact:true}).click();
  await card().getByRole('button',{name:'Position crop for '+seed.name,exact:true}).click();await p.getByRole('button',{name:'Reset framing',exact:true}).click();await p.getByRole('button',{name:'Save framing',exact:true}).click();await card().getByText('Default crop',{exact:true}).waitFor();
  await p.getByLabel('Crop filter',{exact:true}).selectOption('custom');await card().waitFor({state:'detached'});await p.getByLabel('Crop filter',{exact:true}).selectOption('default');await card().waitFor();
  await p.getByLabel('Search leaderboard',{exact:true}).fill('');await p.getByLabel('Crop filter',{exact:true}).selectOption('all');await p.locator('.naiBattleBoard').evaluate(e=>e.scrollTop=650);await p.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleBoard').scrollTop>=650);
  // Edit a mounted card without jumping back to the start of the gallery.
  const target=p.locator('.naiCardDebugPanel').filter({has:p.locator('select[aria-label^="Add trait"]')}).last();const targetName=await target.locator('.naiDebugFilename').textContent();await target.getByLabel('Add trait for '+targetName,{exact:true}).selectOption('birthday');await p.locator('.naiCardDebugPanel').filter({hasText:targetName}).getByRole('button',{name:'Remove Birthday trait',exact:true}).waitFor();assert(await p.locator('.naiBattleBoard').evaluate(e=>e.scrollTop>0));
  await p.screenshot({path:'/tmp/card-debug-desktop.png'});
  await p.setViewportSize({width:1000,height:900});assert(await p.locator('.naiBattleBoard').evaluate(e=>e.scrollWidth<=e.clientWidth+2));await p.screenshot({path:'/tmp/card-debug-compact.png'});
  await p.reload();await p.getByText('Local library connected',{exact:true}).waitFor();await p.locator('#naiBattlesBtn').click();await p.locator('#naiBattleLeaderboard').click();assert(await p.getByLabel('Debug mode',{exact:true}).isChecked());
  await p.getByLabel('Search leaderboard',{exact:true}).fill(seed.name);await card().locator('.naiEdition[data-edition=christmas]').waitFor();await card().getByText('Default crop',{exact:true}).waitFor();
  const ratings=await p.evaluate(async owner=>{const r=document.getElementById('nai-media-host').shadowRoot,b=await r.naiOutfitRequest('/api/battles/summary',{character_id:owner,kind:'images'});return b.entries.map(e=>[e.id,e.rating]);},seed.owner);assert.deepEqual(ratings,seed.ratings);
  await p.getByLabel('Search leaderboard',{exact:true}).fill('');await p.getByLabel('Battle type',{exact:true}).selectOption('sets');await p.locator('.naiCardDebugPanel').first().waitFor();
  const setPanel=p.locator('.naiCardDebugPanel').first(),setName=await setPanel.locator('.naiDebugFilename').textContent();await setPanel.getByLabel('Add trait for '+setName,{exact:true}).selectOption('valentines');await setPanel.getByRole('button',{name:'Remove Valentine’s trait',exact:true}).waitFor();assert(await p.locator('.naiBattleRankCard .naiEdition[data-edition=valentines]').count()>0);
  await p.getByLabel('Battle type',{exact:true}).selectOption('images');await p.getByLabel('Search leaderboard',{exact:true}).fill(seed.name);await card().waitFor();
  await p.getByLabel('Debug mode',{exact:true}).uncheck();assert.equal(await p.locator('.naiCardDebugPanel').count(),0);assert.equal(await card().locator('.naiEdition').count(),0);assert.deepEqual(errors,[]);
  console.log('Passed: automatic sole trait; debug crop outline/status/filter; inline add/remove/display; saved framing reset; no rating-style selector; scroll retention; narrow layout; persisted toggle/edits; normal-view restoration; unchanged MMR.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
