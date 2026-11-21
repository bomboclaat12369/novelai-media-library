'use strict';
const root=document.getElementById('nai-media-host').attachShadow({mode:'open'});
globalThis.gameRoot=root;document.documentElement.dataset.naiStandalone='1';
root.innerHTML='<link rel="stylesheet" href="/game/style.css"><link rel="stylesheet" href="/game/venue.css"><div id="app"></div><dialog id="modal"></dialog><div id="toast" role="status"></div>';
const $=s=>root.querySelector(s);
const escapeHTML=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>'$'+Math.round(n).toLocaleString();
const rarities=['Common','Uncommon','Rare','Epic','Legendary'];
const specialties={tips:'Tips',service:'Booking quality',efficiency:'Energy efficiency',loyalty:'Repeat business'};
let boot,save,revision=0,derived={},screen='club',selected=new Set(),busy=false,page=0,shownPack=null,revealed=new Set();
const defaultCollectionFilter={owner:null,status:'owned',rarity:'',text:''};
let filter={...defaultCollectionFilter},collectionToken=null,spotlightOwner=null;
let toastTimer,interval,actionQueue=Promise.resolve(),restarting=false,renderDeferred=false;
const announcedDecisions=new Set();
const modal=$('#modal');
root.addEventListener('error',e=>{
 const img=e.target;
 if(img.tagName==='IMG'&&(img.classList.contains('inspect-image')||img.classList.contains('booking-photo')||img.parentElement?.classList.contains('activity-photo'))){
  const message=document.createElement('div');message.className='empty';
  message.textContent='Original artwork unavailable. Your card and progress are preserved.';img.replaceWith(message);
 }
},true);
function notify(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),4500);}
function accept(r){
 if(r.catalog){boot.catalog=r.catalog;AfterHoursCards.update(r.catalog);}
 if(r.token){
  boot.token=r.token;
  if(collectionToken!==r.token){
   collectionToken=r.token;filter={...defaultCollectionFilter};spotlightOwner=null;page=0;
  }
 }
 if(r.stage_labels)boot.stage_labels=r.stage_labels;
 if('state'in r){save=r.state;revision=r.revision;derived=r.derived||{};}
}
function act(action,body={},quiet=false){
 if(restarting)return Promise.resolve();
 actionQueue=actionQueue.then(()=>performAct(action,body,quiet)).catch(e=>notify(e.message));return actionQueue;
}
function pendingDecision(){return save?.phase==='night'?save.night.decisions.find(d=>!d.choice&&save.night.elapsed>=d.at&&save.night.elapsed<d.until):null;}
function announceDecision(){const decision=pendingDecision();if(decision&&!announcedDecisions.has(decision.id)){announcedDecisions.add(decision.id);notify('An opportunity is up. Pick an option and the night keeps rolling.');}}
async function performAct(action,body={},quiet=false){
 busy=true;
 const id=crypto.randomUUID();
 try{
  const r=await fetch('/game/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Game-Token':boot.token},body:JSON.stringify({action,body,id,revision})});
  const before=derived.evolutions||{},oldWardrobe=derived.wardrobe;
  const result=await r.json();accept(result);
  if(!r.ok)throw new Error(result.error||'The action could not be completed.');
  render();if(!quiet&&action==='upgrade')notify('Facility upgraded. Your new capacity is ready.');
  const gained=Object.entries(derived.evolutions||{}).filter(([id,line])=>before[id]&&line.forms.length>before[id].forms.length);
  if(gained.length)notify(gained.map(([id,line])=>card(id).name+' · Form '+line.forms.length+'/'+line.total+' earned').join(' · '));
  announceDecision();
  if(typeof announceOutfit==='function')announceOutfit(oldWardrobe);
 }catch(e){notify(e.message);const r=await fetch('/game/api/bootstrap');if(r.ok){boot=await r.json();accept(boot);render();}}
 finally{busy=false;}
}
function pollGame(){
 if(busy||restarting)return;
 if(renderDeferred&&!hasOpenSelect())render();
 if(save?.phase==='night'&&!save.night.paused){act('tick',{},true);return;}
 actionQueue=actionQueue.then(async()=>{
  busy=true;
  try{const r=await fetch('/game/api/state');if(r.ok){const current=await r.json();if(current.revision!==revision){const oldWardrobe=derived.wardrobe;accept(current);render();announceDecision();if(typeof announceOutfit==='function')announceOutfit(oldWardrobe);}}}
  catch{}finally{busy=false;}
 });
}
function restartGame(){
 if(restarting)return;
 restarting=true;clearInterval(interval);
 actionQueue=actionQueue.then(async()=>{
  busy=true;
  const oldToken=boot.token;
  modal.close();
  $('#app').innerHTML='<main class="panel error-panel" role="status"><h1>Restarting the game…</h1><p>Saving your place and loading local updates. This page will reconnect automatically.</p></main>';
  try{
   let response;
   try{response=await fetch('/game/api/restart',{method:'POST',headers:{'Content-Type':'application/json','X-Game-Token':oldToken},body:JSON.stringify({revision}),signal:AbortSignal.timeout(10000)});}
   catch{/* A dropped reply can mean the old process has already exited. */}
   if(response&&!response.ok){const result=await response.json();throw Error(result.error||'The game could not restart.');}
   const deadline=Date.now()+45000;
   while(Date.now()<deadline){
    await new Promise(resolve=>setTimeout(resolve,500));
    try{const r=await fetch('/game/api/bootstrap',{cache:'no-store',signal:AbortSignal.timeout(2000)});if(r.ok){const next=await r.json();if(next.token&&next.token!==oldToken&&!next.restarting){location.reload();return;}}}catch{}
   }
   throw Error('The launcher has not reconnected yet. Check its window, then try reconnecting.');
  }catch(e){
   $('#app').innerHTML=`<main class="panel error-panel"><h1>Waiting to reconnect.</h1><p>${escapeHTML(e.message)}</p><p>Your saved progress is still on this computer.</p><button data-action="reconnect">Reconnect</button></main>`;
  }finally{busy=false;}
 }).catch(e=>notify(e.message));
}
const person=id=>boot.catalog.people[id];
const card=id=>boot.catalog.cards[id];
function evolutionOf(id){return derived.evolutions?.[id];}
function duoSide(id){return save?.owned[id]?.duo_side||'front';}
function displayedArt(id,side){
 return derived.duos?.[id]?.[side||duoSide(id)] || evolutionOf(id)?.forms.at(-1);
}
function hasStarter(owner){return Object.values(boot.catalog.cards).some(c=>c.owner===owner&&c.available&&c.source!=='evolution'&&c.source!=='duo');}
function ownedFor(owner){return Object.keys(save.owned).filter(id=>card(id)?.owner===owner);}
function portrait(c,extra=''){
 const p=person(c.owner)||{name:'Unavailable',color:0};
 const available=displayedArt(c.id)?.image_available??c.available;
 return `<div class="portrait">${save?.owned[c.id]&&available&&c.image?`<img loading="lazy" src="${escapeHTML('/game'+c.image)}" alt="${escapeHTML(p.name)}">`:`<span class="initial">${escapeHTML(p.name[0])}</span><span class="demo-label">${!save?.owned[c.id]?'COLLECT TO REVEAL':boot.catalog.demo?'DEMO PORTRAIT':'ARTWORK UNAVAILABLE'}</span>`}${extra}</div>`;
}
function brand(){return '<div class="brand"><img src="/game/favicon.svg" alt=""><div><strong>After Hours</strong><small>COLLECT · MANAGE · GROW</small></div></div>';}
function flipButton(id,side,packIndex){
 const next=side==='front'?'back':'front';
 const slot=Number.isInteger(packIndex)?` data-index="${packIndex}"`:'';
 return `<button data-action="flip-duo" data-card="${escapeHTML(id)}" data-side="${next}"${slot}>Flip to ${next}</button>`;
}
function cardHTML(c,{controls=false,isNew=null,packIndex,packSide}={}){
 const p=person(c.owner),o=save?.owned[c.id],line=evolutionOf(c.id);
 const duo=c.source==='duo'&&o;
 const side=duo?(packSide||duoSide(c.id)):null;
 const duoLabel=duo?`<small class="evolution-label">Duo · ${escapeHTML(c.name)} · ${side==='front'?'Front':'Back'}</small>`:'';
 const flip=duo?`<div class="card-actions">${flipButton(c.id,side,packIndex)}</div>`:'';
 return `<article class="card rarity-${c.rarity}"><div class="approved-card" data-card-art="${escapeHTML(c.id)}"${side?` data-side="${side}"`: ''}></div><div class="cardinfo">${isNew!==null?`<span class="new-label">${isNew?'NEW DISCOVERY':'EXTRA COPY'}</span>`:''}<strong>${escapeHTML(p.name)}</strong>${duoLabel}${line?`<small class="evolution-label">${escapeHTML(c.name)} · Form ${line.forms.length}/${line.total}</small>`:''}<small>${rarities[c.rarity]} · ${escapeHTML(specialties[c.specialty])}</small><small>${o?`Mastery ${o.mastery}/5 · ${o.copies} copies${o.studio_award?' · Studio award':''}`:'Not collected yet'}</small>${!c.available?((line||duo)?'<small>Set unavailable for new pulls</small>':'<small>Source unavailable · progress retained</small>'):''}${flip}${controls?`<div class="card-actions"><button data-action="inspect" data-card="${escapeHTML(c.id)}" ${!o?'disabled':''}>View</button>${o&&save.people[c.owner]?`<button data-action="equip" data-owner="${escapeHTML(c.owner)}" data-card="${escapeHTML(c.id)}" ${save.phase!=='prepare'?'disabled':''}>${save.people[c.owner].card===c.id?'Equipped':'Equip'}</button>`:''}${o&&o.copies>1&&o.mastery<5?`<button data-action="mastery" data-card="${escapeHTML(c.id)}" ${save.phase!=='prepare'?'disabled':''}>Use extra · +30 XP</button>`:''}</div>`:''}</div></article>`;
}
function hydrateCards(parent=root){
 for(const slot of parent.querySelectorAll('[data-card-art]')){
  const id=slot.dataset.cardArt,line=evolutionOf(id);
  const form=slot.dataset.form?line?.forms[Number(slot.dataset.form)-1]:displayedArt(id,slot.dataset.side);
  AfterHoursCards.mount(slot,boot.catalog,card(id),{owned:!!save?.owned[id],form,total:line?.total});
 }
}
function setup(){
 const people=Object.values(boot.catalog.people).filter(p=>hasStarter(p.id));
 const previous=backupRows.some(b=>b.id==='previous-career.sqlite3')
  ? '<div class="source-banner"><p>Your previous career is backed up.</p><button data-action="restore-backup" data-backup="previous-career.sqlite3">Restore previous career</button></div>' : '';
 return `<main class="setup">${brand()}<div class="eyebrow">A new beginning</div><h1>Every great club starts<br>with the right two.</h1><p class="muted">Choose your founding team. Open the doors, build your collection, and grow together.</p>${previous}${boot.catalog.demo?'<div class="source-banner">Demo mode · 576 sample cards and placeholder artwork. Your media library is not connected.</div>':'<div class="source-banner">Your eligible battle-card catalog · Source images and rankings are read-only.</div>'}<div class="staff-grid">${people.map(p=>{const c=Object.values(boot.catalog.cards).find(c=>c.owner===p.id&&c.available);return `<button class="starter c${p.color} ${selected.has(p.id)?'selected':''}" data-action="select-starter" data-owner="${escapeHTML(p.id)}" aria-pressed="${selected.has(p.id)}">${portrait(c)}<div class="info"><strong>${escapeHTML(p.name)}</strong><small>${selected.has(p.id)?'✓ Selected':'Choose as founder'}</small></div></button>`;}).join('')}</div><div class="setup-footer"><div><strong>${selected.size} of 2 selected</strong><p class="muted">One lounge, one private room, and $600 to begin.</p></div><button class="primary" data-action="new" ${selected.size!==2?'disabled':''}>Open your club →</button></div><p class="source-detail">After Hours · All earnings and cards are part of this local game. Two is your starting team; the club has room to grow.</p></main>`;
}
const navigation=[['club','◇','The club'],['team','♧','Your team'],['packs','▣','Pack shop'],['collection','▤','Collection'],['expansion','⌂','Expansion'],['reports','≋','Night reports']];
function layout(content){return `<div class="layout ${screen==='club'?'illustrated-layout':''}"><aside class="sidebar">${brand()}<nav class="nav" aria-label="Game sections">${navigation.map(([id,icon,title])=>`<button data-screen="${id}" class="${screen===id?'active':''}"><span class="symbol">${icon}</span>${title}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="save-dot">● Saved on this computer</div><p>${boot.catalog.demo?'Demo catalog · placeholder art':'Library catalog · read-only'}</p><a href="/game/api/export">Export game save ↗</a><p>Club · Studio · Resort</p></div></aside><div class="main"><header class="topbar"><div class="breadcrumb">Your business <span class="muted">/</span> ${navigation.find(n=>n[0]===screen)[2]}</div><div class="topstats"><span class="pill">${save.phase==='night'?'NIGHT IN PROGRESS':'PREPARATION'} · DAY ${save.day}</span><span class="amount">${money(save.cash)}</span><small>${Object.keys(save.people).length} girls · ${Object.keys(save.owned).length} cards</small><button class="ghost small" data-action="restart-game" ${boot.restartable?'':'disabled'} title="${boot.restartable?'Load local updates and reconnect automatically':'Reopen the updated Windows launcher once to enable game restarts'}">Restart game</button></div></header><main class="content">${content}</main></div></div>`;}
function staffHTML(owner){
 const p=person(owner),w=save.people[owner],c=card(w.card);
 return `<article class="staff c${p.color}">${portrait(c,`<span class="badge">${rarities[c.rarity]}</span>`)}<div class="staffinfo"><h3>${escapeHTML(p.name)}</h3><small>Career level ${1+Math.floor(w.xp/100)} · ${escapeHTML(specialties[c.specialty])}</small><div class="energy"><span style="width:${w.energy}%"></span></div><small>Energy ${Math.round(w.energy)}/100</small><label for="role-${escapeHTML(owner)}">Tonight's assignment · ${escapeHTML(derived.assignments[owner])}</label><select id="role-${escapeHTML(owner)}" data-plan="${escapeHTML(owner)}" ${save.phase!=='prepare'||['studio','resort'].includes(derived.assignments[owner])?'disabled':''}>${[['room','Private room'],['lounge','Lounge'],['rest','Rest & recover'],['train','Training · $15']].map(([v,l])=>`<option value="${v}" ${w.role===v?'selected':''}>${l}</option>`).join('')}</select><label for="card-${escapeHTML(owner)}">Active card · ${ownedFor(owner).length} owned</label><select id="card-${escapeHTML(owner)}" data-equip="${escapeHTML(owner)}" ${save.phase!=='prepare'?'disabled':''}>${ownedFor(owner).map(id=>`<option value="${escapeHTML(id)}" ${id===w.card?'selected':''}>${escapeHTML(specialties[card(id).specialty])} · ${rarities[card(id).rarity]} · ${card(id).source==='duo'?'Duo · ':''}${escapeHTML(card(id).name)}</option>`).join('')}</select><button class="ghost small full" style="margin-top:10px" data-action="inspect" data-card="${escapeHTML(c.id)}">View active card</button>${typeof wardrobeButton==='function'?wardrobeButton(owner):''}</div></article>`;
}
function legacyClub(){
 const n=save.night,active=Object.keys(save.people).filter(p=>!['rest','train'].includes(n?.assignments[p]||derived.assignments[p])).length,last=save.reports.at(-1);
 return `<div class="pagehead"><div><div class="eyebrow">The evening is yours</div><h1>${n?'Watch your plan unfold.':'A little preparation. A great night.'}</h1><p>${n?'Your team is following the assignments you chose.':'Set the mood, choose your cards, and put the right people in the right places.'}</p></div><button class="ghost" data-action="auto" ${n?'disabled':''}>Auto assign team</button></div><section class="hero"><div><div class="eyebrow">${n?n.demand+' evening':derived.demand+' demand forecast'}</div><h2>${n?(n.paused?'The night is paused.':'The doors are open.'):'Ready when you are.'}</h2><p>${n?`${n.served} paid booking${n.served===1?'':'s'} · ${money(n.revenue)} revenue so far`:`${active} girls assigned to work. Tonight's recurring costs are ${money(derived.recurring)} before any training.`}</p>${n?`<div class="progress-track"><div class="progress-fill" style="width:${n.elapsed/(n.duration||300)*100}%"></div></div><small>${Math.floor(n.elapsed/60)}:${String(Math.floor(n.elapsed%60)).padStart(2,'0')} / ${Math.floor((n.duration||300)/60)}:${String((n.duration||300)%60).padStart(2,'0')}</small>`:''}</div><div class="actions">${n?`<button class="primary" data-action="pause" ${pendingDecision()?'disabled':''}>${pendingDecision()?'Choose an option':n.paused?'Resume':'Pause'}</button><select aria-label="Night speed" id="speed">${(boot.night_speeds||[1,2,4,8]).map(v=>`<option value="${v}" ${n.speed===v?'selected':''}>${v}× speed</option>`).join('')}</select><button class="ghost" data-action="finish">Finish night</button>`:'<button class="primary" data-action="start">Open for the night →</button>'}</div></section><div class="stats"><div class="stat"><span>TEAM</span><strong>${Object.keys(save.people).length}</strong><small>${active} working · ${Object.keys(save.people).length-active} resting / training</small></div><div class="stat"><span>CLUB POSITIONS</span><strong>${save.facilities.rooms+save.facilities.lounge}</strong><small>${save.facilities.rooms} private · ${save.facilities.lounge} lounge</small></div><div class="stat"><span>LAST NIGHT'S PROFIT</span><strong class="${last&&last.profit<0?'negative':'positive'}">${last?money(last.profit):'—'}</strong><small>After wages and operating costs</small></div><div class="stat"><span>YOUR COLLECTION</span><strong>${Object.keys(save.owned).length}</strong><small>${save.totals.packs} packs opened</small></div></div><div class="two-col"><section><div class="sectionhead"><div><h2>Tonight's team</h2><p>A different card changes her specialty. Her energy stays with her.</p></div><button class="small ghost" data-screen="team">Recruit +</button></div><div class="staff-grid">${Object.keys(save.people).map(staffHTML).join('')}</div></section><aside class="sidepanels"><div class="panel"><h3>Your evening plan</h3><p class="note">Match your staffing to capacity. Resting girls still receive wages, and recover faster.</p><label class="policy-label" for="pricing">Price policy</label><select id="pricing" class="full" ${n?'disabled':''}>${[['accessible','Accessible · more bookings'],['standard','Standard · balanced'],['premium','Premium · higher price, fewer bookings']].map(([v,l])=>`<option value="${v}" ${save.pricing===v?'selected':''}>${l}</option>`).join('')}</select><div class="panel-line"><span>Payroll</span><strong>${money(Object.keys(save.people).length*30)}</strong></div><div class="panel-line"><span>Club upkeep</span><strong>${money(derived.upkeep)}</strong></div><div class="panel-line"><span>Recovery suite</span><strong>Level ${save.facilities.recovery}</strong></div></div><div class="panel" style="margin-top:18px"><h3>${n?'Live activity':'A club that keeps growing'}</h3>${n?`<ul class="timeline">${(n.log.length?n.log:['Guests are arriving. Follow each booking in its room.']).map(t=>`<li>${escapeHTML(t)}</li>`).join('')}</ul>`:'<p class="note">Add rooms, build a rest rotation, and give each new recruit a useful place in your business.</p><button class="ghost full" style="margin-top:17px" data-screen="expansion">Explore upgrades →</button>'}</div>${save.cash<derived.recurring&&!n?'<div class="panel" style="margin-top:18px"><h3>Time to regroup</h3><p class="note">Take a two-day recovery break to restore energy and receive an operating reserve. Your collection and club stay intact.</p><button class="soft full" data-action="recovery">Take recovery break</button></div>':''}</aside></div>`;
}
function team(){
 const recruits=Object.values(boot.catalog.people).filter(p=>!save.people[p.id]&&(ownedFor(p.id).length||hasStarter(p.id)));
 return `<div class="pagehead"><div><div class="eyebrow">One team. Many possibilities.</div><h1>Your people make the place.</h1><p>New hires create choices. New cards give your favorites more ways to shine.</p></div><button class="ghost" data-action="auto" ${save.phase!=='prepare'?'disabled':''}>Auto assign</button></div><div class="staff-grid">${Object.keys(save.people).map(staffHTML).join('')}</div><div class="sectionhead"><div><h2>Meet your next recruit</h2><p>Every hire costs $30 per night in wages. Owning one of her cards waives the hiring fee.</p></div></div><div class="staff-grid">${recruits.map(p=>{const owned=ownedFor(p.id),c=card(owned[0])||Object.values(boot.catalog.cards).find(c=>c.owner===p.id&&c.available),cost=owned.length?0:derived.hire_cost;return `<article class="staff c${p.color}">${portrait(c)}<div class="staffinfo"><h3>${escapeHTML(p.name)}</h3><p class="note">${owned.length?'You already pulled her card.':'Includes a basic starter card.'}</p><div class="panel-line"><strong>${cost?money(cost):'Hiring fee waived'}</strong><small>$30 / night</small></div><button class="full ${owned.length?'primary':'ghost'}" data-action="hire" data-owner="${escapeHTML(p.id)}" ${save.phase!=='prepare'||save.cash<cost?'disabled':''}>Recruit ${escapeHTML(p.name)}</button></div></article>`;}).join('')}</div>`;
}
const packDescriptions={standard:'A little of everything. Five cards from across your catalog.',spotlight:'Five cards of one chosen girl. Find a new favorite or build mastery.',themed:'Five cards from a selected category in your collection.',premium:'Five cards, with at least one Epic or Legendary guaranteed.',collector:'Five cards, with at least one unowned card guaranteed.'};
function facilityUpkeep(kind){
 // Older local servers only included the purchase price in the upgrade catalog.
 return boot.upgrades?.[kind]?.upkeep ?? (kind==='rooms'||kind==='lounge'?8:6);
}
function budgetLine(label, remaining){
 const amount = remaining < 0 ? money(-remaining)+' short' : money(remaining)+' left';
 return `<div class="budget-line"><span>${label}</span><strong class="${remaining<0?'negative':''}">${amount}</strong></div>`;
}
function packBudget(price){
 const remaining = save.cash - price - derived.recurring;
 const rows = [budgetLine('After pack, wages & upkeep', remaining)];
 if(save.facilities.rooms === 1){
  const roomCost = derived.upgrade_costs.rooms + facilityUpkeep('rooms');
  rows.push(budgetLine('With room two as well', remaining - roomCost));
 }
 return `<div class="pack-budget">${rows.join('')}</div>`;
}
function packEligible(c){return c.available===undefined||!!c.available;}
function unrevealedDiscoveries(){
 const pack=save.pending_pack;
 if(!pack)return new Set();
 const unseen=new Set(pack.results.filter(row=>row.new).map(row=>row.id));
 for(const index of pack.revealed||[])unseen.delete(pack.results[index].id);
 return unseen;
}
function albumCounts(cards,owner,unseen){
 const tiers=rarities.map(()=>({total:0,owned:0}));
 let total=0,owned=0,retained=0;
 for(const c of cards){
  if(owner&&c.owner!==owner)continue;
  const found=!!save.owned[c.id]&&!unseen.has(c.id);
  if(!packEligible(c)){if(found)retained++;continue;}
  total++;tiers[c.rarity].total++;
  if(found){owned++;tiers[c.rarity].owned++;}
 }
 return {total,owned,retained,tiers};
}
function packChance(perSlot,slots){
 if(perSlot<=0)return '0%';
 if(perSlot>=1)return '100%';
 const percent=-100*Math.expm1(slots*Math.log1p(-perSlot));
 if(percent<0.1)return '<0.1%';
 if(percent>99.9)return '>99.9%';
 return percent.toLocaleString(undefined,{maximumFractionDigits:1})+'%';
}
function discoveryOdds(owner,counts,ownerCount){
 const weights=boot.collection_rules?.rarity_weights;
 if(!owner||!counts.total||!weights)return '';
 let denominator=0,weightedMissing=0;
 for(const [tier,line] of counts.tiers.entries()){
  if(!line.total)continue;
  denominator+=weights[tier];
  weightedMissing+=weights[tier]*(line.total-line.owned)/line.total;
 }
 const single=weightedMissing/denominator;
 return `<div class="discovery-odds"><p>Chance of at least one new ${escapeHTML(person(owner).name)} card per pack</p>
  <dl><div><dt>Standard</dt><dd>${escapeHTML(packChance(single/ownerCount,boot.packs.standard.count))}</dd></div>
  <div><dt>Spotlight</dt><dd>${escapeHTML(packChance(single,boot.packs.spotlight.count))}</dd></div></dl></div>`;
}
function packs(){
 const cards=Object.values(boot.catalog.cards),eligible=cards.filter(packEligible);
 const poolOwners=new Set(eligible.map(c=>c.owner));
 const owners=Object.values(boot.catalog.people).filter(p=>poolOwners.has(p.id));
 const target=[spotlightOwner,save.collection_target,owners[0]?.id].find(id=>poolOwners.has(id));
 const counts=target?albumCounts(eligible,target,unrevealedDiscoveries()):null;
 const themes=[...new Set(eligible.flatMap(c=>c.categories))].sort();
 const spotlight=target?`<label>Spotlight character<select aria-label="Spotlight girl" id="spotlight-target">${owners.map(p=>`<option value="${escapeHTML(p.id)}" ${p.id===target?'selected':''}>${escapeHTML(p.name)}</option>`).join('')}</select></label>
  <p class="spotlight-count">${counts.owned} / ${counts.total} collected · ${counts.total===counts.owned?'All draws are extra copies':(counts.total-counts.owned)+' missing'}</p>
  ${discoveryOdds(target,counts,owners.length)}
  <button class="ghost small" data-action="view-collection" data-owner="${escapeHTML(target)}">View ${escapeHTML(person(target).name)}’s collection</button>`:'<p class="note">No eligible Spotlight cards.</p>';
 return `<div class="pagehead"><div><div class="eyebrow">Something worth opening</div><h1>Your next favorite is in here.</h1><p>See what each pack leaves in cash after one night of wages and upkeep for your current team.</p></div></div>
 <div class="pack-grid">${Object.entries(boot.packs).map(([id,p])=>{
  const disabled=save.phase!=='prepare'||save.cash<p.price||!eligible.length||(id==='premium'&&!eligible.some(c=>c.rarity>=3))||(id==='collector'&&!eligible.some(c=>!save.owned[c.id]))||(id==='themed'&&!themes.length);
  return `<article class="pack ${id}"><div class="pack-art"><div class="wrapper"><span class="diamond">◇</span><strong>${escapeHTML(p.name)}</strong><small>5 COLLECTIBLE CARDS</small></div></div><h2>${escapeHTML(p.name)}</h2><p>${packDescriptions[id]}</p>${id==='spotlight'?spotlight:id==='themed'?`<select aria-label="Pack category" id="themed-target">${themes.map(t=>`<option>${escapeHTML(t)}</option>`).join('')}</select>`:'<div class="pack-detail">Character odds are balanced independently of image count.</div>'}${disabled?'':packBudget(p.price)}<div class="purchase"><strong class="cost">${money(p.price)}</strong><button class="${id==='premium'?'primary':'ghost'}" data-action="pack" data-pack="${id}" ${disabled?'disabled':''}>Open pack</button></div></article>`;}).join('')}</div>
 <div class="panel" style="margin-top:24px"><h3>What is inside?</h3><p class="note">Standard slots choose a girl uniformly, then use rarity weights of ${boot.collection_rules?.rarity_weights.join(' / ')||'55 / 27 / 12 / 5 / 1'} for Common through Legendary among her available tiers. Missing tiers are removed and weights renormalized. Guaranteed slots draw from the qualifying pool. Spotlight packs use the selected girl's pool; themed packs use the selected category. Duplicates remain useful for mastery. All prices and odds are adjustable balance settings.</p></div>`;
}
function cardKind(c){return c.source==='duo'?'Duo':c.source==='evolution'?'Evolution':'Photo';}
function missingCardsTable(cards){
 const groups=new Map();
 for(const c of cards){
  const type=cardKind(c),key=JSON.stringify([c.owner,c.rarity,type]);
  const row=groups.get(key);
  if(row)row.count++;
  else groups.set(key,{owner:c.owner,tier:c.rarity,type,count:1});
 }
 const rows=[...groups.values()].sort((a,b)=>person(a.owner).name.localeCompare(person(b.owner).name)||b.tier-a.tier||a.type.localeCompare(b.type));
 const pages=Math.max(1,Math.ceil(rows.length/24));page=Math.max(0,Math.min(page,pages-1));
 const body=rows.slice(page*24,(page+1)*24).map(r=>`<tr><th scope="row">${escapeHTML(person(r.owner).name)}</th><td>${r.type}</td><td>${rarities[r.tier]}</td><td>${r.count}</td></tr>`).join('');
 const table=`<div class="panel table-wrap missing-collection"><table aria-label="Missing cards by character, type and rarity"><thead><tr><th scope="col">Character</th><th scope="col">Type</th><th scope="col">Rarity</th><th scope="col">Missing</th></tr></thead><tbody>${body}</tbody></table></div>`;
 return {html:table,pages};
}
function collection(){
 const owner=filter.owner??save.collection_target??'',missing=filter.status==='missing';
 const catalog=Object.values(boot.catalog.cards),unseen=unrevealedDiscoveries(),counts=albumCounts(catalog,owner,unseen);
 const name=owner?person(owner).name:'',left=counts.total-counts.owned,search=filter.text.trim().toLowerCase();
 const choices=Object.values(boot.catalog.people);
 const owned=Object.keys(save.owned).filter(id=>!unseen.has(id)).map(card);
 const cards=(missing?catalog:owned).filter(c=>{
  if(owner&&c.owner!==owner||filter.rarity!==''&&c.rarity!==Number(filter.rarity))return false;
  if(missing&&((save.owned[c.id]&&!unseen.has(c.id))||!packEligible(c)))return false;
  if(!search)return true;
  const fields=[person(c.owner).name,cardKind(c),rarities[c.rarity],...c.categories,specialties[c.specialty]];
  if(!missing)fields.push(c.name);
  return fields.join(' ').toLowerCase().includes(search);
 });
 let html='',pages=1;
 if(!cards.length){
  page=0;
  const message=missing&&counts.total&&!left?'Every card in this pack pool is collected.':missing?'No missing cards match these filters.':'No collected cards match these filters.';
  html=`<div class="empty">${message}</div>`;
 }else if(missing){
  ({html,pages}=missingCardsTable(cards));
 }else{
  cards.sort((a,b)=>b.rarity-a.rarity||a.id.localeCompare(b.id));
  pages=Math.ceil(cards.length/24);page=Math.max(0,Math.min(page,pages-1));
  html=`<div class="card-grid">${cards.slice(page*24,(page+1)*24).map(c=>cardHTML(c,{controls:true})).join('')}</div>`;
 }
 const ownerCount=owner&&counts.total?new Set(catalog.filter(packEligible).map(c=>c.owner)).size:0;
 const tracked=save.collection_target;
 const buttons=[];
 if(owner&&boot.collection_rules)buttons.push(`<button class="ghost small" data-action="track-collection" data-owner="${escapeHTML(owner)}" aria-pressed="${owner===tracked}">${owner===tracked?'Untrack '+escapeHTML(name):'Track '+escapeHTML(name)}</button>`);
 if(!owner&&tracked)buttons.push(`<button class="ghost small" data-action="view-collection" data-owner="${escapeHTML(tracked)}">View ${escapeHTML(person(tracked).name)}’s collection</button>`);
 if(owner&&counts.total)buttons.push(`<button class="ghost small" data-action="shop-spotlight" data-owner="${escapeHTML(owner)}">View ${escapeHTML(name)}’s Spotlight pack</button>`);
 const progress=counts.total?`<strong>${counts.owned} / ${counts.total}</strong> collected from the current pack pool · ${left} missing`:'No cards are currently in this pack pool.';
 return `<div class="pagehead"><div><h1>${owner?escapeHTML(name)+'’s collection':'Your collection'}</h1><p class="collection-count">${progress}</p>
  ${counts.retained?`<p class="note">${counts.retained} previously collected ${counts.retained===1?'card is':'cards are'} outside the current pack pool.</p>`:''}</div></div>
  <div class="filters"><select id="filter-owner" aria-label="Filter girl"><option value="">All girls</option>${choices.map(p=>`<option value="${escapeHTML(p.id)}" ${owner===p.id?'selected':''}>${escapeHTML(p.name)}</option>`).join('')}</select>
   <select id="filter-status" aria-label="Collection view"><option value="owned" ${missing?'':'selected'}>Collected cards</option><option value="missing" ${missing?'selected':''}>Missing cards</option></select>
   <select id="filter-rarity" aria-label="Filter rarity"><option value="">All rarities</option>${rarities.map((r,i)=>`<option value="${i}" ${filter.rarity===String(i)?'selected':''}>${r}</option>`).join('')}</select>
   <input id="search" aria-label="Search collection" placeholder="Search character, category or specialty…" value="${escapeHTML(filter.text)}"></div>
  ${buttons.length?`<div class="collection-actions actions">${buttons.join('')}</div>`:''}
  ${discoveryOdds(owner,counts,ownerCount)}${html}
  <div class="pagination">${pages>1?`<button class="ghost small" data-page="${page-1}" ${page===0?'disabled':''}>← Previous</button>`:''}<small>${pages>1?'Page '+(page+1)+' of '+pages+' · ':''}${cards.length} ${missing?'missing':'collected'} ${cards.length===1?'card':'cards'}</small>
  ${pages>1?`<button class="ghost small" data-page="${page+1}" ${page+1>=pages?'disabled':''}>Next →</button>`:''}</div>`;
}
const upgradeText={rooms:['◇','A new private room adds one simultaneous assignment. More rooms need more staff to earn their keep.'],lounge:['♧','Add a lounge position for another working girl. Good for a varied evening and a broader team.'],recovery:['☾','Add 2 energy recovery after working, or 6 after resting and training, per level. A busy team still benefits from rest rotations.'],reception:['⌘','Improve booking acceptance by 1.8 percentage points per level. Useful when demand is quieter.']};
function legacyExpansion(){return `<div class="pagehead"><div><div class="eyebrow">Room to become something more</div><h1>Build beyond the beginning.</h1><p>Grow the club from two founders into a team with real variety, capacity, and a rest rotation.</p></div></div><div class="upgrade-grid">${Object.entries(boot.upgrades).map(([id,u])=>{const l=save.facilities[id],max=l>=u.max;return `<article class="upgrade"><span class="level">${id==='rooms'||id==='lounge'?'POSITIONS':'LEVEL'} ${l} / ${u.max}</span><span class="symbol">${upgradeText[id][0]}</span><h2>${escapeHTML(u.name)}</h2><p>${upgradeText[id][1]}</p><div class="panel-line"><span>Added upkeep</span><strong>${money(facilityUpkeep(id))} / night</strong></div>${!max&&save.phase==='prepare'&&save.cash>=derived.upgrade_costs[id]?budgetLine('After purchase, wages & upkeep',save.cash-derived.upgrade_costs[id]-derived.recurring-facilityUpkeep(id)):''}<div class="actions"><button class="primary" data-action="upgrade" data-kind="${id}" ${max||save.phase!=='prepare'||save.cash<derived.upgrade_costs[id]?'disabled':''}>${max?'Prototype maximum':`Upgrade · ${money(derived.upgrade_costs[id])}`}</button></div></article>`;}).join('')}</div><div class="panel" style="margin-top:22px"><h3>A shared future</h3><p class="note">The resort and studio are planned later departments sharing this same roster and calendar. This prototype focuses on making the growing club and card loop work first.</p></div>`;}
function reports(){return `<div class="pagehead"><div><div class="eyebrow">Learn from every evening</div><h1>The story behind the earnings.</h1><p>Recurring expenses include wages even when someone rests, plus facilities and any training.</p></div><a href="/game/api/export">Export save & history ↗</a></div><div class="stats"><div class="stat"><span>TOTAL REVENUE</span><strong>${money(save.totals.revenue)}</strong></div><div class="stat"><span>OPERATING EXPENSES</span><strong>${money(save.totals.expenses)}</strong></div><div class="stat"><span>COMPLETED BOOKINGS</span><strong>${save.totals.services}</strong></div><div class="stat"><span>PACKS OPENED</span><strong>${save.totals.packs}</strong></div></div><div class="panel table-wrap"><table><thead><tr><th>NIGHT</th><th>DEMAND</th><th>REVENUE</th><th>EXPENSES</th><th>PROFIT</th><th>BOOKINGS</th></tr></thead><tbody>${save.reports.slice().reverse().map(r=>`<tr><td>Day ${r.day}</td><td>${escapeHTML(r.demand)}</td><td>${money(r.revenue)}</td><td>${money(r.expenses)}</td><td class="${r.profit>=0?'positive':'negative'}">${money(r.profit)}</td><td>${r.served} completed · ${r.missed} missed</td></tr>`).join('')||'<tr><td colspan="6">Your first report appears after opening for a night.</td></tr>'}</tbody></table></div><p class="source-detail">The latest 40 nights are shown here. Full transaction and progression history is retained in your save export. Financial history includes every department.</p>`;}
function hasOpenSelect(){
 try{return !!root.querySelector('select:open');}
 catch{return root.activeElement?.tagName==='SELECT';}
}
function render(){
 // Replacing a native select closes its picker, even if focus is restored.
 // Keep accepting clock updates; paint the latest state once it is dismissed.
 if(hasOpenSelect()){renderDeferred=true;return;}
 renderDeferred=false;
 const focusId=root.activeElement?.id,selection=root.activeElement?.selectionStart;
 const venueView=typeof captureVenuePresentation==='function'?captureVenuePresentation():null;
 $('#app').innerHTML=save?layout(({club,team,packs,collection,expansion,reports,studio,resort,saves})[screen]()):setup();
 if(focusId){const el=root.getElementById(focusId);if(el){el.focus({preventScroll:true});if(typeof el.setSelectionRange==='function'&&selection!==null)el.setSelectionRange(selection,selection);}}
 if(typeof restoreVenuePresentation==='function')restoreVenuePresentation(venueView);
 hydrateCards();if(save?.pending_pack)showPack();
 else if(typeof refreshOpenWardrobe==='function')refreshOpenWardrobe();
}
function showPack(){
 const p=save.pending_pack;
 shownPack=p.id;revealed=new Set(p.revealed||[]);
 const all=revealed.size===p.results.length;
 modal.innerHTML=`<div class="modal-head"><div><div class="eyebrow">${escapeHTML(boot.packs[p.type].name)} · opening ${p.id}</div><h2 style="margin-top:8px">Make room for something new.</h2></div><span class="pill">${all?p.results.filter(r=>r.new).length+' new discoveries':revealed.size+' / '+p.results.length+' revealed'}</span></div><div class="reveal-grid">${p.results.map((r,i)=>revealed.has(i)?cardHTML(card(r.id),{isNew:r.new,packIndex:i,packSide:r.duo_side||'front'}):`<button class="card-back" data-action="reveal-card" data-index="${i}" aria-label="Reveal card ${i+1}"><span>◇</span><strong>AFTER HOURS</strong><small>Tap to reveal</small></button>`).join('')}</div><div class="modal-footer"><p class="note">Your cards and purchase are already saved.<br>Extra copies can advance mastery. A new girl's card waives her hiring fee.</p>${all?'<button class="primary" data-action="reveal_done">Add to my collection →</button>':'<button class="primary" data-action="reveal-all">Reveal all five</button>'}</div>`;
 hydrateCards(modal);if(!modal.open)modal.showModal();
}
function inspect(id,number){
 const c=card(id);if(!save.owned[id])return;
 if(c.source==='duo'){
  const side=duoSide(id),art=displayedArt(id,side);
  modal.innerHTML=`<div class="modal-head"><div><h2>${escapeHTML(c.name)}</h2><p class="note">${escapeHTML(person(c.owner).name)} · Duo · ${rarities[c.rarity]}</p></div><button data-action="close-modal" aria-label="Close card">✕</button></div>
   <div class="evolution-view duo-view"><button type="button" class="duo-photo" data-action="flip-duo" data-card="${escapeHTML(id)}" data-side="${side==='front'?'back':'front'}" aria-label="Flip to ${side==='front'?'back':'front'} photo"><span class="approved-card" data-card-art="${escapeHTML(id)}" data-side="${side}"></span></button>
   <div><h3>${side==='front'?'Front':'Back'}</h3>
   <div class="form-picker">${flipButton(id,side)}</div>
   <details class="duo-info"><summary>Info</summary><p class="note">${escapeHTML(specialties[c.specialty])} · Mastery ${save.owned[id].mastery}/5 · Copies ${save.owned[id].copies}</p><p class="note">Your album and equipped card show this side.</p>
   ${art?.original_available?`<a href="/game/api/image/${encodeURIComponent(id)}?original=1&amp;side=${side}" target="_blank" rel="noopener">View original ↗</a>`:''}</details></div></div>`;
  hydrateCards(modal);if(!modal.open)modal.showModal();return;
 }
 const line=evolutionOf(id);
 if(line){
  const form=number===undefined?line.forms.at(-1):line.forms[number-1];
  if(!form)return;
  const buttons=line.forms.map(f=>`<button type="button" data-action="view-form" data-card="${escapeHTML(id)}" data-form="${f.number}" aria-pressed="${f.number===form.number}">Form ${f.number}</button>`).join('');
  modal.innerHTML=`<div class="modal-head"><div><h2>${escapeHTML(c.name)}</h2><p class="note">${escapeHTML(person(c.owner).name)} · Evolution card</p></div><button data-action="close-modal" aria-label="Close card">✕</button></div><div class="evolution-view"><div class="approved-card" data-card-art="${escapeHTML(id)}" data-form="${form.number}"></div><div><h3>Form ${form.number} of ${line.total}</h3><p>${line.forms.length} of ${line.total} forms earned</p><div class="form-picker" aria-label="Earned forms">${buttons}</div><p class="note">${line.next_mastery===null?'Final form earned.':`Next form at mastery ${line.next_mastery}. Equip this card for work or use an extra copy in your album.`}</p>${form.original_available?`<a href="/game/api/image/${encodeURIComponent(id)}?original=1&amp;form=${form.number}" target="_blank" rel="noopener">View original ↗</a>`:''}</div></div>`;
  hydrateCards(modal);
  if(!modal.open)modal.showModal();
  else modal.querySelector('[data-action="view-form"][aria-pressed="true"]')?.focus();
  return;
 }
 modal.innerHTML=`<div class="modal-head"><div><h2>${escapeHTML(person(c.owner).name)}</h2><p class="note">${rarities[c.rarity]} · ${escapeHTML(specialties[c.specialty])}</p></div><button data-action="close-modal" aria-label="Close card">✕</button></div>${c.available&&c.image?`<img class="inspect-image" src="${escapeHTML('/game'+c.image)}?original=1" alt="${escapeHTML(c.name)}">`:`<div class="c${person(c.owner).color}" style="max-width:330px;margin:auto">${portrait(c)}</div>`}<p class="source-detail">${escapeHTML(c.name)} · ${c.ranked?'Battle rating snapshot '+Math.round(c.rating):'Unplaced image; included in the catalog.'}</p>`;hydrateCards(modal);modal.showModal();}
