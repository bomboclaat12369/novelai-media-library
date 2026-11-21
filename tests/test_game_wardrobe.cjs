'use strict';
// Run through the player's controls on an isolated, one-booking fixture.
const assert = require('node:assert/strict');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const route = '/game/api/outfit/patricia-red-gingham';
const child = spawn(process.env.PYTHON_EXE || 'python', ['-B', 'tests/test_game_wardrobe.py', '--serve'],
                    {cwd:root, windowsHide:true, stdio:['ignore','pipe','inherit']});
let browser;

async function run(){
 const lines = createInterface({input:child.stdout});
 const [url] = await Promise.race([
  once(lines,'line'),
  once(child,'exit').then(([code])=>{throw Error('Preview fixture exited with code '+code);})
 ]);
 assert.match(url,/^http:\/\/127\.0\.0\.1:\d+\/game\/$/);
 browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_EXE || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page = await browser.newPage({viewport:{width:1400,height:920}});
 const errors=[],artRequests=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(new URL(r.url()).pathname===route)artRequests.push(r.url());});
 const wardrobe = page.locator('.venue-character').getByRole('button',{name:'Wardrobe'});
 const modal = page.locator('dialog[open]');
 const close = ()=>modal.getByRole('button',{name:'Close wardrobe'}).click();
 const venueArt = page.locator('.character-figure');
 const roomArt = page.locator('.illustrated-room[data-room="room-0"] .room-figure');
 const gate = ()=>page.request.get(new URL(route,url).href);
 await page.goto(url);
 await wardrobe.click();
 assert.match(await modal.innerText(),/Red gingham[\s\S]+Locked/);
 assert.match(await modal.innerText(),/Level 10 \+ matching photo[\s\S]+9 \/ 10[\s\S]+Matching photo collected/);
 assert.match(await modal.innerText(),/Reach level 20[\s\S]+9 \/ 20/);
 assert.equal(await modal.locator('img').count(),0);
 assert.equal(artRequests.length,0);
 assert.equal((await gate()).status(),403);
 assert.equal((await page.request.get(new URL('wardrobe-data/patricia-red-gingham-front.png',url).href)).status(),404);
 await page.setViewportSize({width:390,height:780});
 assert.ok(await modal.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
 await close();
 await page.setViewportSize({width:1400,height:920});
 await page.getByRole('button',{name:'Open for the night'}).click();
 await page.locator('#toast.show .outfit-toast-art').waitFor();
 assert.equal(await page.locator('dialog[open]').count(),0);
 assert.equal(await page.evaluate(()=>save.night.paused),false);
 await wardrobe.click();
 await modal.locator('.wardrobe-art').evaluate(img=>img.decode());
 assert.equal((await gate()).status(),200);
 await modal.getByRole('button',{name:'Wear red gingham'}).click();
 await modal.locator('[data-outfit="patricia-red-gingham"]:disabled').waitFor();
 await close();
 await venueArt.evaluate(img=>img.decode());
 await roomArt.evaluate(img=>img.decode());
 for(const img of [venueArt,roomArt])assert.equal(await img.getAttribute('src'),route);
 assert.equal(await page.locator('.figure-turn').count(),0);
 await page.reload();
 await venueArt.waitFor();
 assert.equal(await venueArt.getAttribute('src'),route);
 await wardrobe.click();
 await modal.getByRole('button',{name:'Wear gym outfit'}).click();
 await modal.locator('[data-outfit="default"]:disabled').waitFor();
 await close();
 await page.getByRole('button',{name:'Show Patricia’s side profile'}).click();
 assert.match(await venueArt.getAttribute('src'),/patricia-side\.png$/);
 assert.match(await roomArt.getAttribute('src'),/patricia-front\.png$/);
 // Exercise the three-view outfit and the player's compressed-file recovery control.
 const triple='patricia-pastel-floral-bikini',outfitUrl=new URL('api/outfit/'+triple+'?view=back',url).href;
 assert.equal((await page.request.get(outfitUrl)).status(),403);
 const exported=await (await page.request.get(new URL('api/export?download=1',url).href)).json();
 const owner=Object.keys(exported.save.state.people).find(id=>exported.catalog.people[id].name==='Patricia');
 exported.save.state.people[owner].xp=5500;
 await page.locator('.nav [data-screen=saves]').click();
 await page.locator('#restore-file').setInputFiles({name:'wardrobe-review.json.gz',mimeType:'application/gzip',
  buffer:require('node:zlib').gzipSync(JSON.stringify(exported))});
 await page.waitForFunction(id=>derived.wardrobe[id].outfits.every(o=>o.unlocked),owner);
 await page.locator('.nav [data-screen=club]').click();await wardrobe.click();
 await modal.locator('[data-outfit-preview]').selectOption(triple);
 await modal.getByRole('button',{name:'Wear pastel floral bikini'}).click();
 await modal.locator('[data-outfit="'+triple+'"]:disabled').waitFor();await close();
 await page.getByRole('button',{name:'Show Patricia’s side profile'}).click();
 await page.getByRole('button',{name:'Show Patricia’s back view'}).click();
 await venueArt.evaluate(img=>img.decode());assert.match(await venueArt.getAttribute('src'),/view=back$/);
 assert.equal((await page.request.get(outfitUrl)).status(),200);
 assert.equal((await page.request.get(outfitUrl.replace('view=back','view=unknown'))).status(),404);
 assert.deepEqual(errors,[]);
 console.log('Wardrobe passed: 19 outfits, locked art, first-booking unlock, phone layout, compressed restore, front/side/back rotation.');
}

run().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{
 try{await browser?.close();}finally{child.kill();}
});
