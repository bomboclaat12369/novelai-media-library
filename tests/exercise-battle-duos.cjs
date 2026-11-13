// Exercise the built standalone against the disposable library in duo_editor_fixture.py.
const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require('playwright');
const {duo:artwork} = require('../assets/cards/editions/catalog.json');

async function run() {
  const [, , base, channel, previewDir] = process.argv;
  const library = await fetch(base + '/api/library').then(r => r.json());
  const [group, setOnly] = library.sets;
  const owner = group.character_id;
  const summary = () => fetch(base + '/api/battles/summary', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({character_id:owner})
  }).then(r => r.json());
  const before = await summary();
  const duo = before.entries.find(e => e.name === group.name && e.duo_side);
  assert(duo && before.entries.some(e => e.name === setOnly.name && e.duo_side));
  const browser = await chromium.launch({channel, headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:960}, deviceScaleFactor:1});
    const errors = [], votes = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if(r.url().endsWith('/api/battles/vote'))votes.push(r.postDataJSON());});
    const button = (scope,name) => scope.getByRole('button',{name,exact:true});
    let overall;
    async function verifyFace(scope, side, ratingsVisible=true) {
      const card = scope.locator('.naiEdition[data-duo-side="'+side+'"]');
      const mid = duo.images[side==='front'?0:1];
      const im = card.locator('img.naiFramedSource');
      await card.waitFor({state:'visible'});
      const letters=await card.locator('.naiEditionLetters').getAttribute('aria-label');
      assert.equal(letters.endsWith(' · '+overall+' OVR'),ratingsVisible);
      assert.equal(letters.includes(' OVR'),ratingsVisible);
      assert.equal(await card.locator('.naiEditionRank').count(),0);
      await page.waitForFunction(({mid,side}) => {
        const root = document.getElementById('nai-media-host').shadowRoot;
        return [...root.querySelectorAll('.naiEdition[data-duo-side="'+side+'"] .naiFramedSource')]
          .some(i => i.dataset.mediaId===mid && i.complete && i.naturalWidth);
      }, {mid,side});
      const digest = await im.evaluate(async i => {
        await i.decode();
        const data = await (await fetch(i.src)).arrayBuffer();
        const sha = await crypto.subtle.digest('SHA-256',data);
        return Array.from(new Uint8Array(sha),x=>x.toString(16).padStart(2,'0')).join('');
      });
      assert.equal(digest,library.media.find(i=>i.id===mid).sha256);
      const metrics = await card.evaluate(async node=>{
        const art=node.querySelector('.naiEditionFrame');await art.decode();
        await Promise.all(node.getAnimations().map(animation=>animation.finished));
        const photo=node.querySelector('.naiFramedSource'),box=photo.parentElement.getBoundingClientRect(),outer=node.getBoundingClientRect();
        return {frame:[art.naturalWidth,art.naturalHeight], ratio:outer.width/outer.height,
          aperture:box.width/box.height, left:(box.x-outer.x)/outer.width, top:(box.y-outer.y)/outer.height,
          bottom:(outer.bottom-box.bottom)/outer.height,photoWidth:photo.getBoundingClientRect().width,
          outerWidth:outer.width,outerHeight:outer.height,windowWidth:box.width,windowHeight:box.height,
          photoX:photo.getBoundingClientRect().x+photo.getBoundingClientRect().width/2-outer.x,
          photoY:photo.getBoundingClientRect().y+photo.getBoundingClientRect().height/2-outer.y,naturalWidth:photo.naturalWidth,naturalHeight:photo.naturalHeight};
      });
      assert.deepEqual(metrics.frame,[1050,1500]);assert(Math.abs(metrics.ratio-.7)<.005, JSON.stringify(metrics));
      assert(Math.abs(metrics.aperture-.75)<.008 && Math.abs(metrics.left-.1)<.006,JSON.stringify(metrics));
      assert(Math.abs(metrics.top-.13)<.006 && Math.abs(metrics.bottom-(1-1315/1500))<.006,JSON.stringify(metrics));
      const frame=library.characters.find(c=>c.id===owner).collection.frames['image:'+mid]||{};
      const ref=frame.reference||((frame.x||frame.y||(frame.zoom&&frame.zoom!==1))?artwork.legacyWindow:null);
      const bw=ref?metrics.outerWidth*ref.width:metrics.windowWidth, bh=ref?metrics.outerHeight*ref.height:metrics.windowHeight;
      const cx=(ref?ref.left:metrics.left)*metrics.outerWidth+bw*(.5+(frame.x||0)/100);
      const cy=(ref?ref.top:metrics.top)*metrics.outerHeight+bh*(.5+(frame.y||0)/100);
      assert(Math.abs(metrics.photoX-cx)<4&&Math.abs(metrics.photoY-cy)<4,JSON.stringify({metrics,frame,cx,cy}));
      const scale=(frame.fit==='fill'?Math.max:Math.min)(bw/metrics.naturalWidth,bh/metrics.naturalHeight);
      assert(Math.abs(metrics.photoWidth-scale*metrics.naturalWidth*(frame.zoom||1))<4,JSON.stringify({metrics,frame}));
      return card;
    }
    await page.goto(base+'/library/');
    await page.locator('#characterSelect').selectOption(owner);
    await page.locator('#naiBattlesBtn').click();
    overall=await page.evaluate(({entry,rows})=>document.getElementById('nai-media-host').shadowRoot.naiCards.ovr(entry,rows),
      {entry:duo,rows:before.entries});
    assert(Number.isFinite(overall),'The ranked fixture must have a real shared overall');
    const arena=page.locator('.naiBattleArena'), tile=arena.locator('[data-entry-id="'+duo.id+'"]');
    const mode=page.getByLabel('Mode',{exact:true});
    assert.deepEqual(await mode.locator('option').allTextContents().then(v=>v.slice(-3)),['Refine top 10','Refine top 25','Refine top 50']);
    const front=await verifyFace(tile,'front');
    if(previewDir)await front.screenshot({path:path.join(previewDir,'Battles-Duo-front.png')});
    await button(tile,'Flip to back').click();
    const back=await verifyFace(tile,'back');
    if(previewDir){
      await back.screenshot({path:path.join(previewDir,'Battles-Duo-back.png')});
      await page.screenshot({path:path.join(previewDir,'Battles-matchup.png')});
    }
    await button(tile,'View full image').click();
    const expanded=page.getByRole('dialog',{name:'Expanded card'});
    await verifyFace(expanded,'back');
    const photo=expanded.locator('.naiExpandedCard');
    const info=button(expanded,'Info');
    await photo.click();await verifyFace(expanded,'front');
    await photo.press('Space');await verifyFace(expanded,'back');
    await info.click();
    assert.equal(await info.getAttribute('aria-pressed'),'true');
    assert.equal(await photo.evaluate(node=>node.inert),true);
    await info.press('Enter');
    assert.equal(await info.getAttribute('aria-pressed'),'false');
    await verifyFace(expanded,'back');
    await button(expanded,'Flip to front').click();await verifyFace(expanded,'front');
    await button(expanded,'Close image').click();
    await page.setViewportSize({width:390,height:844});
    await verifyFace(tile,'back');await button(tile,'Flip to front').click();await verifyFace(tile,'front');
    if(previewDir)await page.screenshot({path:path.join(previewDir,'Battles-phone.png')});
    await page.setViewportSize({width:1440,height:960});
    assert.equal(votes.length,0);
    assert.equal((await summary()).revision,before.revision);
    const showMMR=page.getByRole('checkbox',{name:'Show MMR',exact:true});
    await showMMR.uncheck();await verifyFace(tile,'front',false);assert.equal(await tile.locator('.naiBattleMmr').count(),0);
    await button(tile,'Flip to back').press('Enter');await verifyFace(tile,'back',false);
    await showMMR.check();await verifyFace(tile,'front');
    await button(page,'Leaderboard').click();
    const gallery=page.locator('.naiBattleGallery'), row=gallery.locator('[data-entry-id="'+duo.id+'"]');
    await button(row,'Flip to back').click();await row.locator('[data-duo-side="back"] .naiFramedSource').waitFor();
    await button(row,'View '+group.name).click();await verifyFace(expanded,'back');
    await photo.click();await verifyFace(expanded,'front');
    await button(expanded,'Close image').click();
    await button(row,'Inspect').click();
    assert.equal(await info.getAttribute('aria-pressed'),'true');
    await info.click();await verifyFace(expanded,'back');
    await button(expanded,'Close image').click();
    assert.equal((await summary()).votes,before.votes);
    await button(page,'Back to battles').click();
    await button(tile,'Choose left [←]').click();
    await page.waitForFunction(() => document.getElementById('nai-media-host').shadowRoot.querySelector('.naiBattleStatus').textContent.includes('Last vote'));
    const after=await summary();assert.equal(votes.length,1);assert.equal(after.votes,before.votes+1);
    assert(after.entries.find(e=>e.id===duo.id).rating>duo.rating);
    await mode.selectOption('refine50');
    await button(page,'Apply settings / restart').click();
    await page.waitForFunction(() => document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiBattleChoose:not(:disabled)').length===2);
    assert.equal((await summary()).session.mode,'refine50');
    assert.deepEqual(errors,[]);
    console.log('Verified both Duo faces, original files, saved crop, frame geometry, gallery, one vote and Refine top 50.');
  } finally {await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
