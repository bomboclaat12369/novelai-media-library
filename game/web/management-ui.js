'use strict';
let backupRows=[],saveFilename='',quoteOwner={},quoteKind={},quoteStart={};
const selectedRooms={club:'room-0'}, departmentChoices={studio:{},resort:{}};
const openBookingHistory=new Set();
let bookingReportDay=null;
let reservationLookup=null;
const assignmentNames={room:'Private room',lounge:'Lounge',rest:'Rest',train:'Training',studio:'Studio',resort:'Resort'};
root.addEventListener('toggle',event=>{
 const id=event.target.dataset?.bookingHistory;
 if(id){if(event.target.open)openBookingHistory.add(id);else openBookingHistory.delete(id);}
},true);
const esc=escapeHTML,dis=v=>v?'disabled':'';
function staffAssignment(owner){
 const worker=save.people[owner];
 const booked=derived.reservations.find(c=>c.owner===owner||c.spec.costar===owner);
 if(booked){
  const department=boot.departments[booked.department].name;
  const duty=booked.department==='resort'?'Host':booked.owner===owner?'Lead':'Co-star';
  const dates=booked.start===booked.end?'Night '+booked.start:'Nights '+booked.start+'–'+booked.end;
  return `<div class="staff-reservation"><small>Tonight’s assignment · ${esc(department)}</small>
   <strong>${esc(booked.spec.name)}</strong><span>${duty} · ${dates}</span>
   <small>When unreserved · ${esc(assignmentNames[worker.role])}</small></div>`;
 }
 const roles=[['room','Private room'],['lounge','Lounge'],['rest','Rest & recover'],['train','Training · $15']];
 return `<label for="role-${esc(owner)}">Tonight’s assignment</label>
  <select id="role-${esc(owner)}" data-plan="${esc(owner)}" ${dis(save.phase!=='prepare')}>${roles.map(([id,name])=>`<option value="${id}" ${worker.role===id?'selected':''}>${name}</option>`).join('')}</select>`;
}
function teamHeader(){
 const roles=Object.values(save.night?.assignments||derived.assignments);
 const assigned=role=>roles.filter(value=>value===role).length;
 return `<header class="lounge-heading"><div><div class="eyebrow">Staff / Night ${save.day}</div><h1>Your team</h1></div>
  <div class="actions">${nightControls()}${boot.restartable?'<button class="ghost small" data-action="restart-game">Restart game</button>':''}</div></header>
  <div class="lounge-summary"><span>Cash <strong>${money(save.cash)}</strong></span>
  <span>Private rooms assigned <strong>${assigned('room')} / ${save.facilities.rooms}</strong></span>
  <span>Lounge assigned <strong>${assigned('lounge')} / ${save.facilities.lounge}</strong></span></div>
  ${staffingConflicts()}<div class="venue-event-overlay team-event" aria-live="polite">${opportunities()}</div>`;
}
function initManagementUI(){
 const baseSaves=saves;saves=()=>baseSaves()+writingPanel();
 const baseCollection=collection;collection=()=>baseCollection()+earnedClipsPanel(filter.owner??save.collection_target);
 navigation.splice(1,0,['studio','◈','Studio'],['resort','☼','Resort']);navigation.push(['saves','↺','Saves & catalog']);
 const oldPacks=packs;packs=()=>`<section class="panel voucher"><div><h3>Earned pack rewards</h3><p>${save.pack_vouchers} Standard ${save.pack_vouchers===1?'voucher':'vouchers'} available · one free Standard pack each.</p></div><button data-action="voucher" ${dis(save.phase!=='prepare'||!save.pack_vouchers)}>Redeem a voucher</button></section>`+oldPacks()+voucherHistory();
 const oldTeam=team;team=()=>oldTeam()+development();
}
function head(kicker,title,text){return `<div class="pagehead"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${text}</p></div></div>`;}
function meetingCaption(meeting,activity,worker){
 const text=meeting?meeting.text:activity?activity.label+' · '+activity.status:worker?'Following your prepared assignment.':'Assign a team member or schedule a reservation.';
 const progress=meeting?.progress;
 return `<p class="meeting-text">${esc(text)}</p>${meeting?`<div class="meeting-meta"><span>${esc(meeting.phase)}</span>${progress!==null?`<span>${meeting.remaining}s remaining</span>`:''}</div>${progress!==null?`<div class="progress-track" role="progressbar" aria-label="Meeting progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><div class="progress-fill" style="width:${progress}%"></div></div>`:''}${meeting.timeline?.length?`<div class="booking-heading">Booking ${meeting.booking_number} · ${meeting.finish_count} finish${meeting.finish_count===1?'':'es'} so far</div>${bookingTimeline(meeting.timeline)}`:''}${bookingHistory(meeting)}${meeting.last?`<p class="note meeting-last">Last booking: ${esc(meeting.last.text)} · +${money(meeting.last.value)}</p>`:''}`:''}`;
}
function bookingTimeline(rows){
 return `<ol class="booking-timeline" aria-label="Booking stages in order">${rows.map(row=>`<li class="${row.status==='current'?'is-current':row.status==='paused'?'is-paused':'is-done'}" ${row.status==='current'?'aria-current="step"':''}><div class="booking-step-meta"><strong>${row.status==='current'?'NOW':row.status==='paused'?'PAUSED':'DONE'}</strong><span>${Math.floor(row.at/60)}:${String(Math.floor(row.at%60)).padStart(2,'0')} · ${esc(row.phase)}${row.participants?' · '+esc(row.participants):''}${row.cycle>1?` · Round ${row.cycle}`:''}</span></div><span>${esc(row.text)}</span></li>`).join('')}</ol>`;
}
function bookingHistory(meeting){
 return (meeting?.history||[]).map(past=>`<details class="booking-history" data-booking-history="${esc(past.id)}" ${openBookingHistory.has(past.id)?'open':''}><summary>Booking ${past.number} · ${past.duration}s · ${past.finish_count} finish${past.finish_count===1?'':'es'} · +${money(past.value)}</summary>${bookingTimeline(past.timeline)}</details>`).join('');
}
function contractsEndingOn(day){
 return (save.contracts||[]).filter(c=>c.end===day && c.status==='completed');
}
function voucherReceipts(report){
 const names={first_service:'First 30 bookings',studio_delivery:'First Studio project completed',resort_checkout:'First Resort checkout'};
 const rows=(report?.voucher_rewards||[]).map(reward=>{
  const contract=reward.source==='studio'&&save.contracts.find(c=>c.id===reward.contract);
  const source=contract?person(contract.owner).name+' · '+contract.spec.name:
   names[reward.milestone]||(/^bookings-\d+$/.test(reward.milestone)?reward.milestone.slice(9)+' bookings':'Career milestone');
  return `<li>${esc(source)} · +${reward.amount} Standard ${reward.amount===1?'voucher':'vouchers'}</li>`;
 });
 return rows.length?`<ul class="voucher-receipts">${rows.join('')}</ul>`:'';
}
function voucherHistory(){
 const nights=save.reports.filter(r=>r.voucher_rewards?.length).slice().reverse();
 return nights.length?`<details class="panel"><summary>Voucher history</summary>${nights.map(r=>`<h3>Night ${r.day}</h3>${voucherReceipts(r)}`).join('')}</details>`:'';
}

