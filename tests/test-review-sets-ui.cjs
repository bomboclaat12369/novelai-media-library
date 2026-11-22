// Exercise the assembled Library and a disposable companion over HTTP.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
const {chromium} = require('playwright');

(async () => {
  const server = spawn(process.env.NAI_PYTHON || 'python', ['tests/serve_efficiency_fixture.py'], {
    env:{...process.env, NAI_RELEASE_CONFIG:'release-standalone.json', NAI_TEST_PORT:'0'},
    stdio:['ignore', 'pipe', 'inherit'], windowsHide:true,
  });
  let browser;
  try {
    const lines = createInterface({input:server.stdout});
    const port = await Promise.race([once(lines, 'line').then(([line]) => line.match(/READY (\d+)/)[1]),
      once(server,'exit').then(([code]) => {throw Error('Fixture exited with '+code);})]);
    const base = 'http://127.0.0.1:'+port;
    const get = async path => (await fetch(base+path)).json();
    const initial = await get('/api/library');
    const owner = initial.characters[0].id, image = initial.media[2];
    const held = async () => (await get('/api/review-sets?character_id='+owner)).sets;
    browser = await chromium.launch({executablePath:process.env.NAI_CHROMIUM, headless:true});
    const page = await browser.newPage({viewport:{width:1400,height:960}});
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', async dialog => {errors.push(dialog.message());await dialog.accept();});
    await page.goto(base+'/library/');
    await page.getByText('Local library connected', {exact:true}).waitFor();
    await page.locator('#naiManageSetsBtn').click();
    await page.locator('#naiToolsNewSet').click();
    await page.getByLabel('Set destination').selectOption('under_review');
    await page.locator('#naiSetNameInput').fill('Held shoot');
    await page.locator('#naiSetGallery [data-media-id="'+image.id+'"]').first().click();
    await page.getByRole('button',{name:'Save under review',exact:true}).click();
    const row = page.locator('.naiReviewSetRow');
    await row.getByText('Held Shoot',{exact:true}).waitFor();
    const [group] = await held();
    assert.deepEqual(group.media_ids, [image.id]);
    assert.deepEqual((await get('/api/library')).sets, initial.sets);
    await page.reload();
    await page.getByText('Local library connected', {exact:true}).waitFor();
    await page.getByRole('button',{name:'Sets under review',exact:true}).click();
    await row.getByRole('button',{name:'Review files'}).click();
    await page.locator('#naiSetNameInput').fill('Reviewed shoot');
    await page.getByRole('button',{name:'Save under review',exact:true}).click();
    await row.getByText('Reviewed Shoot',{exact:true}).waitFor();
    await row.getByRole('button',{name:'Review files'}).click();
    const upload=page.waitForEvent('filechooser');
    await page.locator('#naiSetUploadBtn').click();
    const input=await upload;
    await input.setFiles({name:'Extra fixture.png',mimeType:'image/png',buffer:await page.screenshot({clip:{x:0,y:0,width:80,height:90}})});
    await row.getByText('2 files',{exact:true}).waitFor();
    const extra=(await get('/api/library')).media.find(m=>m.original_name==='Extra fixture.png');
    assert(extra&&!extra.in_all);
    await row.getByRole('button',{name:'Promote to regular Set'}).click();
    await page.getByText('No Sets under review.',{exact:true}).waitFor();
    const promoted = (await get('/api/library')).sets.find(s=>s.id===group.id);
    assert.equal(promoted.name,'Reviewed Shoot');assert.deepEqual(promoted.media_ids,[image.id,extra.id]);
    assert.deepEqual(await held(),[]);assert.deepEqual(errors,[]);
    console.log('Held Set creation, edit, reload, separate listing and one-click promotion passed.');
  } finally {await browser?.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
