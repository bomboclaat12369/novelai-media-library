const {test}=require('node:test');
const assert=require('node:assert/strict');
const {fixture,waitFor}=require('./ui-fixture.cjs');
const button=(root,name)=>[...root.querySelectorAll('button')].find(b=>b.textContent===name);
const copy=value=>JSON.parse(JSON.stringify(value));

async function setup(){
 const media=Array.from({length:16},(_,i)=>({id:'p'+i,character_id:'character',original_name:'Photo '+i,media_type:'image',in_all:true,categories:[]}));
 const rows=media.slice(1).map(m=>({id:m.id,name:m.original_name,images:[m.id],tier:'Gold',rating:1400,played:5,position:1,titles:[],owned_editions:[]}));
 Object.assign(rows[0],{id:'duo',duo_side:'front',images:['p0','p1']});
 const frame={fit:'contain',zoom:1.06,x:0,y:0};
 const collection={revision:'first',frames:{},frame_meta:{}};
 for(const {id} of media){
  collection.frames['image:'+id]=frame;
  collection.frame_meta['image:'+id]={mode:id==='p15'?'manual':'auto',checked:id==='p14',token:'token-'+id};
 }
 const state=()=>copy({collection,boards:[{kind:'images',entries:rows}]});
 const {createRequire}=require('node:module');
 const canvasRequire=process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?createRequire(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/package.json'):require;
 const {createCanvas}=canvasRequire('@napi-rs/canvas');
 const f=await fixture({media,sourceModules:['ui-src/card-debug.js','ui-src/battles.js'],configure:w=>{
  w.HTMLCanvasElement.prototype.getContext=function(){return createCanvas(this.width,this.height).getContext('2d');};
 }});
 const {root,w}=f,cards=root.naiCards,requests=[],faces=[],originals=[];
 cards.load=async owner=>{const data=state();cards.cache.set(owner,data);return data;};
 const render=cards.lightCard;
 cards.lightCard=(e,rows,owner,im,show,mid)=>{faces.push([mid,e.duo_side]);return render(e,rows,owner,im,show,mid);};
 let releaseFirst;
 const gate=new Promise(resolve=>{releaseFirst=resolve;});
 root.naiOutfitOriginal=async id=>{
  originals.push(id);if(id==='p0')await gate;
  if(id==='p3')throw Error('Missing original');return new w.Blob(['original']);
 };
 root.naiOutfitRequest=async(path,body)=>{
  assert.equal(path,'/api/collection/frame-review-batch');requests.push(copy(body));
  if(body.revision!==collection.revision)throw Error('Another window changed the crop.');
  for(const {media_id} of body.reviews)collection.frame_meta['image:'+media_id].checked=true;
  collection.revision+='x';return state();
 };
 button(root,'Review card crops').click();
 const sheet=root.querySelector('[aria-label="Review card crops"]');
 return {...f,sheet,cards,collection,requests,faces,originals,releaseFirst};
}

test('approves only displayed original-backed crops, across pages and both Duo faces',async()=>{
 const f=await setup();
 try{
  const {sheet,errors}=f;
  await waitFor(()=>f.originals.length===12,errors);
  assert.ok(sheet.querySelector('.naiCropToolbar button').disabled);
  f.releaseFirst();

  await waitFor(()=>button(sheet,'Approve selected (11)')?.disabled===false,errors);
  assert.equal(sheet.querySelectorAll('.naiFramedSource').length,11);
  assert.deepEqual(f.faces.filter(([id])=>id==='p0'||id==='p1').sort(),[['p0','front'],['p1','back']]);
  const tile=id=>[...sheet.querySelectorAll('.naiCropTile')].find(t=>t.querySelector('label').title===id);
  assert.ok(tile('Photo 3').querySelector('input').disabled);
  tile('Photo 2').querySelector('input').click();
  button(sheet,'Next').click();
  await waitFor(()=>button(sheet,'Approve selected (2)')?.disabled===false,errors);
  assert.ok(f.revoked.length>=11);
  assert.ok(!f.originals.includes('p14')&&!f.originals.includes('p15'));
  button(sheet,'Previous').click();
  await waitFor(()=>button(sheet,'Approve selected (10)')?.disabled===false,errors);
  assert.ok(!tile('Photo 2').querySelector('input').checked);
  button(sheet,'Approve selected (10)').click();
  await waitFor(()=>button(sheet,'Approve selected (2)')?.disabled===false,errors);
  assert.deepEqual(f.requests[0].reviews.map(r=>r.media_id),['p0','p1','p4','p5','p6','p7','p8','p9','p10','p11']);
  assert.equal(f.requests[0].revision,'first');
  assert.ok(f.requests[0].reviews.every(r=>r.token==='token-'+r.media_id));
  assert.ok(!tile('Photo 2').querySelector('input').checked);
  button(sheet,'Close').click();
  assert.ok(!sheet.isConnected);assert.deepEqual(errors,[]);
 }finally{f.releaseFirst();f.dom.window.close();}
});

test('stale approval requires refresh and an adjustment opens the existing editor with the original face',async()=>{
 const f=await setup();try{
  f.releaseFirst();const {sheet,collection}=f;
  await waitFor(()=>button(sheet,'Approve selected (11)')?.disabled===false,f.errors);
  collection.revision='changed';
  button(sheet,'Approve selected (11)').click();
  await waitFor(()=>sheet.querySelector('[role=alert]').textContent.includes('Refresh'),f.errors);
  assert.ok(button(sheet,'Approve selected (11)').disabled);
  button(sheet,'Refresh').click();
  await waitFor(()=>button(sheet,'Approve selected (11)')?.disabled===false,f.errors);
  let adjusted;
  f.cards.adjust=(owner,mid,key,onSaved,context)=>{
   adjusted=[owner,mid,key,context.entry.duo_side];
   collection.frame_meta[key]={mode:'manual'};onSaved();
  };
  sheet.querySelector('[aria-label="Adjust crop for Photo 1 · back"]').click();
  await waitFor(()=>button(sheet,'Approve selected (11)')?.disabled===false,f.errors);
  assert.deepEqual(adjusted,['character','p1','image:p1','back']);
  assert.ok(!sheet.querySelector('[aria-label="Adjust crop for Photo 1 · back"]'));
  assert.equal(f.requests.length,1);assert.deepEqual(f.errors,[]);
 }finally{f.releaseFirst();f.dom.window.close();}
});
