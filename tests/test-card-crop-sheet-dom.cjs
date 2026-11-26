const {test}=require('node:test');
const assert=require('node:assert/strict');
const {fixture,waitFor,delay}=require('./ui-fixture.cjs');
const button=(root,name)=>[...root.querySelectorAll('button')].find(b=>b.textContent===name||b.getAttribute('aria-label')===name);
const copy=value=>JSON.parse(JSON.stringify(value));
const tight={fit:'contain',zoom:1.16,x:0,y:2};
const wider={fit:'contain',zoom:1.08,x:0,y:1};
const fuller={fit:'fill',zoom:1,x:0,y:0};
const fit={fit:'contain',zoom:1,x:0,y:0};

async function setup({open=true,pending=false,analysisUnavailable=false,offline=false,healthyAll=false}={}){
 const media=Array.from({length:offline?32:16},(_,i)=>({id:'p'+i,character_id:'character',original_name:'Photo '+i,media_type:'image',in_all:true,categories:[]}));
 const rows=media.slice(1).map(m=>({id:m.id,name:m.original_name,images:[m.id],tier:'Gold',rating:1400,played:5,position:1,titles:[],owned_editions:[]}));
 Object.assign(rows[0],{id:'duo',duo_side:'front',images:['p0','p1']});
 const collection={revision:'first',frames:{'image:p15':copy(wider)},frame_meta:{},crop_review:{}};
 const actions=[];
 let prior,reject,overviewGate,stale=false,releaseAnalysis=()=>{};
 const analyzed=new Set();
 const analysisGate=pending||healthyAll?new Promise(resolve=>{releaseAnalysis=resolve;}):Promise.resolve();
 const state=()=>copy({collection,boards:[{kind:'images',entries:rows}]});
 const f=await fixture({media,sourceModules:['ui-src/card-debug.js','ui-src/battles.js'],configure:w=>{
  w.HTMLCanvasElement.prototype.getContext=function(){return require('@napi-rs/canvas').createCanvas(this.width,this.height).getContext('2d');};
  Object.defineProperties(w.HTMLImageElement.prototype,{
   naturalWidth:{get(){return 800;},configurable:true},naturalHeight:{get(){return 1200;},configurable:true},complete:{get(){return true;},configurable:true}
  });
  w.HTMLElement.prototype.getBoundingClientRect=()=>({x:0,y:0,left:0,top:0,width:200,height:400,right:200,bottom:400});
 }});
 const {root,w}=f,cards=root.naiCards,faces=[],originals=[],thumbs=[],battleCalls=[],stateCalls=[];
 if(healthyAll)w.sessionStorage.setItem('nai-crop-review:character',JSON.stringify({filter:'all'}));
 cards.load=async owner=>{const data=state();cards.cache.set(owner,data);return data;};
 const render=cards.lightCard;
 cards.lightCard=(e,rows,owner,im,show,mid)=>{faces.push([mid,e.duo_side]);return render(e,rows,owner,im,show,mid);};
 root.naiOutfitOriginal=async id=>{originals.push(id);return new w.Blob(['original']);};
 root.naiLoadThumbnail=async(id,im)=>{thumbs.push(id);if(id==='p3')throw Error('Missing preview');im.src='blob:fixture-'+id;};
 const getProposal=mid=>{
  const index=Number(mid.slice(1)),marker=collection.crop_review[mid]||{},meta=collection.frame_meta['image:'+mid],isManual=index===15||meta?.checked;
  const category=isManual?'saved':offline?(analyzed.has(mid)?'unavailable':'pending'):
   healthyAll||pending&&index>=11?(analyzed.has(mid)?index===12?'likely':'needs_look':'pending'):'needs_look';
  const analysis_status=category==='pending'?'pending':category==='unavailable'||analysisUnavailable&&mid==='p5'?'unavailable':'ready';
  const fallback=mid==='p5'||mid==='p12'?wider:fit;
  return {
   category,token:'token-'+mid+'-'+analysis_status,source_token:'source-'+mid,checked:index===14||!!meta?.checked,
   flagged:!!marker.flagged,deferred:!!marker.deferred,analysis_status,
   reason:category==='needs_look'?'Compare edges':'Ready',
   options:{suggested:{frame:collection.frames['image:'+mid]||(analysis_status==='ready'?tight:fallback),label:'Suggested crop'},
    ...(analysis_status==='ready'?{wider:{frame:wider,label:'More body'},fuller:{frame:fuller,label:'Fill opening'}}:{}),
    fit:{frame:fit,label:'Fit whole photo'}},
  };
 };
 const getQueue=()=>{
  const queue={flagged:[],needs_look:[],likely:[],fit:[],later:[],checked:[],pending:[],unavailable:[]};
  for(const {id} of media){
   const p=getProposal(id),bucket=p.flagged?'flagged':p.deferred?'later':p.checked?'checked':p.category;
   if(id!=='p15'||p.flagged)queue[bucket]?.push(id);
  }
  return queue;
 };
 const pair={id:'same-match',left:'duo',right:'p2',reason:'Fixture'};
 root.naiOutfitRequest=async(path,body)=>{
  if(path.startsWith('/api/battles/')){
   battleCalls.push(path);
   return {entries:rows,revision:'battle',kind:'images',votes:8,scope_count:rows.length,
    session:{pair,available:true,limit:0,done:0,mode:'rank'}};
  }
  if(path.endsWith('crop-review-state')){
   stateCalls.push(copy(body));
   const ids=body.media_ids||[];
   if(!ids.length&&overviewGate){const gate=overviewGate;overviewGate=null;await gate;}
   if(body.analyze!==false&&healthyAll&&ids.length)await analysisGate;
   if(body.analyze!==false&&pending&&ids.some(id=>['p11','p12','p13'].includes(id)))await analysisGate;
   if(body.analyze!==false)ids.forEach(id=>analyzed.add(id));
   return copy({revision:collection.revision,proposals:Object.fromEntries(ids.map(id=>[id,getProposal(id)])),queue:getQueue()});
  }
  actions.push(copy({path,...body}));
  if(stale||body.revision!==collection.revision){stale=false;throw Error('The crop changed. Refresh the sheet.');}
  if(reject){const message=reject;reject=null;throw Error(message);}
  if(path.endsWith('crop-review-undo')){
   assert.equal(body.undo_token,'undo');
   Object.assign(collection,prior);
  }else{
   prior=copy(collection);
   for(const {media_id:mid,choice,frame,token} of body.reviews){
    const key='image:'+mid,p=getProposal(mid);
    assert.ok([p.token,p.source_token].includes(token));
    if(choice==='suggested'&&p.analysis_status!=='ready')throw Error('Crop analysis is unavailable. Choose Fit or Adjust.');
    if(choice==='flag')collection.crop_review[mid]={flagged:true};
    else if(choice==='unflag')delete collection.crop_review[mid];
    else if(choice==='later')collection.crop_review[mid]={deferred:true};
    else{
     collection.frames[key]=choice==='manual'?copy(frame):copy(p.options[choice].frame);
     collection.frame_meta[key]={mode:choice==='manual'?'manual':'reviewed',checked:true};
     delete collection.crop_review[mid];
    }
   }
  }
  collection.revision+='x';return {...state(),undo_token:path.endsWith('save')?'undo':undefined};
 };
 const openSheet=(scope=root)=>{button(scope,'Review card crops').click();return root.querySelector('[aria-label="Review card crops"]');};
 const sheet=open?openSheet():null;
 return {...f,sheet,root,cards,collection,faces,originals,thumbs,battleCalls,stateCalls,openSheet,releaseAnalysis,
  get actions(){return actions;},stale(){stale=true;},fail(message){reject=message;},
  pauseOverview(){
   let resume,fail;
   overviewGate=new Promise((resolve,reject)=>{resume=resolve;fail=message=>reject(Error(message));});
   return {resume,fail};
  }};
}

