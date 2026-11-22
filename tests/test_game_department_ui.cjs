'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),output=path.join(root,'.release-output','department-venues');
fs.mkdirSync(output,{recursive:true});
const server=spawn(process.env.PYTHON_EXE,['-B','tests/serve_illustrated_fixture.py',fs.mkdtempSync(path.join(output,'career-')),'--departments'],
    {cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
let browser,stderr='';
server.stderr.on('data',chunk=>stderr+=chunk);
async function run(){
 const {url}=await new Promise((resolve,reject)=>{
  let received='';const timer=setTimeout(()=>reject(Error('Fixture startup timed out. '+stderr)),18000);
  server.stdout.on('data',chunk=>{received+=chunk;const row=received.split('\n').find(s=>s.startsWith('{'));if(row){clearTimeout(timer);resolve(JSON.parse(row));}});
  server.once('exit',code=>{clearTimeout(timer);reject(Error('Server exit '+code+' '+stderr));});
 });
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXE||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:960},locale:'en-US'}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto(url);
 const nav=async name=>{
  await page.locator('.nav [data-screen="'+name+'"]').click();
  await page.locator('.layout[data-page="'+name+'"]').waitFor();
 };
 const size=async(width,height)=>{
  await page.setViewportSize({width,height});
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 };
 const noOverflow=async()=>{
  const layout=await page.evaluate(()=>{
   const protruding=[...gameRoot.querySelectorAll('*')].filter(el=>{
    if(el.getBoundingClientRect().right<=innerWidth+1)return false;
    for(let p=el.parentElement;p;p=p.parentElement)if(['auto','scroll','hidden','clip'].includes(getComputedStyle(p).overflowX))return false;
    return true;
   }).slice(0,14).map(el=>el.tagName+'.'+el.className);
   return {width:innerWidth,actual:document.documentElement.scrollWidth,protruding};
  });
  assert.ok(layout.actual<=layout.width+1,JSON.stringify(layout));
 };
 const snapshot=async name=>{await noOverflow();await page.screenshot({path:path.join(output,name+'.png')});};
 await page.locator('.lounge-heading').waitFor();
 await page.evaluate(()=>clearInterval(interval));
 const base=await page.locator('.layout').evaluate(el=>getComputedStyle(el).backgroundColor);
 const personId=name=>page.evaluate(n=>Object.keys(boot.catalog.people).find(k=>boot.catalog.people[k].name===n),name);
 const patricia=await personId('Patricia'),alice=await personId('Alice'),third=await personId('Unillustrated guest');
 for(const dept of ['studio','resort']){
  await nav(dept);await page.locator('.department-gate').waitFor();
  assert.equal(await page.locator('.layout').evaluate(el=>getComputedStyle(el).backgroundColor),base);
  assert.equal(await page.locator('.sidebar').evaluate(el=>getComputedStyle(el).position),'static');
  assert.ok(await page.locator('.department-preview .room-scene-'+dept).isVisible());
  await size(2540,1280);await noOverflow();await size(1440,960);await snapshot(dept+'-opening');
  await size(390,844);await snapshot(dept+'-phone');await size(1440,960);
 }
 await nav('studio');await page.getByRole('button',{name:'Open Studio',exact:true}).click();
 await page.locator('[data-quote-kind=studio]').selectOption('feature_film');
 await page.locator('[data-quote-owner=studio]').selectOption(patricia);
 await page.locator('[data-contract-choice=costar]').selectOption(third);
 await page.waitForFunction(()=>gameRoot.querySelector('.quote')?.innerText.includes('$360'));
 await page.getByRole('button',{name:'Reserve & pay deposit'}).click();
 await page.locator('.cast-picker').waitFor();
 assert.ok(await page.locator('.character-figure').getAttribute('src').then(src=>src.endsWith('patricia-front.png')));
 await page.getByRole('button',{name:/Co-star ·/}).click();
 assert.match(await page.locator('.character-heading h2').innerText(),/Unillustrated guest/);
 await page.getByRole('button',{name:/Lead · Patricia/}).click();
 await page.locator('.figure-turn').click();
 assert.match(await page.locator('.character-figure').getAttribute('src'),/patricia-side/);
 await page.locator('.figure-turn').click();
 await nav('resort');await page.getByRole('button',{name:'Open Resort',exact:true}).click();
 await page.locator('[data-quote-owner=resort]').selectOption(alice);
 await page.locator('[data-contract-choice=service_plan]').selectOption('dining');
 await page.waitForFunction(()=>gameRoot.querySelector('.quote')?.innerText.includes('$84'));
 await page.getByRole('button',{name:'Reserve & pay deposit'}).click();
 await page.locator('.department-tracker').waitFor();
 await page.getByRole('button',{name:'Enlarge booking photograph'}).click();
 assert.ok(await page.locator('.enlarged-booking-media img').isVisible());
 await page.getByRole('button',{name:'Close photograph'}).click();
 await nav('team');
 const staffCard=name=>page.locator('article.staff').filter({has:page.getByRole('heading',{name,exact:true})});
 assert.match(await staffCard('Patricia').locator('.staff-reservation').innerText(),/Adult feature[\s\S]*Lead · Nights 7–9/);
 assert.match(await staffCard('Unillustrated guest').locator('.staff-reservation').innerText(),/Co-star · Nights 7–9/);
 assert.match(await staffCard('Alice').locator('.staff-reservation').innerText(),/Quiet retreat[\s\S]*Host · Nights 7–8/);
 assert.equal(await page.locator('.staffinfo [data-plan]').count(),0);
 assert.equal(await page.locator('.layout').evaluate(el=>getComputedStyle(el).backgroundColor),base);
 await page.locator('.team-calendar summary').click();
 const week=page.locator('.team-calendar table');
 assert.equal(await week.getByRole('columnheader').count(),8);
 assert.equal(await week.getByRole('row',{name:/Unillustrated guest/}).getByRole('cell',{name:'Studio · Adult feature'}).count(),3);
 assert.equal(await week.getByRole('row',{name:/Alice/}).getByRole('cell',{name:'Resort · Quiet retreat'}).count(),2);
 assert.equal(await week.locator('.proposed-night').count(),0);
 await snapshot('team-staff-schedule');await size(390,844);await noOverflow();await size(1440,960);
 await page.getByRole('button',{name:'Open for the night',exact:false}).click();
 await page.waitForFunction(()=>save.phase==='night');
 await page.getByLabel('Night speed').selectOption('8');
 await page.evaluate(()=>{interval=setInterval(pollGame,400);});
 await page.waitForFunction(()=>save.night.wave>=1);
 for(const dept of ['studio','resort']){
  await nav(dept);
  assert.ok(await page.locator('.contract-stages [aria-current=step]').isVisible());
  assert.match(await page.locator('.department-tracker').innerText(),dept==='studio'?/Adult feature/:/Quiet retreat/);
  await page.waitForFunction(()=>[...gameRoot.querySelectorAll('.character-figure,.booking-photo')].every(i=>i.complete&&i.naturalWidth));
  await snapshot(dept+'-working');
  await page.locator('.department-tracker').screenshot({path:path.join(output,dept+'-tracker.png')});
  await size(390,844);await noOverflow();await size(1440,960);
 }
 const handled=new Set();
 for(let nights=0;nights<2;nights++){
  while(await page.evaluate(()=>!!save.night)){
   await page.waitForFunction(()=>!save.night||!!pendingDecision(),null,{timeout:35000});
   const event=await page.evaluate(()=>pendingDecision());
   if(!event)continue;
   if(event.department){
    await nav(event.kind==='studio_cut'?'team':event.kind==='resort_request'?'reports':event.department==='studio'?'resort':'studio');
    assert.ok(await page.locator('.venue-event-overlay .decision').isVisible());
    handled.add(event.kind);
   }
   await page.locator('[data-action=decision][data-choice="'+(event.department?'accept':'decline')+'"]').first().click();
   await page.waitForFunction(id=>!save.night||save.night.decisions.find(d=>d.id===id)?.choice!=null,event.id);
   if(event.kind==='resort_private'){
    await nav('resort');await page.locator('.suite-booking [aria-current=step]').waitFor();
    assert.equal(await page.locator('.department-tracker [aria-current=step]').count(),1);
    assert.match(await page.locator('.department-tracker').innerText(),/On hold/);
    await page.locator('.department-tracker').screenshot({path:path.join(output,'resort-private-booking.png')});
   }
  }
  if(nights===0){
   await nav('resort');
   await page.getByRole('button',{name:/Open for the night/}).click();
   await page.waitForFunction(()=>save.phase==='night');
  }
 }
 assert.ok(handled.has('resort_private')&&handled.has('resort_request'));
 await nav('resort');
 const regular=page.locator('[data-contract-choice=guest] option');
 assert.equal(await regular.count(),2);
 await page.locator('[data-contract-choice=guest]').selectOption(await regular.nth(1).getAttribute('value'));
 await page.waitForFunction(()=>gameRoot.querySelector('.department-brief').innerText.includes('Visit 2'));
 await nav('team');
 const returned=staffCard('Alice').locator('[data-plan]');
 assert.ok(await returned.isEnabled());
 assert.equal(await returned.inputValue(),await page.evaluate(id=>save.people[id].role,alice));
 assert.equal(await staffCard('Patricia').locator('[data-plan]').count(),0);
 await page.evaluate(()=>clearInterval(interval));
 await page.getByRole('button',{name:/Open for the night/}).click();
 await page.waitForFunction(()=>save.phase==='night');
 await page.getByRole('button',{name:'Finish night',exact:true}).click();
 await page.waitForFunction(()=>save.phase==='prepare'&&save.day===10);
 await nav('reports');
 const report=await page.evaluate(()=>save.reports.at(-1));
 assert.equal(await page.locator('#booking-report-night').inputValue(),String(report.day));
 const cash=n=>'$'+Math.round(n).toLocaleString('en-US');
 const readLines=locator=>locator.locator('div').evaluateAll(rows=>Object.fromEntries(rows.map(row=>[row.querySelector('dt').textContent,row.querySelector('dd').textContent])));
 for(const day of [9,8,7]){
  await page.getByLabel('Report night').selectOption(String(day));
  const r=await page.evaluate(day=>save.reports.find(row=>row.day===day),day);
  const amounts={Club:0,Studio:0,Resort:0},venueFor={room:'Club',lounge:'Club',studio:'Studio',resort:'Resort'};
  for(const [owner,role] of Object.entries(r.assignments))if(venueFor[role])amounts[venueFor[role]]+=r.earnings[owner];
  assert.equal(Object.values(amounts).reduce((a,b)=>a+b,0),r.revenue);
  assert.deepEqual(await readLines(page.locator('.venue-revenue')),Object.fromEntries(Object.entries(amounts).map(([k,v])=>[k,cash(v)])));
  assert.deepEqual(await readLines(page.locator('.night-costs')),{'Wages':cash(r.costs.payroll),'Venue upkeep':cash(r.costs.upkeep),'Training':cash(r.costs.training),'Business decisions':cash(r.costs.decisions)});
  assert.match(await page.locator('.report-heading h2').innerText(),new RegExp('Night '+day));
  if(day===7)continue;
  const contract=await page.evaluate(day=>save.contracts.find(c=>c.end===day),day);
  const staffNights=day===9?6:2;
  const rate=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:0,maximumFractionDigits:2})
   .format((contract.revenue-contract.spec.fee-(contract.service_cost||0))/staffNights);
  const receipt=page.locator('.report-receipts .receipt-staff-time');
  assert.equal(await receipt.locator('strong').textContent(),rate+' per staff-night');
  assert.ok((await receipt.innerText()).includes(staffNights+' staff-nights'));
 }
 assert.deepEqual(await page.evaluate(()=>venueRevenue({revenue:110,department_revenue:70,earnings:{a:55},assignments:{a:'studio'}})),{club:40,departments:70});
 assert.equal(await page.evaluate(()=>venueRevenue({revenue:110})),null);
 await page.getByLabel('Report night').selectOption('9');
 await snapshot('night-reports');
 await size(390,844);await snapshot('night-reports-phone');
 for(const name of ['packs','collection','expansion','saves','reports']){
  await nav(name);await noOverflow();
  assert.equal(await page.locator('.layout').evaluate(el=>getComputedStyle(el).backgroundColor),base);
  assert.ok(await page.getByRole('button',{name:'Restart game',exact:true}).isVisible());
 }
 await noOverflow();assert.deepEqual(errors,[]);
 console.log('Checked staff schedules, cross-venue decisions, return guests, nightly venue totals, two- and six-staff-night receipts, and phone navigation.');
}
run().catch(error=>{console.error(error.stack);process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();});
