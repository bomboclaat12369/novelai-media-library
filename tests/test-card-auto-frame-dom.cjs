const {test}=require('node:test'),assert=require('node:assert/strict');
const {fixture,waitFor,delay}=require('./ui-fixture.cjs');
const copy=x=>JSON.parse(JSON.stringify(x));
const frame={x:0,y:0,zoom:16/15,fit:'contain',reference:{left:.1,top:.13,width:.8,height:1120/1500}};
const media=['unchecked','checked','manual','default'].map(id=>({id,character_id:'character',media_type:'image',original_name:id+'.jpg',categories:[],in_all:true,width:800,height:1000}));
const entries=media.map((m,i)=>({id:m.id,name:m.original_name,images:[m.id],count:1,played:3,rating:1250-i*50,rd:200,opponent_count:3,position:i+1,provisional:false,tier:'Gold',rating_status:'Developing',titles:[],owned_editions:[],automatic_editions:[],edition_settings:{choice:'auto',traits:[]}}));
const button=(root,text)=>{const b=[...root.querySelectorAll('button')].find(b=>b.textContent===text);assert.ok(b,'Missing '+text);return b};

async function setup(){
 const auto=(checked,token)=>({mode:'auto',checked,token,algorithm:'centered-edge-fit-v2',side_crop_percent:3.125,vertical_crop_percent:0,frame:copy(frame)});
 let collection={revision:'r1',frames:{'image:unchecked':copy(frame),'image:checked':copy(frame),'image:manual':{x:5,y:0,zoom:1.2,fit:'contain'}},frame_meta:{'image:unchecked':auto(false,'first'),'image:checked':auto(true,'second')}};
 const calls=[];let reject=false;
 const f=await fixture({media:copy(media),configure:w=>{
  Object.defineProperties(w.HTMLElement.prototype,{clientWidth:{get(){return this.classList.contains('naiTradingCard')?420:1000},configurable:true},clientHeight:{get(){return 700},configurable:true}});
  w.HTMLCanvasElement.prototype.getContext=()=>null;
  const normal=w.GM_xmlhttpRequest;w.GM_xmlhttpRequest=o=>{
   const route=new URL(o.url).pathname,b=JSON.parse(typeof o.data==='string'?o.data:'{}');let value,status=200;
   if(route.startsWith('/api/collection/')){
    calls.push({route,body:b});
    if(route.endsWith('frame-review')||route.endsWith('frame-default')){
     const key='image:'+b.media_id,meta=collection.frame_meta[key];
     if(reject||b.revision!==collection.revision||b.token!==meta?.token){status=400;value={error:'Automatic positioning changed. Refresh the card.'};}
     else {if(route.endsWith('frame-review'))meta.checked=b.checked;else {collection.frames[key]={x:0,y:0,zoom:1,fit:'contain'};collection.frame_meta[key]={mode:'manual',reason:'restored_default'};}collection.revision+='x';}
    }else if(route.endsWith('/frame')){
     if(b.revision!==collection.revision){status=400;value={error:'Stale frame revision'};}
     else {collection.frames[b.key]=copy(b.frame);collection.frame_meta[b.key]={mode:'manual'};collection.revision+='x';}
    }
    value??={collection:copy(collection),name:'Fixture'};
   }else if(route.startsWith('/api/battles/'))value={entries:copy(entries),revision:'battle',kind:'images',votes:8,recorded_votes:8,ranked_count:4,scope_count:4,unfinished_count:0,session:null,trophies:[],achievements:[]};
   else return normal(o);
   queueMicrotask(()=>o.onload({status,responseText:JSON.stringify(value)}));return {abort(){}};
  };
 }});
 await f.root.naiCards.load('character');
 return {...f,calls,get collection(){return collection},reject(){reject=true}};
}

