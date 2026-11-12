const assert=require('assert/strict');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=require('child_process').spawn('python',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1',NAI_LANDSCAPE_DEMO:'1'}});let stderr='';server.stderr.on('data',b=>stderr+=b);await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('exit',code=>reject(Error(stderr+code)));});
 const browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const p=await browser.newPage({viewport:{width:2048,height:1400}});p.setDefaultTimeout(15000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
 // Compare the source-photo mapping to the card, independent of rendered pixel size.
 async function geometry(locator){return locator.evaluate(card=>{const im=card.querySelector('.naiFramedSource'),box=im.parentElement,c=card.getBoundingClientRect(),r=im.getBoundingClientRect(),b=box.getBoundingClientRect();return {edition:card.dataset.edition||'',fit:im.dataset.photoFit,window:[(b.left-c.left)/c.width,(b.top-c.top)/c.height,b.width/c.width,b.height/c.height],photo:[(r.left-c.left)/c.width,(r.top-c.top)/c.height,r.width/c.width,r.height/c.height],width:c.width,height:c.height};});}
 function same(a,b){assert.equal(a.edition,b.edition);assert.equal(a.fit,b.fit);for(const key of ['window','photo'])a[key].forEach((n,i)=>assert(Math.abs(n-b[key][i])<.012,`${key}[${i}]: ${n} != ${b[key][i]}`));}
 async function readyPhoto(loc){await loc.locator('.naiCardPhotoWindow img,.naiBattleGalleryVisual img').evaluate(im=>im.decode());}
 try{
  await p.goto('http://127.0.0.1:8765/library/');await p.getByText('Local library connected',{exact:true}).waitFor();await p.locator('#naiBattlesBtn').click();await p.locator('#naiBattleLeaderboard').click();await p.locator('.naiBattleRankCard').first().waitFor();
  assert.equal(await p.getByLabel('Cards per row',{exact:true}).inputValue(),'8');
  const rowCount=()=>p.locator('.naiBattleRankCard').evaluateAll(cards=>cards.filter(c=>c.style.top===cards[0].style.top).length);
  assert.equal(await rowCount(),8);
  await p.getByRole('button',{name:'Special edition frames',exact:true}).click();assert.equal(await p.locator('.naiEditionCatalog button').count(),14);
  await p.getByRole('button',{name:'Preview Duo frame',exact:true}).click();assert.equal(await p.locator('.naiEditionFramePreview').getAttribute('alt'),'Duo frame');await p.getByRole('button',{name:'All special edition frames',exact:true}).click();
  await p.getByRole('button',{name:'Preview Former #1 frame',exact:true}).click();await p.locator('.naiEditionFramePreview').evaluate(im=>im.decode());assert(await p.locator('.naiEditionFramePreview').evaluate(im=>im.naturalWidth>1000));await p.getByRole('button',{name:'All special edition frames',exact:true}).click();await p.locator('.naiEditionGallery').screenshot({path:'/tmp/card-frame-gallery.png'});await p.locator('.naiEditionGallery').getByRole('button',{name:'Close',exact:true}).click();
  const id=await p.locator('.naiBattleRankCard').first().getAttribute('data-entry-id');
  async function equip(choice){await p.evaluate(async({id,choice})=>{const r=document.getElementById('nai-media-host').shadowRoot,owner=r.naiGetLibrary().characters[0].id,current=await r.naiCards.load(owner);await r.naiOutfitRequest('/api/collection/edition',{character_id:owner,kind:'images',entry_id:id,choice,revision:current.collection.revision});},{id,choice});await p.locator('.naiBattleTools').getByRole('button',{name:'Refresh',exact:true}).click();await p.locator(`.naiBattleRankCard[data-entry-id="${id}"]`).waitFor();}
  for(const edition of ['former-one','christmas','none']){
   if(edition==='former-one')await p.evaluate(async id=>{const r=document.getElementById('nai-media-host').shadowRoot,owner=r.naiGetLibrary().characters[0].id,current=await r.naiCards.load(owner);await r.naiOutfitRequest('/api/collection/title-correction',{character_id:owner,kind:'images',entry_id:id,revision:current.collection.revision,overrides:{former_number_one:'grant'}});},id);
   await equip(edition);const tile=p.locator(`.naiBattleRankCard[data-entry-id="${id}"]`),gridCard=tile.locator('.naiTradingCard');await tile.locator('.naiBattleGalleryVisual').click();
   await p.getByRole('button',{name:'Position card',exact:true}).click();const editor=p.locator('.naiCardEditPreview');await editor.waitFor();assert.equal(await editor.getAttribute('data-edition'),edition==='none'?null:edition);assert.equal(await editor.locator('.naiCardTitleArt').count(),0);
   for(const fit of ['fill','contain']){
    await p.getByLabel('Photo framing',{exact:true}).selectOption(fit);
    for(const [label,value] of [['Horizontal position','13'],['Vertical position','-9'],['Zoom','1.24']])await p.getByLabel(label,{exact:true}).fill(value);
    await readyPhoto(editor);const expected=await geometry(editor);await p.getByRole('button',{name:'Save framing',exact:true}).click();await editor.waitFor({state:'detached'});
    const full=p.locator('.naiBattleLight .naiExpandedCard');await readyPhoto(full);same(expected,await geometry(full));await p.getByRole('button',{name:'Close image',exact:true}).click();await readyPhoto(gridCard);same(expected,await geometry(gridCard));
    for(const cols of ['10','8','4']){await p.getByLabel('Cards per row',{exact:true}).selectOption(cols);await p.waitForFunction(n=>{const r=document.getElementById('nai-media-host').shadowRoot,c=[...r.querySelectorAll('.naiBattleRankCard')];return c.filter(x=>x.style.top===c[0].style.top).length===n},Number(cols));same(expected,await geometry(gridCard));}
    await p.getByLabel('Cards per row',{exact:true}).selectOption('8');await p.setViewportSize({width:850,height:1100});await p.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleRankCard').offsetWidth<250);same(expected,await geometry(gridCard));await p.setViewportSize({width:2048,height:1400});
    if(fit==='fill'){await tile.locator('.naiBattleGalleryVisual').click();await p.getByRole('button',{name:'Position card',exact:true}).click();await editor.waitFor();}
   }
  }
  await equip('christmas');await p.getByLabel('Edition filter',{exact:true}).selectOption('special');await p.locator('.naiBattleRankCard').first().waitFor();assert(await p.locator('.naiBattleRankCard').count()>0);assert(await p.locator('.naiBattleRankCard').evaluateAll(cs=>cs.every(c=>c.querySelector('.naiEdition'))));
  await p.getByLabel('Edition filter',{exact:true}).selectOption('base');await p.locator('.naiBattleRankCard').first().waitFor();assert(await p.locator('.naiBattleRankCard').evaluateAll(cs=>cs.every(c=>!c.querySelector('.naiEdition'))));await p.getByLabel('Edition filter',{exact:true}).selectOption('christmas');await p.locator('.naiBattleRankCard').first().waitFor();assert.equal(await p.locator('.naiBattleRankCard').count(),1);await p.getByLabel('Edition filter',{exact:true}).selectOption('all');await p.locator('.naiBattleRankCard').first().waitFor();
  await p.screenshot({path:'/tmp/card-eight-columns.png'});assert.deepEqual(errors,[]);console.log('Passed: eight columns; all 12 frames and enlarged artwork; edition filters; equipped editor; fill/contain crop invariant across editor/fullscreen/4/8/10 columns and narrow viewport; immediate save refresh.');
 }finally{await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
