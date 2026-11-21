'use strict';
// Exercise the purchase forecasts and a real two-night checkout in a disposable career.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {randomUUID} = require('node:crypto');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const output = path.join(root, '.release-output', 'morning-budget');
fs.mkdirSync(output, {recursive:true});
const dir = fs.mkdtempSync(path.join(output, 'career-'));
const server = spawn(process.env.PYTHON_EXE, ['-B','-m','game.server','--port','0','--save',path.join(dir,'game.sqlite3')],
    {cwd:root, windowsHide:true, stdio:['ignore','pipe','pipe']});
let browser, errors = '';
server.stderr.on('data', chunk => { errors += chunk; });
const money = value => '$'+Math.round(value).toLocaleString('en-US');

async function check() {
    const url = await new Promise((resolve, reject) => {
        let out = '';
        const timer = setTimeout(() => reject(Error('Test server startup timed out. '+errors)), 15000);
        server.stdout.on('data', chunk => {
            out += chunk;
            const match = out.match(/After Hours: (http:\/\/127\.0\.0\.1:\d+\/game\/)/);
            if (match) { clearTimeout(timer); resolve(match[1]); }
        });
        server.once('exit', code => { clearTimeout(timer); reject(Error('Server exited '+code+' '+errors)); });
    });
    browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_EXE||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
    const page = await browser.newPage({viewport:{width:1400,height:960},locale:'en-US'});
    const jsErrors = [];
    page.on('pageerror', e => jsErrors.push(e.message));
    const get = async endpoint => (await page.request.get(url+'api/'+endpoint)).json();
    const {token, catalog} = await get('bootstrap');
    let current = await get('state');
    async function act(action, body={}) {
        const response = await page.request.post(url+'api/action', {headers:{'X-Game-Token':token, Origin:new URL(url).origin},
            data:{action, body, revision:current.revision, id:randomUUID()}});
        current = await response.json();
        assert.ok(response.ok(), action+' '+(current.error||response.status()));
    }
    const night = async () => { await act('auto'); await act('start'); await act('finish'); };
    const nav = screen => page.locator('.nav [data-screen="'+screen+'"]').click();
    await act('new',{selected:['demo-0','demo-2'],seed:19});
    await page.goto(url);
    await nav('studio');
    const goals = page.locator('.opening-goals');
    assert.match(await goals.innerText(),/Paid club bookings\s+0 \/ 18/);
    assert.match(await goals.innerText(),/Opening funds\s+\$50 short/);
    await nav('resort');
    assert.match(await goals.innerText(),/Studio\s+Still closed/);
    assert.match(await goals.innerText(),/Completed Studio projects\s+0 \/ 2/);
    await nav('packs');
    await page.evaluate(() => clearInterval(interval));
    const standard = page.locator('.pack.standard');
    assert.deepEqual(await standard.locator('.budget-line strong').allTextContents(), ['$404 left','$46 left']);
    assert.equal(await page.locator('.pack.spotlight .budget-line strong').last().textContent(), '$54 short');
    assert.ok(await page.locator('.pack.spotlight [data-action=pack]').isEnabled());
    await standard.screenshot({path:path.join(output,'standard-pack.png')});
    await standard.getByRole('button',{name:'Open pack'}).click();
    await page.locator('[data-action=reveal-all]').click();
    await page.locator('[data-action=reveal_done]').click();
    await nav('expansion');
    const upgrade = page.locator('.upgrade').filter({has:page.locator('[data-kind=rooms]')});
    assert.equal(await upgrade.locator('.budget-line strong').textContent(), '$46 left');
    await upgrade.locator('[data-kind=rooms]').click();
    await page.waitForFunction(() => save.facilities.rooms===2);
    current = await get('state');
    assert.equal(current.state.cash-current.derived.recurring, 46);
    await nav('packs');
    assert.equal(await standard.locator('.budget-line').count(), 1);

    // Grow through the same reserve, delivery and checkout code used by a player.
    const ownedPeople = new Set(Object.keys(current.state.owned).map(i=>catalog.cards[i].owner));
    for (const owner of ownedPeople) {
        if (!current.state.people[owner] && Object.keys(current.state.people).length<3) await act('hire',{owner});
    }
    const rested = () => Object.keys(current.state.people).sort((a,b)=>current.state.people[b].energy-current.state.people[a].energy);
    const schedule = (department,kind,owner,start=current.state.day) => act('schedule',{department,kind,owner,start});
    while (!current.state.departments.resort || current.state.cash<400 || current.state.people[rested()[1]].energy<32) {
        assert.ok(current.state.day<45, 'Departments available within the sample career');
        if (!current.state.departments.studio && current.derived.unlocks.studio && current.state.cash>=850) await act('department',{kind:'studio'});
        if (current.state.departments.studio && current.state.totals.studio_completed<2) await schedule('studio','portrait',rested()[0]);
        if (!current.state.departments.resort && current.derived.unlocks.resort && current.state.cash>=1650) await act('department',{kind:'resort'});
        await night();
    }
    const [creator,host] = rested(), firstDay=current.state.day;
    await schedule('studio','portrait',host,firstDay+2);
    const beforeQuote = current;
    await page.reload();
    await nav('resort');
    await page.evaluate(() => clearInterval(interval));
    const choose = (dept,field,value) => page.locator('[data-quote-'+field+'="'+dept+'"]').selectOption(String(value));
    const reserve = page.getByRole('button',{name:'Reserve & pay deposit'});
    const nextOpening = page.locator('[data-action=use-reservation-start]');
    const availability = page.locator('.reservation-check');
    await choose('resort','owner',host);
    await choose('resort','kind','weekend');
    await nextOpening.waitFor();
    assert.match(await availability.innerText(),new RegExp('Night '+(firstDay+2)+' overlaps'));
    assert.match(await availability.innerText(),/Portrait session at the Studio/);
    assert.ok(await reserve.isDisabled());
    assert.equal(await page.locator('.reservation-calendar .proposed-night').count(),3);
    assert.equal(await nextOpening.getAttribute('data-start'),String(firstDay+3));
    await nextOpening.click();
    assert.equal(await page.locator('[data-quote-start=resort]').inputValue(),String(firstDay+3));
    assert.ok(await reserve.isEnabled());
    const afterQuote = await get('state');
    assert.equal(afterQuote.revision,beforeQuote.revision);
    assert.equal(afterQuote.state.cash,beforeQuote.state.cash);
    // A different open window changes the plan while this quote is displayed.
    await act('training',{owner:host,value:current.state.people[host].training==='studio'?'resort':'studio'});
    await choose('resort','kind','retreat');
    await page.waitForFunction(expected=>revision===expected,current.revision);
    await choose('resort','start',firstDay);
    await reserve.click();
    await page.waitForFunction(day=>save.contracts.some(c=>c.department==='resort'&&c.start===day&&c.status==='active'),firstDay);
    await nav('studio');
    await choose('studio','owner',creator);
    await choose('studio','start',firstDay+2);
    await nextOpening.waitFor();
    assert.match(await availability.innerText(),/Every Studio position is booked/);
    assert.ok(await reserve.isDisabled());
    await choose('studio','kind','editorial');
    await choose('studio','start',firstDay);
    await reserve.click();
    await page.waitForFunction(day=>save.contracts.some(c=>c.kind==='editorial'&&c.start===day),firstDay);
    current=await get('state');
    assert.equal(current.state.cash,beforeQuote.state.cash-60-110);
    await night(); await night();
    const finished = current.state.contracts.filter(c=>c.status==='completed' && c.end===firstDay+1);
    assert.equal(finished.length,2);
    const report = current.state.reports.at(-1);
    await page.reload();
    const section = page.locator('[data-venue-section=activity]');
    assert.match(await section.locator('summary').textContent(),/1 Studio project · 1 Resort checkout/);
    await section.locator('summary').click();
    const receipts = section.locator('.contract-receipts li');
    assert.equal(await receipts.count(),2);
    for (const c of finished) {
        const receipt = receipts.filter({hasText:catalog.people[c.owner].name});
        const values = await receipt.locator('dd').allTextContents();
        const expected = [money(c.revenue)];
        if (c.department==='resort') {
            assert.ok(report.earnings[c.owner]<c.revenue);
            expected.push(money(report.earnings[c.owner]));
        }
        expected.push(money(c.revenue-c.spec.fee));
        assert.deepEqual(values,expected);
        assert.match(await receipt.locator('.receipt-plan').innerText(),
            c.owner===host?/Studio · Reserved/:/Can reassign/);
    }
    await section.screenshot({path:path.join(output,'morning-contracts.png')});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await receipts.evaluateAll(els=>els.every(el=>el.getBoundingClientRect().right<=innerWidth)));
    await section.getByRole('button',{name:'View reports'}).click();
    const detail=page.locator('details').filter({has:page.locator('summary',{hasText:'Night '+report.day+' · planning and decisions'})});
    await detail.locator('summary').click();
    assert.equal(await detail.locator('.contract-receipts li').count(),2);
    assert.equal(await detail.locator('.receipt-plan').count(),0);
    assert.equal((await get('state')).revision,current.revision);
    // Someone covers the lounge while its usual host delivers a Studio project.
    await night();
    const [returning,cover]=rested();
    for(const owner of Object.keys(current.state.people))await act('plan',{owner,role:'rest'});
    await act('plan',{owner:returning,role:'lounge'});
    await schedule('studio','portrait',returning);
    await act('plan',{owner:cover,role:'lounge'});
    await act('start');await act('finish');
    await page.reload();
    const clash=page.locator('.staffing-conflicts');
    assert.match(await clash.innerText(),/Lounge · 2 assigned to 1 position/);
    assert.match(await clash.innerText(),/is back from the Studio/);
    const open=page.getByRole('button',{name:'Open for the night'});
    assert.ok(await open.isDisabled());
    await clash.getByRole('button',{name:'Rest '+catalog.people[cover].name,exact:true}).click();
    await clash.waitFor({state:'hidden'});
    assert.ok(await open.isEnabled());
    await open.click();
    await page.waitForFunction(()=>save.phase==='night');
    assert.equal(await page.evaluate(owner=>save.night.assignments[owner],returning),'lounge');
    assert.deepEqual(jsErrors,[]);
    console.log('Passed opening goals, reservation conflicts and alternatives, purchase forecasts, settlement and next assignments.');
}
check().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(async()=>{await browser?.close();server.kill();});
