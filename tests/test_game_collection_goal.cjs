'use strict';
// A real pack opening and catalog refresh in a disposable three-character library.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {randomUUID}=require('node:crypto');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');

const root=path.resolve(__dirname,'..');
const scratch=path.join(root,'.release-output','collection-goal');
fs.mkdirSync(scratch,{recursive:true});
const folder=fs.mkdtempSync(path.join(scratch,'career-'));
const library=path.join(folder,'library');
fs.mkdirSync(library);
fs.writeFileSync(path.join(library,'sample.svg'),'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="navy"/></svg>');
const photo=(owner,id)=>({id,character_id:owner,original_name:'hidden-title-'+id,media_type:'image',stored_rel:'sample.svg'});
const deep=Array.from({length:5},(_,i)=>'deep-'+i);
const data={_tracking_store:'collection-goal-fixture',characters:[
 {id:'small',name:'Small Gallery'},{id:'deep',name:'Deep Gallery'},{id:'guest',name:'Guest'}],
 media:[photo('small','small-a'),photo('small','small-b'),photo('guest','guest-a'),...deep.map(id=>photo('deep',id)),...['f1','f2','f3'].map(id=>({...photo('deep',id),in_all:false}))],
 sets:[{id:'deep-set',name:'Hidden set title',kind:'set',character_id:'deep',media_ids:[...deep,'f1','f2','f3'],
        after_hours_evolution:{version:1,status:'ready',media_ids:['f1','f2','f3']},
        after_hours_duo:{version:1,media_ids:deep.slice(0,2)}}]};
const writeLibrary=()=>fs.writeFileSync(path.join(library,'library.json'),JSON.stringify(data));
writeLibrary();
const server=spawn(process.env.PYTHON_EXE||'python',['-B','-m','game.server','--port','0','--library',library,'--save',path.join(folder,'career.sqlite3')],
 {cwd:root,windowsHide:true,stdio:['ignore','pipe','inherit']});
