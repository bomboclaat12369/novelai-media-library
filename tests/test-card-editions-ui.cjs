const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=require('child_process').spawn('python',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1'}});let stderr='';server.stderr.on('data',b=>stderr+=b);await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('exit',code=>reject(Error(stderr+code)));});
 const b=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const p=await b.newPage({viewport:{width:1440,height:1050}});p.setDefaultTimeout(15000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
 try{
  await p.goto('http://127.0.0.1:8765/library/');await p.getByText('Local library connected',{exact:true}).waitFor();
  const ids=await p.evaluate(()=>{const r=document.getElementById('nai-media-host').shadowRoot,l=r.naiGetLibrary();return {owner:l.characters[0].id,id:l.media.find(m=>m.in_all).id}});
  await p.locator('#naiBattlesBtn').click();await p.locator('#naiBattleLeaderboard').click();await p.locator('.naiBattleRankCard').first().waitFor();
  await p.locator('.naiBattleGalleryVisual').first().click();await p.locator('.naiExpandedCard .naiCardPhotoWindow img').waitFor();
  await p.locator('.naiExpandedCard').click();await p.locator('.naiCardUtilities>summary').click();
  const options=await p.getByLabel('Card edition',{exact:true}).locator('option').evaluateAll(es=>es.map(e=>e.value));
  for(const key of ['cosplay','pregnant-orchid','hall-of-fame','valentines','signature','birthday','halloween','hidden-gem','whore-stage','christmas'])assert(options.includes(key));
  assert(!options.includes('naked'));assert(!options.includes('video-premiere'));
  await p.getByLabel('Card edition',{exact:true}).selectOption('christmas');await p.getByLabel('Rating display',{exact:true}).selectOption('number');
  await p.getByRole('button',{name:'Save card appearance',exact:true}).click();await p.locator('.naiExpandedCard[data-edition=christmas]').waitFor({state:'attached'});
  await p.locator('.naiCardBackBody h2').click();await p.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiFlipCard').dataset.flipped==='false');
  await p.locator('.naiExpandedCard .naiEditionFrame').evaluate(im=>im.decode());
  assert.equal(await p.locator('.naiExpandedCard .naiCardPhotoWindow img').evaluate(e=>getComputedStyle(e).objectFit),'cover');
  await p.locator('.naiFlipCard').evaluate(e=>Promise.all(e.getAnimations({subtree:true}).map(a=>a.finished)));await p.screenshot({path:'/tmp/editions-live-card.png'});
  await p.getByRole('button',{name:'Position card',exact:true}).click();await p.getByLabel('Photo framing',{exact:true}).selectOption('contain');await p.getByRole('button',{name:'Save framing',exact:true}).click();
  await p.getByRole('button',{name:'Close image',exact:true}).click();
  await p.reload();await p.getByText('Local library connected',{exact:true}).waitFor();await p.locator('#naiBattlesBtn').click();await p.locator('#naiBattleLeaderboard').click();
  await p.locator('.naiEdition[data-edition=christmas]').first().waitFor();
  // Render every approved frame with actual app components, both photo orientations,
  // native rank assets, Captain, and live labels; no production records are touched.
  const summary=await p.evaluate(async()=>{
   const r=document.getElementById('nai-media-host').shadowRoot,owner=r.naiGetLibrary().characters[0].id;
   return r.naiOutfitRequest('/api/battles/summary',{character_id:owner,kind:'images'});
  });
  const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../assets/cards/editions/catalog.json')));
  for(const [id,edition] of Object.entries(catalog.editions)){
   await p.evaluate(async({id,rows,index})=>{
    const r=document.getElementById('nai-media-host').shadowRoot;let panel=r.querySelector('#edition-test');if(panel)panel.remove();panel=document.createElement('div');panel.id='edition-test';panel.style.cssText='position:fixed;inset:0;z-index:2147483647;background:#18202b;display:flex;justify-content:center;align-items:center';r.append(panel);
    const entry={...rows[1],edition_id:id,edition_settings:{rating_style:'side',captain_corner:index%2?'right':'left'},tier:['Bronze','Diamond','Grandmaster','Silver','Gold','Platinum','Master'][index%7],titles:[{id:'team_captain',name:'Captain'}],title_choice:'auto'};
    const im=document.createElement('img');const c=document.createElement('canvas');c.width=index%2?1200:800;c.height=index%2?800:1200;const ctx=c.getContext('2d');ctx.fillStyle='#588496';ctx.fillRect(0,0,c.width,c.height);im.src=c.toDataURL();await im.decode();
    const card=r.naiCards.lightCard(entry,rows,r.naiGetLibrary().characters[0].id,im,true);card.style.cssText+=';width:560px!important;height:800px!important';panel.append(card);await document.fonts.ready;await Promise.all([...card.querySelectorAll('img')].map(im=>im.decode()));
   },{id,rows:summary.entries,index:Object.keys(catalog.editions).indexOf(id)});
   const card=p.locator('#edition-test .naiEdition');assert.equal(await card.count(),1);
   const check=await card.evaluate(e=>{const frame=e.querySelector('.naiEditionFrame'),box=e.querySelector('.naiCardPhotoWindow'),c=e.querySelector('canvas'),im=box.querySelector('img');return {native:frame.naturalWidth,box:[box.offsetWidth,box.offsetHeight],left:box.offsetLeft,top:box.offsetTop,clip:getComputedStyle(e).clipPath,canvas:[c.width,c.height],fit:getComputedStyle(im).objectFit,rank:e.querySelector('.naiEditionRank').getBoundingClientRect().width}});
   assert(check.native>1000);assert(check.box.every(n=>n>300));assert(check.left>35&&check.top>50);assert.equal(check.clip,'none');assert(check.canvas[0]>=1000);assert.equal(check.fit,'cover');assert(check.rank>40);
   await card.screenshot({path:'/tmp/edition-'+id+'.png'});
  }
  await p.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#edition-test').remove());
  // An assigned set edition must retain the voting mosaic and hidden-rating mode.
  await p.getByLabel('Battle type',{exact:true}).selectOption('sets');await p.locator('.naiBattleRankCard').first().waitFor();
  await p.evaluate(async()=>{const r=document.getElementById('nai-media-host').shadowRoot,owner=r.naiGetLibrary().characters[0].id,current=await r.naiCards.load(owner),board=await r.naiOutfitRequest('/api/battles/summary',{character_id:owner,kind:'sets'});await r.naiOutfitRequest('/api/collection/edition',{character_id:owner,kind:'sets',entry_id:board.entries[0].id,choice:'cosplay',revision:current.collection.revision});});
  await p.locator('.naiBattleTools').getByRole('button',{name:'Refresh',exact:true}).click();await p.locator('.naiEdition[data-edition=cosplay]').waitFor();
  await p.locator('#naiBattleStart').click();await p.waitForFunction(()=>{const r=document.getElementById('nai-media-host').shadowRoot;return r.querySelectorAll('.naiBattleChoose').length===2&&[...r.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled)});
  assert(await p.locator('.naiBattleMosaic').count()>0);await p.getByLabel('Show MMR',{exact:true}).uncheck();assert.equal(await p.locator('.naiBattleCard .naiEdition').count(),0);
  await p.locator('.naiBattleChoose').first().click();await p.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled));
  assert.deepEqual(errors,[]);console.log('Passed: 12 editions render; native assets; seven ranks; portrait/landscape fill; picker save and refresh persistence; contain framing; no browser errors.');
 }finally{await b.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
