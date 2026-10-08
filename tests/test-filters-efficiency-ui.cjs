// Focused checks for combined filtering, collection controls and refresh efficiency.
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
 const media=Array.from({length:6},(_,i)=>({id:'img'+i,character_id:'c',media_type:'image',original_name:`Image ${i}.png`,sha256:'source'+i,thumb_rel:'thumb'+i,categories:[],in_all:true,in_review:false,width:64,height:96,file_bytes:1000,created_at:new Date(1700000000000+i*1000).toISOString()}));
 window.lib={characters:[{id:'c',name:'Fixture',categories:[{id:'dresscat',name:'Dress',media_type:'image'},{id:'othercat',name:'Other',media_type:'image'}]}],media,sets:[{id:'beach',character_id:'c',kind:'set',name:'Beach',media_ids:['img0','video'],cover_media_id:'img0'},{id:'dress',character_id:'c',kind:'set',name:'Dress',media_ids:['img1','img2','img3'],cover_media_id:'img1'},{id:'conn',character_id:'c',kind:'connection',name:'Pink bikini',media_ids:['img0','video']}]};
 for(let i=0;i<media.length;i++){media[i].categories=[i===3?'othercat':'dresscat'];media[i].favorite=[0,2,4].includes(i);}
 media.push({id:'video',character_id:'c',media_type:'video',original_name:'Video.mp4',sha256:'vid',thumb_rel:'video-thumb',categories:[],in_videos:true},{id:'video2',character_id:'c',media_type:'video',original_name:'Video2.mp4',sha256:'vid2',thumb_rel:'video-thumb2',categories:[],in_videos:true});
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

const ids=()=>page.locator('#grid .tile[data-id]').evaluateAll(nodes=>nodes.map(n=>n.dataset.id));
await page.locator('[data-cat="dresscat"]').click();
await page.locator('#naiCombinedFilters').click();
await page.locator('[data-filter="favorite"]').selectOption('yes');
assert.deepEqual(await ids(),['img0','img2','img4']);
await page.locator('[data-filter="connection"]').selectOption('no');
assert.deepEqual(await ids(),['img2','img4']);
await page.locator('[data-filter="set"]').selectOption('no');
assert.deepEqual(await ids(),['img4']);
await page.screenshot({path:'/tmp/nai-combined-filters.png'});
await page.locator('#naiClearCombinedFilters').click();
await page.locator('[data-filter="favorite"]').selectOption('yes');
await page.getByRole('button',{name:'Done',exact:true}).click();
await page.evaluate(()=>document.getElementById('nai-media-host').shadowRoot.naiSelectMedia('img0'));
const before=await page.evaluate(()=>({reads:requests.filter(r=>r.route==='/api/library').length,originals:requests.filter(r=>r.route==='/api/media/img0/original').length}));
await page.locator('#favBtn').click();
await page.waitForFunction(()=>!document.getElementById('nai-media-host').shadowRoot.querySelector('#grid .tile[data-id="img0"]'));
await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,300)));
assert.deepEqual(await ids(),['img2','img4']);
assert.deepEqual(await page.evaluate(()=>({reads:requests.filter(r=>r.route==='/api/library').length,originals:requests.filter(r=>r.route==='/api/media/img0/original').length})),before,'favorite edit does not refetch library/original');
await page.locator('#naiCombinedFilters').click();await page.locator('#naiClearCombinedFilters').click();await page.getByRole('button',{name:'Done',exact:true}).click();
await page.locator('#naiSetsCat').click();await page.locator('[data-group-filter="set"]').click();
await page.locator('#naiSetSort').selectOption('images-desc');
assert.deepEqual(await page.locator('.naiSetTile').evaluateAll(nodes=>nodes.map(n=>n.dataset.setId)),['dress','beach']);
await page.locator('#naiSetVideoPresence').selectOption('yes');assert.equal(await page.locator('.naiSetTile').count(),1);assert.equal(await page.locator('.naiSetTile').getAttribute('data-set-id'),'beach');
await page.locator('#naiSetVideoPresence').selectOption('no');assert.equal(await page.locator('.naiSetTile').getAttribute('data-set-id'),'dress');
await page.locator('#naiSetVideoPresence').selectOption('any');
await page.locator('.naiSetTile[data-set-id="dress"]').click();await page.locator('#naiSetBackBtn').waitFor();
await page.locator('#naiCombinedFilters').click();await page.locator('[data-filter="favorite"]').selectOption('yes');await page.getByRole('button',{name:'Done',exact:true}).click();
assert.deepEqual(await ids(),['img2']);
await page.locator('#randomBtn').click();await page.waitForFunction(()=>JSON.parse(localStorage.getItem('nai-media-v1-ui')).selectedMediaId==='img2');
assert.equal(await page.locator('#counter').textContent(),'1 / 1');
await page.locator('#naiCombinedFilters').click();await page.locator('#naiClearCombinedFilters').click();await page.getByRole('button',{name:'Done',exact:true}).click();
await page.evaluate(()=>{const r=document.getElementById('nai-media-host').shadowRoot;window.savedTile=r.querySelector('.tile[data-id="img1"]');window.gridChanges=0;window.mo=new MutationObserver(list=>{for(const m of list)gridChanges+=m.addedNodes.length+m.removedNodes.length});mo.observe(r.getElementById('grid'),{childList:true});});
await page.locator('.tile[data-id="img1"]').click();await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,180)));
assert.equal(await page.evaluate(()=>savedTile===document.getElementById('nai-media-host').shadowRoot.querySelector('.tile[data-id="img1"]')),true);
assert.equal(await page.evaluate(()=>{mo.disconnect();return gridChanges}),0,'set selection keeps grid intact');
await page.locator('#videosModeBtn').click();await page.locator('#naiCombinedFilters').click();await page.locator('[data-filter="connection"]').selectOption('no');assert.deepEqual(await ids(),['video2']);
assert.deepEqual(await page.evaluate(()=>alerts),[]);assert.deepEqual(errors,[]);
console.log('PASS: combined conditions/navigation, no-refetch metadata edits, set video filters/image sorting, stable set tiles, video connection filter.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
