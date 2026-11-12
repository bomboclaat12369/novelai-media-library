'use strict';
let selectedRoom='room-0',backupRows=[],saveFilename='',quoteOwner={},quoteKind={},quoteStart={};
const openBookingHistory=new Set();
let bookingReportDay=null;
root.addEventListener('toggle',event=>{
 const id=event.target.dataset?.bookingHistory;
 if(id){if(event.target.open)openBookingHistory.add(id);else openBookingHistory.delete(id);}
},true);
const esc=escapeHTML,dis=v=>v?'disabled':'';
function initManagementUI(){
 const reportsBeforeBookings=reports;reports=()=>reportsBeforeBookings()+bookingReports();
 navigation.splice(1,0,['studio','◈','Studio'],['resort','☼','Resort']);navigation.push(['saves','↺','Saves & catalog']);
 const oldPacks=packs;packs=()=>`<section class="panel voucher"><div><h3>Earned pack rewards</h3><p>${save.pack_vouchers} Standard voucher(s) from deliveries and milestones.</p></div><button data-action="voucher" ${dis(save.phase!=='prepare'||!save.pack_vouchers)}>Redeem a voucher</button></section>`+oldPacks();
 const oldTeam=team;team=()=>oldTeam()+development();
 const oldReports=reports;reports=()=>oldReports()+`<section class="panel"><h2>Department results</h2><p>${save.totals.studio_completed} Studio deliveries · ${save.totals.resort_completed} Resort checkouts · ${money(save.totals.contract_revenue)} department revenue.</p><p class="note">Night reports include department earnings, wages, upkeep and business decisions. Deposits are recorded separately when scheduling; capital purchases are in the full history.</p></section>`+save.reports.slice(-3).reverse().map(r=>`<details class="panel"><summary>Night ${r.day} · planning and decisions</summary><p>Department revenue ${money(r.department_revenue)} · training ${money(r.training_cost)} · business choices ${money(r.decision_costs)}.</p><ul>${(r.activity||[]).map(t=>`<li>${esc(t)}</li>`).join('')}</ul></details>`).join('');
}
function head(kicker,title,text){return `<div class="pagehead"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${text}</p></div></div>`;}
function meetingCaption(meeting,activity,worker){
 const text=meeting?meeting.text:activity?activity.label+' · '+activity.status:worker?'Following your prepared assignment.':'Assign a team member or schedule a reservation.';
 const progress=meeting?.progress;
 return `<p class="meeting-text">${esc(text)}</p>${meeting?`<div class="meeting-meta"><span>${esc(meeting.phase)}</span>${progress!==null?`<span>${meeting.remaining}s remaining</span>`:''}</div>${progress!==null?`<div class="progress-track" role="progressbar" aria-label="Meeting progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><div class="progress-fill" style="width:${progress}%"></div></div>`:''}${meeting.timeline?.length?`<div class="booking-heading">Booking ${meeting.booking_number} · ${meeting.finish_count} finish${meeting.finish_count===1?'':'es'} so far</div>${bookingTimeline(meeting.timeline)}`:''}${bookingHistory(meeting)}${meeting.last?`<p class="note meeting-last">Last booking: ${esc(meeting.last.text)} · +${money(meeting.last.value)}</p>`:''}`:''}`;
}
function bookingTimeline(rows){
 return `<ol class="booking-timeline" aria-label="Booking stages in order">${rows.map(row=>`<li class="${row.status==='current'?'is-current':row.status==='paused'?'is-paused':'is-done'}" ${row.status==='current'?'aria-current="step"':''}><div class="booking-step-meta"><strong>${row.status==='current'?'NOW':row.status==='paused'?'PAUSED':'DONE'}</strong><span>${Math.floor(row.at/60)}:${String(Math.floor(row.at%60)).padStart(2,'0')} · ${esc(row.phase)}${row.cycle>1?` · Round ${row.cycle}`:''}</span></div><span>${esc(row.text)}</span></li>`).join('')}</ol>`;
}
function bookingHistory(meeting){
 return (meeting?.history||[]).map(past=>`<details class="booking-history" data-booking-history="${esc(past.id)}" ${openBookingHistory.has(past.id)?'open':''}><summary>Booking ${past.number} · ${past.duration}s · ${past.finish_count} finish${past.finish_count===1?'':'es'} · +${money(past.value)}</summary>${bookingTimeline(past.timeline)}</details>`).join('');
}
function bookingReports(){
 const available=save.reports.filter(r=>Array.isArray(r.booking_history));
 if(!available.length)return '';
 const report=available.find(r=>r.day===bookingReportDay)||available.at(-1);
 return `<section class="panel"><h2>Booking histories</h2><label>Night<select id="booking-report-night">${available.slice().reverse().map(r=>`<option value="${r.day}" ${r.day===report.day?'selected':''}>Night ${r.day}</option>`).join('')}</select></label>${report.booking_history.map(meeting=>{
  const name=person(meeting.owner).name;
  const rows=meeting.segments.filter(s=>s.label).map(s=>({text:s.label.text.replace('{worker}',name),at:s.start-meeting.start,cycle:s.cycle,status:'done',phase:s.slot==='meeting.stage'?`Stage ${s.stage_index}`:s.slot.slice(8)}));
  return `<h3>${esc(name)}</h3>`+bookingHistory({history:[{id:meeting.id,number:meeting.sequence,value:meeting.value,duration:Math.round(meeting.end-meeting.start),finish_count:meeting.finish_count,timeline:rows}]});
 }).join('')||'<p>No private-room bookings that night.</p>'}</section>`;
}
function decisionContext(decision){
 if(!decision.worker)return 'Venue-wide';
 const owners=Object.keys(save.people).filter(p=>save.night?.assignments[p]==='room');
 const index=owners.indexOf(decision.worker);
 return `${person(decision.worker).name}${index>=0?` · Private room ${index+1}`:' · Lounge'}`;
}
function stageLabelsPanel(){
 const info=boot.stage_labels;if(!info)return '';
 return `<section class="panel stage-labels-panel"><h2>Stage labels</h2><p>${info.entries} labels · ${info.custom?'Your imported pack':'Included pack'}</p><label>Import stage labels<input id="stage-label-file" type="file" accept=".json,.zip,application/json,application/zip"></label><p class="note">Choose a stage-label JSON or ZIP. This replaces the active pack. Your wording stays exactly as written. New label selections use this pack; labels already shown remain saved. Missing phases use built-in wording.</p>${info.length_warnings?`<p class="note">${info.length_warnings} labels exceed the suggested 2–6 words. Their wording is preserved.</p>`:''}${info.error?`<p class="negative">The imported pack could not load; included labels are in use. ${esc(info.error)}</p>`:''}${save.night&&!save.night.stage_tracking?'<p class="note">Stage tracking begins next night. This ongoing night keeps its existing activity summaries.</p>':''}</section>`;
}
function importStageLabels(file){
 if(file.size>32*1024*1024){notify('This label pack exceeds 32 MB.');return;}
 actionQueue=actionQueue.then(async()=>{
  busy=true;
  try{
   const response=await fetch('/game/api/stage-labels',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Game-Token':boot.token},body:file});
   const result=await response.json();
   if(!response.ok)throw Error(result.error||'The label pack could not be imported.');
   accept(result);render();notify(`${result.stage_labels.entries} labels imported. Wording preserved.`);
  }catch(e){notify(e.message);}
  finally{busy=false;}
 }).catch(e=>notify(e.message));
 return actionQueue;
}
function opportunities(){const n=save.night;if(!n)return '';return n.decisions.filter(d=>!d.choice&&n.elapsed>=d.at&&n.elapsed<d.until).map(d=>{const rule=boot.decisions[d.kind],copy=d.copy||rule;return `<section class="panel decision" aria-label="Business opportunity"><div class="eyebrow">${esc(decisionContext(d))} · A business decision</div><h2>${esc(copy.title)}</h2><p>${esc(copy.detail)}</p><div class="actions">${rule.options.map(o=>`<button class="${o.id==='decline'?'ghost':'primary'}" data-action="decision" data-decision="${d.id}" data-choice="${o.id}">${esc(o.label)}</button>`).join('')}</div><small>Pick an option and operations carry on automatically.</small></section>`;}).join('');}
function venue(){
 const nightSeconds=save.night ? (save.night.duration ?? 300) : boot.night_duration;
 const nightLength=nightSeconds ? `${nightSeconds/60}-minute night · ` : '';
 const slots=[];
 for(const [role,label,count] of [['room','Private room',save.facilities.rooms],['lounge','Lounge',save.facilities.lounge],['studio','Studio',save.departments.studio],['resort','Guest suite',save.departments.resort]]){
  const staff=Object.keys(save.people).filter(p=>(save.night?.assignments[p]||derived.assignments[p])===role);
  for(let i=0;i<count;i++)slots.push({id:role+'-'+i,label:label+' '+(i+1),owner:staff[i],role});
 }
 const chosen=slots.find(r=>r.id===selectedRoom)||slots[0];selectedRoom=chosen.id;
 const worker=save.people[chosen.owner],c=worker?card(worker.card):null,activity=save.night?.activities[chosen.owner];
 const variants=chosen.owner?ownedFor(chosen.owner).filter(id=>(evolutionOf(id)?.forms.at(-1)?.image_available??card(id).available)&&card(id).image):[];
 const photo=variants.length?card(variants[(save.night?.wave||0)%variants.length]):c;
 return `<section class="venue"><div class="venue-map panel"><div class="sectionhead"><div><h2>Your venue</h2><p>Select a room to follow its evening.</p></div><span class="pill">${slots.length} positions</span></div><div class="room-grid">${slots.map(r=>`<button class="room-tile ${r.id===chosen.id?'selected':''} ${r.owner?'staffed':''}" data-action="select-room" data-room="${r.id}" aria-pressed="${r.id===chosen.id}"><span>${r.role==='studio'?'◈':r.role==='resort'?'☼':'◇'}</span><strong>${r.label}</strong><small>${r.owner?esc(person(r.owner).name):'Unstaffed'}</small><em>${r.owner?(save.night?esc(derived.meetings?.[r.owner]?.phase||'In operation'):'Prepared'):'No bookings'}</em></button>`).join('')}</div><p class="venue-key">● Staffed · ○ Available · ${nightLength}Rooms keep their own booking times</p></div><article class="activity-panel"><div class="activity-photo">${photo?.image&&(evolutionOf(photo.id)?.forms.at(-1)?.image_available??photo.available)&&save.owned[photo.id]?`<img src="${esc('/game'+photo.image+'?original=1')}" alt="${esc(person(photo.owner).name)} · owned photograph">`:`<div class="activity-placeholder"><span>${worker?esc(person(chosen.owner).name[0]):'◇'}</span><p>${worker?(boot.catalog.demo?'Demo portrait':'Artwork unavailable'):'Ready for the next booking'}</p></div>`}</div><div class="activity-caption"><div class="eyebrow">${chosen.label}</div><h2>${worker?esc(person(chosen.owner).name):'An open possibility'}</h2>${meetingCaption(derived.meetings?.[chosen.owner],activity,worker)}${worker?`<small>Energy ${Math.round(worker.energy)} · Equipped: ${esc(specialties[c.specialty])}</small><button class="ghost small" data-action="inspect" data-card="${esc(c.id)}">Inspect equipped card</button>`:''}</div></article></section>`;
}
function savedPlans(){return `<section class="panel plan-panel"><h3>Keep a useful plan</h3><div class="form-grid"><label>Plan name<input id="plan-name" maxlength="40" placeholder="e.g. Weekend rotation"></label><button data-action="save-plan" ${dis(save.phase!=='prepare')}>Save current plan</button><label>Retained plans<select id="plan-choice"><option value="">Choose a plan</option>${Object.keys(save.saved_plans).map(n=>`<option>${esc(n)}</option>`).join('')}</select></label><button data-action="load-plan" ${dis(save.phase!=='prepare')}>Load plan</button><button data-action="delete-plan" ${dis(save.phase!=='prepare')}>Remove plan</button></div><small>Retains pricing, assignments, equipment and training. Reservations always take priority. Card changes never restore energy.</small></section>`;}
function club(){return legacyClub().replace('<div class="two-col">',opportunities()+venue()+savedPlans()+'<div class="two-col">');}
function development(){return `<section class="panel"><h2>Career development</h2><div class="development-grid">${Object.entries(save.people).map(([p,w])=>`<div><h3>${esc(person(p).name)}</h3><p class="note">Club ${w.skills.club} · Studio ${w.skills.studio} · Resort ${w.skills.resort} skill XP</p><label>Starting game strength<select data-profile="${esc(p)}" ${dis(save.phase!=='prepare')}>${Object.entries(boot.profiles).map(([k,v])=>`<option value="${k}" ${w.profile===k?'selected':''}>${v.name} · +4% ${v.focus}</option>`).join('')}</select></label><label>Training focus<select data-training="${esc(p)}" ${dis(save.phase!=='prepare')}>${['club','studio','resort'].map(k=>`<option ${w.training===k?'selected':''}>${k}</option>`).join('')}</select></label></div>`).join('')}</div><p class="note">These configurable traits are game rules, not claims about the people in your photographs. Changing a focus preserves earned progress.</p></section>`;}
function studio(){return departmentUI('studio');}function resort(){return departmentUI('resort');}
function departmentUI(dept){
 const isStudio=dept==='studio',table=isStudio?boot.projects:boot.stays,level=save.departments[dept];
 const intro=head('One shared calendar',isStudio?'The Studio':'The Resort',isStudio?'Reserve a creator for a defined project. Earn money, pack vouchers and occasional special card awards.':'Welcome multi-night stays. Balance package expectations, staffing, energy and guest satisfaction.');
 if(!level)return intro+`<section class="panel"><h2>${derived.unlocks[dept]?'Ready to open':'The next milestone'}</h2><p>${isStudio?'Reach night 4 and complete 18 club bookings.':'Complete two Studio projects.'}</p><p>${money(derived.department_costs[dept])} to open · ${money(boot.departments[dept].upkeep)} upkeep/night</p><button class="primary" data-action="department" data-kind="${dept}" ${dis(!derived.unlocks[dept]||save.cash<derived.department_costs[dept]||save.phase!=='prepare')}>Open ${boot.departments[dept].name}</button></section>`;
 const owner=quoteOwner[dept]&&save.people[quoteOwner[dept]]?quoteOwner[dept]:Object.keys(save.people)[0],kind=quoteKind[dept]||Object.keys(table)[0];quoteOwner[dept]=owner;quoteKind[dept]=kind;
 const quote=derived.quotes[dept][owner][kind],start=Math.max(save.day,Number(quoteStart[dept]||save.day));quoteStart[dept]=start;
 const active=save.contracts.filter(c=>c.department===dept&&c.status==='active'),completed=save.contracts.filter(c=>c.department===dept&&c.status==='completed').slice(-8).reverse();
 return intro+opportunities()+`<section class="panel"><div class="actions"><strong>${level} ${isStudio?'production position(s)':'guest suite(s)'} · ${money(level*boot.departments[dept].upkeep)} upkeep/night</strong><button data-screen="club">${save.night?'Watch the shared night':'Return to Club to open tonight'} →</button></div></section><div class="department-layout"><section class="panel"><h2>${isStudio?'Schedule a project':'Book a stay'}</h2><label>${isStudio?'Project':'Package'}<select data-quote-kind="${dept}">${Object.entries(table).map(([id,p])=>`<option value="${id}" ${id===kind?'selected':''}>${p.name} · ${p.days} night(s)</option>`).join('')}</select></label><label>Assigned ${isStudio?'creator':'host'}<select data-quote-owner="${dept}">${Object.keys(save.people).map(id=>`<option value="${esc(id)}" ${owner===id?'selected':''}>${esc(person(id).name)} · energy ${Math.round(save.people[id].energy)}</option>`).join('')}</select></label><label>Starting night<select data-quote-start="${dept}">${Array.from({length:15},(_,i)=>save.day+i).map(d=>`<option value="${d}" ${d===start?'selected':''}>Night ${d}</option>`).join('')}</select></label><div class="quote"><p><strong>Nights ${start}–${start+quote.days-1}</strong> · one worker reserved</p><p>Deposit ${money(quote.fee)} · ${quote.energy} energy/night</p><p>${isStudio?`Estimated payout ${money(quote.estimated_pay)} · ${Math.round(quote.success_chance*100)}% delivery chance. Rework pays 55%.`:`Base rate ${money(quote.rate)}/night; quality adjusts payment. Satisfaction ${quote.expectation}+ earns a checkout bonus.`}</p><p>${quote.packs?`${quote.packs} Standard voucher on successful delivery. `:''}${isStudio&&quote.days>=2?'20% chance of an extra card award on successful delivery.':''}</p></div><button class="primary full" data-action="schedule" data-department="${dept}" ${dis(save.phase!=='prepare'||save.cash<quote.fee)}>Reserve & pay deposit</button><p class="note">These dates replace club work. The calendar rejects worker and capacity conflicts. Cancelling frees the reservation without refunding its deposit.</p></section><section><h2>Active reservations</h2>${active.map(c=>`<article class="panel reservation"><h3>${esc(c.spec.name)} · ${esc(person(c.owner).name)}</h3><p>Nights ${c.start}–${c.end} · ${c.nights}/${c.spec.days} completed</p><p>${isStudio?'Shared career and equipped card apply.':`Satisfaction ${c.satisfaction}/100 · ${money(c.revenue)} earned`}</p><button class="ghost" data-action="cancel_contract" data-contract="${c.id}" ${dis(save.phase!=='prepare')}>Cancel · no deposit refund</button></article>`).join('')||'<p class="note">No active reservations.</p>'}<h3>Recent deliveries</h3>${completed.map(c=>`<p class="completed">${esc(c.spec.name)} · ${esc(person(c.owner).name)} · ${money(c.revenue)}${c.special_card?' · special card awarded':''}${c.success===false?' · reduced fee':''}</p>`).join('')||'<p class="note">Completed work appears here.</p>'}</section></div>`+calendarUI();
}
function calendarUI(){return `<section class="panel table-wrap"><h2>Shared availability</h2><table><thead><tr><th>Team member</th>${Array.from({length:7},(_,i)=>`<th>Night ${save.day+i}</th>`).join('')}</tr></thead><tbody>${Object.keys(save.people).map(p=>`<tr><td>${esc(person(p).name)}</td>${Array.from({length:7},(_,i)=>{const day=save.day+i,c=save.contracts.find(c=>c.owner===p&&c.status==='active'&&c.start<=day&&c.end>=day);return `<td>${c?c.department:'Available'}</td>`;}).join('')}</tr>`).join('')}</tbody></table><p class="note">Available dates follow the current club/rest/training plan. Every department advances together.</p></section>`;}
function expansion(){return legacyExpansion().replace(/<div class="panel" style="margin-top:22px"><h3>A shared future[\s\S]*$/,'')+`<div class="upgrade-grid">${Object.entries(boot.departments).map(([id,d])=>`<article class="upgrade"><span class="level">${save.departments[id]} / 6 POSITIONS</span><h2>${d.name}</h2><p>${id==='studio'?'Milestone: night 4 and 18 club bookings.':'Milestone: complete two Studio projects.'}</p><p>${derived.unlocks[id]?'✓ Milestone met':'Still in progress'} · ${money(d.upkeep)} added upkeep/night</p><button data-action="department" data-kind="${id}" ${dis(save.phase!=='prepare'||!derived.unlocks[id]||save.departments[id]>=6||save.cash<derived.department_costs[id])}>${save.departments[id]?'Expand':'Open'} · ${money(derived.department_costs[id])}</button></article>`).join('')}</div><section class="panel"><h2>Keep the evening fresh</h2><p>Promotion costs $150: +3 reputation and +3.5 percentage points of club booking acceptance for four nights. Most useful with a larger staffed venue.</p><p>${save.promotion_until>=save.day?`Active through night ${save.promotion_until}.`:'No active campaign.'}</p><button data-action="marketing" ${dis(save.phase!=='prepare'||save.cash<150||save.promotion_until>=save.day+3)}>Book campaign · $150</button><p class="note">Earn one voucher at your first 30 bookings, first Studio delivery and first Resort checkout. Every further 250 club bookings earns two. No mandatory reset.</p></section>`;}
async function loadBackups(){const r=await fetch('/game/api/backups');if(r.ok){const d=await r.json();backupRows=d.backups;saveFilename=d.save_name;}}
function saves(){return head('A continuing business','Keep what you have built.','Every action is committed to a separate disk save. Restore creates a new save and preserves the current file.')+`<div class="department-layout"><section class="panel"><h2>Save & recover</h2><p>Active: <strong>${esc(saveFilename)}</strong></p><div class="actions"><a href="/game/api/export">Export save & history ↗</a><button data-action="backup-now">Create backup</button></div><label>Restore a JSON export<input id="restore-file" type="file" accept=".json,application/json"></label><p class="note">Use this library's export. Version-1 prototype saves migrate without resetting money, cards or progress. Unfinished nights resume paused.</p><h3>Recent backups</h3>${backupRows.map(b=>`<p class="backup-row"><span>Revision ${Number(b.id.split('.')[0])} · ${Math.round(b.bytes/1024)} KB</span><button data-action="restore-backup" data-backup="${esc(b.id)}">Restore as new save</button></p>`).join('')||'<p>No backups yet.</p>'}</section><section class="panel"><h2>Catalog additions</h2><p>${Object.keys(boot.catalog.people).length} retained identities · ${Object.keys(boot.catalog.cards).length} cards</p><p>Refresh after adding eligible Main photos, staff, or ready evolution Sets. New arrivals enter hiring and packs without starting payroll.</p><button data-action="refresh-catalog" ${dis(save.phase!=='prepare')}>Refresh catalog read-only</button><p class="note">Rarity, mastery and discovery history stay fixed. Missing files retain their cards. Imported save paths cannot choose source media.</p><h3>Optional stories</h3><p class="note">Narrative history is reserved separately. Story import, relationships and generation remain deferred and never block business progression.</p></section></div>`+stageLabelsPanel();}
function managementRequest(path,data={}){
 actionQueue=actionQueue.then(async()=>{
  busy=true;
  try{
   const response=await fetch('/game/api/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-Game-Token':boot.token},body:JSON.stringify({revision,...data})});
   const r=await response.json();accept(r);
   if(!response.ok)throw Error(r.error||'The operation could not be saved.');
   if(path==='restore'){
    const response=await fetch('/game/api/bootstrap');boot=await response.json();accept(boot);modal.close();shownPack=null;
    notify('Restored to a new save. The previous file is preserved.');
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
 if(a==='select-room'){selectedRoom=b.dataset.room;render();return true;}
 if(a==='voucher'){await act('pack',{pack:'standard',voucher:true});return true;}
 if(a==='save-plan'){await act('save_plan',{name:$('#plan-name').value});return true;}
 if(a==='load-plan'||a==='delete-plan'){await act(a==='load-plan'?'load_plan':'delete_plan',{name:$('#plan-choice').value});return true;}
 if(a==='schedule'){const d=b.dataset.department;await act(a,{department:d,owner:quoteOwner[d],kind:quoteKind[d],start:Number(quoteStart[d]||save.day)});return true;}
 if(a==='department'){await act(a,{kind:b.dataset.kind});return true;}
 if(a==='cancel_contract'){await act(a,{contract:Number(b.dataset.contract)});return true;}
 if(a==='decision'){await act(a,{decision:b.dataset.decision,choice:b.dataset.choice});return true;}
 if(a==='backup-now'){await managementRequest('backup');return true;}
 if(a==='refresh-catalog'){await managementRequest('refresh');return true;}
 if(a==='restore-backup'){await managementRequest('restore',{backup:b.dataset.backup});return true;}
 return false;
}
function managementChange(el){
 if(el.id==='booking-report-night'){bookingReportDay=Number(el.value);render();return true;}
 if(el.id==='stage-label-file'&&el.files[0]){importStageLabels(el.files[0]);return true;}
 if(el.dataset.profile){act('profile',{owner:el.dataset.profile,value:el.value});return true;}
 if(el.dataset.training){act('training',{owner:el.dataset.training,value:el.value});return true;}
 if(el.dataset.quoteOwner){quoteOwner[el.dataset.quoteOwner]=el.value;render();return true;}
 if(el.dataset.quoteKind){quoteKind[el.dataset.quoteKind]=el.value;render();return true;}
 if(el.dataset.quoteStart){quoteStart[el.dataset.quoteStart]=Number(el.value);render();return true;}
 if(el.id==='restore-file'&&el.files[0]){const file=el.files[0];if(file.size>32*1024*1024)notify('This export exceeds the 32 MB recovery limit.');else file.text().then(text=>managementRequest('restore',{export:JSON.parse(text)})).catch(()=>notify('Invalid JSON file. Your current save is unchanged.'));return true;}
 return false;
}
