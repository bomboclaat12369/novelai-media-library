// Exercises the assembled Library against a disposable companion; no user data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');

(async () => {
  const server = spawn(process.env.NAI_PYTHON || 'python', ['tests/serve_efficiency_fixture.py'], {
    env:{...process.env, NAI_RELEASE_CONFIG:'release-standalone.json', NAI_TEST_PORT:'0'},
    windowsHide:true,
  });
  let browser, stderr = '';
  server.stderr.on('data', chunk => stderr += chunk);
  try {
    const port = await new Promise((resolve, reject) => {
      let output = '';
      server.stdout.on('data', chunk => {
        output += chunk;
        const ready = output.match(/READY (\d+)/);
        if (ready) resolve(Number(ready[1]));
      });
      server.on('error', reject);
      server.on('exit', code => reject(Error(stderr + code)));
    });
    const base = 'http://127.0.0.1:' + port;
    const library = async () => (await fetch(base + '/api/library')).json();
    const initial = await library(), set = initial.sets[0];
    const create = await fetch(base + '/api/sets', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({character_id:set.character_id, name:'Unmarked Set', media_ids:[]})});
    assert.equal(create.status, 200);
    browser = await chromium.launch({executablePath:process.env.NAI_CHROMIUM, headless:true});
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.setDefaultTimeout(15000);
    const errors = [], writes = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (request.method() === 'POST') writes.push(new URL(request.url()).pathname);});
    await page.goto(base + '/library/');
    await page.getByText('Local library connected', {exact:true}).waitFor();
    const tiles = () => page.locator('.naiSetTile');
    const tile = () => tiles().filter({has:page.locator('.naiSetCaption').filter({hasText:'Blue dress'})});
    const marker = key => page.locator('.naiSetBreadcrumb button[data-reminder="' + key + '"]');
    const pressed = (key, value) => page.waitForFunction(({key,value}) => {
      const button = document.getElementById('nai-media-host').shadowRoot.querySelector('button[data-reminder="' + key + '"]');
      return button?.getAttribute('aria-pressed') === String(value);
    }, {key,value});
    await page.locator('#naiSetsCat').click();
    await tile().click();
    for (const key of ['possible_duo','possible_evolution']) {
      await marker(key).click();
      await pressed(key, true);
      assert.equal((await library()).sets.find(item => item.id === set.id)[key], true);
    }
    fs.mkdirSync('.release-output', {recursive:true});
    await page.screenshot({path:'.release-output/set-reminders-desktop.png'});
    await page.setViewportSize({width:1000,height:760});
    assert(await page.locator('.naiSetBreadcrumb>.naiSetReminders').evaluate(element => {
      const bounds = element.getBoundingClientRect();
      return bounds.left >= 0 && bounds.right <= innerWidth && [...element.children].every(child => {
        const box = child.getBoundingClientRect();
        return box.left >= bounds.left - 1 && box.right <= bounds.right + 1;
      });
    }));
    await page.screenshot({path:'.release-output/set-reminders-compact.png'});
    await page.locator('#naiSetBackBtn').click();
    assert.equal(await tile().locator('.naiSetReminderBadge').count(), 1);
    assert.equal(await tile().locator('.naiSetReminderBadge').getAttribute('title'), 'Possible Duo · Possible Evolution');
    assert(await tile().evaluate(element => {
      const footer = element.querySelector('.naiSetCount').getBoundingClientRect();
      const favorite = element.querySelector('.naiSetFavorite').getBoundingClientRect();
      return [...element.querySelectorAll('.naiSetReminderBadge')].every(badge => {
        const box = badge.getBoundingClientRect();
        return box.bottom < footer.top && box.left >= favorite.right;
      });
    }));
    await page.setViewportSize({width:1440,height:1000});
    await page.reload();
    await page.getByText('Local library connected', {exact:true}).waitFor();
    await page.locator('#naiSetsCat').click();
    await tile().waitFor();
    assert.equal(await tile().locator('.naiSetReminderBadge').getAttribute('title'), 'Possible Duo · Possible Evolution');
    await page.screenshot({path:'.release-output/set-reminders-tiles.png'});
    await page.locator('#naiManageSetsBtn').click();
    const filter = page.getByLabel('Filter Sets by evolution status', {exact:true});
    for (const key of ['possible_duo','possible_evolution']) {
      await filter.selectOption(key);
      assert.equal(await page.locator('.naiSetToolsRow').count(), 1);
      assert.match(await page.locator('.naiSetToolsName').innerText(), /Blue dress/i);
    }
    await filter.selectOption('');
    assert.equal(await page.locator('.naiSetToolsRow').count(), 2);
    await page.locator('.naiSetQuick .modalFoot [data-close]').click();
    await tile().click();
    await page.locator('#naiSetRenameBtn').click();
    const dialog = page.locator('.naiSetQuick');
    await dialog.locator('input[data-reminder="possible_duo"]').uncheck();
    await dialog.locator('[data-save]').click();
    await pressed('possible_duo', false);
    await pressed('possible_evolution', true);
    const saved = (await library()).sets.find(item => item.id === set.id);
    assert.equal(saved.possible_duo, false);
    assert.equal(saved.possible_evolution, true);
    assert(!saved.after_hours_evolution && !saved.after_hours_duo);
    assert.deepEqual((await library()).media, initial.media);
    // Battle summary uses POST for a read-only list query.
    assert.deepEqual([...new Set(writes)].filter(path => /^\/api\/(sets|battles)\b/.test(path) && path !== '/api/battles/summary'), ['/api/sets/' + set.id]);
    // An older companion must not silently pretend to have saved a reminder.
    await page.route(base + '/api/sets/' + set.id, route => route.fulfill({json:{...saved, possible_duo:undefined}}));
    const warning = page.waitForEvent('dialog').then(async dialog => {
      assert.match(dialog.message(), /Update and restart the companion/);
      await dialog.accept();
    });
    await marker('possible_duo').click();
    await warning;
    await pressed('possible_duo', false);
    assert.deepEqual(errors, []);
    console.log('Set reminder browser checks passed: saved toggles, both flags, reload, badges, filters, details, narrow layout, and older-companion warning.');
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch(error => {console.error(error);process.exitCode = 1;});
