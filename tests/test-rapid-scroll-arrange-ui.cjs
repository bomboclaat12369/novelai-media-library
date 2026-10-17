// Real companion integration for persistent Rapid Review and Set organization.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG||'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{
 const server=spawn('python3',['tests/serve_standalone_fixture.py'],{cwd:dir,env:{...process.env,NAI_UI_VERSION:config.version,NAI_FIXTURE_MULTI_SET:'',NAI_FIXTURE_EXTRA_IMAGES:'0',NAI_FIXTURE_SCROLL_SETS:'',NAI_FIXTURE_PENDING:'80'}});let stderr='';server.stderr.on('data',b=>stderr+=b);let browser;
 try{
 const fixture=await new Promise((resolve,reject)=>{server.stdout.on('data',b=>{const text=b.toString();if(text.includes('ready'))resolve(JSON.parse(text));});server.on('exit',c=>reject(Error(stderr+c)));});
 browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
 const context=await browser.newContext({viewport:{width:1700,height:1100}});
 context.setDefaultTimeout(10000);
 await context.route(/^https?:\/\/(?!127\.0\.0\.1(?::|\/)|novelai\.net(?:\/|$))/,r=>r.abort());
 const api=async(route,body)=>{const r=await context.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json();};
 const sourceBytes=await (await context.request.get('http://127.0.0.1:8765/api/media/'+fixture.images[3]+'/original')).body();
 await api('categories',{character_id:fixture.character,name:'Bikini',media_type:'image'});await api('categories',{character_id:fixture.character,name:'Lingerie',media_type:'image'});
 const blue=await api('sets',{character_id:fixture.character,name:'Blue Dress',media_ids:[fixture.images[1],fixture.images[2],fixture.images[3],fixture.images[4]],preserve_placement:true});
 for(const standalone of [true,false]){
  let promptAnswer='Outfits';const page=await context.newPage(),errors=[],alerts=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept(d.type()==='prompt' ? promptAnswer : undefined));
  if(!standalone){
   await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
   await page.exposeFunction('companionRequest',async o=>{if(new URL(o.url).hostname!=='127.0.0.1')return {status:503,text:''};const r=await fetch(o.url,{method:o.method||'GET',headers:o.headers,body:o.data});return {status:r.status,text:o.blob?Buffer.from(await r.arrayBuffer()).toString('base64'):await r.text()};});
   await page.addInitScript(({payload,version})=>{
    window.GM_xmlhttpRequest=o=>{let aborted=false;window.companionRequest({url:o.url,method:o.method,headers:o.headers,data:o.data,blob:o.responseType==='blob'}).then(r=>{if(aborted)return;const response=o.responseType==='blob'?new Blob([Uint8Array.from(atob(r.text),c=>c.charCodeAt(0))]):r.text;o.onload?.({status:r.status,response,responseText:o.responseType==='blob'?'':r.text});o.onloadend?.({});}).catch(e=>{if(!aborted)o.onerror?.(e);});return {abort:()=>{aborted=true;o.onabort?.({});}};};
    document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
   },{payload,version:config.version});
  }
  await page.goto(standalone?'http://127.0.0.1:8765/library/':'https://novelai.net/stories');await page.getByText('Local library connected',{exact:true}).waitFor();
  await page.locator('#naiResumeRapid').waitFor();await page.locator('#naiResumeRapid').click();await page.locator('#naiRapidBulkReview').waitFor();

  await page.locator('#naiReviewCropBtnV254').waitFor();
  await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.querySelector('#reviewStage img')?.naturalWidth>0);
  assert.equal(await page.locator('#naiRapidAddAll').count(),0);assert.equal(await page.locator('#naiRapidExpand').count(),0);

  const widths=await page.locator('.naiRapidFlags .reviewCat').evaluateAll(els=>els.map(e=>e.getBoundingClientRect().width));assert(widths[0]<90);assert(Math.max(...widths)<210);
  assert.equal(await page.locator('#reviewCats #reviewAddCat').count(),1);assert.equal(await page.locator('.naiReviewActions270 #naiReviewCropBtnV254').count(),1);
  const frames=()=>page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  await page.locator('#naiRapidSize').fill('220');await page.locator('#naiRapidSize').dispatchEvent('input');await frames();
  await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop=1050);await frames();
  for(let i=0;i<3;i++){
   const before=await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop);assert(before>1000);
   const id=await page.evaluate(()=>{const r=document.getElementById('nai-media-host').shadowRoot,g=r.querySelector('#naiQueueStrip270'),b=g.getBoundingClientRect(),current=r.querySelector('#reviewStage').dataset.naiReviewMediaId;return [...g.querySelectorAll('.naiQueueThumb270')].find(e=>{const x=e.getBoundingClientRect();return e.dataset.id!==current&&x.top>b.top+10&&x.bottom<b.bottom-10}).dataset.id;});
   await page.locator('.naiQueueThumb270[data-id="'+id+'"] img').click();
   await page.waitForFunction(id=>document.getElementById('nai-media-host').shadowRoot.querySelector('#reviewStage').dataset.naiReviewMediaId===id,id);await frames();
   assert(Math.abs((await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop))-before)<2,'click retains scroll');
  }
  await page.locator('#naiRapidUnselectAll').click();await frames();assert((await page.locator('#naiQueueStrip270').evaluate(g=>g.scrollTop))>1000);
  if(standalone)await page.screenshot({path:'/tmp/rapid-review85.png'});
  await page.locator('#naiReviewClose270').click();
  await page.evaluate(id=>document.getElementById('nai-media-host').shadowRoot.naiOpenGroup(id),blue.id);
  await page.locator('#naiArrangeSet').click();
  const order=async()=>(await api('library')).sets.find(s=>s.id===blue.id).media_ids;
  const drag=async(from,to,fraction=.85,gap=false)=>{
   const a=await page.locator('#grid .tile[data-id="'+from+'"]').boundingBox(),b=await page.locator('#grid .tile[data-id="'+to+'"]').boundingBox();
   await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(a.x+a.width/2+12,a.y+a.height/2,{steps:4});
   const x=gap?b.x+b.width+2:b.x+b.width*fraction,y=b.y+b.height/2;
   await page.mouse.move(x,y,{steps:12});await page.mouse.move(x,y);await page.mouse.up();
  };
  const settle=async(expected)=>{
   await page.waitForFunction(({setId,expected})=>{const r=document.getElementById('nai-media-host').shadowRoot;return !r.getElementById('naiArrangeSet').disabled&&JSON.stringify(r.naiGetLibrary().sets.find(s=>s.id===setId).media_ids)===JSON.stringify(expected)},{setId:blue.id,expected});
   assert.deepEqual(await order(),expected);
  };
  let ids=await order();await drag(ids[0],ids[1]);await settle([ids[1],ids[0],...ids.slice(2)]);
  ids=await order();await drag(ids[3],ids[0],.15);await settle([ids[3],...ids.slice(0,3)]);
  ids=await order();await drag(ids[0],ids[3],.85,true);await settle([...ids.slice(1),ids[0]]);
  await page.locator('#naiArrangeSet').click();assert.equal(await page.locator('#grid .tile[draggable="true"]').count(),0);
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: compact controls, large-thumbnail scroll retained across repeated image clicks and selection changes, native Set drag forwards/backwards/into gaps, persistence, Arrange lock; standalone and NovelAI.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