let browser;
async function run(){
 const url=await new Promise((resolve,reject)=>{
  let output='';
  const timer=setTimeout(()=>reject(Error('Fixture did not open')),15000);
  server.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/After Hours: (http:\/\/127\.0\.0\.1:\d+\/game\/)/);if(match){clearTimeout(timer);resolve(match[1]);}});
  server.once('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited '+code));});
 });
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXE||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({locale:'en-US',viewport:{width:1280,height:900}});
 const errors=[],images=[];
 page.on('pageerror',error=>errors.push(error.message));
 page.on('request',req=>{const part=new URL(req.url()).pathname.split('/api/image/');if(part.length===2)images.push(part[1]);});
 const get=async name=>(await page.request.get(url+'api/'+name)).json();
 let token=(await get('bootstrap')).token;
 const post=async(name,body={})=>{
  const {revision}=await get('state');
  const reply=await page.request.post(url+'api/'+name,{headers:{'X-Game-Token':token,Origin:new URL(url).origin},data:{revision,...body}});
  const result=await reply.json();
  assert.ok(reply.ok(),JSON.stringify(result.error));
  if(result.token)token=result.token;
  return result;
 };
 await post('action',{action:'new',id:randomUUID(),body:{selected:['small','deep'],seed:19}});
 const initial=(await get('state')).state;
 const nav=name=>page.locator('.nav [data-screen="'+name+'"]').click();
 const owner=page.locator('#filter-owner'),view=page.locator('#filter-status'),counts=page.locator('.collection-count');
 await page.goto(url);await nav('collection');
 await owner.selectOption('guest');
 await page.getByRole('button',{name:'Track Guest',exact:true}).click();
 await page.getByRole('button',{name:'Untrack Guest',exact:true}).waitFor();
 let state=(await get('state')).state;
 assert.equal(state.collection_target,'guest');
 assert.deepEqual(state.people,initial.people);assert.deepEqual(state.owned,initial.owned);assert.equal(state.cash,initial.cash);
 await owner.selectOption('small');
 assert.match(await counts.innerText(),/1 \/ 2.*1 missing/);
 assert.deepEqual(await page.locator('.discovery-odds dd').allTextContents(),['59.8%','96.9%']);
 await page.getByRole('button',{name:'Track Small Gallery',exact:true}).click();
 await page.getByRole('button',{name:'Untrack Small Gallery',exact:true}).waitFor();
 await page.reload();await nav('collection');assert.equal(await owner.inputValue(),'small');
 await view.selectOption('missing');await owner.selectOption('deep');
 const missing=page.locator('.missing-collection');
 assert.match(await counts.innerText(),/1 \/ 7.*6 missing/);
 assert.deepEqual(await page.locator('.discovery-odds dd').allTextContents(),['81.7%','>99.9%']);
 assert.equal(await missing.locator('img,[data-card-art],[data-card]').count(),0);
 assert.doesNotMatch(await missing.innerText(),/hidden-title|Hidden set title/);
 assert.match(await missing.innerText(),/Duo/);
 await page.locator('#filter-rarity').selectOption('2');
 assert.equal(await missing.locator('tbody tr').count(),1);
 assert.match(await missing.innerText(),/Evolution\s+Rare\s+1/);
 assert.ok(images.every(id=>initial.owned[id]),'Only owned photos may be requested');
 assert.equal((await page.request.get(url+'api/image/deep-4')).status(),403);
 await page.getByRole('button',{name:'View Deep Gallery’s Spotlight pack'}).click();
 const spotlight=page.locator('.pack.spotlight'),target=spotlight.locator('select');
 assert.equal(await target.inputValue(),'deep');assert.equal((await get('state')).state.cash,initial.cash);
 await target.selectOption('small');
 await spotlight.getByRole('button',{name:'Open pack'}).click();
 await page.locator('dialog[open] .card-back').first().waitFor();
 assert.match(await spotlight.locator('.spotlight-count').textContent(),/1 \/ 2.*1 missing/);
 await page.getByRole('button',{name:'Reveal all five'}).click();
 await page.getByRole('button',{name:'Add to my collection'}).click();
 await page.waitForFunction(()=>!save.pending_pack);
 assert.equal(await target.inputValue(),'small');
 assert.match(await spotlight.locator('.spotlight-count').innerText(),/2 \/ 2.*extra copies/);
 assert.deepEqual(await spotlight.locator('.discovery-odds dd').allTextContents(),['0%','0%']);
 assert.ok(await spotlight.getByRole('button',{name:'Open pack'}).isEnabled());
 await spotlight.getByRole('button',{name:'View Small Gallery’s collection'}).click();
 await view.selectOption('missing');
 assert.match(await page.locator('.empty').innerText(),/Every card in this pack pool is collected/);
 const exported=await get('export');
 assert.equal(exported.save.state.cash,initial.cash-200);
 assert.equal(exported.save.state.collection_target,'small');
 data.media=data.media.filter(c=>c.id!=='small-b');
 data.media.push(photo('small','small-c'));writeLibrary();
 await post('refresh');await post('restore',{export:exported});
 await page.reload();await nav('collection');
 assert.equal(await owner.inputValue(),'small');assert.match(await counts.innerText(),/1 \/ 2.*1 missing/);
 assert.match(await page.locator('.pagehead').innerText(),/1 previously collected card/);
 assert.equal(await page.locator('.card-grid .card').count(),2);
 await page.setViewportSize({width:390,height:844});await view.selectOption('missing');
 assert.equal(await missing.locator('tbody tr').count(),1);
 assert.ok(await missing.evaluate(el=>el.getBoundingClientRect().right<=innerWidth+1));
 await page.getByRole('button',{name:'Untrack Small Gallery'}).click();
 await page.getByRole('button',{name:'Track Small Gallery',exact:true}).waitFor();
 state=(await get('state')).state;assert.equal(state.collection_target,undefined);
 assert.deepEqual(errors,[]);
 console.log('Passed collection tracking, weighted odds, hidden missing art, Spotlight purchase, refresh and restore.');
}
run().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{try{await browser?.close();}finally{server.kill();}});
