// Real-browser regression for raster ranks inheriting ordinary photo styles.
const assert=require('assert/strict'),fs=require('fs'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('exit',c=>reject(Error(stderr+c)))});
  let executablePath=process.env.NAI_CHROMIUM,args=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage'];
  if(process.env.NAI_CHROMIUM_PACKAGE){const {default:packaged}=await import(process.env.NAI_CHROMIUM_PACKAGE+'/build/index.js');executablePath=await packaged.executablePath();args=packaged.args;}
  browser=await chromium.launch({executablePath,headless:true,args});const page=await browser.newPage({viewport:{width:900,height:1050}});page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();
  await page.evaluate(async()=>{const r=document.getElementById('nai-media-host').shadowRoot,owner=r.naiGetLibrary().characters[0].id,board=await r.naiOutfitRequest('/api/battles/summary',{character_id:owner,kind:'images'}),tiers=['Bronze','Silver','Gold','Platinum','Diamond','Master','Grandmaster','Placement'];board.entries.forEach((e,i)=>{e.tier=tiers[i%tiers.length];e.played=20});r.naiRankingsChanged(board);});
  await page.locator('#grid .naiLibraryRank svg.naiRankEmblem').first().waitFor();
  for(const width of [900,1600]){
   await page.setViewportSize({width,height:1050});
   const marks=await page.locator('#grid .naiLibraryRank').evaluateAll(es=>es.map(e=>{const svg=e.querySelector('svg'),rect=svg?.getBoundingClientRect();return {tier:e.title.split(' · ')[0],w:rect?.width,h:rect?.height,ordinaryImages:e.querySelectorAll('img').length,photos:e.closest('.tile').querySelectorAll('img').length}}));
   assert(marks.length>=8);for(const m of marks){assert.equal(m.w,24,m.tier);assert.equal(m.h,24,m.tier);assert.equal(m.ordinaryImages,0);assert.equal(m.photos,1)}assert.equal(new Set(marks.map(m=>m.tier)).size,8);
  }
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('#grid .tile img')].every(i=>i.complete&&i.naturalWidth>0));
  await page.screenshot({path:'/tmp/rank-badges-grid-fixed.png'});
  await page.locator('#grid .tile[data-id]').first().click();await page.locator('.naiViewerRankBadge svg.naiRankEmblem').first().waitFor();
  const viewer=await page.locator('.naiViewerRankBadge svg.naiRankEmblem').first().boundingBox();assert.equal(viewer.width,46);assert.equal(viewer.height,46);
  const checks=await page.evaluate(()=>{
   const r=document.getElementById('nai-media-host').shadowRoot,wrap=document.createElement('div');wrap.id='rank-size-probes';wrap.style.cssText='position:fixed;inset:20px;z-index:2147483647;background:#161c29;display:flex;flex-wrap:wrap;align-content:start;gap:12px;padding:12px';r.append(wrap);const result=[];
   for(const tier of ['Bronze','Silver','Gold','Platinum','Diamond','Master','Grandmaster','Placement'])for(const kind of ['badge','trophy','set','base']){
    const host=document.createElement('div');host.style.cssText='width:180px;height:110px;position:relative';let icon;
    if(kind==='badge'){const badge=r.naiRanks.badge(tier);host.append(badge);icon=badge.querySelector('svg');}
    if(kind==='trophy'){host.className='naiTrophyMedal';icon=r.naiRanks.emblem(tier);host.append(icon);}
    if(kind==='set'){host.className='naiSetTile';const mark=document.createElement('span');mark.className='naiLibraryRank';icon=r.naiRanks.emblem(tier);mark.append(icon);host.append(mark);}
    if(kind==='base'){host.className='naiCardRankShield';host.append(r.naiRanks.badge(tier));icon=host.querySelector('svg');}
    wrap.append(host);const box=icon.getBoundingClientRect();result.push({tier,kind,width:box.width,height:box.height,ordinaryImages:host.querySelectorAll('img').length});
   }return result;
  });
  for(const c of checks){const expected={badge:30,trophy:54,set:24}[c.kind];if(expected){assert.equal(c.width,expected,c.kind+' '+c.tier);assert.equal(c.height,expected)}else{assert(c.width>=30&&c.width<=82);assert.equal(c.width,c.height)}assert.equal(c.ordinaryImages,0)}
  await page.screenshot({path:'/tmp/rank-badges-contexts-fixed.png'});assert.deepEqual(errors,[]);
  console.log('Passed in Chromium: all seven ranks plus Placement; real thumbnail grid at 900/1600px; main viewer; set badges; profile/battle badges; trophies; base-card rank slots. Photos stay unobstructed; no browser errors.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
