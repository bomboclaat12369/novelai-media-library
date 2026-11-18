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
 const layoutBounds=()=>page.evaluate(()=>['.venue-stage','.venue-character','.venue-media-surface','.booking-tracker'].map(selector=>{const box=gameRoot.querySelector(selector).getBoundingClientRect();return [box.x,box.y+scrollY,box.width,box.height].map(value=>Math.round(value*100)/100);}));
 check('Real capacity appears as two private rooms and one lounge',await page.locator('.illustrated-room').count()===3);
 check('Two workers are assigned concurrently',await page.locator('.illustrated-room.is-staffed').count()===2);
 check('Current booking stage is marked separately from earlier stages',await page.locator('.booking-tracker [aria-current="step"]').count()===1&&await page.locator('.booking-tracker .is-done').count()>0);
 await page.getByRole('button',{name:'Show Patricia’s side profile'}).click();
 await page.locator('.character-figure').evaluate(img=>img.decode());
 check('Clicking Patricia shows her approved side profile',(await page.locator('.character-figure').getAttribute('src')).endsWith('/patricia-side.png'));
 await page.getByRole('button',{name:'Show Patricia’s front view'}).press('Enter');
 check('Keyboard activation turns the figure back',(await page.locator('.character-figure').getAttribute('src')).endsWith('/patricia-front.png'));
 await page.locator('.illustrated-room[data-room="room-1"]').click();
 check('Room selection switches to Alice’s own approved illustration',(await page.locator('.character-figure').getAttribute('src')).endsWith('/alice-front.png'));
 await page.getByRole('button',{name:'Show Alice’s side profile'}).click();
 await page.locator('.character-figure').evaluate(img=>img.decode());
 check('Alice has her own approved side profile',(await page.locator('.character-figure').getAttribute('src')).endsWith('/alice-side.png'));
 await page.evaluate(()=>render());
 check('Clock repaint retains the selected view and keyboard focus',await page.evaluate(()=>gameRoot.activeElement?.dataset.action==='turn-character'&&gameRoot.querySelector('.character-figure').src.endsWith('/alice-side.png')));
 await page.locator('.illustrated-room[data-room="room-0"]').click();
 check('Turning one character does not turn another',(await page.locator('.character-figure').getAttribute('src')).endsWith('/patricia-front.png'));
 await page.locator('.illustrated-room[data-room="room-1"]').click();
 check('Returning to a room remembers that character’s view',(await page.locator('.character-figure').getAttribute('src')).endsWith('/alice-side.png'));
 check('Selecting another room leaves the entire career unchanged',JSON.stringify(await read())===JSON.stringify(before));
 check('Turning characters sends no gameplay changes',JSON.stringify(await read())===JSON.stringify(before));
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
 check('Missing art never offers a non-working turn control',await page.locator('.figure-turn').count()===0);
 await page.evaluate(()=>{venueIllustrations=window.savedIllustrations;render();});
 await page.locator('.illustrated-room[data-room="lounge-0"]').click();
 check('An empty room never inherits the previous worker’s photo',await page.locator('.booking-photo').count()===0);
 await page.locator('.illustrated-room[data-room="room-0"]').click();
 await page.locator('.character-figure').evaluate(img=>img.decode());
 await page.locator('.booking-photo').evaluate(img=>img.decode());
 for(const [width,height] of [[1600,1000],[1280,800],[760,1000],[390,844]]){
  await page.setViewportSize({width,height});
  await page.waitForTimeout(80);
  const geometry=await page.evaluate(()=>{
   const figure=gameRoot.querySelector('.character-figure'),media=gameRoot.querySelector('.venue-media'),photo=gameRoot.querySelector('.booking-photo'),surface=gameRoot.querySelector('.venue-media-surface'),rooms=gameRoot.querySelector('.illustrated-rooms'),layout=gameRoot.querySelector('.layout'),tracker=gameRoot.querySelector('.booking-tracker'),venue=gameRoot.querySelector('.illustrated-venue'),steps=[...tracker.querySelectorAll('.booking-scroll>.booking-timeline>li')];
   const bounds=surface.getBoundingClientRect();
   return {overflow:layout.scrollWidth>innerWidth+1,fit:getComputedStyle(figure).objectFit,photoFit:getComputedStyle(photo).objectFit,figure:figure.getBoundingClientRect().toJSON(),media:media.getBoundingClientRect().toJSON(),rooms:rooms.getBoundingClientRect().toJSON(),ratioError:Math.abs(bounds.width/bounds.height-.8),horizontal:steps.every(step=>Math.abs(step.getBoundingClientRect().top-steps[0].getBoundingClientRect().top)<1),fullHistory:Math.abs(tracker.clientWidth-venue.clientWidth)<2};
  });
  check(`No horizontal clipping and complete figure at ${width}×${height}`,!geometry.overflow&&geometry.fit==='contain'&&geometry.figure.x>=0&&geometry.figure.right<=width+1&&geometry.media.right<=width+1);
  check(`Fixed 4:5 frame fits whole photos and history stays horizontal at ${width}`,geometry.ratioError<.01&&geometry.photoFit==='contain'&&geometry.horizontal&&geometry.fullHistory);
  if(width>=1280)check(`Photo viewer has useful desktop space at ${width}`,geometry.media.width>=280&&geometry.media.height>=350&&geometry.media.bottom<=height);
  await page.screenshot({path:path.join(output,`lounge-${width}.png`),fullPage:true});
 }
 await page.setViewportSize({width:1600,height:1000});
 await page.locator('.illustrated-room[data-room="room-1"]').click();
 await page.locator('.character-figure').evaluate(img=>img.decode());
 await page.screenshot({path:path.join(output,'alice.png'),fullPage:true});
 // A landscape photo must not move the frame, figure, rooms or history.
 const portraitBounds=await layoutBounds();
 await page.evaluate(async()=>{const img=gameRoot.querySelector('.booking-photo');window.originalFixtureSrc=img.src;img.src=URL.createObjectURL(new Blob(['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="#4c5f62"/></svg>'],{type:'image/svg+xml'}));await img.decode();fitVenuePresentation();});
 check('Changing a portrait to landscape leaves the whole layout in place',JSON.stringify(await layoutBounds())===JSON.stringify(portraitBounds));
 await page.evaluate(async()=>{const img=gameRoot.querySelector('.booking-photo');URL.revokeObjectURL(img.src);img.src=window.originalFixtureSrc;await img.decode();fitVenuePresentation();});
 check('Returning to a portrait keeps the same frame position',JSON.stringify(await layoutBounds())===JSON.stringify(portraitBounds));
 // Advance only through the actual server clock; check one pending decision
 // while viewing a different room, then resolve it through the real control.
 await page.evaluate(async()=>{if(save.night.paused&&!pendingDecision())await act('pause');await act('speed',{speed:8});});
 for(let i=0;i<32;i++){
  if(await page.evaluate(()=>!!pendingDecision()))break;
  await new Promise(resolve=>setTimeout(resolve,500));
  await page.evaluate(()=>act('tick',{},true));
 }
 check('An ordinary game event arrives through the shared clock',await page.evaluate(()=>!!pendingDecision()));
 const eventBounds=await layoutBounds();
 await page.locator('.venue-event-overlay').evaluate(el=>{el.style.display='none';});
 check('Showing an event does not move the figure, photo or booking history',JSON.stringify(await layoutBounds())===JSON.stringify(eventBounds));
 await page.locator('.venue-event-overlay').evaluate(el=>{el.style.display='';});
 check('Desktop events float entirely over the room column',await page.evaluate(()=>{const event=gameRoot.querySelector('.venue-event-overlay').getBoundingClientRect(),room=gameRoot.querySelector('.venue-overview').getBoundingClientRect(),media=gameRoot.querySelector('.venue-media').getBoundingClientRect();return event.left>=room.left-1&&event.right<=room.right+1&&event.right<media.left&&event.bottom<=innerHeight;}));
 await page.screenshot({path:path.join(output,'event-desktop.png'),fullPage:true});
 // Room selection is still presentation-only even while the event overlays it.
 await page.evaluate(()=>{selectedRoom='lounge-0';render();});
 check('Event choices remain visible while another room is selected',await page.locator('[aria-label="Business opportunity"]').count()>=1);
 await page.setViewportSize({width:390,height:844});
 await page.waitForTimeout(80);
 check('Phone event choices remain within the screen',await page.locator('.venue-event-overlay').evaluate(el=>{const b=el.getBoundingClientRect();return b.left>=0&&b.right<=innerWidth&&b.top>=0&&b.bottom<=innerHeight;}));
 await page.screenshot({path:path.join(output,'event-phone.png'),fullPage:true});
 await page.locator('[data-action="decision"][data-choice="decline"]').first().click();
 await page.waitForFunction(()=>!save.night.paused);
 check('Choosing an event resumes the night automatically',await page.evaluate(()=>save.phase==='night'&&!save.night.paused));
 check('Resolved events leave no overlay behind',await page.locator('.venue-event-overlay').evaluate(el=>getComputedStyle(el).display==='none'));
 await page.evaluate(()=>act('pause'));
 check('No browser errors',errors.length===0);
 const report={checks,errors,fixture,source_media:'Synthetic photo fixtures; native approved illustrations. No personal saves used.'};
 fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify(report,null,2));
 console.log(`${checks.length} focused illustrated-venue checks passed. Screenshots: ${output}`);
})().catch(async error=>{console.error(error.stack);if(stderr)console.error(stderr);if(page)await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{await browser?.close();processServer.kill();});