test('sheet reviews twelve actual frames, protects unrendered and off-page crops, batches approvals, and edits its marked exceptions',async()=>{
 const f=await setup();
 try{
  let {sheet}=f;
  const {errors}=f;
  await waitFor(()=>button(sheet,'Approve all (11)')?.disabled===false,errors).catch(e=>{throw Error(sheet.textContent,{cause:e});});
  assert.equal(sheet.querySelectorAll('.naiCropTile').length,12);
  assert.equal(sheet.querySelectorAll('.naiFramedSource').length,11);
  assert.deepEqual(f.faces.filter(([id])=>id==='p0'||id==='p1').sort(),[['p0','front'],['p1','back']]);
  assert.deepEqual(f.originals,[]);
  assert.ok(sheet.querySelector('[aria-label="Mark Photo 3 for editing"]').disabled);
  const check=photo=>sheet.querySelector('[aria-label="Mark Photo '+photo+' for editing"]');
  check(2).click();check(4).click();
  button(sheet,'Approve others & edit 2').click();
  await waitFor(()=>button(sheet,'[3] More body')?.disabled===false,errors);
  assert.deepEqual(f.actions[0].reviews.map(r=>r.media_id),['p0','p1','p5','p6','p7','p8','p9','p10','p11']);
  assert.equal(f.actions[0].revision,'first');
  assert.ok(f.actions[0].reviews.every(r=>r.choice==='suggested'));
  const editor=sheet.querySelector('.naiCropException');
  const key=(type,key)=>editor.dispatchEvent(new f.w.KeyboardEvent(type,{key,bubbles:true,cancelable:true}));
  const preview=editor.querySelector('.naiCropEditView');
  const card=preview.querySelector('.naiTradingCard');
  key('keydown',' ');
  assert.equal(preview.dataset.mode,'original');
  assert.equal(preview.querySelector('.naiTradingCard'),card);
  key('keyup',' ');
  assert.equal(preview.dataset.mode,'crop');
  key('keydown','3');
  assert.equal(button(editor,'[3] More body').getAttribute('aria-pressed'),'true');
  assert.equal(editor.querySelector('h3').textContent,'Photo 2');
  assert.equal(f.actions.length,1);
  assert.equal(f.collection.frames['image:p2'],undefined);
  key('keydown','Enter');
  await waitFor(()=>editor.querySelector('h3')?.textContent==='Photo 4',errors);
  assert.deepEqual(f.originals,['p2','p4']);
  assert.deepEqual(f.collection.frames['image:p2'],wider);
  button(editor,'Later').click();
  await waitFor(()=>button(sheet,'Approve all (2)')?.disabled===false,errors);
  assert.equal(f.collection.frame_meta['image:p4'],undefined);
  assert.deepEqual(f.collection.crop_review.p4,{deferred:true});
  button(sheet,'Later (1)').click();
  await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 4"]')?.disabled===false,errors);
  assert.equal(sheet.querySelectorAll('.naiCropTile').length,1);
  button(sheet,'Close').click();
  sheet=f.openSheet();
  await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 4"]')?.disabled===false,errors);
  assert.equal(button(sheet,'Later (1)').getAttribute('aria-pressed'),'true');
  button(sheet,'Undo last').click();
  await waitFor(()=>sheet.querySelector('[role=status]').textContent==='No crops saved for later.',errors);
  button(sheet,'Needs a look').click();
  await waitFor(()=>button(sheet,'Approve all (3)')?.disabled===false,errors);
  assert.equal(f.collection.crop_review.p4,undefined);
  assert.equal(f.collection.frame_meta['image:p3'],undefined);
  assert.ok(f.revoked.length>=2);
  assert.deepEqual(errors,[]);
 }finally{f.dom.window.close();}
});

