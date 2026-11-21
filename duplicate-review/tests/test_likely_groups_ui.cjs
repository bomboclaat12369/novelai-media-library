const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {createInterface} = require('node:readline');
const {chromium} = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');

(async()=>{
  const server=spawn(process.env.NAI_PYTHON||'python3',['duplicate-review/tests/serve_organizer.py','--likely-sets'],{stdio:['ignore','pipe','inherit']});
  let browser;
  try{
    const lines=createInterface({input:server.stdout});
    const info=JSON.parse(await Promise.race([once(lines,'line').then(([s])=>s),once(server,'exit').then(([code])=>{throw Error('Server exit '+code)})]));
    browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM,headless:true});
    const page=await browser.newPage({viewport:{width:1280,height:820}});
    page.setDefaultTimeout(15000);
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(info.url);
    await page.waitForFunction(()=>data?.job&&view?.images.length&&!busy);
    const screenshotPost=await page.evaluate(()=>currentId);
    const open=async()=>{
      await page.getByRole('button',{name:'Auto-match Sets',exact:true}).click();
      await page.getByRole('button',{name:'Review likely groups'}).click();
      await page.waitForFunction(()=>document.querySelector('#likelyGroupsDialog[open] .likely-photos')&&!busy);
    };
    await open();
    const dialog=page.getByRole('dialog',{name:'Likely groups across posts'});
    const picker=dialog.getByRole('combobox',{name:'Destination Set'});
    while(await picker.inputValue()!==''){
      await dialog.getByRole('button',{name:'Next group'}).click();
      await page.waitForFunction(()=>!busy);
    }
    assert((await dialog.locator('h3').count())>=2);
    await dialog.getByText('How suggestions are ranked',{exact:true}).click();
    await dialog.getByText(/Workbench is using the standard outfit and setting weights|Workbench tuned outfit and setting weights/).waitFor();
    await dialog.getByRole('button',{name:/Enlarge/}).first().click();
    await page.locator('#viewerClose').click();
    const checks=dialog.getByRole('checkbox');
    const all=await checks.count();
    assert(all>=3);
    await dialog.getByRole('textbox',{name:'New Set name'}).fill('Cross post test');
    await checks.last().uncheck();
    await dialog.getByRole('button',{name:'Approve selected ('+(all-1)+')',exact:true}).click();
    await page.waitForFunction(()=>data.sets.some(s=>s.name==='Cross Post Test')&&!busy);
    const saved=await page.evaluate(()=>data.sets.find(s=>s.name==='Cross Post Test'));
    assert.equal(saved.members.length,all-1);
    assert(!saved.auto_members?.length);
    await dialog.getByRole('button',{name:'Undo last review'}).click();
    await page.waitForFunction(()=>!data.sets.some(s=>s.name==='Cross Post Test')&&!busy);
    const status=dialog.getByRole('status');
    const first=await status.textContent();
    await dialog.getByRole('button',{name:'Dismiss group'}).click();
    await page.waitForFunction(()=>!busy);
    assert.notEqual(await status.textContent(),first);
    await dialog.getByRole('button',{name:'Close',exact:true}).click();
    assert.equal(await page.evaluate(()=>currentId),screenshotPost);
    await page.waitForLoadState('networkidle');
    await page.reload();
    await page.waitForFunction(()=>data?.job&&view?.images.length&&!busy);
    await open();
    assert.notEqual(await status.textContent(),first);
    await dialog.getByRole('button',{name:'Undo last review'}).click();
    await page.waitForFunction(()=>!busy);
    assert.equal(await status.textContent(),first);
    await dialog.getByRole('combobox',{name:'Suggestion range'}).selectOption('broader');
    await page.waitForFunction(()=>!busy);
    assert.match(await status.textContent(),/No pending cross-post groups/);
    await dialog.getByRole('combobox',{name:'Suggestion range'}).selectOption('closest');
    await page.waitForFunction(()=>!busy);
    await picker.selectOption('library:existing');
    await page.waitForFunction(()=>document.querySelector('#likelyGroupsDialog .match-examples img')&&!busy);
    await page.setViewportSize({width:430,height:760});
    assert(await dialog.evaluate(d=>d.scrollWidth<=d.clientWidth+2));
    await page.waitForLoadState('networkidle');
    assert.deepEqual(errors,[]);
    console.log('Verified cross-post approval, photo exclusions, previews, destinations, Undo, dismissal, both ranges and mobile layout.');
  }finally{if(browser)await browser.close();server.kill()}
})().catch(err=>{console.error(err);process.exitCode=1});
