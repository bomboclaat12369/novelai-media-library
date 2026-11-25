// Use the assembled standalone Library and the real post history/thumbnail routes.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
const {chromium} = require('playwright');

(async () => {
  const server = spawn(process.env.NAI_PYTHON || 'python', ['tests/serve_efficiency_fixture.py'], {
    env:{...process.env, NAI_RELEASE_CONFIG:'release-standalone.json', NAI_POST_HISTORY_FIXTURE:'1', NAI_TEST_PORT:'0'},
    stdio:['ignore','pipe','inherit'], windowsHide:true
  });
  let browser;
  try {
    const lines = createInterface({input:server.stdout});
    const port = await Promise.race([once(lines,'line').then(([s]) => s.match(/READY (\d+)/)[1]),
      once(server,'exit').then(([code]) => {throw Error('Fixture exited with ' + code);})]);
    const base = 'http://127.0.0.1:' + port;
    const library = () => fetch(base+'/api/library').then(r => r.json());
    const before = await library();
    const [first, focus, unknown] = before.media;
    browser = await chromium.launch({executablePath:process.env.NAI_CHROMIUM, headless:true});
    const page = await browser.newPage({viewport:{width:1400,height:960}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base+'/library/');
    await page.getByText('Local library connected', {exact:true}).waitFor();
    async function open(id) {
      await page.locator('.tile[data-id="'+id+'"]').first().click();
      await page.getByRole('button',{name:'Original post history',exact:true}).click();
      return page.getByRole('dialog',{name:'Original post history'});
    }
    const dialog = await open(focus.id);
    await dialog.getByText('25–31 of 31 recorded').waitFor();
    assert.match(await dialog.locator('[aria-current=true]').innerText(), /#26 · This photo/);
    await dialog.getByRole('button',{name:'View slide_26.png'}).click();
    await dialog.locator('.naiPostLarge').evaluate(img => img.decode());
    await dialog.getByRole('button',{name:'Back to post'}).click();
    await dialog.getByRole('button',{name:'Previous'}).click();
    await dialog.getByText('1–24 of 31 recorded').waitFor();
    await dialog.getByRole('button',{name:'View slide_2.png',exact:true}).click();
    await dialog.locator('.naiPostLarge').evaluate(img => img.decode());
    assert.equal(await dialog.getByRole('button',{name:'Show in Library'}).count(), 0);
    await page.keyboard.press('Escape');
    await dialog.getByRole('button',{name:'Back to this photo'}).click();
    await dialog.getByText('25–31 of 31 recorded').waitFor();
    await dialog.getByLabel('Original post',{exact:true}).selectOption('forum:smg:12345');
    await dialog.getByText('1–1 of 1 recorded').waitFor();
    await dialog.getByLabel('Original post',{exact:true}).selectOption('instagram:fixture:fixtureABC');
    await dialog.getByRole('button',{name:'Previous'}).click();
    await dialog.getByRole('button',{name:'View slide_1.png',exact:true}).click();
    await dialog.getByRole('button',{name:'Show in Library'}).click();
    await page.locator('.tile.active[data-id="'+first.id+'"]').waitFor();
    await open(unknown.id);
    await dialog.getByText('No original post is recorded for this photo.').waitFor();
    await dialog.getByText(unknown.original_name,{exact:true}).waitFor();
    await dialog.getByRole('button',{name:'Close'}).click();
    await open(focus.id);
    await page.setViewportSize({width:390,height:820});
    await dialog.getByText('25–31 of 31 recorded').waitFor();
    assert(await dialog.evaluate(d => d.scrollWidth <= d.clientWidth + 2));
    await dialog.getByRole('button',{name:'Close'}).click();
    if (process.env.NAI_LIVE_POST_NAVIGATION) {
      await page.setViewportSize({width:1400,height:960});
      const linked = before.media.find(m => m.original_name === 'Workbench link.jpg');
      await open(linked.id);
      const link = dialog.getByRole('link',{name:'Open in Workbench',exact:true});
      await link.waitFor();
      const popup = page.waitForEvent('popup');
      await link.click();
      const wb = await popup;
      await wb.locator('#grid .connected-focus').waitFor();
      const position = await wb.evaluate(() => ({id:view.focus_id, order:view.order, post:currentId}));
      assert.deepEqual(position,{id:linked.sha256,order:'original',post:'post:1'});
      await wb.close();
      await dialog.getByRole('button',{name:'Close'}).click();
    }
    await page.getByRole('button',{name:'Review card crops',exact:true}).click();
    const sheet = page.locator('[aria-label="Review card crops"]').last();
    await sheet.getByRole('button',{name:'Approve selected (3)'}).waitFor();
    await sheet.getByRole('checkbox',{name:'Crop example 2.png'}).uncheck();
    await sheet.getByRole('button',{name:'Approve selected (2)'}).click();
    await sheet.getByText('1–1 of 1 unchecked crops').waitFor();
    assert.match(await sheet.locator('.naiCropTile label').innerText(), /Crop example 2/);
    assert.equal((await library()).media.length, before.media.length);
    assert.deepEqual((await library()).sets, before.sets);
    assert.deepEqual(errors, []);
    console.log('Original post history, a full-size Workbench-only preview, and batch crop approval passed in the assembled Library in Edge.');
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch(e => {console.error(e);process.exitCode=1;});
