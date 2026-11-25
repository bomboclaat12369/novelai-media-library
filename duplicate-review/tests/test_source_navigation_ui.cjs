const assert = require('node:assert/strict');
const http = require('node:http');
const {spawn} = require('node:child_process');
const {createInterface} = require('node:readline');
const {chromium} = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + '/playwright');

async function run() {
  const fixture = spawn(process.env.TEST_PYTHON || 'python3',
    ['-B', 'duplicate-review/tests/serve_organizer.py', '--source-post'], {stdio:['pipe','pipe','inherit']});
  let browser, library;
  try {
    const lines = createInterface({input:fixture.stdout})[Symbol.asyncIterator]();
    const info = JSON.parse((await lines.next()).value);
    const link = new URL(info.url);
    link.search = new URLSearchParams({sourceCollection:info.collection,sourcePost:info.post,sourcePhoto:info.focus});
    const marker = await fetch(new URL('/api/workbench/post-navigation',link));
    assert.deepEqual(await marker.json(),{post_navigation:1});
    assert(!marker.headers.get('Content-Security-Policy').includes('nonce-'));
    const denied = await fetch(new URL('/api/organizer/source-post',link),{method:'POST',body:'{}'});
    assert.equal(denied.status,403);
    library = http.createServer((_req,res)=>{
      res.setHeader('Content-Type','text/html');
      res.end('<a target="_blank" rel="noopener noreferrer" href="'+link.href.replaceAll('&','&amp;')+'">Open original post</a>');
    });
    await new Promise(resolve=>library.listen(0,'127.0.0.1',resolve));
    const options = process.env.NAI_CHROMIUM ? {executablePath:process.env.NAI_CHROMIUM} : {channel:'msedge'};
    browser = await chromium.launch({...options,headless:true});
    const context = await browser.newContext({viewport:{width:1400,height:900}});
    const requests = [];
    context.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname.startsWith('/api/organizer/')) requests.push(url);
    });
    const normal = await context.newPage();
    await normal.goto(info.url);
    await normal.waitForFunction(()=>sessionReady && view);
    assert.equal(await normal.evaluate(()=>data.job),'other-job');
    assert(requests.some(url=>url.pathname==='/api/organizer/collections'));
    assert(!requests.some(url=>url.pathname==='/api/organizer/source-post'));
    assert(requests.some(url=>url.pathname==='/api/organizer/page' && url.searchParams.get('job')==='other-job'));
    const oldView = await normal.evaluate(()=>[currentKind,currentId,offset]);
    const from = await context.newPage();
    await from.goto('http://127.0.0.1:'+library.address().port);
    requests.length = 0;
    const opened = context.waitForEvent('page');
    await from.getByRole('link',{name:'Open original post'}).click();
    const page = await opened;
    const anchor = page.locator('#grid .connected-focus');
    await anchor.waitFor();
    assert.equal(await anchor.getAttribute('data-id'),info.focus);
    await page.waitForFunction(()=>sessionReady && view && document.querySelector('.connected-focus img')?.naturalWidth>0);
    const observed = await page.evaluate(()=>({
      job:data.job,post:currentId,order:view.order,pageOffset:offset,total:view.total,
      before:view.ids[view.ids.indexOf(view.focus_id)-1],after:view.ids[view.ids.indexOf(view.focus_id)+1],
      selection:[...selection],draft:$('setName').value
    }));
    assert.deepEqual(observed,{job:info.job,post:info.post,order:'original',pageOffset:60,total:121,
      before:info.before,after:info.after,selection:[info.ids[3]],draft:'Unfinished shoot'});
    assert.equal(new URL(page.url()).search,'');
    assert(requests.some(url=>url.pathname==='/api/organizer/source-post'));
    assert(!requests.some(url=>url.pathname==='/api/organizer/collections'));
    assert(requests.some(url=>url.pathname==='/api/organizer/page' && url.searchParams.get('job')===info.job));

    const stalePage = normal.waitForResponse(response=>{
      const url = new URL(response.url());
      return url.pathname==='/api/organizer/page' && url.searchParams.get('kind')==='all_images';
    });
    await normal.getByRole('button',{name:'All images',exact:true}).click();
    const rejected = await stalePage;
    assert.equal(new URL(rejected.url()).searchParams.get('job'),'other-job');
    assert.equal(rejected.status(),400);
    await normal.locator('#notice').filter({hasText:'collection changed in another window'}).waitFor();
    assert.deepEqual(await normal.evaluate(()=>[currentKind,currentId,offset]),oldView);

    await page.reload();
    await page.waitForFunction(()=>sessionReady && view);
    assert.equal(await page.locator('#order').inputValue(),'original');
    assert.equal(await page.evaluate(()=>offset),60);
    link.searchParams.set('sourceCollection',info.other);
    await page.goto(link.href);
    await page.getByText('Original post unavailable',{exact:true}).waitFor();
    assert.equal(await page.locator('#grid .card').count(),0);
    assert.equal(await page.evaluate(()=>data.job),info.job);
    await page.getByRole('button',{name:'Open whole post'}).click();
    await page.waitForFunction(()=>sessionReady && view && view.total===1);
    assert.equal(await page.evaluate(()=>data.job),'other-job');
    assert.equal(await page.locator('#grid .connected-focus').count(),0);
    await page.goto(info.url+'?sourcePhoto=');
    const unavailable = page.getByText('Original post unavailable',{exact:true});
    await unavailable.waitFor();
    assert.equal(await page.getByRole('button',{name:'Open whole post'}).count(),0);
    const retried = page.waitForResponse(r=>new URL(r.url()).pathname==='/api/organizer/source-post');
    await page.getByRole('button',{name:'Try again'}).click();
    assert.equal((await retried).status(),400);
    await unavailable.waitFor();
    assert.equal(new URL(page.url()).search,'?sourcePhoto=');
    await page.getByRole('button',{name:'Continue in organizer'}).click();
    await page.waitForFunction(()=>sessionReady && view);
    assert.equal(new URL(page.url()).search,'');
    assert.equal(await page.evaluate(()=>data.job),'other-job');
    await page.goto(info.url+'?setList=under_review');
    await page.waitForFunction(()=>sessionReady && view);
    assert.equal(await page.locator('#setFilter').inputValue(),'under_review');
    assert.equal(new URL(page.url()).search,'');
    console.log('Original post link passed in '+await browser.version()+
      ': normal startup, focused photo 97 of 121, original neighbors, preserved draft, stale tab, reload, recovery and held-Set navigation.');
  } finally {
    await browser?.close();
    library?.close();
    fixture.stdin.end();
  }
}
run().catch(error=>{console.error(error);process.exitCode=1});
