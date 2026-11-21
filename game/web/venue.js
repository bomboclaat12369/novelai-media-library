'use strict';

// Presentation only. Stable Library identities select approved illustrations;
// all assignments, booking stages, money and earned media come from the game.
let venueIllustrations={};
const venueSections=new Set();
const venueViews=new Map();
const wardrobeSelection=new Map();
const roomClip=new Map();
const clipUrl=id=>'/game/api/video/'+encodeURIComponent(id);
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
 const clips=derived.videos?.[chosen.owner]||[],clip=clips.find(c=>c.id===roomClip.get(chosen.owner));
 return {slots,chosen,worker,equipped,photo,url,clips,clip,meeting:derived.meetings?.[chosen.owner],activity:save.night?.activities[chosen.owner]};
}
function illustration(owner){
 const base=venueIllustrations[owner],closet=derived.wardrobe?.[owner];
 const selected=closet?.outfits.find(outfit=>outfit.unlocked&&outfit.id===closet.equipped);
 if(!selected?.art)return base;
 return {...selected.art,working_height_cm:base?.working_height_cm||165.1};
}
function wardrobeButton(owner){
 return derived.wardrobe?.[owner]?.outfits.length
  ? `<button class="ghost small" data-action="wardrobe" data-owner="${esc(owner)}">Wardrobe</button>` : '';
}
function wardrobeChoice(owner,id,label,equipped){
 return `<button class="${equipped?'ghost':'primary'} small" data-action="wear-outfit" data-owner="${esc(owner)}" data-outfit="${esc(id)}" ${equipped?'disabled':''}>${equipped?'Wearing':esc('Wear '+label)}</button>`;
}
function outfitGoal(title,level,target,detail){
 const count=Math.min(level,target);
 return `<div class="outfit-goal"><div><strong>${esc(title)}</strong><span>${count} / ${target}</span></div><progress aria-label="${esc(title)}" value="${count}" max="${target}"></progress><small>${esc(detail)}</small></div>`;
}
function showWardrobe(owner){
 const closet=derived.wardrobe?.[owner];
 if(!closet)return;
 const name=person(owner).name;
 const selected=closet.outfits.find(o=>o.id===(wardrobeSelection.get(owner)||closet.equipped))||closet.outfits[0];
 const stamp=JSON.stringify([closet,selected.id]);
 const existing=modal.querySelector('[data-wardrobe-owner]');
 if(modal.open&&existing?.dataset.wardrobeOwner===owner&&existing.dataset.stamp===stamp)return;
 const focused=modal.contains(root.activeElement)?root.activeElement?.dataset.action:null;
 const outfit=selected;
 const goals=(outfit.photo_level?outfitGoal('Level '+outfit.photo_level+' + matching photo',closet.level,outfit.photo_level,outfit.has_photo?'Matching photo collected':'Matching photo still needed')+'<div class="outfit-or">or</div>':'')
  +outfitGoal('Reach level '+outfit.career_level,closet.level,outfit.career_level,'Any collection qualifies');
 const entries=`<label>Outfits · ${closet.outfits.filter(o=>o.unlocked).length} / ${closet.outfits.length} earned<select data-outfit-preview="${esc(owner)}">${closet.outfits.map(o=>`<option value="${esc(o.id)}" ${o.id===outfit.id?'selected':''}>${esc(o.name)} · ${o.unlocked?'Unlocked':'Level '+o.career_level}</option>`).join('')}</select></label><article class="wardrobe-outfit"><div class="wardrobe-row"><h3>${esc(outfit.name)}</h3><span>${outfit.unlocked?'Unlocked':'Locked'}</span></div>
   ${outfit.unlocked?`<img class="wardrobe-art" src="${esc(outfit.art.image)}" alt="${esc(name+' in '+outfit.name)}">${wardrobeChoice(owner,outfit.id,outfit.name.toLowerCase(),closet.equipped===outfit.id)}`:goals}</article>`;
 modal.innerHTML=`<div data-wardrobe-owner="${esc(owner)}"><div class="modal-head"><div><h2>${esc(name)}’s wardrobe</h2><p class="note">Career level ${closet.level}</p></div><button data-action="close-modal" aria-label="Close wardrobe">✕</button></div>
  <div class="wardrobe-row gym-outfit"><h3>Gym outfit</h3>${wardrobeChoice(owner,'default','gym outfit',closet.equipped==='default')}</div>${entries}</div>`;
 modal.firstElementChild.dataset.stamp=stamp;
 if(!modal.open)modal.showModal();
 else if(focused)modal.querySelector('[data-action="close-modal"]')?.focus({preventScroll:true});
}
modal.addEventListener('change',event=>{
 const owner=event.target.dataset.outfitPreview;
 if(owner){wardrobeSelection.set(owner,event.target.value);showWardrobe(owner);modal.querySelector('[data-outfit-preview]')?.focus();}
});
function refreshOpenWardrobe(){
 const panel=modal.open&&modal.querySelector('[data-wardrobe-owner]');
 if(!panel)return;
 const owner=panel.dataset.wardrobeOwner;
 if(derived.wardrobe?.[owner])showWardrobe(owner);
 else modal.close();
}
function announceOutfit(previous){
 for(const [owner,closet] of Object.entries(derived.wardrobe||{})){
  const earned=closet.outfits.find(outfit=>outfit.unlocked&&previous?.[owner]?.outfits.some(old=>old.id===outfit.id&&!old.unlocked));
  if(!earned)continue;
  notify(person(owner).name+' unlocked '+earned.name+'.');
  const image=document.createElement('img');
  image.className='outfit-toast-art';image.alt='';image.src=earned.art.image;
  $('#toast').prepend(image);
  break;
 }
}
function turnCharacter(owner){
 const art=illustration(owner);
 if(!art?.side)return;
 venueViews.set(owner,characterView(art,owner).next);
 render();
}
function characterView(art,owner){
 const views=['front',...['side','back'].filter(key=>art?.[key])],saved=venueViews.get(owner);
 const index=Math.max(0,views.indexOf(saved)),labels={front:'front view',side:'side profile',back:'back view'};
 return {art:index?art[views[index]]:art,label:labels[views[index]],next:views[(index+1)%views.length],nextLabel:labels[views[(index+1)%views.length]]};
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
 const view=characterView(art,chosen.owner);
 const figure=art?`<img class="character-figure" data-venue-art-key="${esc('selected:'+art.appearance_id+':'+view.art.sha256)}" data-venue-src="${esc(view.art.image)}" alt="${esc(name)} · ${view.label}" style="--figure-scale:${Math.min(1,art.working_height_cm/165.1)}">`:`<div class="figure-fallback"><span>${worker?esc(name[0]):'◇'}</span><p>${worker?'Character illustration coming later.':'Choose your team’s assignments below.'}</p></div>`;
 return `<aside class="venue-character" aria-label="Selected character">
  <div class="character-heading"><h2>${esc(name)}</h2>${art?.side?`<span>${view.label[0].toUpperCase()+view.label.slice(1)} · Click to turn</span>`:''}</div>
  ${art?.side?`<button type="button" class="figure-stage figure-turn" data-action="turn-character" data-owner="${esc(chosen.owner)}" aria-label="Show ${esc(name)}’s ${view.nextLabel}">${figure}</button>`:`<div class="figure-stage">${figure}</div>`}
  <div class="character-caption">${worker?`<div class="character-energy"><span>Energy</span><strong>${Math.round(worker.energy)} / 100</strong></div><div class="energy"><span style="width:${Math.max(0,Math.min(100,worker.energy))}%"></span></div><div class="character-actions">${wardrobeButton(chosen.owner)}<button class="ghost small" data-action="inspect" data-card="${esc(equipped.id)}">View equipped card</button></div><small>${esc(specialties[equipped.specialty])} · Career level ${1+Math.floor(worker.xp/100)}</small>`:`<p>${esc(roomStatus(chosen))}</p>`}</div>
 </aside>`;
}
function illustratedVenue(){
 const context=venueContext(),{slots,chosen,worker,url,clips,clip,meeting,activity}=context;
 if(!chosen)return '<section class="panel">No rooms are available yet.</section>';
 const name=worker?person(chosen.owner).name:'No booking selected';
 return `<section class="illustrated-venue">
  <div class="venue-stage"><section class="venue-overview" aria-label="Room overview"><div class="venue-section-head"><h2>Your venue</h2><span>${slots.length} positions</span></div>
   <div class="illustrated-rooms" data-scroll-key="rooms">${slots.map(slot=>`<button class="illustrated-room ${slot.owner?'is-staffed':''}" data-action="select-room" data-room="${esc(slot.id)}" aria-pressed="${slot.id===chosen.id}"><div class="room-title"><strong>${esc(slot.label)}</strong><span>${esc(roomStatus(slot))}</span></div>${roomScene(slot)}<div class="room-name">${slot.owner?esc(person(slot.owner).name):'No team assigned'}<span>${slot.id===chosen.id?'Viewing':'View room →'}</span></div></button>`).join('')}</div>
   <p class="venue-footnote">All rooms run together. ${((save.night?.duration??boot.night_duration)/60).toLocaleString()}-minute nights at 1×.</p>
   <div class="venue-event-overlay" aria-live="polite">${opportunities()}</div>
  </section>
  ${characterPanel(context)}
   <article class="venue-media" aria-label="Booking ${clip?'video':'photograph'}"><div class="venue-section-head"><div><span class="eyebrow">${esc(chosen.label)}</span><h2>${esc(name)}</h2></div><button class="ghost small" data-action="enlarge-booking-media" ${url||clip?'':'disabled'} aria-label="Enlarge booking ${clip?'video':'photograph'}">Enlarge ↗</button></div>
    <div class="venue-media-surface" data-venue-media-key="${esc(clip?clipUrl(clip.id):url||'empty:'+chosen.id)}">${clip?`<video class="booking-photo" controls playsinline preload="metadata" data-venue-src="${esc(clipUrl(clip.id))}" aria-label="${esc(clip.name)}"></video>`:url?`<img class="booking-photo" data-venue-src="${esc(url)}" alt="${esc(name)} · earned photograph">`:`<div class="activity-placeholder"><span>${worker?esc(name[0]):'◇'}</span><p>${worker?(boot.catalog.demo?'Demo artwork':'No earned photograph available'):'Ready for the next booking'}</p></div>`}</div>
    <div class="venue-media-footer">${clips.length?`<select data-room-clip="${esc(chosen.owner)}" aria-label="Booking media"><option value="">Earned photographs</option>${clips.map(c=>`<option value="${esc(c.id)}" ${c.id===clip?.id?'selected':''}>Video · ${esc(c.name)}</option>`).join('')}</select>`:`<span>${url?'From your earned collection':worker?'Your card progress is preserved':'Assign a team member to this room'}</span>`}<span>${worker?ownedFor(chosen.owner).length+' card'+(ownedFor(chosen.owner).length===1?'':'s')+' collected':''}</span></div>
   </article>
  </div>
  <aside class="booking-tracker" aria-label="Selected booking tracker" data-booking-key="${esc(chosen.id+':'+(meeting?.booking_number||'idle'))}"><div class="venue-section-head"><h2>Booking history <span>· ${esc(name)}</span></h2><span class="live-indicator">${save.night?(save.night.paused?'Paused':'Live'):'Preparation'}</span></div><div class="booking-scroll">${meetingCaption(meeting,activity,worker)}</div></aside>
 </section>`;
}
function nightControls(){
 const n=save.night;
 return n?`<button class="primary" data-action="pause" ${pendingDecision()?'disabled':''}>${pendingDecision()?'Choose an option':n.paused?'Resume':'Pause'}</button><select aria-label="Night speed" id="speed">${(boot.night_speeds||[1,2,4,8]).map(value=>`<option value="${value}" ${n.speed===value?'selected':''}>${value}× speed</option>`).join('')}</select><button class="ghost" data-action="finish">Finish night</button>`:`<button class="ghost" data-action="auto">Auto assign team</button><button class="primary" data-action="start" ${derived.staffing_conflicts?.length?'disabled':''}>Open for the night →</button>`;
}
function venueActivity(night, last){
 const contracts = !night && last ? contractsEndingOn(last.day) : [];
 const studio = contracts.filter(c=>c.department==='studio').length;
 const resort = contracts.length - studio;
 const counts = [];
 if(studio)counts.push(studio+' Studio '+(studio===1?'project':'projects'));
 if(resort)counts.push(resort+' Resort '+(resort===1?'checkout':'checkouts'));
 const vouchers=!night&&last?.voucher_rewards?.reduce((sum,r)=>sum+r.amount,0);
 if(vouchers)counts.push(vouchers+' '+(vouchers===1?'voucher':'vouchers'));
 const heading = counts.length ? 'Night '+last.day+' · '+counts.join(' · ') : 'Across the venue';
 const caption = night ? 'Live activity & results' : (counts.length?'Payouts & tonight’s team':'Recent results');
 const body = night
  ? `<ul class="timeline">${(night.log.length?night.log:['Guests will arrive throughout the night.']).map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`
  : `<p>${last?`Night ${last.day} finished at ${money(last.profit)} after costs.`:'Your first evening’s results will appear here.'}</p>
     ${contractReceipts(last, contracts, true)}${voucherReceipts(last)}${vouchers?'<button class="primary small" data-screen="packs">Open pack shop →</button> ':''}<button class="ghost small" data-screen="reports">View reports →</button>`;
 return `<details class="venue-log panel" data-venue-section="activity" ${venueSections.has('activity')?'open':''}>
  <summary>${heading} <span>${caption}</span></summary>${body}</details>`;
}
function staffingConflicts(){
 const groups=derived.staffing_conflicts;
 if(save.night||!groups?.length)return '';
 const returns=contractsEndingOn(save.day-1);
 const rows=groups.map(group=>{
  const description=group.role==='room'?'Private rooms':'Lounge';
  const returned=returns.filter(c=>group.owners.includes(c.owner)).map(c=>esc(person(c.owner).name)+' is back from the '+esc(boot.departments[c.department].name)+'.');
  const choices=group.owners.map(owner=>`<button class="ghost small" data-action="rest-for-coverage" data-owner="${esc(owner)}">Rest ${esc(person(owner).name)}</button>`);
  return `<div><strong>${description} · ${group.owners.length} assigned to ${group.capacity} ${group.capacity===1?'position':'positions'}</strong>
   ${returned.length?`<p>${returned.join(' ')}</p>`:''}<div class="actions">${choices.join('')}</div></div>`;
 });
 return `<section class="panel staffing-conflicts" aria-label="Staffing conflicts"><h2>Choose who works tonight</h2>
  ${rows.join('')}<button class="ghost small" data-screen="team">Change team assignments</button></section>`;
}
function nextDepartmentOpening(){
 if(save.phase!=='prepare')return '';
 const dept=['studio','resort'].find(key=>!save.departments[key]);
 if(!dept)return '';
 const name=esc(boot.departments[dept].name);
 const title=canOpenDepartment(dept)?`${name} is ready to open`:`Next opening · ${name}`;
 return `<section class="panel next-opening" aria-labelledby="next-opening-title">
  <h2 id="next-opening-title">${title}</h2>
  ${openingGoals(dept)}
  <button class="ghost small" data-screen="${dept}">View ${name} →</button>
 </section>`;
}
function illustratedClub(){
 const n=save.night,last=save.reports.at(-1),clock=seconds=>Math.floor(seconds/60)+':'+String(Math.floor(seconds%60)).padStart(2,'0');
 return `<div class="lounge-heading"><div><div class="eyebrow">The club / Night ${save.day}</div><h1>${n?'An evening at After Hours':'Make tonight your own.'}</h1></div><div class="actions">${nightControls()}${boot.restartable?'<button class="ghost small" data-action="restart-game">Restart game</button>':''}</div></div>
  <div class="lounge-summary"><span>Cash <strong>${money(save.cash)}</strong></span><span>${n?`${clock(n.elapsed)} / ${clock(n.duration||boot.night_duration)} · ${n.paused?'Paused':'Doors open'}`:`${esc(derived.demand)} demand`}</span><span>${n?`${n.served} paid bookings · <strong>${money(n.revenue)}</strong> earned`:`<strong>${money(derived.recurring)}</strong> recurring costs`}</span><span>Last night ${last?`<strong class="${last.profit<0?'negative':'positive'}">${money(last.profit)}</strong> net`:'—'}</span></div>
  ${staffingConflicts()}${illustratedVenue()}${nextDepartmentOpening()}
  <details class="venue-planning panel" data-venue-section="planning" ${venueSections.has('planning')?'open':''}><summary>Tonight’s plan <span>Assignments, cards & prices</span></summary><div class="venue-plan-body"><div class="sectionhead"><p>Each girl keeps her career and energy across cards.</p><button class="ghost small" data-screen="team">Team & recruitment →</button></div><div class="staff-grid">${Object.keys(save.people).map(staffHTML).join('')}</div><label class="policy-label" for="pricing">Price policy</label><select id="pricing" ${n?'disabled':''}>${[['accessible','Accessible · more bookings'],['standard','Standard · balanced'],['premium','Premium · higher price, fewer bookings']].map(([value,label])=>`<option value="${value}" ${save.pricing===value?'selected':''}>${label}</option>`).join('')}</select>${savedPlans()}</div></details>
  ${venueActivity(n,last)}
  ${save.cash<derived.recurring&&!n?'<section class="panel"><h3>Time to regroup</h3><p>Take a two-day recovery break to restore energy and receive an operating reserve.</p><button data-action="recovery">Take recovery break</button></section>':''}`;
}
function enlargeBookingMedia(){
 const {url,chosen,clip}=venueContext();
 if(clip){openClip(chosen.owner,clip.id);return;}
 if(!url)return;
 const name=person(chosen.owner).name;
 modal.innerHTML=`<div class="modal-head"><div><h2>${esc(name)}</h2><p class="note">${esc(chosen.label)} · Earned photograph</p></div><button data-action="close-modal" aria-label="Close photograph">✕</button></div><div class="enlarged-booking-media"><img class="inspect-image" src="${esc(url)}" alt="${esc(name)} · earned photograph"></div>`;
 modal.showModal();
}
// Preserve the same decoded media element and reading position across clock updates.
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
 for(const img of panel.querySelectorAll('[data-venue-src]')){
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
