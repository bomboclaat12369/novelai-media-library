'use strict';
// A focused real-browser check of the illustrated presentation and existing
// ownership/clock boundaries. Only disposable fixture careers are modified.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const output=path.join(root,'.release-output','illustrated-venue');
fs.mkdirSync(output,{recursive:true});
const fixture=fs.mkdtempSync(path.join(output,'fixture-'));
const processServer=spawn(process.env.PYTHON_EXE,['tests/serve_illustrated_fixture.py',fixture],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
let browser,page,stderr='';processServer.stderr.on('data',part=>stderr+=part);
const checks=[],errors=[];
function check(name,condition){assert.ok(condition,name);checks.push(name);}
(async()=>{
 const {url}=await new Promise((resolve,reject)=>{
  let stdout='';const timer=setTimeout(()=>reject(Error('Fixture startup timed out: '+stderr)),20000);
  processServer.stdout.on('data',part=>{stdout+=part;const line=stdout.split('\n').find(line=>line.startsWith('{'));if(line){clearTimeout(timer);resolve(JSON.parse(line));}});
  processServer.once('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited '+code+': '+stderr));});
 });
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXE||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 page=await browser.newPage({viewport:{width:1600,height:1000}});
 page.on('pageerror',error=>errors.push(error.message));
 page.on('response',response=>{if(response.status()>=500)errors.push(response.status()+' '+response.url());});
 await page.goto(url);
 await page.locator('.illustrated-venue').waitFor();
 await page.evaluate(()=>{clearInterval(interval);});
 await page.locator('.booking-photo').evaluate(img=>img.decode());
 await page.locator('.character-figure').evaluate(img=>img.decode());
 const read=()=>page.evaluate(()=>({state:save,revision}));
 const before=await read();
 check('Real capacity appears as two private rooms and one lounge',await page.locator('.illustrated-room').count()===3);
 check('Two workers are assigned concurrently',await page.locator('.illustrated-room.is-staffed').count()===2);
 check('Current booking stage is marked separately from earlier stages',await page.locator('.booking-tracker [aria-current="step"]').count()===1&&await page.locator('.booking-tracker .is-done').count()>0);
 await page.locator('.illustrated-room[data-room="room-1"]').click();
 check('Room selection switches to Alice’s own approved illustration',(await page.locator('.character-figure').getAttribute('src')).endsWith('/alice-front.png'));
 check('Selecting another room leaves the entire career unchanged',JSON.stringify(await read())===JSON.stringify(before));
 const expected=await page.locator('.booking-photo').getAttribute('src');
 await page.getByRole('button',{name:'Enlarge booking photograph'}).click();
 check('Enlarge shows the same earned original',await page.locator('.enlarged-booking-media img').getAttribute('src')===expected);
 await page.getByRole('button',{name:'Close photograph'}).click();
 check('Enlarging does not change the assignment, card or booking',JSON.stringify(await read())===JSON.stringify(before));
 await page.locator('.character-caption [data-action="inspect"]').click();
 await page.locator('#modal .naiTradingCard, #modal .inspect-image').first().waitFor();
 await page.locator('#modal [data-action="close-modal"]').click();
 checks.push('Existing equipped-card inspection remains available');
 await page.evaluate(()=>{window.retainedPhoto=gameRoot.querySelector('.booking-photo');window.retainedFigure=gameRoot.querySelector('.character-figure');render();});
 check('Clock repaint retains the decoded photograph and approved figure',await page.evaluate(()=>window.retainedPhoto===gameRoot.querySelector('.booking-photo')&&window.retainedFigure===gameRoot.querySelector('.character-figure')));
 const unowned=await page.request.get(url+'api/image/0-1?original=1');
 check('Unowned photographs remain inaccessible',unowned.status()===403);
 const traversal=await page.request.get(url+'illustrations/%2e%2e/server.py');
 check('Illustration routes do not expose source paths',traversal.status()===404);
 await page.evaluate(()=>{window.savedIllustrations=venueIllustrations;venueIllustrations={};render();});
 check('Missing character art keeps the earned photo and a readable fallback',await page.locator('.figure-fallback').count()===1&&await page.locator('.booking-photo').getAttribute('src')===expected);
 await page.evaluate(()=>{venueIllustrations=window.savedIllustrations;render();});
 await page.locator('.illustrated-room[data-room="lounge-0"]').click();
 check('An empty room never inherits the previous worker’s photo',await page.locator('.booking-photo').count()===0);
 await page.locator('.illustrated-room[data-room="room-0"]').click();
 await page.locator('.character-figure').evaluate(img=>img.decode());
 await page.locator('.booking-photo').evaluate(img=>img.decode());
 for(const [width,height] of [[1600,1000],[1280,800],[760,1000],[390,844]]){
  await page.setViewportSize({width,height});
  const geometry=await page.evaluate(()=>{
   const figure=gameRoot.querySelector('.character-figure'),media=gameRoot.querySelector('.venue-media'),rooms=gameRoot.querySelector('.illustrated-rooms'),layout=gameRoot.querySelector('.layout');
   return {overflow:layout.scrollWidth>innerWidth+1,fit:getComputedStyle(figure).objectFit,figure:figure.getBoundingClientRect().toJSON(),media:media.getBoundingClientRect().toJSON(),rooms:rooms.getBoundingClientRect().toJSON()};
  });
  check(`No horizontal clipping and complete figure at ${width}×${height}`,!geometry.overflow&&geometry.fit==='contain'&&geometry.figure.x>=0&&geometry.figure.right<=width+1&&geometry.media.right<=width+1);
  if(width>=1280)check(`Photo viewer has useful desktop space at ${width}`,geometry.media.width>=360&&geometry.media.height>=350&&geometry.media.bottom<=height);
  await page.screenshot({path:path.join(output,`lounge-${width}.png`),fullPage:true});
 }
 await page.setViewportSize({width:1600,height:1000});
 await page.locator('.illustrated-room[data-room="room-1"]').click();
 await page.locator('.character-figure').evaluate(img=>img.decode());
 await page.screenshot({path:path.join(output,'alice.png'),fullPage:true});
 // Advance only through the actual server clock; check one pending decision
 // while viewing a different room, then resolve it through the real control.
 await page.evaluate(async()=>{if(save.night.paused&&!pendingDecision())await act('pause');await act('speed',{speed:8});});
 for(let i=0;i<32;i++){
  if(await page.evaluate(()=>!!pendingDecision()))break;
  await new Promise(resolve=>setTimeout(resolve,500));
  await page.evaluate(()=>act('tick',{},true));
 }
 check('An ordinary game event arrives through the shared clock',await page.evaluate(()=>!!pendingDecision()));
 await page.locator('.illustrated-room[data-room="lounge-0"]').click();
 check('Event choices remain visible while another room is selected',await page.locator('[aria-label="Business opportunity"]').count()>=1);
 await page.locator('[data-action="decision"][data-choice="decline"]').first().click();
 await page.waitForFunction(()=>!save.night.paused);
 check('Choosing an event resumes the night automatically',await page.evaluate(()=>save.phase==='night'&&!save.night.paused));
 await page.evaluate(()=>act('pause'));
 check('No browser errors',errors.length===0);
 const report={checks,errors,fixture,source_media:'Synthetic photo fixtures; native approved illustrations. No personal saves used.'};
 fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify(report,null,2));
 console.log(`${checks.length} focused illustrated-venue checks passed. Screenshots: ${output}`);
})().catch(async error=>{console.error(error.stack);if(stderr)console.error(stderr);if(page)await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{await browser?.close();processServer.kill();});
