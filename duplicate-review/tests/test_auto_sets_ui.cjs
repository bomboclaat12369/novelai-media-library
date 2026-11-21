const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
const {chromium} = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');

(async () => {
  const server = spawn(process.env.NAI_PYTHON||'python3',['duplicate-review/tests/serve_organizer.py','--auto-sets'],{stdio:['ignore','pipe','inherit']});
  let browser;
  try {
    const lines = createInterface({input:server.stdout});
    const info = JSON.parse(await Promise.race([once(lines,'line').then(([line])=>line),
      once(server,'exit').then(([code])=>{throw Error('Organizer fixture stopped: '+code)})]));
    browser = await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true});
    const page = await browser.newPage({viewport:{width:1500,height:1000}});
    const errors = [];
    page.on('pageerror',error=>errors.push(error.message));
    page.setDefaultTimeout(15000);
    await page.goto(info.url);
    await page.waitForFunction(()=>data?.job && view?.images.length && !busy);
    const original = await page.evaluate(()=>currentId);
    await page.getByRole('button',{name:'Auto-match Sets',exact:true}).click();
    const dialog = page.getByRole('dialog',{name:'Auto-match Sets',exact:true});
    await dialog.getByRole('button',{name:'Match photos',exact:true}).click();
    await dialog.getByRole('button',{name:'Review unmatched photos'}).waitFor();
    assert.match(await dialog.getByRole('status').textContent(),/12 photos in 2 new Sets.*4 unmatched/);
    assert.equal(await page.evaluate(()=>currentId),original);
    await dialog.getByRole('button',{name:'Review unmatched photos'}).click();
    await page.waitForFunction(()=>currentKind==='unmatched' && view.total===4 && !busy);
    await page.waitForLoadState('networkidle');
    await page.reload();
    await page.waitForFunction(()=>currentKind==='unmatched' && view?.total===4 && !busy);
    await page.locator('#undo').click();
    await page.waitForFunction(()=>view?.total===16 && !busy);
    await page.waitForLoadState('networkidle');
    assert.deepEqual(errors,[]);
    console.log('Browser verified auto-matching, keeping the current post, unmatched review, restart and Undo.');
  } finally {
    if(browser) await browser.close();
    server.kill();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
