const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
const {chromium} = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');

(async () => {
  const server=spawn(process.env.NAI_PYTHON||'python3',['duplicate-review/tests/serve_bulk_fixture.py'],{stdio:['ignore','pipe','inherit']});
  let browser;
  try {
    const info=JSON.parse((await once(createInterface({input:server.stdout}),'line'))[0]);
    browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true});
    const page=await browser.newPage();
    await page.goto(info.url+'/bulk');
    await page.locator('#roots').fill(info.incoming);
    await page.locator('#start').click();
    await page.locator('#phase').filter({hasText:'Evaluation ready'}).waitFor();
    await page.locator('.group').first().click();
    await page.locator('#setName').fill('Kept for later');
    await page.getByRole('button',{name:'Confirm and hold for review'}).click();
    await page.waitForFunction(()=>current?.folder_set?.under_review&&!busy);
    const held=await page.evaluate(()=>({id:current.folder_set.id,members:[...current.members]}));
    await page.getByRole('link',{name:'Sets under review'}).click();
    await page.waitForFunction(id=>currentKind==='set'&&currentId===id&&view?.ids?.length&&!busy,held.id);
    assert.equal(await page.locator('#setFilter').inputValue(),'under_review');
    assert.deepEqual(await page.evaluate(()=>[...view.ids].sort()),[...held.members].sort());
    await page.goto(info.url+'/bulk');
    await page.locator('.group').first().click();
    await page.getByRole('button',{name:'Promote to regular Set'}).click();
    await page.waitForFunction(()=>current?.folder_set&&!current.folder_set.under_review&&!busy);
    await page.goto(info.url+'/organizer');
    await page.waitForFunction(()=>data?.sets?.length&&!busy);
    const regular=await page.evaluate(id=>data.sets.find(g=>g.id===id),held.id);
    assert(!regular.under_review);
    assert.deepEqual([...regular.members].sort(),[...held.members].sort());
    console.log('Verified evaluation and Folder Organizer share one held Set and one promotable membership.');
  } finally {
    if(browser)await browser.close();
    server.kill();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