root.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b||b.disabled)return;
 if(b.dataset.action==='reconnect'){location.reload();return;}
 if(restarting)return;
 if(b.dataset.action==='restart-game'){restartGame();return;}
 if(b.dataset.screen){screen=b.dataset.screen;page=0;if(screen==='saves')await loadBackups();render();window.scrollTo(0,0);return;}
 if(b.dataset.page!==undefined){page=Number(b.dataset.page);render();return;}
 const action=b.dataset.action;if(!action)return;
 if(await managementClick(b,action))return;
 if(action==='track-collection'){
  const owner=b.dataset.owner;
  filter.owner=owner;spotlightOwner=null;
  await act('track_collection',{owner:save.collection_target===owner?null:owner});
  return;
 }
 if(action==='view-collection'){
  filter={...defaultCollectionFilter,owner:b.dataset.owner};page=0;
  screen='collection';render();window.scrollTo(0,0);return;
 }
 if(action==='shop-spotlight'){
  spotlightOwner=b.dataset.owner;screen='packs';page=0;render();
  $('#spotlight-target')?.focus();return;
 }
 if(action==='select-starter'){if(selected.has(b.dataset.owner))selected.delete(b.dataset.owner);else if(selected.size<2)selected.add(b.dataset.owner);else notify('Choose two founders. Deselect one to change your team.');render();return;}
 if(action==='reveal-card'){await act('reveal',{index:Number(b.dataset.index)});showPack();return;}
 if(action==='reveal-all'){await act('reveal',{all:true});showPack();return;}
 if(action==='inspect'){inspect(b.dataset.card);return;}
 if(action==='view-form'){inspect(b.dataset.card,Number(b.dataset.form));return;}
 if(action==='flip-duo'){
  const {card:id,side,index}=b.dataset;
  const inspecting=!!b.closest('.duo-view');
  const infoOpen=inspecting&&modal.querySelector('.duo-info').open;
  const packSlot=index!==undefined;
  const body={card:id,side};
  if(packSlot)body.index=Number(index);
  await act('duo_side',body);
  if(duoSide(id)!==side)return;
  if(inspecting&&modal.open){inspect(id);modal.querySelector('.duo-info').open=infoOpen;}
  const view=inspecting||packSlot?modal:$('#app');
  const selector=`[data-action="flip-duo"][data-card="${CSS.escape(id)}"]`+(packSlot?`[data-index="${index}"]`:'');
  const button=view.querySelector(inspecting?(b.classList.contains('duo-photo')?'.duo-view .duo-photo':'.duo-view .form-picker button'):selector);
  button?.closest('.card,.duo-view')?.querySelector('.approved-card')?.classList.add('duo-turn');
  button?.focus({preventScroll:true});
  return;
 }
 if(action==='close-modal'){modal.close();return;}
 if(action==='reveal_done'){await act(action);if(!save.pending_pack){modal.close();shownPack=null;}return;}
 if(action==='new'){await act('new',{selected:[...selected]});return;}
 if(action==='pack'){const pack=b.dataset.pack;const target=pack==='spotlight'?$('#spotlight-target').value:pack==='themed'?$('#themed-target').value:null;await act('pack',{pack,target});return;}
 const body={};for(const key of ['owner','card','kind'])if(b.dataset[key])body[key]=b.dataset[key];
 await act(action,body);
});
root.addEventListener('change',e=>{
 const el=e.target;
 if(managementChange(el))return;
 if(el.dataset.plan)act('plan',{owner:el.dataset.plan,role:el.value});
 else if(el.dataset.equip)act('equip',{owner:el.dataset.equip,card:el.value});
 else if(el.id==='pricing')act('price',{pricing:el.value});
 else if(el.id==='speed')act('speed',{speed:Number(el.value)});
 else if(el.id==='spotlight-target'){spotlightOwner=el.value;render();}
 else if(el.id.startsWith('filter-')){filter[el.id.slice(7)]=el.value;page=0;render();}
});
let searchTimer;
root.addEventListener('input',e=>{if(e.target.id==='search'){filter.text=e.target.value;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{page=0;render();},180);}});
modal.addEventListener('cancel',e=>{if(save?.pending_pack)e.preventDefault();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollGame();});
let playerPresence=null;
function connectPlayerPresence(){
 if(!boot?.player_presence||window.self!==window.top||playerPresence)return;
 playerPresence=new EventSource('/game/api/player-presence?key='+encodeURIComponent(boot.player_presence));
}
window.addEventListener('pagehide',()=>{playerPresence?.close();playerPresence=null;});
window.addEventListener('pageshow',connectPlayerPresence);
async function start(){
 try{const response=await fetch('/game/api/bootstrap');if(!response.ok)throw new Error('The game server is unavailable.');boot=await response.json();connectPlayerPresence();await AfterHoursCards.init(boot.catalog);initManagementUI();await initVenue();accept(boot);if(!save)await loadBackups();render();announceDecision();interval=setInterval(pollGame,1000);}
 catch(e){$('#app').innerHTML=`<main class="panel error-panel"><h1>Unable to open the club.</h1><p>${escapeHTML(e.message)}</p><p class="note">Your saved game has not been replaced. Restart the local game launcher and reload this page.</p></main>`;}
}
document.addEventListener('DOMContentLoaded',start,{once:true});