test('debug separates automatic unchecked, checked, manual and default framing',async()=>{
 const f=await setup();try{
  const cards=f.root.naiCards;
  const panels=entries.map(e=>cards.debugPanel(e,'character','images',()=>{},entries));panels.forEach(p=>f.root.append(p));
  assert.equal(panels[0].querySelector('.naiDebugCrop').textContent,'Auto-positioned · Unchecked');
  assert.equal(panels[1].querySelector('.naiDebugCrop').textContent,'Auto-positioned · Checked');
  assert.equal(panels[2].querySelector('.naiDebugCrop').textContent,'Custom crop');
  assert.equal(panels[3].querySelector('.naiDebugCrop').textContent,'Default crop');
  assert.ok(panels[0].querySelector('.naiDebugCrop').title.includes('3.13%'));
  const reviewed=cards.cache.get('character').collection.frame_meta['image:checked'];
  reviewed.side_crop_percent=0;reviewed.vertical_crop_percent=1.35;
  assert.match(cards.debugPanel(entries[1],'character','images',()=>{},entries).querySelector('.naiDebugCrop').title,/1\.35% hidden at top and bottom/);
  assert.equal(panels[2].textContent.includes('Mark checked'),false);
  for(const [filter,want] of [['all',4],['auto',2],['auto-unchecked',1],['auto-checked',1],['custom',1],['default',1]])assert.equal(entries.filter(e=>cards.matchesCropFilter('character',e.id,filter)).length,want);
  assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('review and restore use the displayed auto token and update cached framing',async()=>{
 const f=await setup();try{
  const cards=f.root.naiCards;let refreshes=0;
  const panel=cards.debugPanel(entries[0],'character','images',()=>{refreshes++},entries);f.root.append(panel);
  button(panel,'Mark checked').click();await waitFor(()=>refreshes===1,f.errors);
  assert.equal(cards.framingStatus('character','unchecked'),'auto-checked');
  assert.equal(f.calls.find(c=>c.route.endsWith('frame-review')).body.token,'first');
  assert.equal(cards.cache.get('character').collection.frames['image:unchecked'].zoom,16/15);
  const checked=cards.debugPanel(entries[0],'character','images',()=>{refreshes++},entries);f.root.append(checked);
  button(checked,'Restore default').click();await waitFor(()=>refreshes===2,f.errors);
  assert.equal(cards.framingStatus('character','unchecked'),'default');
  assert.equal(cards.cache.get('character').collection.frames['image:unchecked'].zoom,1);
  assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('a stale review rejection is visible and never marks the card checked',async()=>{
 const f=await setup();try{
  const panel=f.root.naiCards.debugPanel(entries[0],'character','images',()=>assert.fail('Unexpected refresh'),entries);f.root.append(panel);f.reject();
  button(panel,'Mark checked').click();await waitFor(()=>panel.querySelector('.naiDebugMessage').textContent.includes('Refresh the card'),f.errors);
  assert.equal(f.root.naiCards.framingStatus('character','unchecked'),'auto-unchecked');
  await waitFor(()=>!button(panel,'Mark checked').disabled,f.errors);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('opening a position marks the preview checked and refreshes the unchecked queue on close',async()=>{
 const f=await setup();try{
  f.root.getElementById('naiBattlesBtn').click();await waitFor(()=>f.root.getElementById('naiBattleLeaderboard')&&!f.root.getElementById('naiBattleLeaderboard').disabled,f.errors);f.root.getElementById('naiBattleLeaderboard').click();
  await waitFor(()=>f.root.querySelector('[aria-label="Debug mode"]'),f.errors);
  const debug=f.root.querySelector('[aria-label="Debug mode"]');debug.checked=true;debug.dispatchEvent(new f.w.Event('change'));
  await waitFor(()=>f.root.querySelectorAll('.naiCardDebugPanel').length===4,f.errors);
  let filter=f.root.querySelector('[aria-label="Crop filter"]');filter.value='auto-unchecked';filter.dispatchEvent(new f.w.Event('change'));
  await waitFor(()=>f.root.querySelectorAll('.naiCardDebugPanel').length===1,f.errors);
  button(f.root.querySelector('.naiCardDebugPanel'),'Position / crop').click();
  const editor=await waitFor(()=>f.root.querySelector('.naiCardEditor'),f.errors);
  await waitFor(()=>editor.querySelector('.naiCardZoomValue')&&!button(editor,'Close').disabled,f.errors);
  assert.equal(editor.querySelector('.naiCollectionError').textContent,'');
  assert.equal(editor.querySelector('.naiCardZoomValue').textContent.trim(),'106.67%');
  assert.equal(f.collection.frame_meta['image:unchecked'].checked,true);
  assert.equal(f.calls.filter(c=>c.route.endsWith('/frame-review')).length,1);
  button(editor,'Close').click();
  await waitFor(()=>f.root.querySelectorAll('.naiCardDebugPanel').length===0,f.errors);
  assert.equal(f.root.querySelector('[aria-label="Crop filter"]').value,'auto-unchecked');
  const toggle=f.root.querySelector('[aria-label="Debug mode"]');toggle.checked=false;toggle.dispatchEvent(new f.w.Event('change'));
  await waitFor(()=>f.root.querySelectorAll('.naiBattleRankCard').length===4,f.errors);
  assert.equal(f.root.querySelector('[aria-label="Crop filter"]'),null);assert.equal(f.root.querySelectorAll('.naiCardDebugPanel').length,0);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('viewing and saving unchanged retains automatic status; editing zoom saves at the reviewed revision',async()=>{
 const f=await setup();try{
  const cards=f.root.naiCards;
  for(const edit of [false,true]){
   await cards.adjust('character','unchecked','image:unchecked',()=>{},{entry:entries[0],rows:entries});
   const editor=f.root.querySelector('.naiCardEditor');
   if(edit){
    const zoom=editor.querySelector('[aria-label="Zoom"]');zoom.value='1.144';
    zoom.dispatchEvent(new f.w.Event('input'));assert.equal(zoom.getAttribute('aria-valuetext'),'114.4%');
   }
   button(editor,'Save framing').click();await waitFor(()=>!editor.isConnected,f.errors);
   assert.equal(cards.framingStatus('character','unchecked'),edit?'custom':'auto-checked');
  }
  assert.equal(f.calls.filter(c=>c.route.endsWith('/frame-review')).length,1);
  const saves=f.calls.filter(c=>c.route.endsWith('/frame')).map(c=>c.body);
  assert.equal(saves.length,1);assert.equal(saves[0].revision,'r1x');assert.equal(saves[0].frame.zoom,1.144);
  assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close();}
});

test('failed original loads and stale reviews leave the frame unchecked',async()=>{
 const f=await setup();try{
  const cards=f.root.naiCards,original=f.root.naiOutfitOriginal;
  f.root.naiOutfitOriginal=async()=>{throw Error('Original unavailable');};
  const open=()=>cards.adjust('character','unchecked','image:unchecked',()=>assert.fail('Unexpected refresh'),{entry:entries[0],rows:entries});
  await open();let editor=f.root.querySelector('.naiCardEditor');
  assert.match(editor.querySelector('.naiCollectionError').textContent,/Original unavailable/);
  assert.equal(f.calls.filter(c=>c.route.endsWith('/frame-review')).length,0);button(editor,'Close').click();
  f.root.naiOutfitOriginal=original;f.reject();
  await open();editor=f.root.querySelector('.naiCardEditor');
  assert.match(editor.querySelector('.naiCollectionError').textContent,/Refresh the card/);
  assert.equal(cards.framingStatus('character','unchecked'),'auto-unchecked');assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close();}
});

test('production photo layout fills height with exact side cropping and ignores legacy references',async()=>{
 const f=await setup();try{
  const cards=f.root.naiCards,card=f.w.document.createElement('div'),box=f.w.document.createElement('div'),im=f.w.document.createElement('img');
  card.className='naiTradingCard';box.className='naiCardPhotoWindow';card.append(box);box.append(im);f.root.append(card);
  Object.defineProperties(card,{clientWidth:{value:420},clientHeight:{value:600}});
  Object.defineProperties(box,{clientWidth:{value:336},clientHeight:{value:448},offsetLeft:{value:42},offsetTop:{value:78}});
  Object.defineProperties(im,{naturalWidth:{value:800},naturalHeight:{value:1000}});
  im.naiLegacyFramingReference={left:.02,top:.05,width:.9,height:.55};cards.applyFrame(im,frame);
  const width=parseFloat(im.style.width)/100*336*frame.zoom,height=parseFloat(im.style.height)/100*448*frame.zoom;
  assert.ok(Math.abs(height-448)<1e-8);assert.ok(Math.abs((1-336/width)/2-.03125)<1e-8);
  assert.equal(parseFloat(im.style.left),50);assert.ok(Math.abs(parseFloat(im.style.top)-50)<1e-8);
  assert.ok(im.style.transform.includes('scale('+frame.zoom+')'));assert.deepEqual(f.errors,[]);
  const tall=f.w.document.createElement('img');box.replaceChildren(tall);
  Object.defineProperties(tall,{naturalWidth:{value:730},naturalHeight:{value:1000}});
  const narrowFrame={...frame,zoom:750/730};cards.applyFrame(tall,narrowFrame);
  const filled=parseFloat(tall.style.width)/100*336*narrowFrame.zoom;
  const overflow=parseFloat(tall.style.height)/100*448*narrowFrame.zoom-448;
  assert.ok(Math.abs(filled-336)<1e-8);assert.ok(overflow>0);assert.ok((overflow/2)/(overflow+448)<.02);
  assert.equal(parseFloat(tall.style.left),50);assert.ok(Math.abs(parseFloat(tall.style.top)-50)<1e-8);
 }finally{f.dom.window.close()}
});
