'use strict';

function bookingChoices(dept,kind,owner){
 const picked=departmentChoices[dept];
 if(dept==='studio'){
  return kind==='feature_film'&&picked.costar!==owner&&save.people[picked.costar]?{costar:picked.costar}:{};
 }
 const choices={};
 if(boot.department_play.plans[picked.service_plan])choices.service_plan=picked.service_plan;
 if(derived.returning_guests?.[picked.guest])choices.guest=picked.guest;
 return choices;
}
function departmentScenery(dept){
 if(dept==='studio')return `<div class="room-wall"></div><div class="room-floor"></div>
  <i class="shoot-backdrop"></i><i class="shoot-stool"></i><i class="shoot-softbox"></i><i class="shoot-camera"></i>`;
 return `<div class="room-wall"></div><div class="room-floor"></div><i class="suite-window"><b></b></i>
  <i class="suite-curtain"></i><div class="room-sofa"><i></i><b></b></div>
  <div class="room-lamp"></div><div class="room-plant"><i></i><b></b><em></em></div><div class="room-table"></div>`;
}
function departmentPreview(dept,level){
 const studio=dept==='studio',place=studio?'Production floor':'Guest suites';
 const description=studio?'Cast a shoot, direct it on set, and deliver the finished work.':'Plan each guest’s stay, handle requests, and earn a return visit.';
 return `<figure class="department-preview"><div class="venue-section-head"><h2>${place}</h2><span>${level?'Open':'Before opening'}</span></div>
  ${roomScene({id:dept+'-preview',role:dept,index:0})}<figcaption>${level?(studio?'No shoot scheduled tonight.':'No guests in residence tonight.'):description}</figcaption>
  <div class="venue-event-overlay department-overlay" aria-live="polite">${opportunities()}</div></figure>`;
}
function departmentHeader(dept,level,staffed){
 const studio=dept==='studio',name=boot.departments[dept].name,n=save.night,total=save.totals[dept+'_completed'];
 let actions=n?nightControls():'';
 if(!n&&staffed)actions+=`<button class="ghost" data-action="department-desk">${studio?'Plan a shoot':'Book a stay'} ↓</button>`;
 if(!n&&level)actions+=`<button class="primary" data-action="start" ${dis(derived.staffing_conflicts?.length)}>Open for the night →</button>`;
 actions+='<button class="ghost" data-screen="club">Back to Club</button>';
 if(boot.restartable)actions+='<button class="ghost small" data-action="restart-game">Restart game</button>';
 const inventory=studio?(level===1?'production position':'production positions'):(level===1?'guest suite':'guest suites');
 return `<header class="lounge-heading"><div><div class="eyebrow">${name} / Night ${save.day}</div><h1>The ${name}</h1></div><div class="actions">${actions}</div></header>
  <div class="lounge-summary"><span>Cash <strong>${money(save.cash)}</strong></span><span>${n?(n.paused?'Night paused':'Night in progress'):'Preparation'}</span>
  ${level?`<span><strong>${level}</strong> ${inventory}</span><span><strong>${money(level*boot.departments[dept].upkeep)}</strong> nightly upkeep</span><span>${total} ${studio?'delivered':'checked out'}</span>`:''}</div>`;
}
function bookingGoalText(goal){
 return goal.current>=goal.target?'Unlocked · '+goal.current+' '+goal.unit:goal.current+' / '+goal.target+' '+goal.unit;
}
function departmentOpening(dept,table){
 const studio=dept==='studio',ready=canOpenDepartment(dept),details=boot.departments[dept],cost=derived.department_costs[dept];
 const examples=Object.entries(table).map(([key,p])=>{
  const goal=derived.booking_goals?.[key];
  return `<li><strong>${esc(p.name)}</strong><span>${p.days} ${p.days===1?'night':'nights'} · ${studio?money(p.pay)+' base fee':money(p.rate)+' per night'}${goal?' · '+esc(bookingGoalText(goal)):''}</span></li>`;
 }).join('');
 return `<div class="department-front">${departmentPreview(dept,0)}
  <section class="panel department-gate"><h2>${ready?'Ready to open':'Opening requirements'}</h2>${openingGoals(dept,true)}
  <p>${money(cost)} to open · ${money(details.upkeep)} upkeep per night</p>
  ${ready&&save.phase==='prepare'?budgetLine('After opening and one night of wages &amp; upkeep',save.cash-cost-derived.recurring-details.upkeep):''}
  <button class="primary" data-action="department" data-kind="${dept}" ${dis(!ready||save.phase!=='prepare')}>Open ${details.name}</button></section></div>
  <section class="department-catalog"><h2>${studio?'Production briefs':'Stay packages'}</h2><ul>${examples}</ul></section>`;
}
function choiceSelect(key,label,rows,current){
 return `<label>${label}<select data-contract-choice="${key}">${rows.map(([id,text])=>`<option value="${esc(id)}" ${id===current?'selected':''}>${esc(text)}</option>`).join('')}</select></label>`;
}
function departmentChoicesUI(dept,kind,owner,quote){
 const picked=bookingChoices(dept,kind,owner);
 if(dept==='studio'){
  const people=Object.keys(save.people).filter(id=>id!==owner).map(id=>[id,person(id).name]);
  const match=card(save.people[owner].card)?.specialty===quote.preferred_specialty;
  return `${kind==='feature_film'?choiceSelect('costar','Co-star',[['','Shoot solo'],...people],picked.costar||''):''}
   <p class="department-brief"><strong>${quote.medium==='film'?'Film brief':'Photo brief'}</strong> · ${esc(quote.brief)}
   <small>Preferred specialty · ${esc(specialties[quote.preferred_specialty])}. ${match?'The lead’s equipped card adds 6% of base quality each working beat.':'A matching equipped card improves quality each working beat.'}${kind==='feature_film'?' A co-star adds $35 per night to the deposit and raises the production fee by 30%. Both cast members are reserved. The co-star receives a third of the earnings credit.':''}</small></p>`;
 }
 const guest=quote.guest_offer;
 const regulars=Object.entries(derived.returning_guests||{}).map(([key,g])=>[key,g.name+' · returning']);
 return `${choiceSelect('guest','Guest',[['','New guest'],...regulars],picked.guest||'')}
  ${choiceSelect('service_plan','Service plan',Object.entries(boot.department_play.plans),picked.service_plan||'standard')}
  <p class="department-brief"><strong>${esc(guest.name)}</strong> · ${guest.visit===1?'First stay':'Visit '+guest.visit+' · $10 extra per night'}
  <small>Enjoys ${esc(boot.department_play.preferences[guest.preference].toLowerCase())}. Matching service earns extra satisfaction.
  ${{standard:'Standard service uses the base rate and energy.',privacy:'Quiet service saves 3 energy and pays $6 less per night.',dining:'Private dining adds $12 per night to the deposit.',leisure:'Activities add $10 nightly pay and cost 4 extra energy per night.'}[quote.service_plan]}${kind==='vip'?' During the stay you can arrange a paid farewell for a highly satisfied guest.':''}</small></p>`;
}
function departmentDesk(dept,table,owner,kind,start,quote,horizon){
 const studio=dept==='studio';
 const milestone=Object.entries(derived.booking_goals||{}).find(([,goal])=>goal.department===dept);
 const progress=milestone?`<p class="department-milestone"><strong>${esc(table[milestone[0]].name)}</strong> · ${esc(bookingGoalText(milestone[1]))}</p>`:'';
 return `<section class="panel department-desk"><h2 id="department-desk" tabindex="-1">${studio?'Schedule a project':'Book a stay'}</h2>${progress}<div class="desk-fields">
  <label>${studio?'Production brief':'Package'}<select id="quote-kind-${dept}" data-quote-kind="${dept}">${Object.entries(table).map(([key,p])=>{
   const goal=derived.booking_goals?.[key];
   return `<option value="${key}" ${key===kind?'selected':''}>${esc(p.name)} · ${p.days} ${p.days===1?'night':'nights'}${goal&&goal.current<goal.target?' · Locked':''}</option>`;
  }).join('')}</select></label>
  <label>${studio?'Lead cast':'Assigned host'}<select id="quote-owner-${dept}" data-quote-owner="${dept}">${Object.keys(save.people).map(key=>`<option value="${esc(key)}" ${key===owner?'selected':''}>${esc(person(key).name)} · ${Math.round(save.people[key].energy)} energy</option>`).join('')}</select></label>
  <label>Starting night<select id="quote-start-${dept}" data-quote-start="${dept}">${Array.from({length:horizon+1},(_,i)=>save.day+i).map(day=>`<option value="${day}" ${day===start?'selected':''}>Night ${day}</option>`).join('')}</select></label>
  ${departmentChoicesUI(dept,kind,owner,quote)}</div>${contractTerms(dept,quote,start)}
  ${reservationControls(dept,owner,kind,start,quote)}<p class="note">Cancelling frees the dates. The deposit is nonrefundable.</p></section>`;
}
function contractHistory(c){
 const entries=[];
 for(const row of c.work_log||[])entries.push({day:row.day,time:row.elapsed??row.wave*30,
  text:row.stage+(row.worked?'':' · missed')+(row.earned!==undefined?' · '+money(row.earned):'')});
 for(const row of c.decisions||[])entries.push({day:row.day,time:row.elapsed??180,text:row.result});
 for(const booking of c.private_bookings||[]){
  for(const stage of booking.segments){
   if(stage.label)entries.push({day:booking.day,time:stage.start,text:stage.label.text.replace('{worker}',person(c.owner).name)});
  }
  if(booking.completed)entries.push({day:booking.day,time:booking.end,text:'Private booking paid · '+money(booking.value)});
 }
 if(!entries.length)return '';
 entries.sort((a,b)=>a.day-b.day||a.time-b.time);
 const days=[...new Set(entries.map(row=>row.day))];
 return `<details class="contract-history" data-venue-section="contract-${c.id}" ${venueSections.has('contract-'+c.id)?'open':''}><summary>Work history</summary>
  ${days.map(day=>`<h4>Night ${day}</h4><ul>${entries.filter(row=>row.day===day).map(row=>`<li>${esc(row.text)}</li>`).join('')}</ul>`).join('')}</details>`;
}
function departmentReservations(dept){
 const studio=dept==='studio',contracts=save.contracts.filter(c=>c.department===dept);
 const active=contracts.filter(c=>c.status==='active').sort((a,b)=>a.start-b.start),completed=contracts.filter(c=>c.status==='completed').slice(-8).reverse();
 const roster=c=>[c.owner,c.spec.costar].filter(Boolean).map(id=>esc(person(id).name)).join(' + ');
 return `<section class="panel department-reservations"><h2>Active reservations</h2>${active.map(c=>`<article class="reservation"><h3>${esc(c.spec.name)} · ${roster(c)}</h3>
  <p>${c.guest?esc(c.guest.name)+' · ':''}${reservationDatesLabel(c)} · ${c.nights}/${c.spec.days} completed</p>
  ${!studio?`<p>Satisfaction ${c.satisfaction}/100 · target ${c.spec.expectation} · ${money(c.revenue)} earned</p>`:''}
  ${c.license_fee?`<p>Photo license · ${money(c.license_fee)} at settlement · ${c.delivery_vouchers} Standard voucher on successful delivery</p>`:''}
  ${c.farewell_fee?`<p>Farewell reserved · ${money(c.farewell_fee)} extra at ${c.farewell_target}/100 satisfaction at checkout</p>`:''}
  ${contractHistory(c)}<button class="ghost small" data-action="cancel_contract" data-contract="${c.id}" ${dis(save.phase!=='prepare')}>Cancel · no deposit refund</button></article>`).join('')||'<p class="note">No active reservations.</p>'}
  <h2>${studio?'Recent deliveries':'Recent checkouts'}</h2>${completed.map(c=>`<article class="completed"><strong>${esc(c.spec.name)} · ${roster(c)}</strong><p>${money(c.revenue)}${c.success===false?' · rework fee':''}${c.guest?' · '+esc(c.guest.name)+(c.return_invited?' · willing to return':' · checked out'):''}${c.special_card?' · '+studioCardReward(c.special_card):''}</p>${contractHistory(c)}</article>`).join('')||'<p class="note">Completed work appears here.</p>'}</section>`;
}
function contractStageNames(c){
 const studio=c.department==='studio';
 const stages=boot.department_play.stages;
 const names=(stages[c.kind]||stages[studio?(c.spec.medium||'photo'):'resort']).slice();
 if(!studio&&save.day>reservationNights(c)[0])names[0]='Review the guest itinerary';
 if(save.day===c.end)names[5]=studio?(c.spec.medium==='film'?'Deliver the final cut':'Deliver the selects'):'Check the guest out';
 return names;
}
function departmentTracker(slot){
 const c=slot.contract,studio=slot.role==='studio';
 if(!c)return `<aside class="booking-tracker"><h2>${studio?'Production board':'Guest itinerary'}</h2><p>No reservation for this position tonight.</p></aside>`;
 const shiftNumber=reservationNights(c).indexOf(save.day)+1;
 if(!c.operations){
  const schedule='Night '+shiftNumber+' of '+c.spec.days+' · '+(studio?'Delivery':'Checkout')+' on night '+c.end;
  return `<aside class="booking-tracker department-tracker"><h2>${esc(c.spec.name)}</h2><p>${esc(person(c.owner).name)} · ${schedule}</p>
   <p>${save.night?'Shift progress · '+save.night.wave+' of 6 parts completed.':'Reserved for tonight.'} ${studio?'': 'Satisfaction '+c.satisfaction+'/100.'}</p></aside>`;
 }
 const work=(c.work_log||[]).filter(row=>row.day===save.day),next=work.length;
 const names=contractStageNames(c);
 const m=c.private_bookings?.at(-1),privateNow=m?.day===save.day&&!m.completed;
 const statuses=names.map((name,i)=>{
  const row=work.find(w=>w.wave===i+1);
  const due=!row&&i===next&&!!save.night;
  return `<li ${due&&!privateNow?'aria-current="step"':''}><small>${row?(row.worked?'Complete':'Missed'):due?(privateNow?'On hold':'Current'):'Upcoming'}</small><strong>${esc(row?.stage||name)}</strong></li>`;
 }).join('');
 const rows=m&&m.day===save.day?m.segments.filter(s=>s.label):[];
 const result=rows.length?`<div class="suite-booking"><h3>Private booking · ${m.completed?money(m.value)+' earned':'in progress'}</h3>
  <ol class="contract-stages">${rows.map((s,i)=>`<li ${!m.completed&&i===rows.length-1?'aria-current="step"':''}><small>${!m.completed&&i===rows.length-1?'Current':'Complete'}</small><strong>${esc(s.label.text.replace('{worker}',person(c.owner).name))}</strong></li>`).join('')}</ol></div>`:'';
 return `<aside class="booking-tracker department-tracker" data-booking-key="dept-${c.id}"><div class="venue-section-head"><h2>${studio?'Production board':'Guest itinerary'} <span>· ${esc(c.spec.name)}</span></h2><span class="live-indicator">${save.night?(save.night.paused?'Paused':'Live'):'Preparation'}</span></div>
  <p>${c.guest?esc(c.guest.name)+' · ':''}Night ${shiftNumber} of ${c.spec.days} · ${studio?'Delivery':'Checkout'} on night ${c.end}${studio&&derived.delivery_chances?.[c.id]!=null?' · '+Math.round(100*derived.delivery_chances[c.id])+'% delivery chance with sufficient work':''}${c.guest?' · Satisfaction '+c.satisfaction+'/100':''}${c.spec.costar?' · Co-star '+esc(person(c.spec.costar).name):''}</p>
  <ol class="contract-stages" data-scroll-key="contract-${c.id}-${save.day}">${statuses}</ol>${result}</aside>`;
}
function departmentUI(dept){
 const studio=dept==='studio',level=save.departments[dept],table=studio?boot.projects:boot.stays;
 const slots=venueSlots(dept),staffed=slots.some(s=>s.owner),header=departmentHeader(dept,level,staffed);
 if(!level)return header+departmentOpening(dept,table);
 const owner=save.people[quoteOwner[dept]]?quoteOwner[dept]:Object.keys(save.people)[0],kind=quoteKind[dept]||Object.keys(table)[0];
 quoteOwner[dept]=owner;quoteKind[dept]=kind;
 const horizon=boot.reservation_horizon??14,start=Math.min(save.day+horizon,Math.max(save.day,Number(quoteStart[dept]||save.day)));
 quoteStart[dept]=start;
 const lookup=save.phase==='prepare'?reservationLookupFor(dept,owner,kind):null;
 const quote=lookup?.quote||derived.quotes[dept][owner][kind],desk=departmentDesk(dept,table,owner,kind,start,quote,horizon);
 const reservations=departmentReservations(dept);
 const floor=staffed?illustratedVenue(slots)+`<div class="department-front">${desk}${reservations}</div>`:
  `<div class="department-front">${departmentPreview(dept,level)}${desk}</div>${reservations}`;
 return header+staffingConflicts()+floor+calendarUI(owner,start,quote.days,bookingChoices(dept,kind,owner).costar);
}