test('background analysis keeps ready cards usable and excludes newly classified likely crops from Needs a look',async()=>{
 const f=await setup({pending:true});
 try{
  const {sheet,errors}=f;
  await waitFor(()=>button(sheet,'Approve all (10)')?.disabled===false,errors);
  assert.match(sheet.querySelector('[role=status]').textContent,/Analyzing 3 more crops/);
  assert.equal(sheet.querySelectorAll('.naiCropTile').length,11);
  f.releaseAnalysis();
  await waitFor(()=>button(sheet,'Approve all (11)')?.disabled===false&&!sheet.querySelector('[role=status]').textContent.includes('Analyzing'),errors);
  assert.equal(sheet.querySelectorAll('.naiCropTile').length,12);
  assert.ok(!sheet.querySelector('[aria-label="Edit crop for Photo 12"]'));
  assert.ok(!button(sheet,'Next').disabled);
  button(sheet,'Next').click();
  await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 13"]')?.disabled===false,errors);
  button(sheet,'Close').click();
  const reopened=f.openSheet();
  await waitFor(()=>reopened.querySelector('[aria-label="Edit crop for Photo 13"]')?.disabled===false,errors);
  button(reopened,'All auto crops').click();
  await waitFor(()=>button(reopened,'Next')?.disabled===false,errors);
  button(reopened,'Next').click();
  await waitFor(()=>reopened.querySelector('[aria-label="Edit crop for Photo 12"]')?.disabled===false,errors);
  assert.equal(reopened.querySelector('[aria-label="Edit crop for Photo 15"]'),null);
  assert.deepEqual(errors,[]);
 }finally{f.releaseAnalysis();f.dom.window.close();}
});

