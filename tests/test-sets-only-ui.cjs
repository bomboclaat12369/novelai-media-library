// Focused browser check for replacement screen and individual thumbnails in normal categories.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG || 'candidate-userscript-2.8.66.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{const browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM || '/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});try{
for(const standalone of [false,true]){
const page=await browser.newPage({viewport:{width:1700,height:1000}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
await page.route('http://127.0.0.1:8765/**',r=>r.fulfill({status:404,body:''}));
await page.goto('https://novelai.net/stories');
await page.evaluate(()=>{
 const media=Array.from({length:220},(_,i)=>({id:'img'+i,character_id:'c',media_type:'image',original_name:`Image ${i}.png`,sha256:'source'+i,thumb_rel:'thumb'+i,categories:[],in_all:true,in_review:false,width:64,height:96,file_bytes:1000,created_at:new Date(1700000000000+i*1000).toISOString()}));
 window.lib={characters:[{id:'c',name:'Fixture',categories:[{id:'dresscat',name:'Dress',media_type:'image'}]}],media,sets:[{id:'beach',character_id:'c',kind:'set',name:'Beach',media_ids:['img0','video'],cover_media_id:'video'},{id:'dress',character_id:'c',kind:'set',name:'Dress',media_ids:[]},{id:'conn',character_id:'c',kind:'connection',name:'Retired link',media_ids:['img0']}]};
 media[0].categories=['dresscat'];media[0].favorite=true;media.push({id:'video',character_id:'c',media_type:'video',sha256:'vid',thumb_rel:'video-thumb',original_name:'Cover.mp4',categories:[],in_videos:true});
 window.requests=[];window.alerts=[];window.alert=m=>alerts.push(m);window.confirm=()=>true;
 window.GM_xmlhttpRequest=o=>{const route=new URL(o.url).pathname,method=o.method||'GET';requests.push({route,method,url:o.url,background:!!o.naiBackground});let canceled=false;
 setTimeout(()=>{if(canceled)return;try{let value={};
 if(route==='/api/health')value={ok:true,version:9,mixed_collections:true,video_set_only:true,featured_flags:true};
 else if(route==='/api/library')value=lib;
 else if(route.endsWith('/quality'))value={width:64,height:96,file_bytes:1000};
 else if(route==='/api/import/file'){const f=o.data.get('file');value={item:{id:'saved'+lib.media.length,character_id:'c',media_type:f.type.startsWith('video/')?'video':'image',original_name:f.name,sha256:f.name,thumb_rel:'thumb',categories:[],in_all:true,in_videos:true},duplicate:false};lib.media.push(value.item);}
 else if(route.startsWith('/api/media/') && method==='POST'){
 const m=lib.media.find(m=>m.id===route.split('/')[3]);if(!m)throw Error('Unknown media');
 if(route.endsWith('/replace')){m.original_name=o.data.get('file').name;m.sha256='replacement';m.thumb_rel='newthumb';}
 else Object.assign(m,JSON.parse(o.data));value=m;
 }else if(route==='/api/sets' && method==='POST'){value={id:'newset'+lib.sets.length,...JSON.parse(o.data)};lib.sets.push(value);}
 else if(route.startsWith('/api/sets/') && method==='POST'){value=lib.sets.find(s=>s.id===route.split('/')[3]);const body=JSON.parse(o.data);if(body.add_media_ids)body.media_ids=[...new Set([...value.media_ids,...body.add_media_ids])];Object.assign(value,body);if(!body.preserve_placement)for(const id of value.media_ids){const m=lib.media.find(m=>m.id===id);if(!m.categories.length)m[m.media_type==='video'?'in_videos':'in_all']=false;}}
 else if(o.responseType==='blob'){const replacement=o.url.includes('replacement');o.onload({status:200,response:new Blob([`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="96"><rect width="64" height="96" fill="${replacement?'blue':'red'}"/></svg>`],{type:'image/svg+xml'})});return;}
 o.onload({status:200,responseText:JSON.stringify(value)});
 }catch(e){alerts.push(e.message);o.onerror?.(e);}},5);return {abort(){canceled=true;o.onabort?.({})}};};
});
if(standalone)await page.evaluate(()=>document.documentElement.dataset.naiStandalone='1');
await page.evaluate(payload);await page.getByText('Local library connected',{exact:true}).waitFor();


await page.locator('#grid .tile[data-id="img0"]').click();await page.locator('#stage1 img').waitFor();
assert.equal(await page.locator('#naiMemberships [data-group-id="conn"]').count(),0);
assert.equal(await page.locator('#naiAddToSetMedia').textContent(),'Add to Set…');
await page.locator('#naiAddToSetMedia').click();
assert.equal(await page.locator('#naiAssignKind').count(),0);
assert.equal(await page.locator('#naiAssignExisting option[value="conn"]').count(),0);
await page.locator('#naiAssignSearch').fill('Dress');assert.equal(await page.locator('#naiAssignExisting option').count(),1);
await page.locator('#naiAssignAdd').click();await page.locator('.naiGroupAssign').waitFor({state:'detached'});
assert(await page.evaluate(()=>lib.sets.find(s=>s.id==='dress').media_ids.includes('img0')));
await page.locator('#naiCombinedFilters').click();assert.equal(await page.locator('[data-filter="connection"]').count(),0);await page.getByRole('button',{name:'Done',exact:true}).click();
await page.locator('#naiSetsCat').click();assert.equal(await page.locator('[data-group-filter]').count(),0);assert(!/Connections/i.test(await page.locator('#grid').textContent()));
await page.locator('#naiManageSetsBtn').click();assert.equal(await page.locator('#naiGroupKind').count(),0);
await page.locator('#naiNewSetBtn').click();await page.locator('#naiSetNameInput').fill('New set');
await page.locator('#naiSaveSetBtn').click();await page.locator('.naiSetEditor').waitFor({state:'detached'});
assert(await page.evaluate(()=>lib.sets.some(s=>s.name==='New set'&&s.kind==='set')));
// A positioned media layer must not cover the inner active outline.
await page.locator('#stage1 img').evaluate(img=>img.style.cssText='position:absolute;inset:0;width:100%;height:100%;max-width:none;max-height:none;object-fit:fill');
const border=await page.locator('#stage1').evaluate(stage=>{const s=getComputedStyle(stage,'::after');return {z:s.zIndex,color:s.borderTopColor,pointer:s.pointerEvents};});
assert.equal(border.z,'100');assert.equal(border.color,'rgb(143, 133, 255)');assert.equal(border.pointer,'none');
await page.locator('#stage1').screenshot({path:'/tmp/nai66-border-'+(standalone?'standalone':'overlay')+'.png'});
assert.deepEqual(errors,[]);assert.deepEqual(await page.evaluate(()=>alerts),[]);await page.close();
}
console.log('PASS: both interfaces use Sets only; assignment/search/create work; foreground active border is noninteractive.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
