// Real preferences/API and standalone dialogs; stub jobs avoid model downloads in UI tests.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{cwd:dir});let browser,stderr='';server.stderr.on('data',x=>stderr+=x);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.on('exit',()=>reject(Error(stderr)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/photoshoot-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1366,height:900}});page.setDefaultTimeout(12000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const api=async(route,body)=>{const r=await page.request[body?'post':'get']('http://127.0.0.1:8765/api/'+route,body?{data:body}:{});assert.equal(r.status(),200,await r.text());return r.json()};
  const lib=await api('library'),owner=lib.characters[0].id,query=lib.media.find(m=>!lib.sets.some(s=>s.media_ids.includes(m.id))),searches=[],scans=[],jobs=new Map();
  const results=lib.sets.map(s=>({set_id:s.id,name:s.name,matches:s.media_ids.slice(0,3),score:.8,image_count:s.media_ids.length}));
  const complete=(body,scan)=>({id:'fixture-'+jobs.size,matching_mode:body.matching_mode,running:false,phase:'Finished',results,individual_results:[],scan_results:scan?[{media_id:query.id,name:query.original_name,placement:'Main',stronger:false,results:body.target_set_id?results.filter(s=>s.set_id===body.target_set_id):results}]:[],assigned_ids:[],elapsed_seconds:.05,done:0,total:0});
  for(const [endpoint,scan] of [['find-matches',false],['scan',true]])await page.route('**/api/sets/'+endpoint,route=>{const body=route.request().postDataJSON();(scan?scans:searches).push(body);const job=complete(body,scan);jobs.set(job.id,job);return route.fulfill({contentType:'application/json',body:JSON.stringify(job)})});
  await page.route('**/api/sets/match-status?*',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(jobs.get(new URL(route.request().url()).searchParams.get('id')))}));
  const open=()=>page.evaluate(q=>{document.getElementById('nai-media-host').shadowRoot.naiFindMatchingSets({queries:[q],onChoose:()=>{}})},query);
  const dialog=page.locator('.naiMatchDialog'),mode=page.getByRole('combobox',{name:'Matching mode',exact:true});
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();
  await open();await page.locator('.naiMatchCard').first().waitFor();assert.equal(await mode.inputValue(),'outfit');assert.equal(searches.at(-1).matching_mode,'outfit');
  await mode.selectOption('photoshoot');await page.getByRole('button',{name:'Focus on details',exact:true}).waitFor();await page.waitForFunction(()=>!document.getElementById('nai-media-host').shadowRoot.querySelector('[aria-label="Matching mode"]').disabled);
  assert.equal(searches.at(-1).matching_mode,'photoshoot');assert.equal((await api('sets/matching-preferences?character_id='+owner)).mode,'photoshoot');
  assert(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth));await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiMatchCard img')].every(i=>i.complete&&i.naturalWidth>0));await page.screenshot({path:'/tmp/photoshoot-matching.png'});
  await page.locator('.naiMatchHead button').click();await page.reload();await page.getByText('Local library connected',{exact:true}).waitFor();await open();await page.locator('.naiMatchCard').first().waitFor();assert.equal(await mode.inputValue(),'photoshoot');
  await page.locator('.naiMatchHead button').click();
  const scan=target=>page.evaluate(({owner,target})=>{document.getElementById('nai-media-host').shadowRoot.naiScanForSets(owner,target)},{owner,target});
  await scan(null);await page.getByRole('button',{name:'Start scan',exact:true}).click();await page.locator('.naiScanSuggestion').first().waitFor();assert.equal(scans.at(-1).matching_mode,'photoshoot');assert.equal(await page.getByRole('combobox',{name:'Scan result filter'}).inputValue(),'all');
  await page.waitForFunction(()=>[...document.getElementById('nai-media-host').shadowRoot.querySelectorAll('.naiScanSuggestion img')].every(i=>i.complete&&i.naturalWidth>0));await page.screenshot({path:'/tmp/photoshoot-scan.png'});
  await mode.selectOption('outfit');await page.getByRole('button',{name:'Start scan',exact:true}).waitFor();assert.equal(await page.locator('.naiScanSuggestion').count(),0);await page.getByRole('button',{name:'Start scan',exact:true}).click();await page.getByRole('combobox',{name:'Scan result filter'}).waitFor();assert.equal(scans.at(-1).matching_mode,'outfit');assert.equal(await page.getByRole('combobox',{name:'Scan result filter'}).inputValue(),'stronger');
  await mode.selectOption('photoshoot');await page.locator('.naiScanSuggestion').first().waitFor();assert.equal(scans.length,2); // resumes the matching mode's earlier result
  await page.locator('.naiMatchHead button').click();await scan(lib.sets[0].id);await page.getByRole('button',{name:'Start scan',exact:true}).click();await page.locator('.naiScanSuggestion').first().waitFor();assert.equal(scans.at(-1).target_set_id,lib.sets[0].id);assert.equal(scans.at(-1).matching_mode,'photoshoot');
  assert.equal(await page.locator('.naiScanSuggestion').count(),1);await page.locator('.naiMatchHead button').click();
  const after=await api('library');assert.deepEqual(after.media,lib.media);assert.deepEqual(after.sets,lib.sets);assert.deepEqual(errors,[]);
  console.log('Photoshoot UI: saved per-person mode, automatic search, refresh persistence, mode-separated scans, reverse scan and read-only suggestions passed.');
 }finally{if(browser)await browser.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