test('failed crop saves preserve the active edit and explicit retry, keyboard input, and untouched close',async()=>{
 const f=await setup();
 try{
  const {sheet,w,errors}=f;
  await waitFor(()=>button(sheet,'Approve all (11)')?.disabled===false,errors).catch(e=>{throw Error(sheet.textContent,{cause:e});});
  f.stale();button(sheet,'Approve all (11)').click();
  await waitFor(()=>sheet.querySelector('[role=alert]').textContent.includes('Refresh'),errors);
  assert.ok(button(sheet,'Approve all (11)').disabled);
  assert.deepEqual(f.collection.frames,{'image:p15':wider});
  button(sheet,'Refresh').click();
  await waitFor(()=>button(sheet,'Approve all (11)')?.disabled===false,errors).catch(e=>{throw Error(sheet.textContent,{cause:e});});
  sheet.querySelector('[aria-label="Edit crop for Photo 1 · back"]').click();
  const editor=sheet.querySelector('.naiCropException');
  await waitFor(()=>button(editor,'Save & next')?.disabled===false,errors);
  assert.equal(f.actions.length,1);
  const zoom=editor.querySelector('[aria-label=Zoom]');
  zoom.dispatchEvent(new w.KeyboardEvent('keydown',{key:'2',bubbles:true}));
  assert.equal(f.actions.length,1);
  const opening=editor.querySelector('.naiCropEditView .naiCardPhotoWindow');
  for(const [type,x,y] of [['pointerdown',10,30],['pointermove',20,50],['pointerup',20,50]]){
   opening.dispatchEvent(new w.MouseEvent(type,{clientX:x,clientY:y,button:0,bubbles:true}));
  }
  opening.dispatchEvent(new w.WheelEvent('wheel',{deltaY:-60,bubbles:true,cancelable:true}));
  f.fail('Temporary save failure.');
  editor.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  await waitFor(()=>sheet.querySelector('[role=alert]').textContent.includes('Temporary')&&!button(editor,'Save & next').disabled,errors);
  assert.equal(editor.querySelector('h3').textContent,'Photo 1 · back');
  assert.equal(f.collection.frames['image:p1'],undefined);
  button(editor,'Save & next').click();
  await waitFor(()=>f.collection.frames['image:p1']?.zoom>tight.zoom&&editor.hidden,errors);
  assert.equal(f.actions.at(-1).reviews[0].choice,'manual');
  const frame=f.collection.frames['image:p1'];
  assert.ok(Math.abs(frame.x-5/frame.reference.width)<.001);
  assert.ok(Math.abs(frame.y-2-5/frame.reference.height)<.001);
  button(sheet,'Undo last').click();
  await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 1 · back"]')?.disabled===false,errors);
  assert.equal(f.collection.frames['image:p1'],undefined);
  sheet.querySelector('[aria-label="Edit crop for Photo 2"]').click();
  await waitFor(()=>button(editor,'Save & next')?.disabled===false,errors);
  const before=f.actions.length;
  button(sheet,'Close').click();
  assert.equal(f.actions.length,before);
  assert.equal(f.collection.frame_meta['image:p2'],undefined);
  assert.deepEqual(errors,[]);
 }finally{f.dom.window.close();}
});

test('an unavailable analysis offers an individual decision without entering batch approval',async()=>{
 const f=await setup({analysisUnavailable:true});
 try{
  const {sheet,w,errors}=f;
  await waitFor(()=>button(sheet,'Approve all (10)')?.disabled===false,errors);
  assert.match(sheet.querySelector('[role=status]').textContent,/1 preview unavailable · 1 to check individually/);
  const check=sheet.querySelector('[aria-label="Mark Photo 5 for editing"]');
  assert.equal(check.disabled,false);
  check.click();button(sheet,'Approve others & edit 1').click();
  const editor=sheet.querySelector('.naiCropException');
  await waitFor(()=>button(editor,'[2] Keep current crop')?.disabled===false,errors);
  assert.ok(f.actions[0].reviews.every(r=>r.media_id!=='p5'));
  editor.dispatchEvent(new w.KeyboardEvent('keydown',{key:'2',bubbles:true,cancelable:true}));
  assert.equal(f.actions.length,1);
  assert.equal(editor.hidden,false);
  button(editor,'Save & next').click();
  await waitFor(()=>editor.hidden,errors);
  assert.equal(f.actions.at(-1).reviews[0].choice,'manual');
  assert.deepEqual(f.collection.frames['image:p5'],wider);
  assert.deepEqual(errors,[]);
 }finally{f.dom.window.close();}
});

