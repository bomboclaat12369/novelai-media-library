// Focused Manage Sets filtering/selection and standalone footer order checks.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG || 'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{const browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM || '/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});try{
for(const standalone of [false,true]){
const page=await browser.newPage({viewport:{width:1700,height:1000}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
await page.route('http://127.0.0.1:8765/**',r=>r.fulfill({status:404,body:''}));
await page.goto('https://novelai.net/stories');
await page.evaluate(()=>{
 const media=Array.from({length:5000},(_,i)=>({id:'img'+i,character_id:'c',media_type:'image',original_name:`Image ${i}.png`,sha256:'source'+i,thumb_rel:'thumb'+i,categories:[],in_all:true,in_review:false,width:64,height:96,file_bytes:1000,created_at:new Date(1700000000000+i*1000).toISOString()}));
 window.lib={characters:[{id:'c',name:'Fixture',categories:[{id:'dresscat',name:'Dress',media_type:'image'},{id:'vcat',name:'Video category',media_type:'video'}]}],media,sets:[{id:'beach',character_id:'c',kind:'set',name:'Beach',media_ids:['img0','video'],cover_media_id:'video'},{id:'dress',character_id:'c',kind:'set',name:'Dress',media_ids:[]},{id:'conn',character_id:'c',kind:'connection',name:'Retired link',media_ids:['img0']}]};
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

if(standalone){
 const checkFooter=async()=>{const b=await page.locator('#naiCompactFooter').evaluate(el=>{const n=el.querySelector('.viewerNav').getBoundingClientRect(),m=el.querySelector('.naiStandaloneMetadata').getBoundingClientRect();return {bottom:n.bottom,top:m.top,height:el.getBoundingClientRect().height};});assert(b.bottom<=b.top);assert.equal(b.height,63);};
 await checkFooter();
 await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia('video'));await checkFooter();
 await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia('img0'));
}
await page.locator('#naiManageSetsBtn').click();await page.locator('#naiNewSetBtn').click();await page.locator('#naiSetNameInput').fill('Filtered set');
const cards=page.locator('#naiSetGallery .naiSetPick'),card=id=>page.locator(`#naiSetGallery .naiSetPick[data-media-id="${id}"]`);
assert((await cards.count())<100,'bounded DOM for 5001 media');await card('img0').evaluate(el=>window.firstCard=el);await card('img0').click();assert(await card('img0').evaluate(el=>el===window.firstCard),'selection preserves card node');
const writes=await page.evaluate(()=>requests.filter(r=>r.method==='POST').length);
await page.locator('#naiGroupCategory').selectOption('dresscat');assert.equal(await cards.count(),1);
await page.locator('#naiGroupFiltersBtn').click();await page.locator('#naiGroupFavorite').selectOption('yes');assert.equal(await cards.count(),1);
await page.locator('#naiGroupFeatured').selectOption('yes');assert.equal(await cards.count(),0);assert.match(await page.locator('#naiSetGallery').textContent(),/No media matches/);
await page.locator('#naiGroupFeatured').selectOption('any');assert.equal(await cards.count(),1);
await page.locator('#naiGroupMembership').selectOption('none');assert.equal(await cards.count(),0);
await page.locator('#naiGroupClearFilters').click();assert((await cards.count())<100);
await page.locator('#naiGroupFiltersDone').click();await page.locator('#naiGroupCategory').selectOption('__none');assert((await cards.count())<100);
await card('img1').click();
assert.match(await page.locator('#naiSetSelectionSummary').textContent(),/2 files selected/);
await page.locator('#naiGroupFiltersBtn').click();await page.locator('#naiGroupSelectedOnly').check();assert.equal(await cards.count(),1);
await page.locator('#naiGroupCategory').selectOption('');assert.equal(await cards.count(),2);
await page.locator('#naiGroupMediaType').selectOption('video');assert.equal(await cards.count(),0);assert.equal(await page.locator('#naiGroupCategory option[value="dresscat"]').count(),0);
await page.locator('#naiGroupCategory').selectOption('vcat');await page.locator('#naiGroupMediaType').selectOption('image');assert.equal(await page.locator('#naiGroupCategory').inputValue(),'');assert.equal(await cards.count(),2);
await page.locator('#naiGroupSearch').fill('Image 0');assert.equal(await cards.count(),1);
assert.equal(await page.evaluate(()=>requests.filter(r=>r.method==='POST').length),writes,'filters make no writes');
await page.locator('#naiGroupSearch').fill('');if(await page.locator('#naiGroupFilterPanel').isHidden())await page.locator('#naiGroupFiltersBtn').click();
await page.locator('.modal.large').screenshot({path:'/tmp/nai68-manager-'+(standalone?'standalone':'overlay')+'.png'});
await page.locator('#naiGroupFiltersDone').click();await page.locator('#naiSaveSetBtn').click();await page.locator('.naiSetEditor').waitFor({state:'detached'});
const saved=await page.evaluate(()=>lib.sets.find(s=>s.name==='Filtered set'));assert.deepEqual(saved.media_ids,['img0','img1']);assert.equal(saved.cover_media_id,'img0');

// Viewport changes preserve far-away selections and cover.
await page.locator('#naiManageSetsBtn').click();await page.locator('#naiNewSetBtn').click();
await page.locator('#naiSetGallery').evaluate(el=>el.scrollTop=el.scrollHeight);
await page.locator('#naiSetGallery .naiSetPick[data-media-id="img4999"]').waitFor();
await page.locator('#naiSetGallery .naiSetPick[data-media-id="img4999"]').click();
assert((await cards.count())<100);
await page.locator('#naiSetGallery').evaluate(el=>el.scrollTop=0);await card('img0').waitFor();
assert.match(await page.locator('#naiSetSelectionSummary').textContent(),/1 files selected/);
await page.locator('.modalWrap [data-close]').first().click();
if(!standalone){
 await page.locator('#grid .tile').first().click();await page.locator('#stage1 img').waitFor();
 await page.locator('.toggle').click();
 assert.equal(await page.locator('#grid img,#stage1 img,#stage2 img,#stage1 video,#stage2 video').count(),0);
 const n=await page.evaluate(()=>requests.filter(r=>/\/(original|thumb)/.test(r.route)).length);
 await page.waitForTimeout(500);
 assert.equal(await page.evaluate(()=>requests.filter(r=>/\/(original|thumb)/.test(r.route)).length),n,'no visual requests while hidden');
 await page.locator('.toggle').click();await page.locator('#stage1 img').waitFor();await page.locator('#grid .tile').first().waitFor();
 await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia('video'));
 await page.locator('#stage1 video').waitFor();await page.locator('#stage1 video').evaluate(v=>window.previousVideo=v);
 await page.locator('.toggle').click();await page.waitForTimeout(100);
 assert(await page.evaluate(()=>previousVideo.paused&&!previousVideo.hasAttribute('src')),'hidden video released');
 await page.locator('.toggle').click();await page.locator('#stage1 video').waitFor();await page.locator('#videoTools').waitFor();

}
assert.deepEqual(errors,[]);assert.deepEqual(await page.evaluate(()=>alerts),[]);await page.close();
}
console.log('PASS: 5001-item bounded Set gallery, persistent selections, suspend/resume;  compact footer buttons above info for images/videos; category/combined manager filters; hidden selections and cover survive saving in both interfaces.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
