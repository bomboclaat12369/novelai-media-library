'use strict';

// Presentation only. Stable Library identities select approved illustrations;
// all assignments, booking stages, money and earned media come from the game.
let venueIllustrations={};
const venueSections=new Set();
const venueViews=new Map();
let venueResizeObserver;
async function initVenue(){
 try{
  const response=await fetch('/game/illustrations/characters.json');
  if(response.ok)venueIllustrations=(await response.json()).characters||{};
 }catch{/* An unavailable illustration never prevents opening a career. */}
}
root.addEventListener('toggle',event=>{
 const key=event.target.dataset?.venueSection;
 if(key){if(event.target.open)venueSections.add(key);else venueSections.delete(key);}
},true);

function venueSlots(){
 const slots=[];
 for(const [role,label,count] of [['room','Private room',save.facilities.rooms],['lounge','Lounge',save.facilities.lounge],['studio','Studio',save.departments.studio],['resort','Guest suite',save.departments.resort]]){
  const owners=Object.keys(save.people).filter(id=>(save.night?.assignments[id]||derived.assignments[id])===role);
  for(let i=0;i<count;i++)slots.push({id:role+'-'+i,label:label+' '+(i+1),owner:owners[i],role,index:i});
 }
 return slots;
}
function venueContext(){
 const slots=venueSlots(),chosen=slots.find(slot=>slot.id===selectedRoom)||slots[0];
 if(!chosen)return {slots};
 selectedRoom=chosen.id;
 const worker=save.people[chosen.owner],equipped=worker?card(worker.card):null;
 const variants=chosen.owner?ownedFor(chosen.owner).filter(id=>(displayedArt(id)?.image_available??card(id).available)&&card(id).image):[];
 const photo=variants.length?card(variants[(save.night?.wave||0)%variants.length]):equipped;
 const art=photo?displayedArt(photo.id):null;
 const available=photo?.image&&save.owned[photo.id]&&(art?.image_available??photo.available);
 const query=[];
 if(available&&(art?.original_available??photo.original_available))query.push('original=1');
 if(available&&photo.source==='duo')query.push('side='+duoSide(photo.id));
 if(available&&photo.source==='evolution'&&art?.number)query.push('form='+art.number);
 const url=available?'/game'+photo.image+(query.length?'?'+query.join('&'):''):null;
 return {slots,chosen,worker,equipped,photo,url,meeting:derived.meetings?.[chosen.owner],activity:save.night?.activities[chosen.owner]};
}
function illustration(owner){return venueIllustrations[owner];}
function turnCharacter(owner){
 if(!illustration(owner)?.side)return;
 venueViews.set(owner,venueViews.get(owner)==='side'?'front':'side');
 render();
}
function roomStatus(slot){
 if(!slot.owner)return 'Available';
 if(!save.night)return 'Prepared';
 return derived.meetings?.[slot.owner]?.phase||save.night.activities?.[slot.owner]?.status||'In operation';
}
function roomScene(slot){
 const art=illustration(slot.owner),kind=slot.role==='lounge'?1:slot.role==='resort'?2:slot.index%3;
 // Authored cutaway scenery follows the reviewed lounge reference. Figures
 // remain separate, complete native PNGs; this is not character animation.
 return `<div class="room-scene room-scene-${kind}" aria-hidden="true">
  <div class="room-wall"><i class="wall-art"><b></b></i><i class="wall-window"><b></b></i></div>
  <div class="room-floor"></div><div class="room-sofa"><i></i><b></b></div>
  <div class="room-lamp"><i></i></div><div class="room-plant"><i></i><b></b><em></em></div><div class="room-table"></div>
  ${art?`<img class="room-figure" data-venue-art-key="${esc(slot.id+':'+art.appearance_id+':'+art.sha256)}" data-venue-src="${esc(art.image)}" alt="" style="--figure-scale:${Math.min(1,art.working_height_cm/165.1)}">`:slot.owner?`<span class="room-initial">${esc(person(slot.owner).name[0])}</span>`:''}
 </div>`;
}
function characterPanel(context){
 const {chosen,worker,equipped}=context,art=illustration(chosen.owner),name=worker?person(chosen.owner).name:'Your next opening';
 const side=!!art?.side&&venueViews.get(chosen.owner)==='side',view=side?art.side:art;
 const figure=art?`<img class="character-figure" data-venue-art-key="${esc('selected:'+art.appearance_id+':'+view.sha256)}" data-venue-src="${esc(view.image)}" alt="${esc(name)} · ${side?'side profile':'front view'}" style="--figure-scale:${Math.min(1,art.working_height_cm/165.1)}">`:`<div class="figure-fallback"><span>${worker?esc(name[0]):'◇'}</span><p>${worker?'Character illustration coming later.':'Choose your team’s assignments below.'}</p></div>`;
 return `<aside class="venue-character" aria-label="Selected character">
  <div class="character-heading"><h2>${esc(name)}</h2>${art?.side?`<span>${side?'Side profile':'Front view'} · Click to turn</span>`:''}</div>
  ${art?.side?`<button type="button" class="figure-stage figure-turn" data-action="turn-character" data-owner="${esc(chosen.owner)}" aria-label="Show ${esc(name)}’s ${side?'front view':'side profile'}">${figure}</button>`:`<div class="figure-stage">${figure}</div>`}
  <div class="character-caption">${worker?`<div class="character-energy"><span>Energy</span><strong>${Math.round(worker.energy)} / 100</strong></div><div class="energy"><span style="width:${Math.max(0,Math.min(100,worker.energy))}%"></span></div><button class="ghost small full" data-action="inspect" data-card="${esc(equipped.id)}">View equipped card</button><small>${esc(specialties[equipped.specialty])} · Career level ${1+Math.floor(worker.xp/100)}</small>`:`<p>${esc(roomStatus(chosen))}</p>`}</div>
 </aside>`;
}
function illustratedVenue(){
 const context=venueContext(),{slots,chosen,worker,url,meeting,activity}=context;
 if(!chosen)return '<section class="panel">No rooms are available yet.</section>';
 const name=worker?person(chosen.owner).name:'No booking selected';
 return `<section class="illustrated-venue">
  <div class="venue-stage"><section class="venue-overview" aria-label="Room overview"><div class="venue-section-head"><h2>Your venue</h2><span>${slots.length} positions</span></div>
   <div class="illustrated-rooms" data-scroll-key="rooms">${slots.map(slot=>`<button class="illustrated-room ${slot.owner?'is-staffed':''}" data-action="select-room" data-room="${esc(slot.id)}" aria-pressed="${slot.id===chosen.id}"><div class="room-title"><strong>${esc(slot.label)}</strong><span>${esc(roomStatus(slot))}</span></div>${roomScene(slot)}<div class="room-name">${slot.owner?esc(person(slot.owner).name):'No team assigned'}<span>${slot.id===chosen.id?'Viewing':'View room →'}</span></div></button>`).join('')}</div>
   <p class="venue-footnote">All rooms run together. ${((save.night?.duration??boot.night_duration)/60).toLocaleString()}-minute nights at 1×.</p>
   <div class="venue-event-overlay" aria-live="polite">${opportunities()}</div>
  </section>
  ${characterPanel(context)}
   <article class="venue-media" aria-label="Booking photograph"><div class="venue-section-head"><div><span class="eyebrow">${esc(chosen.label)}</span><h2>${esc(name)}</h2></div><button class="ghost small" data-action="enlarge-booking-media" ${url?'':'disabled'} aria-label="Enlarge booking photograph">Enlarge ↗</button></div>
    <div class="venue-media-surface" data-venue-media-key="${esc(url||'empty:'+chosen.id)}">${url?`<img class="booking-photo" data-venue-src="${esc(url)}" alt="${esc(name)} · earned photograph">`:`<div class="activity-placeholder"><span>${worker?esc(name[0]):'◇'}</span><p>${worker?(boot.catalog.demo?'Demo artwork':'No earned photograph available'):'Ready for the next booking'}</p></div>`}</div>
    <div class="venue-media-footer"><span>${url?'From your earned collection':worker?'Your card progress is preserved':'Assign a team member to this room'}</span><span>${worker?ownedFor(chosen.owner).length+' card'+(ownedFor(chosen.owner).length===1?'':'s')+' collected':''}</span></div>
   </article>
  </div>
  <aside class="booking-tracker" aria-label="Selected booking tracker" data-booking-key="${esc(chosen.id+':'+(meeting?.booking_number||'idle'))}"><div class="venue-section-head"><h2>Booking history <span>· ${esc(name)}</span></h2><span class="live-indicator">${save.night?(save.night.paused?'Paused':'Live'):'Preparation'}</span></div><div class="booking-scroll">${meetingCaption(meeting,activity,worker)}</div></aside>
 </section>`;
}
function nightControls(){
 const n=save.night;
 return n?`<button class="primary" data-action="pause" ${pendingDecision()?'disabled':''}>${pendingDecision()?'Choose an option':n.paused?'Resume':'Pause'}</button><select aria-label="Night speed" id="speed">${(boot.night_speeds||[1,2,4,8]).map(value=>`<option value="${value}" ${n.speed===value?'selected':''}>${value}× speed</option>`).join('')}</select><button class="ghost" data-action="finish">Finish night</button>`:'<button class="ghost" data-action="auto">Auto assign team</button><button class="primary" data-action="start">Open for the night →</button>';
}
function venueActivity(night, last){
 const contracts = !night && last ? contractsEndingOn(last.day) : [];
 const studio = contracts.filter(c=>c.department==='studio').length;
 const resort = contracts.length - studio;
 const counts = [];
 if(studio)counts.push(studio+' Studio '+(studio===1?'project':'projects'));
 if(resort)counts.push(resort+' Resort '+(resort===1?'checkout':'checkouts'));
 const heading = counts.length ? 'Night '+last.day+' · '+counts.join(' · ') : 'Across the venue';
 const caption = night ? 'Live activity & results' : (counts.length?'Payouts & tonight’s team':'Recent results');
 const body = night
  ? `<ul class="timeline">${(night.log.length?night.log:['Guests will arrive throughout the night.']).map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`
  : `<p>${last?`Night ${last.day} finished at ${money(last.profit)} after costs.`:'Your first evening’s results will appear here.'}</p>
     ${contractReceipts(last, contracts, true)}<button class="ghost small" data-screen="reports">View reports →</button>`;
 return `<details class="venue-log panel" data-venue-section="activity" ${venueSections.has('activity')?'open':''}>
  <summary>${heading} <span>${caption}</span></summary>${body}</details>`;
}
function illustratedClub(){
 const n=save.night,last=save.reports.at(-1),clock=seconds=>Math.floor(seconds/60)+':'+String(Math.floor(seconds%60)).padStart(2,'0');
 return `<div class="lounge-heading"><div><div class="eyebrow">The club / Night ${save.day}</div><h1>${n?'An evening at After Hours':'Make tonight your own.'}</h1></div><div class="actions">${nightControls()}${boot.restartable?'<button class="ghost small" data-action="restart-game">Restart game</button>':''}</div></div>
  <div class="lounge-summary"><span>Cash <strong>${money(save.cash)}</strong></span><span>${n?`${clock(n.elapsed)} / ${clock(n.duration||boot.night_duration)} · ${n.paused?'Paused':'Doors open'}`:`${esc(derived.demand)} demand`}</span><span>${n?`${n.served} paid bookings · <strong>${money(n.revenue)}</strong> earned`:`<strong>${money(derived.recurring)}</strong> recurring costs`}</span><span>Last night ${last?`<strong class="${last.profit<0?'negative':'positive'}">${money(last.profit)}</strong> net`:'—'}</span></div>
  ${illustratedVenue()}
  <details class="venue-planning panel" data-venue-section="planning" ${venueSections.has('planning')?'open':''}><summary>Tonight’s plan <span>Assignments, cards & prices</span></summary><div class="venue-plan-body"><div class="sectionhead"><p>Each girl keeps her career and energy across cards.</p><button class="ghost small" data-screen="team">Team & recruitment →</button></div><div class="staff-grid">${Object.keys(save.people).map(staffHTML).join('')}</div><label class="policy-label" for="pricing">Price policy</label><select id="pricing" ${n?'disabled':''}>${[['accessible','Accessible · more bookings'],['standard','Standard · balanced'],['premium','Premium · higher price, fewer bookings']].map(([value,label])=>`<option value="${value}" ${save.pricing===value?'selected':''}>${label}</option>`).join('')}</select>${savedPlans()}</div></details>
  ${venueActivity(n,last)}
  ${save.cash<derived.recurring&&!n?'<section class="panel"><h3>Time to regroup</h3><p>Take a two-day recovery break to restore energy and receive an operating reserve.</p><button data-action="recovery">Take recovery break</button></section>':''}`;
}
function enlargeBookingMedia(){
 const {url,chosen}=venueContext();if(!url)return;
 const name=person(chosen.owner).name;
 modal.innerHTML=`<div class="modal-head"><div><h2>${esc(name)}</h2><p class="note">${esc(chosen.label)} · Earned photograph</p></div><button data-action="close-modal" aria-label="Close photograph">✕</button></div><div class="enlarged-booking-media"><img class="inspect-image" src="${esc(url)}" alt="${esc(name)} · earned photograph"></div>`;
 modal.showModal();
}
// Keep decoded media and reading position through clock repainting. This also
// leaves a stable surface for future playback, without adding video unlocks.
function captureVenuePresentation(){
 const panel=$('.illustrated-venue');if(!panel)return null;
 return {media:panel.querySelector('[data-venue-media-key]'),art:[...panel.querySelectorAll('[data-venue-art-key]')],scroll:[...panel.querySelectorAll('[data-scroll-key]')].map(el=>({key:el.dataset.scrollKey,top:el.scrollTop,left:el.scrollLeft,atEnd:el.scrollWidth-el.clientWidth-el.scrollLeft<12})),focus:root.activeElement?.dataset?.room,turnFocus:root.activeElement?.dataset?.action==='turn-character'?root.activeElement.dataset.owner:null};
}
// A fixed 4:5 frame keeps the scene still when photographs change. Only the
// browser size controls layout; the entire photo fits inside the same frame.
function fitVenuePresentation(){
 const panel=$('.illustrated-venue');if(!panel)return;
 const ratio=.8;
 const narrow=innerWidth<=760,gap=narrow?14:24,rail=narrow?0:210;
 const available=panel.clientWidth-rail-gap*(narrow?1:2);
 const height=Math.max(120,Math.min(Math.max(380,Math.min(700,innerHeight-390)),available/(2/3+ratio)));
 panel.style.setProperty('--portrait-height',height+'px');
 panel.style.setProperty('--media-ratio',ratio);
 positionVenueEvents();
}
function positionVenueEvents(){
 const overview=$('.venue-overview');if(!overview)return;
 const bounds=overview.getBoundingClientRect();
 overview.style.setProperty('--event-left',bounds.left+'px');
 overview.style.setProperty('--event-width',bounds.width+'px');
 overview.style.setProperty('--event-top',Math.max(12,Math.min(bounds.top+54,innerHeight-260))+'px');
}
window.addEventListener('resize',fitVenuePresentation);
window.addEventListener('scroll',positionVenueEvents,{passive:true});
function restoreVenuePresentation(previous){
 previous=previous||{art:[],scroll:[]};
 venueResizeObserver?.disconnect();
 const panel=$('.illustrated-venue');if(!panel)return;
 const next=panel.querySelector('[data-venue-media-key]');
 if(previous.media&&next?.dataset.venueMediaKey===previous.media.dataset.venueMediaKey)next.replaceWith(previous.media);
 for(const nextArt of panel.querySelectorAll('[data-venue-art-key]')){
  const oldArt=previous.art.find(node=>node.dataset.venueArtKey===nextArt.dataset.venueArtKey);
  if(oldArt){oldArt.alt=nextArt.alt;nextArt.replaceWith(oldArt);}
 }
 for(const img of panel.querySelectorAll('img[data-venue-src]')){
  if(img.getAttribute('src')!==img.dataset.venueSrc)img.src=img.dataset.venueSrc;
 }
 fitVenuePresentation();
 venueResizeObserver=venueResizeObserver||new ResizeObserver(fitVenuePresentation);
 venueResizeObserver.observe(panel);
 for(const timeline of panel.querySelectorAll('.booking-timeline'))timeline.dataset.scrollKey='stages:'+(timeline.closest('[data-booking-history]')?.dataset.bookingHistory||panel.querySelector('.booking-tracker').dataset.bookingKey);
 for(const el of panel.querySelectorAll('[data-scroll-key]')){
  const position=previous.scroll.find(item=>item.key===el.dataset.scrollKey);
  if(el.dataset.scrollKey.startsWith('stages:')&&(!position||position.atEnd))el.scrollLeft=el.scrollWidth;
  else if(position){el.scrollTop=position.top;el.scrollLeft=position.left;}
 }
 if(previous.focus)panel.querySelector(`.illustrated-room[data-room="${CSS.escape(previous.focus)}"]`)?.focus({preventScroll:true});
 if(previous.turnFocus)panel.querySelector(`.figure-turn[data-owner="${CSS.escape(previous.turnFocus)}"]`)?.focus({preventScroll:true});
}