test('unanalysed crops on later pages can be fitted or kept while analysis is offline',async()=>{
 const f=await setup({offline:true});
 try{
  const {sheet,w,errors}=f;
  const status=sheet.querySelector('[role=status]'),editor=sheet.querySelector('.naiCropException');
  await waitFor(()=>status.textContent.includes('Automatic analysis unavailable'),errors);
  assert.equal(sheet.querySelectorAll('.naiCropTile').length,4);
  assert.equal(button(sheet,'Approve all').disabled,true);
  const analyzed=f.stateCalls.filter(call=>call.analyze!==false&&call.media_ids?.length);
  assert.deepEqual(analyzed.map(call=>call.media_ids),[['p0','p1','p2','p3']]);
  button(sheet,'All auto crops').click();
  await waitFor(()=>!button(sheet,'Next').disabled,errors);
  button(sheet,'Next').click();
  await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 12"]')?.disabled===false,errors);
  assert.ok(status.textContent.includes('to check individually'));
  assert.ok(button(sheet,'Approve all').disabled);
  sheet.querySelector('[aria-label="Edit crop for Photo 12"]').click();
  await waitFor(()=>button(editor,'Save & next')?.disabled===false,errors);
  assert.ok(button(editor,'[1] Fit whole photo'));
  editor.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
  await waitFor(()=>f.collection.frame_meta['image:p12']?.mode==='manual'&&editor.hidden,errors);
  assert.deepEqual(f.collection.frames['image:p12'],wider);
  const fitTile=await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 13"]')?.disabled===false&&sheet.querySelector('[aria-label="Edit crop for Photo 13"]'),errors);
  fitTile.click();
  await waitFor(()=>button(editor,'Save & next')?.disabled===false,errors);
  assert.equal(editor.querySelectorAll('.naiCropTreatments button').length,1);
  assert.equal(button(editor,'[1] Fit whole photo').getAttribute('aria-pressed'),'true');
  button(editor,'Save & next').click();
  await waitFor(()=>f.actions.at(-1)?.reviews[0].media_id==='p13'&&editor.hidden,errors);
  assert.equal(f.actions.at(-1).reviews[0].choice,'fit');
  assert.deepEqual(f.collection.frames['image:p13'],fit);
  await waitFor(()=>!button(sheet,'Next').disabled,errors);
  button(sheet,'Next').click();
  await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 25"]')?.disabled===false,errors);
  assert.deepEqual(f.stateCalls.filter(call=>call.analyze!==false&&call.media_ids?.length),analyzed);
  assert.equal(f.actions.length,2);
  assert.deepEqual(errors,[]);
 }finally{f.dom.window.close();}
});

test('restored All auto crops keeps analyzing and updates visible marked cards in place',async()=>{
 const f=await setup({healthyAll:true});
 try{
  const {sheet,errors,root,w}=f;
  const save=()=>button(sheet,'Approve others & edit 1');
  const marked=await waitFor(()=>{
   const checkbox=sheet.querySelector('[aria-label="Mark Photo 0 · front for editing"]');
   return checkbox&&!checkbox.disabled&&checkbox;
  },errors);
  assert.equal(button(sheet,'All auto crops').getAttribute('aria-pressed'),'true');
  marked.click();marked.focus();
  const tile=marked.closest('.naiCropTile'),im=tile.querySelector('.naiFramedSource');
  assert.equal(button(sheet,'Edit 1').disabled,false);
  assert.equal(tile.querySelector('.naiCropDetails small').textContent,'Ready');
  await waitFor(()=>f.stateCalls.some(call=>call.analyze!==false&&call.media_ids?.includes('p0')),errors);
  f.releaseAnalysis();
  await waitFor(()=>save()?.disabled===false,errors);
  assert.equal(tile.querySelector('.naiCropDetails small').textContent,'Compare edges');
  assert.equal(tile.querySelector('.naiFramedSource'),im);
  assert.equal(tile.querySelector('input'),marked);
  assert.equal(root.activeElement,marked);
  assert.equal(marked.checked,true);
  assert.match(w.sessionStorage.getItem('nai-crop-review:character'),/token-p0-ready/);
  save().click();
  const editor=sheet.querySelector('.naiCropException');
  await waitFor(()=>editor.querySelector('h3')?.textContent==='Photo 0 · front',errors);
  assert.equal(root.activeElement,editor);
  assert.ok(f.actions[0].reviews.every(r=>r.media_id!=='p0'));
  assert.deepEqual(errors,[]);
 }finally{f.releaseAnalysis();f.dom.window.close();}
});

