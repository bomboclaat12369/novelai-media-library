// Focused browser check for replacement screen and individual thumbnails in normal categories.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(dir,process.env.NAI_RELEASE_CONFIG || 'release-userscript.json')));
const payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
(async()=>{const browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM || '/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});try{
const page=await browser.newPage({viewport:{width:1700,height:1000}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
await page.route('http://127.0.0.1:8765/**',r=>r.fulfill({status:404,body:''}));
await page.goto('https://novelai.net/stories');
await page.evaluate(()=>{
 const media=Array.from({length:220},(_,i)=>({id:'img'+i,character_id:'c',media_type:'image',original_name:`Image ${i}.png`,sha256:'source'+i,thumb_rel:'thumb'+i,categories:[],in_all:true,in_review:false,width:64,height:96,file_bytes:1000,created_at:new Date(1700000000000+i*1000).toISOString()}));
 window.lib={characters:[{id:'c',name:'Fixture',categories:[{id:'dresscat',name:'Dress',media_type:'image'}]}],media,sets:[{id:'beach',character_id:'c',kind:'set',name:'Beach',media_ids:['img0','video'],cover_media_id:'video'},{id:'dress',character_id:'c',kind:'set',name:'Dress',media_ids:[]},{id:'conn',character_id:'c',kind:'connection',name:'Pink bikini',media_ids:[]}]};
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
await page.evaluate(payload);await page.getByText('Local library connected',{exact:true}).waitFor();

for(const cat of ['all','favorites','dresscat']){
 await page.locator(`[data-cat="${cat}"]`).click();
 assert.equal(await page.locator('#grid .naiSetTile').count(),0,'normal category never substitutes set cards');
 assert.equal(await page.locator('#grid .tile[data-id="img0"] img[data-mid="img0"]').count(),1);
 assert.equal(await page.locator('#grid .tile[data-id="video"]').count(),0);
}
await page.locator('#naiSetsCat').click();
await page.locator('.naiSetTile[data-set-id="beach"]').waitFor();
assert.equal(await page.locator('.naiSetTile[data-set-id="beach"]').getAttribute('data-cover-id'),'video');
await page.locator('[data-cat="all"]').click();
await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia('img0'));
await page.locator('#editBtn').click();
assert.equal(await page.locator('#replaceSourceBtn').textContent(),'Replace Source Image');
await page.locator('#replaceSourceBtn').click();
await page.locator('#naiReplacementDrop').waitFor();
assert.ok(await page.locator('#naiReplacementSave').isDisabled());
// Clicking the drop box opens the chooser, and choosing remains unsaved until Replace.
const chooser=page.waitForEvent('filechooser');await page.locator('#naiReplacementDrop').click();
await (await chooser).setFiles({name:'cancel.png',mimeType:'image/png',buffer:Buffer.from('image')});
assert.match(await page.locator('#naiReplacementFile').textContent(),/cancel.png/);
assert.equal(await page.evaluate(()=>requests.filter(r=>r.route.endsWith('/replace')).length),0);
await page.locator('[data-replacement-close]').last().click();
await page.locator('#replaceSourceBtn').click();
await page.evaluate(()=>{window.leakedDrop=false;window.addEventListener('drop',()=>window.leakedDrop=true);const zone=document.getElementById('nai-media-host').shadowRoot.getElementById('naiReplacementDrop'),data=new DataTransfer();data.items.add(new File(['replacement'],'new.png',{type:'image/png'}));for(const type of ['dragover','drop'])zone.querySelector('.dropTitle').dispatchEvent(new DragEvent(type,{dataTransfer:data,bubbles:true,composed:true,cancelable:true}));});
assert.equal(await page.evaluate(()=>leakedDrop),false,'replacement drop must not reach NovelAI');
assert.match(await page.locator('#naiReplacementFile').textContent(),/new.png/);
assert.equal(await page.evaluate(()=>requests.filter(r=>r.route.endsWith('/replace')).length),0);
await page.locator('#naiReplacementSave').click();
await page.waitForFunction(()=>document.getElementById('nai-media-host').shadowRoot.getElementById('selectedName').textContent==='new.png');
assert.equal(await page.evaluate(()=>requests.filter(r=>r.route.endsWith('/replace')).length),1);
assert.ok(await page.evaluate(()=>requests.some(r=>r.route==='/api/media/img0/original'&&r.url.includes('source=replacement'))));
assert.deepEqual(await page.evaluate(()=>lib.sets[0].media_ids),['img0','video']);
assert.deepEqual(await page.evaluate(()=>alerts),[]);assert.deepEqual(errors,[]);
console.log('PASS: own thumbnails in normal categories, set cover preserved, replacement chooser/drop, cancel and explicit save.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
