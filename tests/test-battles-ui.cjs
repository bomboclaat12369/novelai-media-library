const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,'release-userscript.json'))),payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{cwd:dir});let stderr='',browser;server.stderr.on('data',b=>stderr+=b);
 try{
 await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});context.setDefaultTimeout(15000);
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 const lib=await api('library'),owner=lib.characters[0].id,main=new Set(lib.media.filter(m=>m.in_all).map(m=>m.id));
 const state=kind=>api('battles/state',{character_id:owner,kind});
 for(const standalone of [true,false]){
  const oldProfile=await api('profile/state',{character_id:owner});await api('profile/save',{character_id:owner,revision:oldProfile.profile.revision,profile:{photos:[],measurements:{},notes:''}});
  const page=await context.newPage(),errors=[];let battleRequests=0;page.on('pageerror',e=>errors.push(e.message));
  if(!standalone){
   await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
   await page.exposeFunction('companionRequest',async o=>{if(o.url.includes('/api/battles/')&&!o.url.includes('/api/battles/state'))battleRequests++;const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
   await page.addInitScript(({payload,version})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
   },{payload,version:config.version});
  }
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');
  await page.getByText('Local library connected',{exact:true}).waitFor();
  await page.locator('#naiProfileBtn').click();await page.getByRole('button',{name:'Edit profile',exact:true}).click();
  await page.getByLabel('Height feet',{exact:true}).fill('5');await page.getByLabel('Height inches',{exact:true}).fill('7.5');await page.getByLabel('Height status',{exact:true}).selectOption('confirmed');
  await page.getByLabel('Bust',{exact:true}).fill('35');await page.getByLabel('Bra size',{exact:true}).fill('34D (US)');
  await page.getByRole('button',{name:'Choose photos',exact:true}).click();await page.getByLabel('Profile photo category',{exact:true}).selectOption('dress');assert.equal(await page.locator('.naiProfilePickGrid button').count(),8);await page.locator('.naiProfilePickGrid button').first().click();
  await page.getByRole('button',{name:'Save profile',exact:true}).click();await page.getByRole('button',{name:'Edit profile',exact:true}).waitFor();
  await page.getByRole('button',{name:'Close',exact:true}).click();await page.locator('#naiProfileBtn').click();await page.locator('.naiProfileHero').waitFor();assert((await page.locator('.naiProfileBody').textContent()).includes('5 ft 7.5 in'));
  await page.getByRole('button',{name:'Close',exact:true}).click();
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia(id),lib.media[1].id);
  await page.locator('#naiProfileBtn').click();await page.getByRole('button',{name:'Edit profile',exact:true}).click();await page.getByRole('button',{name:'Choose photos',exact:true}).click();await page.getByRole('button',{name:'Use '+lib.media[1].original_name,exact:true}).click();const makeMain=page.getByRole('button',{name:'Make profile photo',exact:true});if(await makeMain.count())await makeMain.click();await page.getByRole('button',{name:'Save profile',exact:true}).click();await page.getByRole('button',{name:'Edit profile',exact:true}).waitFor();
  assert.equal((await api('profile/state',{character_id:owner})).profile.photos[0],lib.media[1].id);
  if(standalone)await page.screenshot({path:'/tmp/profile-ui.png'});
  await page.getByRole('button',{name:'Close',exact:true}).click();
  if(!standalone){assert.equal(await page.locator('#naiBattlesBtn,#naiPlaceImage,.naiPlaceSet').count(),0);await page.locator('#naiProfileBtn').click();assert.equal(await page.getByRole('button',{name:'Trophy Cabinet',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Open battles',exact:true}).count(),0);assert.equal(battleRequests,0);assert.deepEqual(errors,[]);await page.close();continue;}
  await page.locator('#naiBattlesBtn').click();
  await page.getByLabel('Mode',{exact:true}).selectOption('winner');await page.getByLabel('Session',{exact:true}).selectOption('10');await page.locator('#naiBattleStart').click();
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].length===2&&[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled)).catch(async error=>{console.error({standalone,errors,ui:await page.locator('.naiBattleError').textContent(),images:await page.locator('.naiBattlePhoto,.naiBattleSetImage').evaluateAll(images=>images.map(im=>({src:im.src,complete:im.complete,width:im.naturalWidth}))) });throw error});
  assert(await page.locator('.naiBattlePhoto').first().evaluate(im=>im.getBoundingClientRect().height>innerHeight*.65));
  assert(await page.locator('.naiBattlePhoto').evaluateAll(images=>images.every(im=>im.naturalWidth>=1600&&im.naturalHeight===2400)));
  const ids=await page.locator('.naiBattleCard').evaluateAll(cards=>cards.map(c=>c.dataset.entryId));assert(ids.every(id=>main.has(id)));
  const before=await state('images');assert.equal(before.entries.length,4);
  await page.locator('.naiBattleChoose').first().click();await page.waitForFunction(n=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.includes(n+' saved votes'),before.votes+1);
  const after=await state('images');assert.equal(after.votes,before.votes+1);assert([after.session.pair.left,after.session.pair.right].includes(ids[0]));
  await page.locator('.naiBattleCard[data-entry-id="'+ids[0]+'"] .naiBattleMmr').click();await page.locator('.naiRankHistory svg').waitFor();assert((await page.locator('.naiRankHistory').textContent()).includes('Recent comparisons'));await page.getByRole('button',{name:'Close history',exact:true}).click();
  const flagId=await page.locator('.naiBattleCard').first().getAttribute('data-entry-id');await page.locator('.naiBattleCard').first().getByRole('button',{name:'Flag for removal',exact:true}).click();await page.locator('.naiBattleCard').first().getByRole('button',{name:'Clear removal flag',exact:true}).waitFor();assert((await api('library')).media.find(m=>m.id===flagId).flagged_for_removal);
  await page.locator('.naiBattleCard').first().getByRole('button',{name:'Clear removal flag',exact:true}).click();
  await page.locator('#naiBattleUndo').click();await page.waitForFunction(n=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.includes(n+' saved votes'),before.votes);
  await page.getByRole('button',{name:'Close',exact:true}).click();await page.locator('#naiBattlesBtn').click();await page.locator('.naiBattleCard').first().waitFor();
  assert.deepEqual((await state('images')).session.pair,before.session.pair);
  await page.getByLabel('Mode',{exact:true}).selectOption('placements');await page.getByLabel('Battle category',{exact:true}).selectOption('dress');await page.locator('#naiBattleStart').click();await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.startsWith('2 eligible images'));const scoped=await state('images');assert.equal(scoped.entries.length,4);assert.equal(scoped.session.category,'dress');
  await page.getByLabel('Battle type',{exact:true}).selectOption('sets');await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.startsWith('2 eligible sets'));
  await page.getByLabel('Minimum set images',{exact:true}).fill('5');await page.getByLabel('Similar-size opponents',{exact:true}).check();await page.locator('#naiBattleStart').click();
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].length===2&&[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose')].every(b=>!b.disabled));
  assert.equal(await page.locator('.naiBattleSetImage').count(),11);assert.equal(await page.getByRole('heading',{name:'Small set',exact:true}).count(),0);
  assert(await page.locator('.naiBattleSetImage').evaluateAll(images=>images.every(im=>im.naturalWidth>=1600&&im.naturalHeight===2400)));
  await page.locator('.naiBattleCard').first().getByRole('button',{name:'Browse full set ⛶',exact:true}).click();await page.locator('.naiBattleLight').waitFor();const navBefore=(await state('sets')).votes;await page.keyboard.press('ArrowRight');assert((await page.locator('.naiBattleLight .naiBattleBrowse').textContent()).includes('2 /'));assert.equal((await state('sets')).votes,navBefore);await page.getByRole('button',{name:'Close image',exact:true}).click();
  assert(await page.locator('.naiBattleWrap').evaluate(w=>w.scrollHeight<=w.clientHeight+2));
  if(standalone)await page.screenshot({path:'/tmp/battles-sets.png'});
  const setBefore=await state('sets');await page.keyboard.press('ArrowRight');await page.waitForFunction(n=>document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.includes(n+' saved votes'),setBefore.votes+1);
  await page.locator('#naiBattleTrophies').click();assert((await page.locator('.naiCabinet').textContent()).includes('Comparisons completed'));await page.locator('#naiBattleLeaderboard').click();assert.equal(await page.locator('.naiBattleRankCard').count(),3);assert((await page.locator('.naiBattleBoard').textContent()).includes('Provisional'));
  assert.equal((await state('images')).votes,before.votes);await page.locator('#naiBattleUndo').click();
  await page.getByRole('button',{name:'Close',exact:true}).click();
  const ratingStart=await api('battles/start',{character_id:owner,kind:'images',revision:(await state('images')).revision,mode:'rank',limit:10});
  const ranking=await api('battles/vote',{character_id:owner,kind:'images',revision:ratingStart.revision,pair_id:ratingStart.session.pair.id,outcome:'left'});
  await page.locator('#naiProfileBtn').click();await page.locator('.naiProfileTop button').first().waitFor();assert((await page.locator('.naiProfileTop button').first().textContent()).includes(Math.round(ranking.entries[0].rating)+' MMR'));
  await page.getByRole('button',{name:'Trophy Cabinet',exact:true}).click();await page.locator('.naiTrophyCard').first().waitFor();assert((await page.locator('.naiCabinet').textContent()).includes('Comparisons completed'));await page.getByRole('button',{name:'Overview',exact:true}).click();await page.getByRole('button',{name:'Close',exact:true}).click();await page.locator('#sortSelect').selectOption('rank_high');await page.locator('#grid .naiLibraryRank').first().waitFor();assert(await page.locator('#sortDirectionBtn').isDisabled());const rankedId=ranking.entries[0].id;
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia(id),rankedId);await page.locator('#editImagesBtn').click();await page.locator('#naiEditRemoval').click();await page.locator('#naiEditRemoval').filter({hasText:'Clear removal flag'}).waitFor();await page.getByRole('button',{name:'Close',exact:true}).click();await page.locator('[data-cat="flagged_removal"]').click();await page.waitForFunction(id=>{const tiles=[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('#grid .tile[data-id]')];return tiles.length===1&&tiles[0].dataset.id===id},rankedId);await page.locator('#grid .naiRemovalMark').waitFor();assert.equal(await page.locator('#grid .naiRemovalMark').count(),1);await page.locator('#editImagesBtn').click();await page.locator('#naiEditRemoval').click();await page.getByRole('button',{name:'Close',exact:true}).click();await page.waitForFunction(()=>!document.getElementById('nai-media-host').shadowRoot.querySelector('#grid .tile[data-id]'));
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Standalone battles passed, including original-resolution image/set tiles. NovelAI keeps profiles and read-only badges but has no battle controls or battle mutations.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