function studioCardReward(id){
 const awarded=card(id);
 if(!awarded||!save.owned[id])return 'Card awarded';
 return `<button class="ghost small" data-action="inspect" data-card="${esc(id)}">View awarded card · ${esc(awarded.name)}</button>`;
}

function venueRevenue(report){
 const amounts={club:0,studio:0,resort:0};
 const destinations={room:'club',lounge:'club',studio:'studio',resort:'resort'};
 const valid=n=>Number.isSafeInteger(n)&&n>=0;
 const roles=report.assignments,paid=report.earnings,dept=report.department_revenue;
 const hasDept=valid(dept)&&valid(report.revenue)&&dept<=report.revenue;
 if(dept!=null&&!hasDept)return null;
 if(roles&&paid){
  let complete=Object.keys(roles).every(id=>valid(paid[id]));
  for(const [id,value] of Object.entries(paid)){
   const venue=destinations[roles[id]];
   if(!valid(value)||(!venue&&value!==0)){complete=false;break;}
   if(venue)amounts[venue]+=value;
  }
  if(complete&&Object.values(amounts).reduce((sum,n)=>sum+n,0)===report.revenue
     &&(!hasDept||amounts.studio+amounts.resort===dept))return amounts;
 }
 if(!hasDept)return null;
 if(dept===0)return {club:report.revenue,studio:0,resort:0};
 return {club:report.revenue-dept,departments:dept};
}
function nightlyRevenue(report){
 const split=venueRevenue(report);
 if(!split)return '<p class="note">This older report records total revenue only.</p>';
 const names={club:'Club',studio:'Studio',resort:'Resort',departments:'Studio and Resort combined'};
 return `<dl class="venue-revenue" aria-label="Revenue by venue">${Object.entries(split).map(([key,value])=>
  `<div><dt>${names[key]}</dt><dd>${money(value)}</dd></div>`).join('')}</dl>`;
}
function nightReports(){
 const recent=save.reports.slice().reverse(),r=recent.find(row=>row.day===bookingReportDay)||recent[0];
 const header=`<header class="lounge-heading"><h1>Night reports</h1><a href="/game/api/export?download=1">Export save &amp; history ↗</a></header>`;
 if(!r)return header+'<section class="panel"><h2>Your first night</h2><p>Open the Club for a night to see what it earned.</p></section>';
 const stats=`<div class="lounge-summary"><span>Career revenue <strong>${money(save.totals.revenue)}</strong></span><span>Career expenses <strong>${money(save.totals.expenses)}</strong></span>
  <span>${save.totals.services} Club ${save.totals.services===1?'booking':'bookings'} · ${save.totals.studio_completed} Studio ${save.totals.studio_completed===1?'delivery':'deliveries'} · ${save.totals.resort_completed} ${save.totals.resort_completed===1?'checkout':'checkouts'}</span>
  <span>${save.totals.packs} ${save.totals.packs===1?'pack':'packs'} opened</span></div>`;
 const picker=`<label class="report-picker">Report night <select id="booking-report-night">${recent.map(row=>`<option value="${row.day}" ${row===r?'selected':''}>Night ${row.day} · ${esc(row.demand)}</option>`).join('')}</select></label>`;
 const costs=r.costs?[['Wages',r.costs.payroll],['Venue upkeep',r.costs.upkeep],['Training',r.costs.training],['Business decisions',r.costs.decisions]]:
  [['Training',r.training_cost],['Business decisions',r.decision_costs]].filter(([,v])=>Number.isFinite(v));
 const costLines=costs.map(([name,value])=>`<div><dt>${name}</dt><dd>${money(value)}</dd></div>`).join('');
 const contracts=contractsEndingOn(r.day),vouchers=voucherReceipts(r);
 const decisions=(r.decisions||[]).filter(d=>d.choice).map(d=>`<li><strong>${esc(d.copy?.title||boot.decisions[d.kind]?.title||d.kind)}</strong> · ${d.choice==='accept'?'Accepted':'Passed'}${d.automatic?' automatically':''}${d.result?' · '+esc(d.result):''}</li>`).join('');
 const records=recent.map(row=>`<tr><th scope="row">${row.day}</th><td>${esc(row.demand)}</td><td>${money(row.revenue)}</td><td>${money(row.expenses)}</td><td>${money(row.profit)}</td><td>${row.served} completed · ${row.missed} missed</td></tr>`).join('');
 return header+stats+`<section class="panel night-balance"><div class="report-heading"><h2>Night ${r.day} · ${money(r.profit)} after costs</h2>${picker}</div>
  <div class="report-columns"><div><h3>Revenue received · ${money(r.revenue)}</h3>${nightlyRevenue(r)}<p class="note">Studio fees arrive on delivery. Resort lodging pays each night.</p></div>
  <div><h3>Operating costs · ${money(r.expenses)}</h3><dl class="night-costs">${costLines}</dl>${!r.costs?'<p class="note">This older report combines wages and upkeep in its total.</p>':''}</div></div></section>
  ${contracts.length||vouchers?`<section class="panel report-receipts"><h2>Completed work and rewards</h2>${contractReceipts(r,contracts)}${vouchers}</section>`:''}
  <details class="panel report-decisions" data-venue-section="report-${r.day}" ${venueSections.has('report-'+r.day)?'open':''}><summary>Night ${r.day} · planning and decisions</summary>
   ${decisions?`<h3>Decisions</h3><ul>${decisions}</ul>`:''}
   ${r.activity?.length?`<h3>Shift log</h3><ul>${r.activity.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`:''}</details>
  ${bookingReports(r)}
  <details class="panel report-history" data-venue-section="past-reports" ${venueSections.has('past-reports')?'open':''}><summary>Previous nights · ${recent.length} reports</summary>
   <div class="table-wrap"><table><thead><tr><th>Night</th><th>Demand</th><th>Revenue</th><th>Expenses</th><th>After costs</th><th>Club bookings</th></tr></thead><tbody>${records}</tbody></table></div>
   <p class="note">The last 40 nights are available here. Your export keeps the full transaction history.</p></details>`;
}

function contractReceipts(report, contracts, showTonight=false){
 if(!contracts.length)return '';
 const roles = assignmentNames;
 const rows = contracts.map(c=>{
  const studio = c.department==='studio';
  const outcome = studio ? (c.success===false?'Studio rework':'Studio delivery') : 'Resort checkout';
  const name = person(c.owner).name;
  const title = c.spec.name || (studio?'Studio project':'Resort stay');
  const lines = [[studio?'Delivery payout':'Entire stay', money(c.revenue)]];
  if(c.delivery_extra)lines.push(['Alternate cuts included',money(c.delivery_extra)]);
  if(c.cover_fee)lines.push(['Cover commission included',money(c.cover_bonus_paid||0)]);
  const privatePay=(c.private_bookings||[]).filter(m=>m.completed).reduce((sum,m)=>sum+m.value,0);
  if(privatePay)lines.push(['Private bookings included',money(privatePay)]);
  if(!studio){
   const nightlyPay = report.earnings?.[c.owner];
   if(Number.isFinite(nightlyPay))lines.push(['Checkout night', money(nightlyPay)]);
   lines.push(['Guest satisfaction', c.satisfaction+'/100 · target '+c.spec.expectation]);
   if(Number.isFinite(c.checkout_bonus_paid))lines.push(['Checkout bonus included', money(c.checkout_bonus_paid)]);
  }
  if(Number.isFinite(c.spec.fee))lines.push(['After '+money(c.spec.fee)+' deposit', money(c.revenue-c.spec.fee)]);
  if(c.service_cost)lines.push(['After deposit and guest requests',money(c.revenue-c.spec.fee-c.service_cost)]);
  const castSize=c.spec.costar?2:1,staffNights=c.nights*castSize;
  const directReturn=c.revenue-c.spec.fee-(c.service_cost||0);
  const perNight=Number.isFinite(directReturn)&&staffNights>0?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',
   minimumFractionDigits:0,maximumFractionDigits:2}).format(directReturn/staffNights):null;
  const staffTime=perNight?`<p class="receipt-staff-time"><strong>${perNight} per staff-night</strong> · ${staffNights} ${staffNights===1?'staff-night':'staff-nights'} (${castSize} ${castSize===1?'person':'people'} × ${c.nights} ${c.nights===1?'night':'nights'}). After direct costs, before wages and upkeep.</p>`:'';
  const rewards = [];
  if(studio && c.success && Number.isSafeInteger(c.spec.packs) && c.spec.packs>0 &&
     !report.voucher_rewards?.some(r=>r.contract===c.id))
   rewards.push(c.spec.packs+' Standard '+(c.spec.packs===1?'voucher':'vouchers'));
  if(c.special_card)rewards.push(studioCardReward(c.special_card));
  const role = derived.assignments?.[c.owner];
  let plan = '';
  if(showTonight && roles[role] && save.people[c.owner]){
   const booked = role==='studio'||role==='resort';
   plan = `<p class="receipt-plan"><strong>Tonight</strong> · ${roles[role]} · ${booked?'Reserved':'Can reassign'} · ${Math.round(save.people[c.owner].energy)} energy</p>`;
  }
  const cast=c.spec.costar?name+' + '+person(c.spec.costar).name:name;
  const guest=c.guest?`<p>${esc(c.guest.name)} · ${c.return_invited?'wants to book another stay':'checked out'}</p>`:'';
  return `<li><strong>${esc(cast)} · ${esc(title)}</strong><small>${outcome}</small>
   <dl>${lines.map(([label,value])=>`<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl>
   ${staffTime}${guest}${rewards.length?`<p>${rewards.join(' · ')}</p>`:''}${contractHistory(c)}${plan}</li>`;
 });
 return `<ul class="contract-receipts" aria-label="Completed contracts">${rows.join('')}</ul>`;
}

function bookingReports(report){
 if(!Array.isArray(report.booking_history))return '';
 return `<section class="panel"><h2>Club booking histories · Night ${report.day}</h2>${report.booking_history.map(meeting=>{
  const name=person(meeting.owner).name;
  const partner=meeting.group?.partner?person(meeting.group.partner).name:'';
  const rows=meeting.segments.filter(s=>s.label).map(s=>{
   let participants='';
   if(meeting.group&&s.start>=meeting.group.start){
    if(partner)participants=({original:name,joining:partner,both:name+' + '+partner})[s.workers];
    else participants=['meeting.cleanup','meeting.complete'].includes(s.slot)?'Both clients':s.client==='joining'?'Second client':'First client';
   }
   const text=s.label.text.replace(/\{(worker|partner)\}/g,(_,key)=>key==='partner'||s.workers==='joining'?partner:name);
   return {text,participants,at:s.start-meeting.start,cycle:s.cycle,status:'done',phase:s.slot==='meeting.stage'?`Stage ${s.stage_index}`:s.slot.slice(8)};
  });
  return `<h3>${esc(name)}</h3>`+bookingHistory({history:[{id:meeting.id,number:meeting.sequence,value:meeting.value,duration:Math.round(meeting.end-meeting.start),finish_count:meeting.finish_count,timeline:rows}]});
 }).join('')||'<p>No private-room bookings that night.</p>'}</section>`;
}
function decisionContext(decision){
 if(decision.department)return boot.departments[decision.department].name+' · '+person(decision.worker).name;
 if(!decision.worker)return 'Venue-wide';
 const owners=Object.keys(save.people).filter(p=>save.night?.assignments[p]==='room');
 const index=owners.indexOf(decision.worker);
 return `${person(decision.worker).name}${decision.partner?' + '+person(decision.partner).name:decision.client==='joining'?' · Second client':''}${index>=0?` · Private room ${index+1}`:' · Lounge'}`;
}
function stageLabelsPanel(){
 const info=boot.stage_labels;if(!info)return '';
 return `<section class="panel stage-labels-panel"><h2>Stage labels</h2><p>${info.entries} labels · ${info.custom?'Your imported pack':'Included pack'}</p><label>Import stage labels<input id="stage-label-file" type="file" accept=".json,.zip,application/json,application/zip"></label><p class="note">Choose a stage-label JSON or ZIP. This replaces the active pack. Your wording stays exactly as written. New label selections use this pack; labels already shown remain saved. Missing phases use built-in wording.</p>${info.length_warnings?`<p class="note">${info.length_warnings} labels exceed the suggested 2–6 words. Their wording is preserved.</p>`:''}${info.error?`<p class="negative">The imported pack could not load; included labels are in use. ${esc(info.error)}</p>`:''}${save.night&&!save.night.stage_tracking?'<p class="note">Stage tracking begins next night. This ongoing night keeps its existing activity summaries.</p>':''}</section>`;
}
function writingPanel(){
 const info=boot.stage_labels;
 const list=Object.entries(info?.writing_packs||{}).map(([id,n])=>`<li>${esc(id)} · ${n} entries</li>`).join('');
 return `<section class="panel"><h2>Event and group wording</h2><p>Import offline event variations or group stages. Your selected wording is saved with each offer or stage.</p><label>Import writing pack<input id="event-writing-file" type="file" accept=".json,application/json"></label>${list?'<ul>'+list+'</ul>':'<small>Using the included wording.</small>'}${(info?.writing_errors||[]).map(e=>`<p class="negative">${esc(e)}</p>`).join('')}</section>`;
}
function importStageLabels(file,writing=false){
 const limit=writing?64:32;
 if(file.size>limit*1024*1024){notify('This pack exceeds '+limit+' MiB.');return;}
 actionQueue=actionQueue.then(async()=>{
  busy=true;
  try{
   const response=await fetch('/game/api/'+(writing?'writing-pack':'stage-labels'),{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Game-Token':boot.token},body:file});
   const result=await response.json();
   if(!response.ok)throw Error(result.error||'The label pack could not be imported.');
   accept(result);render();notify(writing?'Writing pack imported.':`${result.stage_labels.entries} labels imported. Wording preserved.`);
  }catch(e){notify(e.message);}
  finally{busy=false;}
 }).catch(e=>notify(e.message));
 return actionQueue;
}
function opportunities(){
 const n=save.night;
 if(!n)return '';
 return n.decisions.filter(d=>!d.choice&&n.elapsed>=d.at&&n.elapsed<d.until).map(d=>{
  const rule=boot.decisions[d.kind],copy=d.copy||rule;
  let reason='';
  if(d.department&&rule.energy>save.people[d.worker].energy)reason=person(d.worker).name+' needs '+rule.energy+' energy to accept.';
  if(d.department&&rule.cost>save.cash+n.revenue-n.decision_costs)reason='The till needs '+money(rule.cost)+' to accept.';
  return `<section class="panel decision" aria-label="Business opportunity"><div class="eyebrow">${esc(decisionContext(d))} · A business decision</div>
   <h2>${esc(copy.title)}</h2><p>${esc(copy.detail)}</p>${reason?`<p>${esc(reason)}</p>`:''}
   <div class="actions">${rule.options.map(o=>`<button class="${o.id==='decline'?'ghost':'primary'}" data-action="decision" data-decision="${esc(d.id)}" data-choice="${o.id}" ${dis(!!reason&&o.id==='accept')}>${esc(o.label)}</button>`).join('')}</div>
   <small>Pick an option and operations carry on automatically.</small></section>`;
 }).join('');
}
function venue(){return illustratedVenue();}
function savedPlans(){return `<section class="panel plan-panel"><h3>Keep a useful plan</h3><div class="form-grid"><label>Plan name<input id="plan-name" maxlength="40" placeholder="e.g. Weekend rotation"></label><button data-action="save-plan" ${dis(save.phase!=='prepare')}>Save current plan</button><label>Retained plans<select id="plan-choice"><option value="">Choose a plan</option>${Object.keys(save.saved_plans).map(n=>`<option>${esc(n)}</option>`).join('')}</select></label><button data-action="load-plan" ${dis(save.phase!=='prepare')}>Load plan</button><button data-action="delete-plan" ${dis(save.phase!=='prepare')}>Remove plan</button></div><small>Retains pricing, assignments, equipment and training. Reservations always take priority. Card changes never restore energy.</small></section>`;}
function club(){return illustratedClub();}
function development(){return `<section class="panel"><h2>Career development</h2><div class="development-grid">${Object.entries(save.people).map(([p,w])=>`<div><h3>${esc(person(p).name)}</h3><p class="note">Club ${w.skills.club} · Studio ${w.skills.studio} · Resort ${w.skills.resort} skill XP</p><label>Starting game strength<select data-profile="${esc(p)}" ${dis(save.phase!=='prepare')}>${Object.entries(boot.profiles).map(([k,v])=>`<option value="${k}" ${w.profile===k?'selected':''}>${v.name} · +4% ${v.focus}</option>`).join('')}</select></label><label>Training focus<select data-training="${esc(p)}" ${dis(save.phase!=='prepare')}>${['club','studio','resort'].map(k=>`<option ${w.training===k?'selected':''}>${k}</option>`).join('')}</select></label></div>`).join('')}</div><p class="note">These configurable traits are game rules, not claims about the people in your photographs. Changing a focus preserves earned progress.</p></section>`;}
function reservationLookupFor(department,owner,kind){
 const choices=bookingChoices(department,kind,owner);
 const key=JSON.stringify([boot.token,revision,department,owner,kind,choices]);
 if(reservationLookup?.key===key)return reservationLookup;
 const request={key},requestedRevision=revision,requestedToken=boot.token;
 reservationLookup=request;
 const query=new URLSearchParams({department,owner,kind,...choices});
 (async()=>{
  try{
   const response=await fetch('/game/api/reservation-options?'+query);
   const result=await response.json();
   if(!response.ok)throw Error(result.error||'Couldn’t check availability.');
   if(result.revision===requestedRevision&&result.token===requestedToken){request.options=result.options;request.quote=result.quote;}
   else if(reservationLookup===request){
    if(screen!==department){reservationLookup=null;return;}
    const refresh=await fetch('/game/api/bootstrap');
    if(!refresh.ok)throw Error('Couldn’t refresh the current schedule.');
    const current=await refresh.json();
    if(reservationLookup===request&&revision===requestedRevision&&boot.token===requestedToken){
     accept(current);
     reservationLookup=null;
     render();
     return;
    }
   }
  }catch(error){request.error=error.message;}
  if(reservationLookup===request&&screen===department)render();
 })();
 return request;
}
function reservationControls(dept,owner,kind,start,quote){
 const button=disabled=>`<button class="primary full" data-action="schedule" data-department="${dept}" ${dis(disabled)}>Reserve &amp; pay deposit</button>`;
 if(save.phase!=='prepare')return '<p class="note">Reservations reopen after tonight.</p>'+button(true);
 if(!Number.isInteger(boot.reservation_horizon))return button(save.cash<quote.fee);
 const lookup=reservationLookupFor(dept,owner,kind);
 if(lookup.error)return `<p class="note">${esc(lookup.error)} <button class="ghost small" data-action="retry-reservation">Try again</button></p>`+button(true);
 if(!lookup.options)return '<p role="status" class="note">Checking available nights…</p>'+button(true);
 const {first,last,conflicts,low_energy,low_costar_energy,low_cash}=lookup.options;
 const conflict=conflicts[start],worker=save.people[owner],name=person(owner).name,lines=[];
 let alternative='';
 if(conflict){
  if(conflict.contract!=null){
   const booked=save.contracts.find(contract=>contract.id===conflict.contract);
   const busyName=booked&&[booked.owner,booked.spec.costar].includes(quote.costar)&&quote.costar?person(quote.costar).name:name;
   lines.push(booked?`Night ${conflict.night} overlaps ${busyName}’s ${booked.spec.name} at the ${boot.departments[booked.department].name} (${nightRange(booked.start,booked.end)}).`:`${name} is already booked on night ${conflict.night}.`);
  }else{
   lines.push(dept==='studio'?`Every Studio position is booked on night ${conflict.night}.`:`Every Resort suite is booked on night ${conflict.night}.`);
  }
  if(!low_energy&&!low_costar_energy&&!low_cash){
   const free=Array.from({length:last-first+1},(_,i)=>first+i).filter(day=>!conflicts[day]);
   const next=free.find(day=>day>start)??free[0];
   if(next!==undefined)alternative=`<button class="ghost small" data-action="use-reservation-start" data-department="${dept}" data-start="${next}">${next>start?'Use next opening':'Use earlier opening'} · night ${next}</button>`;
   else lines.push(`All start dates through night ${last} have a conflict. Try another worker or a shorter booking.`);
  }
 }
 if(low_energy)lines.push(`${name} has ${Math.floor(worker.energy)} energy. She needs ${quote.energy} to reserve this booking.`);
 if(low_costar_energy)lines.push(`${person(quote.costar).name} needs ${quote.energy} energy to co-star.`);
 if(low_cash)lines.push(`You need ${money(quote.fee-save.cash)} more for the deposit.`);
 const blocked=!!conflict||low_energy||low_costar_energy||low_cash;
 if(!blocked){
  lines.push(`${name} can take this booking. It replaces her current ${assignmentNames[worker.role].toLowerCase()} assignment for ${quote.days===1?'one night':quote.days+' nights'}.`);
  lines.push(`${money(save.cash-quote.fee)} left after the deposit.`);
 }
 const reserve=blocked?'':budgetLine('After deposit and one night of wages &amp; upkeep',save.cash-quote.fee-derived.recurring);
 return `<div class="reservation-check" role="status">${lines.map(line=>`<p>${esc(line)}</p>`).join('')}${reserve}${alternative}</div>`+button(blocked);
}
function nightRange(start,end){return start===end?'night '+start:'nights '+start+'–'+end;}
function contractTerms(dept,quote,start){
 const end=start+quote.days-1,castSize=quote.costar?2:1,staffNights=castSize*quote.days;
 let terms;
 if(dept==='studio'){
  const rewards=[];
  if(quote.packs)rewards.push(`${quote.packs} Standard voucher on successful delivery.`);
  if(quote.days>=2)rewards.push('20% chance of an extra card on successful delivery.');
  terms=`<p>Paid on delivery, night ${end}. A successful project earns an estimated ${money(quote.estimated_pay)} · <strong>${money(quote.estimated_pay-quote.fee)} after the deposit</strong>.</p>
   <p>${Math.round(quote.success_chance*100)}% delivery chance with sufficient work completed. Rework pays 55% of the quality-adjusted fee.</p>
   ${rewards.length?`<p>${rewards.join(' ')}</p>`:''}`;
 }else{
  const baseAfterDeposit=quote.rate*quote.days-quote.fee;
  const bonus=Number.isFinite(quote.checkout_bonus)?money(quote.checkout_bonus)+' bonus':'checkout bonus';
  terms=`<p>${money(quote.rate)} base per night · <strong>${money(baseAfterDeposit)} for the stay after the deposit</strong>. Service quality adjusts nightly pay.</p>
   <p>Night ${end} checkout · ${bonus} at ${quote.expectation}/100 satisfaction or higher.</p>`;
 }
 return `<div class="quote"><p><strong>${quote.days===1?'Night '+start:'Nights '+start+'–'+end}</strong></p>
  <p>Deposit due now ${money(quote.fee)} · ${quote.energy} energy/night</p>
  <p>Reserves ${staffNights} ${staffNights===1?'staff-night':'staff-nights'} (${castSize} ${castSize===1?'person':'people'} × ${quote.days} ${quote.days===1?'night':'nights'}).</p>${terms}</div>`;
}
function canOpenDepartment(dept){
 return derived.unlocks[dept] && save.cash >= derived.department_costs[dept];
}
function openingGoals(dept,bars=false){
 const goals=derived.opening_progress?.[dept];
 if(!goals)return `<p>${dept==='studio'?'Reach night 4 and complete 18 club bookings.':'Open the Studio and complete two projects.'}</p>`;
 const labels={night:'Nights reached',bookings:'Paid club bookings',studio:'Studio',projects:'Completed Studio projects'};
 const rows=Object.entries(goals).map(([key,[current,target]])=>{
  const met=current>=target;
  const progress=key==='studio'?(met?'Open':'Still closed'):Math.min(current,target)+' / '+target;
  return `<div><dt>${labels[key]}</dt><dd class="${met?'positive':''}">${met?'✓ ':''}${progress}</dd>${bars?`<dd class="goal-meter"><progress aria-label="${labels[key]}" max="${target}" value="${Math.min(current,target)}"></progress></dd>`:''}</div>`;
 });
 const cost=derived.department_costs[dept];
 rows.push(`<div><dt>Opening funds</dt><dd>${save.cash>=cost?money(cost)+' available':money(cost-save.cash)+' short of '+money(cost)}</dd>${bars?`<dd class="goal-meter"><progress aria-label="Opening funds" max="${cost}" value="${Math.max(0,Math.min(save.cash,cost))}"></progress></dd>`:''}</div>`);
 return `<dl class="opening-goals" aria-label="Department opening progress">${rows.join('')}</dl>`;
}
function studio(){return departmentUI('studio');}function resort(){return departmentUI('resort');}
function calendarUI(owner,start,duration,costar){
 const preview=!!owner&&save.phase==='prepare',first=preview?Math.max(save.day,start-1):save.day;
 const days=Array.from({length:7},(_,i)=>first+i),last=days[days.length-1],booked=new Map();
 for(const contract of save.contracts){
  if(contract.status!=='active'||contract.end<first||contract.start>last)continue;
  for(const member of [contract.owner,contract.spec.costar].filter(Boolean)){
   if(!booked.has(member))booked.set(member,new Map());
   for(let night=Math.max(first,contract.start);night<=Math.min(last,contract.end);night++)booked.get(member).set(night,contract);
  }
 }
 const inRange=day=>preview&&day>=start&&day<start+duration;
 const rows=Object.entries(save.people).map(([id,worker])=>{
  const cells=days.map(day=>{
   const existing=booked.get(id)?.get(day),selected=(id===owner||id===costar)&&inRange(day);
   const text=existing?`${boot.departments[existing.department].name} · ${existing.spec.name}`:assignmentNames[worker.role];
   return `<td class="${selected?'proposed-night':''}">${esc(text)}</td>`;
  }).join('');
  return `<tr><th scope="row">${esc(person(id).name)}</th>${cells}</tr>`;
 }).join('');
 const proposed=[owner,costar].filter(Boolean).map(id=>esc(person(id).name)).join(' and ');
 const table=`<table><caption>${preview?'Proposed dates for '+proposed+' are highlighted. ':''}Unreserved nights show the current team plan.</caption><thead><tr><th scope="col">Team member</th>${days.map(day=>`<th scope="col" class="${inRange(day)?'range-night':''}">Night ${day}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`;
 if(owner)return `<section class="panel table-wrap reservation-calendar"><h2>Shared availability</h2>${table}</section>`;
 return `<details class="panel team-calendar" data-venue-section="team-schedule" ${venueSections.has('team-schedule')?'open':''}>
  <summary>Staff schedule · Nights ${first}–${last}</summary><div class="table-wrap reservation-calendar">${table}</div></details>`;
}
function expansion(){return legacyExpansion().replace(/<div class="panel" style="margin-top:22px"><h3>A shared future[\s\S]*$/,'')+`<div class="upgrade-grid">${Object.entries(boot.departments).map(([id,d])=>`<article class="upgrade"><span class="level">${save.departments[id]} / 6 POSITIONS</span><h2>${d.name}</h2>${save.departments[id]?'':openingGoals(id)}<p>${money(d.upkeep)} added upkeep/night</p><button data-action="department" data-kind="${id}" ${dis(save.phase!=='prepare'||!derived.unlocks[id]||save.departments[id]>=6||save.cash<derived.department_costs[id])}>${save.departments[id]?'Expand':'Open'} · ${money(derived.department_costs[id])}</button></article>`).join('')}</div><section class="panel"><h2>Keep the evening fresh</h2><p>Promotion costs $150: +3 reputation and +3.5 percentage points of club booking acceptance for four nights. Most useful with a larger staffed venue.</p><p>${save.promotion_until>=save.day?`Active through night ${save.promotion_until}.`:'No active campaign.'}</p><button data-action="marketing" ${dis(save.phase!=='prepare'||save.cash<150||save.promotion_until>=save.day+3)}>Book campaign · $150</button><p class="note">Earn one voucher at your first 30 bookings, first Studio delivery and first Resort checkout. Every further 250 club bookings earns two. No mandatory reset.</p></section>`;}
async function loadBackups(){const r=await fetch('/game/api/backups');if(r.ok){const d=await r.json();backupRows=d.backups;saveFilename=d.save_name;}}
function saves(){
 return head('Careers and backups','Your next beginning.','Start a new career or recover the progress saved in a backup.')+`
 <section class="panel"><h2>Start fresh</h2>
 <p>Choose two founders and begin on night 1 with $600. Your current career is kept as a Previous career backup.</p>
 <button data-action="new-career">Start new career</button></section>
 <div class="department-layout"><section class="panel"><h2>Save & recover</h2>
 <p>Active save · <strong>${esc(saveFilename)}</strong></p>
 <div class="actions"><a href="/game/api/export?download=1">Export save & history ↗</a><button data-action="backup-now">Create backup</button></div>
 <label>Restore a career export<input id="restore-file" type="file" accept=".json,.gz,application/json,application/gzip"></label>
 <p class="note">Restore brings back the backup's money, cards and progress. Unfinished nights resume paused.</p>
 <h3>Recent backups</h3>
 ${backupRows.map(b=>`<p class="backup-row"><span>${esc(b.label||'Revision '+Number(b.id.split('.')[0]))} · ${Math.round(b.bytes/1024)} KB</span><button data-action="restore-backup" data-backup="${esc(b.id)}">Restore backup</button></p>`).join('')||'<p>No backups yet.</p>'}
 </section><section class="panel"><h2>Catalog additions</h2>
 <p>${Object.keys(boot.catalog.people).length} retained identities · ${Object.keys(boot.catalog.cards).length} cards</p>
 <p>Refresh after adding eligible Main photos, staff, Duos, or ready evolutions. New arrivals enter hiring and packs without starting payroll.</p>
 <button data-action="refresh-catalog" ${dis(save.phase!=='prepare')}>Refresh catalog read-only</button>
 <p class="note">Rarity, mastery and discovery history stay fixed. Missing files retain their cards. Imported save paths cannot choose source media.</p>
 <h3>Optional stories</h3><p class="note">Narrative history is reserved separately. Story import, relationships and generation remain deferred and never block business progression.</p>
 </section></div>`+(!boot.catalog.demo?'<section class="panel"><h2>Video rewards</h2><p>Collect a photo to unlock videos in its Set. You can pair other clips with a photo for all careers using this Library. A career keeps the clips it has earned when you reorganize a Set or change a pairing.</p><button data-action="clip-editor">Edit video pairings</button></section>':'')+stageLabelsPanel();
}
function earnedClipsPanel(owner){
 const rows=Object.entries(derived.videos||{}).filter(([id])=>!owner||owner===id);
 if(boot.catalog.demo||filter.status==='missing')return '';
 return `<section class="panel"><h2>Earned videos</h2>${rows.length?rows.map(([id,clips])=>`<h3>${esc(person(id).name)}</h3><div class="actions">${clips.map(c=>`<button class="ghost" data-action="play-clip" data-owner="${esc(id)}" data-clip="${esc(c.id)}">▶ ${esc(c.name)}</button>`).join('')}</div>`).join(''):'<p>Collect a photo from a Set with video to unlock its clips.</p>'}</section>`;
}
function openClip(owner,id){
 const clip=derived.videos?.[owner]?.find(c=>c.id===id);if(!clip)return;
 $('.venue-media video')?.pause();
 modal.innerHTML=`<div class="modal-head"><h2>${esc(clip.name)}</h2><button data-action="close-modal" aria-label="Close video">✕</button></div><video class="clip-player" controls playsinline preload="metadata" src="${esc(clipUrl(id))}"></video>`;
 modal.showModal();
}
modal.addEventListener('close',()=>modal.querySelector('video')?.pause());
let pairingEditor;
async function editClipPair(body={}){
 const token=boot.token;
 try{
  const response=await fetch('/game/api/video-pairings',{method:'POST',headers:{'Content-Type':'application/json','X-Game-Token':token},body:JSON.stringify(body)});
  const result=await response.json();if(!response.ok)throw Error(result.error);
  if(boot.token!==token)return;
  pairingEditor=result.editor;
  if(result.revision>=revision)accept(result);
  render();showClipEditor(body.clip);
  if(body.clip)notify(body.photo?'Video pairing saved.':'Video pairing removed.');
 }catch(e){notify(e.message);}
}
function showClipEditor(selected){
 const {clips,photos,pairs}=pairingEditor,ids=Object.keys(clips).sort((a,b)=>clips[a].name.localeCompare(clips[b].name));
 const id=Object.hasOwn(clips,selected)?selected:ids[0],owner=clips[id]?.owner;
 const options=Object.entries(photos).filter(([,p])=>p.owner===owner).sort((a,b)=>a[1].name.localeCompare(b[1].name));
 modal.innerHTML=`<div class="modal-head"><h2>Video pairings</h2><button data-action="close-modal" aria-label="Close pairings">✕</button></div>${id?`<label>Clip without a Set match<select id="pair-clip">${ids.map(k=>`<option value="${esc(k)}" ${k===id?'selected':''}>${esc(person(clips[k].owner).name+' · '+clips[k].name)}</option>`).join('')}</select></label><label>Matching photo<select id="pair-photo"><option value="">Unpaired</option>${options.map(([k,p])=>`<option value="${esc(k)}" ${k===pairs[id]?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label><button class="primary" data-action="save-clip-pair">Save pairing</button>`:'<p>All eligible clips already have Set matches, or this Library has no eligible clips.</p>'}`;
 if(!modal.open)modal.showModal();
}
function managementRequest(path,data={}){
 actionQueue=actionQueue.then(async()=>{
  busy=true;
  try{
   const file=data instanceof File;
   const headers={'Content-Type':file?'application/octet-stream':'application/json','X-Game-Token':boot.token,'X-Game-Revision':String(revision)};
   const response=await fetch('/game/api/'+path,{method:'POST',headers,body:file?data:JSON.stringify({revision,...data})});
   const r=await response.json();accept(r);
   if(!response.ok)throw Error(r.error||'The operation could not be saved.');
   if(path==='new-career'){location.reload();return;}
   if(path==='restore'){
    const response=await fetch('/game/api/bootstrap');boot=await response.json();accept(boot);modal.close();shownPack=null;
    notify('Backup restored. You are back on night '+save.day+'.');
   }
   await loadBackups();render();
  }catch(e){
   notify(e.message);
   const response=await fetch('/game/api/bootstrap');if(response.ok){boot=await response.json();accept(boot);render();}
  }finally{busy=false;}
 }).catch(e=>notify(e.message));
 return actionQueue;
}
async function managementClick(b,a){
 if(a==='play-clip'){openClip(b.dataset.owner,b.dataset.clip);return true;}
 if(a==='clip-editor'){await editClipPair();return true;}
 if(a==='save-clip-pair'){b.disabled=true;const clip=$('#pair-clip').value;try{await editClipPair({clip,photo:$('#pair-photo').value||null,previous:pairingEditor.pairs[clip]||null});}finally{b.disabled=false;}return true;}
 if(a==='new-career'){
  modal.innerHTML=`<div class="modal-head"><h2>Start a new career?</h2></div>
   <p>Choose two founders and begin on night 1 with $600. Your current career will be backed up.</p>
   <p class="note">You can restore Previous career from the founder screen or Saves & catalog.</p>
   <div class="modal-footer"><button data-action="close-modal">Keep playing</button><button class="primary" data-action="confirm-new-career">Start new career</button></div>`;
  modal.showModal();return true;
 }
 if(a==='confirm-new-career'){b.disabled=true;await managementRequest('new-career');b.disabled=false;return true;}
 if(a==='enlarge-booking-media'){enlargeBookingMedia();return true;}
 if(a==='turn-character'){turnCharacter(b.dataset.owner);return true;}
 if(a==='wardrobe'){showWardrobe(b.dataset.owner);return true;}
 if(a==='wear-outfit'){
  b.disabled=true;venueViews.delete(b.dataset.owner);
  await act('wear_outfit',{owner:b.dataset.owner,outfit:b.dataset.outfit});
  if(b.isConnected)b.disabled=false;
  return true;
 }
 if(a==='select-room'){selectedRooms[screen]=b.dataset.room;render();return true;}
 if(a==='view-cast'){featuredCast.set(Number(b.dataset.contract),b.dataset.owner);render();return true;}
 if(a==='department-desk'){const desk=$('#department-desk');desk?.focus({preventScroll:true});desk?.scrollIntoView({block:'start'});return true;}
 if(a==='use-reservation-start'){quoteStart[b.dataset.department]=Number(b.dataset.start);render();return true;}
 if(a==='rest-for-coverage'){await act('plan',{owner:b.dataset.owner,role:'rest'});return true;}
 if(a==='retry-reservation'){reservationLookup=null;render();return true;}
 if(a==='voucher'){await act('pack',{pack:'standard',voucher:true});return true;}
 if(a==='save-plan'){await act('save_plan',{name:$('#plan-name').value});return true;}
 if(a==='load-plan'||a==='delete-plan'){await act(a==='load-plan'?'load_plan':'delete_plan',{name:$('#plan-choice').value});return true;}
 if(a==='schedule'){const d=b.dataset.department;await act(a,{department:d,owner:quoteOwner[d],kind:quoteKind[d],start:Number(quoteStart[d]||save.day),...bookingChoices(d,quoteKind[d],quoteOwner[d])});return true;}
 if(a==='department'){await act(a,{kind:b.dataset.kind});return true;}
 if(a==='cancel_contract'){await act(a,{contract:Number(b.dataset.contract)});return true;}
 if(a==='decision'){await act(a,{decision:b.dataset.decision,choice:b.dataset.choice});return true;}
 if(a==='backup-now'){await managementRequest('backup');return true;}
 if(a==='refresh-catalog'){await managementRequest('refresh');return true;}
 if(a==='restore-backup'){await managementRequest('restore',{backup:b.dataset.backup});return true;}
 return false;
}
function managementChange(el){
 if(el.dataset.roomClip){roomClip.set(el.dataset.roomClip,el.value);render();return true;}
 if(el.id==='pair-clip'){showClipEditor(el.value);return true;}
 if(el.id==='booking-report-night'){bookingReportDay=Number(el.value);render();return true;}
 if(el.id==='stage-label-file'&&el.files[0]){importStageLabels(el.files[0]);return true;}
 if(el.id==='event-writing-file'&&el.files[0]){importStageLabels(el.files[0],true);return true;}
 if(el.dataset.profile){act('profile',{owner:el.dataset.profile,value:el.value});return true;}
 if(el.dataset.training){act('training',{owner:el.dataset.training,value:el.value});return true;}
 if(el.dataset.quoteOwner){quoteOwner[el.dataset.quoteOwner]=el.value;render();return true;}
 if(el.dataset.quoteKind){quoteKind[el.dataset.quoteKind]=el.value;render();return true;}
 if(el.dataset.quoteStart){quoteStart[el.dataset.quoteStart]=Number(el.value);render();return true;}
 if(el.dataset.contractChoice){departmentChoices[screen][el.dataset.contractChoice]=el.value;render();return true;}
 if(el.id==='restore-file'&&el.files[0]){
  const file=el.files[0];if(file.size>256*1024*1024)notify('Choose a career export of up to 256 MiB.');
  else managementRequest('restore',file);
  return true;
 }
 return false;
}