test('Battles flags the displayed Duo face without a new matchup, a vote, or a crop change',async()=>{
 const f=await setup({open:false});
 try{
  const {root,errors}=f;
  root.getElementById('naiBattlesBtn').click();
  const left=await waitFor(()=>root.querySelector('.naiBattleCard[data-entry-id=duo]'),errors,5000).catch(e=>{throw Error(root.querySelector('.naiBattleWrap')?.textContent,{cause:e});});
  left.querySelector('.naiDuoFlip').click();
  const back=root.querySelector('.naiBattleCard[data-entry-id=duo]');
  const flag=back.querySelector('.naiFlagCrop');
  const before=[...f.battleCalls];
  flag.click();
  await waitFor(()=>flag.getAttribute('aria-pressed')==='true',errors);
  assert.deepEqual(f.collection.crop_review,{p1:{flagged:true}});
  assert.deepEqual(f.battleCalls,before);
  assert.equal(root.querySelector('.naiBattleCard[data-entry-id=duo]'),back);
  assert.match(root.querySelector('.naiBattleStatus').textContent,/8 saved votes/);
  assert.equal(f.collection.frames['image:p1'],undefined);
  assert.equal(f.actions.at(-1).reviews[0].token,'source-p1');
  assert.deepEqual(errors,[]);
 }finally{await delay(100);f.dom.window.close();}
});

test('treatments, original peek and beyond-frame view are local until explicit save',async()=>{
 const f=await setup();
 try{
  const {sheet,w,errors}=f;
  const edit=sheet.querySelector('.naiCropException'),samples=new Map(),apply=f.cards.applyFrame;
  f.cards.applyFrame=(im,frame)=>{
   if(im.closest('.naiCropTreatmentCard'))samples.set(im,copy(frame));
   apply(im,frame);
  };
  await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 1 \u00b7 back"]')?.disabled===false,errors);
  sheet.querySelector('[aria-label="Edit crop for Photo 1 \u00b7 back"]').click();
  await waitFor(()=>button(edit,'Save & next')?.disabled===false,errors);
  const stage=edit.querySelector('.naiCropEditView'),card=stage.querySelector('.naiTradingCard');
  const im=card.querySelector('.naiFramedSource'),source=im.src;
  const fitType=edit.querySelector('[aria-label="Photo framing"]'),zoom=edit.querySelector('[aria-label=Zoom]');
  assert.equal(card.dataset.duoSide,'back');
  assert.match(edit.querySelector('.naiCardOriginalSize').textContent,/800.*1,200/);
  assert.equal(zoom.value,String(tight.zoom));
  for(const [name,frame] of [['[1] Fit whole photo',fit],['[2] Suggested crop',tight],['[3] More body',wider],['[4] Fill opening',fuller]]){
   const sampleCard=button(edit,name).querySelector('.naiCropTreatmentCard');
   const sample=sampleCard.querySelector('.naiFramedSource');
   assert.equal(sampleCard.dataset.duoSide,'back');
   assert.equal(sampleCard.getAttribute('aria-hidden'),'true');
   assert.equal(sample.src,source);
   assert.deepEqual(samples.get(sample),frame);
  }
  assert.equal(f.actions.length,0);
  const key=(type,key)=>stage.dispatchEvent(new w.KeyboardEvent(type,{key,bubbles:true,cancelable:true}));
  button(edit,'[1] Fit whole photo').click();
  assert.equal(zoom.value,'1');
  key('keydown','4');
  assert.equal(fitType.value,'fill');
  assert.equal(button(edit,'[4] Fill opening').getAttribute('aria-pressed'),'true');

  button(edit,'Show photo beyond frame').click();
  assert.equal(stage.dataset.mode,'overflow');
  assert.equal(stage.querySelector('.naiTradingCard'),card);
  assert.equal(card.style.visibility,'');
  assert.ok(card.querySelector('.naiEditionFrame'));
  const overflow=stage.querySelector('.naiCropOverflowPhoto');
  assert.equal(overflow.hidden,false);
  assert.equal(overflow.src,source);
  assert.equal(stage.querySelector('.naiCropCardBoundary').hidden,false);
  assert.equal(stage.querySelector('.naiCropAperture').hidden,false);
  key('keydown',' ');
  assert.equal(stage.dataset.mode,'original');
  assert.equal(stage.querySelector('.naiCropAperture').hidden,true);
  assert.equal(stage.querySelector('.naiTradingCard'),card);
  assert.equal(card.style.visibility,'');
  assert.equal(overflow.hidden,true);
  assert.equal(im.src,source);
  assert.equal(zoom.disabled,true);
  assert.equal(button(edit,'Save & next').disabled,true);
  key('keyup',' ');
  assert.equal(stage.dataset.mode,'overflow');
  button(edit,'Peek original').click();
  key('keyup',' ');
  assert.equal(stage.dataset.mode,'original');
  button(edit,'Peek original').click();
  assert.equal(stage.dataset.mode,'overflow');
  button(edit,'Show photo beyond frame').click();
  assert.equal(stage.dataset.mode,'crop');
  assert.equal(fitType.value,'fill');
  assert.equal(f.actions.length,0);

  button(edit,'Reset framing').click();
  assert.equal(zoom.value,'1');
  assert.equal(fitType.value,'contain');
  assert.ok([...edit.querySelectorAll('.naiCropTreatments button')].every(b=>b.getAttribute('aria-pressed')==='false'));
  const reset=button(edit,'Reset framing');
  reset.focus();
  reset.dispatchEvent(new w.KeyboardEvent('keydown',{key:'2',bubbles:true,cancelable:true}));
  assert.equal(f.root.activeElement,stage);
  assert.equal(zoom.value,String(tight.zoom));
  assert.equal(f.actions.length,0);
  key('keydown','Enter');
  await waitFor(()=>edit.hidden,errors);
  assert.deepEqual(f.actions[0].reviews,[{media_id:'p1',token:'token-p1-ready',choice:'suggested'}]);
  assert.deepEqual(f.collection.frames['image:p1'],tight);
  assert.deepEqual(errors,[]);
 }finally{f.dom.window.close();}
});

test('review edge buttons place unavoidable padding and recover overpan without applying a crop',async()=>{
 const f=await setup();
 try{
  const {sheet,w,errors}=f;
  const edit=sheet.querySelector('.naiCropException');
  const link=await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 2"]'),errors);
  await waitFor(()=>!link.disabled,errors);link.click();
  await waitFor(()=>button(edit,'Save & next')?.disabled===false,errors);
  const stage=edit.querySelector('.naiCropEditView'),card=stage.querySelector('.naiTradingCard');
  const opening=card.querySelector('.naiCardPhotoWindow'),im=opening.querySelector('.naiFramedSource');
  Object.defineProperties(card,{clientWidth:{value:420},clientHeight:{value:600}});
  Object.defineProperties(opening,{clientWidth:{value:336},clientHeight:{value:448},offsetLeft:{value:42},offsetTop:{value:78}});
  const edge=direction=>button(edit,'Move photo all the way '+direction);
  const position=(label,value)=>{
   const slider=edit.querySelector('[aria-label="'+label+'"]');
   slider.value=value;slider.dispatchEvent(new w.Event('input'));
  };
  const pixels=(attribute,span)=>parseFloat(im.style[attribute])/100*span;
  const near=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-8,`${actual} != ${expected}`);
  button(edit,'[1] Fit whole photo').click();
  const left=edge('left'),right=edge('right');
  const horizontal=edit.querySelector('[aria-label="Horizontal position"]');
  assert.equal(left.nextElementSibling,horizontal);
  assert.equal(horizontal.nextElementSibling,right);
  left.click();
  near(pixels('left',336)-pixels('width',336)/2,0);
  right.click();
  near(pixels('left',336)+pixels('width',336)/2,336);
  position('Vertical position',23);
  edge('up').click();
  near(pixels('top',448),224);
  assert.equal(f.actions.length,0);

  position('Zoom',1.16);position('Horizontal position',39);position('Vertical position',-32);
  button(edit,'Show photo beyond frame').click();
  const topBefore=im.style.top;
  left.click();
  near(pixels('left',336)+pixels('width',336)*1.16/2,336);
  assert.equal(im.style.top,topBefore);
  right.click();
  near(pixels('left',336)-pixels('width',336)*1.16/2,0);
  const leftBefore=im.style.left;
  edge('up').click();
  near(pixels('top',448)+pixels('height',448)*1.16/2,448);
  edge('down').click();
  near(pixels('top',448)-pixels('height',448)*1.16/2,0);
  assert.equal(im.style.left,leftBefore);
  button(edit,'Peek original').click();
  assert.ok(['left','right','up','down'].every(direction=>edge(direction).disabled));
  button(edit,'Peek original').click();
  assert.equal(stage.dataset.mode,'overflow');
  assert.equal(f.actions.length,0);
  button(edit,'Save & next').click();
  await waitFor(()=>edit.hidden,errors);
  const result=f.actions[0].reviews[0];
  assert.equal(result.choice,'manual');
  near(result.frame.x,(448*800/1200*1.16-336)/2/336*100);
  near(result.frame.y,8);
  assert.equal(result.frame.fit,'contain');
  assert.equal(result.frame.zoom,1.16);
  assert.deepEqual(result.frame.reference,{left:.1,top:.13,width:.8,height:448/600});
  assert.deepEqual(errors,[]);
 }finally{f.dom.window.close();}
});

test('review sliders and dragging stay continuous beyond the old pan limit',async()=>{
 const f=await setup();
 try{
  const {sheet,w,errors}=f;
  const edit=sheet.querySelector('.naiCropException');
  const label='[aria-label="Edit crop for Photo 2"]';
  const link=await waitFor(()=>sheet.querySelector(label)?.disabled===false&&sheet.querySelector(label),errors);
  link.click();
  await waitFor(()=>button(edit,'Save & next')?.disabled===false,errors);
  const stage=edit.querySelector('.naiCropEditView'),card=stage.querySelector('.naiTradingCard');
  const opening=card.querySelector('.naiCardPhotoWindow'),im=opening.querySelector('img');
  Object.defineProperties(card,{clientWidth:{value:420},clientHeight:{value:600}});
  Object.defineProperties(opening,{clientWidth:{value:336},clientHeight:{value:448},offsetLeft:{value:42},offsetTop:{value:78}});
  Object.defineProperties(im,{naturalWidth:{value:3072},naturalHeight:{value:384}});
  button(edit,'[4] Fill opening').click();
  const slider=label=>edit.querySelector('[aria-label="'+label+'"]');
  const move=(label,position)=>{
   const control=slider(label);
   control.value=position;control.dispatchEvent(new w.Event('input'));
  };
  move('Zoom',3);
  button(edit,'Move photo all the way right').click();
  assert.equal(Number(slider('Horizontal position').value),1550);
  move('Horizontal position',1549.9);
  button(edit,'Show photo beyond frame').click();
  for(const [type,x,y] of [['pointerdown',10,30],['pointermove',10,35],['pointerup',10,35]]){
   opening.dispatchEvent(new w.MouseEvent(type,{clientX:x,clientY:y,button:0,bubbles:true}));
  }
  assert.equal(Number(slider('Horizontal position').value),1549.9);
  for(const [type,x,y] of [['pointerdown',10,30],['pointermove',8,30],['pointerup',8,30]]){
   opening.dispatchEvent(new w.MouseEvent(type,{clientX:x,clientY:y,button:0,bubbles:true}));
  }
  assert.ok(Math.abs(Number(slider('Horizontal position').value)-1549.9)<1);
  assert.equal(f.actions.length,0);
  button(edit,'Save & next').click();
  await waitFor(()=>edit.hidden,errors);
  assert.ok(Math.abs(f.actions[0].reviews[0].frame.x-(1549.9-200/336))<1e-8);
  assert.deepEqual(errors,[]);
 }finally{f.dom.window.close();}
});

test('refresh disarms the previous draft during a delayed read and leaves a recovery path on failure',async()=>{
 const f=await setup();
 try{
  const {sheet,w,errors}=f,editor=sheet.querySelector('.naiCropException');
  await waitFor(()=>sheet.querySelector('[aria-label="Edit crop for Photo 2"]')?.disabled===false,errors);
  sheet.querySelector('[aria-label="Edit crop for Photo 2"]').click();
  await waitFor(()=>button(editor,'Save & next')?.disabled===false,errors);
  button(editor,'[1] Fit whole photo').click();
  const oldSave=button(editor,'Save & next'),oldLater=button(editor,'Later');
  const reject=f.pauseOverview();
  button(sheet,'Refresh').click();
  assert.equal(oldSave.isConnected,false);
  assert.equal(button(editor,'Back to sheet').disabled,false);
  await waitFor(()=>sheet.querySelector('[role=status]').textContent==='Loading crop review\u2026',errors);
  oldSave.click();oldLater.click();
  editor.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
  assert.equal(f.actions.length,0);
  reject.fail('The Library did not respond.');
  await waitFor(()=>sheet.querySelector('[role=alert]').textContent.includes('did not respond'),errors);
  assert.equal(button(editor,'Save & next'),undefined);
  assert.equal(button(editor,'Back to sheet').disabled,false);

  const recover=f.pauseOverview();
  button(sheet,'Refresh').click();
  assert.equal(button(editor,'Save & next'),undefined);
  recover.resume();
  await waitFor(()=>button(editor,'Save & next')?.disabled===false,errors);
  assert.equal(editor.querySelector('h3').textContent,'Photo 2');
  assert.equal(button(editor,'[2] Suggested crop').getAttribute('aria-pressed'),'true');
  assert.equal(f.collection.frames['image:p2'],undefined);
  assert.equal(f.actions.length,0);
  assert.deepEqual(errors,[]);
 }finally{f.dom.window.close();}
});
