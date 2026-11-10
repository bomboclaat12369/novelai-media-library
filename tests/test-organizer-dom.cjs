const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const repo=path.resolve(__dirname,'..'),delay=ms=>new Promise(r=>setTimeout(r,ms));
async function ready(fn){for(let i=0;i<100;i++){if(fn())return;await delay(10)}throw Error('Organizer did not become ready')}
async function fixture(custom={}){
 const errors=[],calls=[];
 const photo={id:'photo',name:'Photo.png',path:'/source/Photo.png',media_type:'image',sources:['first'],sets:[],quarantined:false,discarded:false};
 const state={job:'job',scope:'fixture',collections:[{id:'job',name:'Fixture',roots:['/source']}],posts:[{id:'first',label:'Post 1',count:1,remaining:1,kind:'folder',status:'pending'},{id:'second',label:'Post 2',count:1,remaining:1,kind:'folder',status:'pending'}],sets:[],up_next:[],later_count:0,category_catalog:{categories:[],character_id:'owner'},state:{revision:1,selection:[],new_name:'',new_colors:[],new_categories:[]},images:2,indexed:2,unresolved:0,unassigned_count:2,unsorted_count:0,discarded_count:0,progress:{running:false,done:2,total:2},inventory_complete:true};
 Object.assign(state,custom.state||{});const photos=custom.photos||[photo];
 const code=fs.readFileSync(path.join(repo,'duplicate-review/organizer.html'),'utf8').replaceAll('__TOKEN__','fixture').replace('__ORGANIZER_WORKFLOW__',fs.readFileSync(path.join(repo,'duplicate-review/missing-files.js'),'utf8')+'\n'+fs.readFileSync(path.join(repo,'duplicate-review/organizer-workflow.js'),'utf8')+'\n'+fs.readFileSync(path.join(repo,'duplicate-review/organizer-search.js'),'utf8')).replace('__ORGANIZER_SESSION__',fs.readFileSync(path.join(repo,'duplicate-review/organizer-session.js'),'utf8')).replace('__UPDATER__','');
 const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('Not implemented:'))errors.push(e.message)});
 const dom=new JSDOM(code,{url:'http://127.0.0.1:8844/organizer',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'))};w.HTMLElement.prototype.scrollIntoView=function(){};w.ResizeObserver=class{observe(){}disconnect(){}};
 w.fetch=async(url,options={})=>{const u=new URL(url,w.location),route=u.pathname.split('/').at(-1),body=JSON.parse(options.body||'{}'),query=Object.fromEntries(u.searchParams);calls.push({route,body,query});let data=state;
 if(route==='page'){
  const {kind,id}=query,ids=custom.pages?.[kind+':'+id]||(kind==='up_next'?state.up_next:kind==='imports'?(state.individuals||[]).map(r=>r.id).filter(Boolean):photos.map(p=>p.id));
  const at=ids.includes(query.focus)?ids.indexOf(query.focus):Number(query.offset)||0,offset=Math.floor(Math.max(0,Math.min(at,Math.max(0,ids.length-1)))/60)*60;
  data={label:kind==='up_next'?'Up next':kind==='imports'?'Individual import queue':state.posts.find(p=>p.id===id)?.label||state.sets.find(s=>s.id===id)?.name,total:ids.length,offset,ids,images:ids.slice(offset,offset+60).map(id=>photos.find(p=>p.id===id)||photo),job:'job'};
  if(!query.peek)state.state.view={kind,id,offset,order:query.order};
 }
 else if(route==='draft'){state.state.selection=body.ids;state.state.new_name=body.new_name;data={ok:true};}
 else if(route==='pin'){state.up_next=body.pinned?['photo']:[];state.state.revision++;}
 else if(route==='post'){state.posts.find(p=>p.id===body.id).status=body.status;state.later_count=state.posts.filter(p=>p.status==='deferred').length;state.state.revision++;}
 else if(route==='related')data={images:[],posts:[],sets:[],total:0};
 else if(route==='transfer-preview')data={token:'preview',sets:[{name:'Draft',action:'Create',count:1}],imports:[],existing_count:1,conflicts:[],issues:['Source file missing']};
 else if(route==='session'){state.state.ui=body.ui;data={ok:true};}
 if(custom.route){const override=await custom.route(route,body,state,calls);if(override!==undefined)data=override;}
 return {ok:true,json:async()=>JSON.parse(JSON.stringify(data))};};}});
 try{await ready(()=>dom.window.document.querySelector('[data-star]')&&dom.window.eval('sessionReady'))}catch(e){const note=dom.window.document.getElementById('notice').textContent;dom.window.close();throw Error(note+' '+JSON.stringify(errors)+' '+JSON.stringify(calls));}
 return {dom,d:dom.window.document,state,calls,errors};
}
test('organizer stars do not change selection and Later moves to the next active post',async()=>{
 const f=await fixture();try{f.d.querySelector('[data-star="photo"]').click();await ready(()=>f.state.up_next.length===1);await delay(10);assert.deepEqual(f.state.state.selection,[]);assert.match(f.d.getElementById('upNext').textContent,/1/);
 f.d.getElementById('defer').click();await ready(()=>f.d.getElementById('title').textContent==='Post 2');assert.equal(f.state.posts[0].status,'deferred');assert.equal(f.state.later_count,1);assert.deepEqual(f.state.up_next,['photo']);assert.deepEqual(f.errors,[]);
 f.d.getElementById('upNext').click();await ready(()=>f.d.getElementById('title').textContent==='Up next');assert.ok([...f.d.querySelectorAll('button')].some(b=>b.textContent==='Start here'));
 }finally{f.dom.window.close()}
});
test('organizer transfer preview blocks Apply when source issues are present',async()=>{
 const f=await fixture();try{f.d.getElementById('applyDrafts').click();await ready(()=>f.d.getElementById('transferDialog').open);const dialog=f.d.getElementById('transferDialog');assert.ok(dialog.textContent.includes('Source file missing'));assert.ok([...dialog.querySelectorAll('button')].find(b=>b.textContent==='Apply changes').disabled);assert.ok(!f.calls.some(c=>c.route==='transfer-apply'));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});


test('Organizer exposes the shared missing-file finder',async()=>{
 const f=await fixture();try{const launch=[...f.dom.window.document.querySelectorAll('button')].find(b=>b.textContent==='Missing files');assert.ok(launch);launch.click();await ready(()=>f.dom.window.document.querySelector('.naiMissingPanel'));assert.ok(f.dom.window.document.querySelector('[aria-label="Folders to search for missing originals"]'));assert.deepEqual(f.errors,[]);}finally{f.dom.window.close()}
});

test('girl selector follows section identity while a new inventory has its own job ID',async()=>{
 const f=await fixture();try{f.state.section_id='girl:nikki';f.state.roots=['C:/Nikki'];f.state.collections=[{id:'girl:alice',name:'Alice',roots:[],character_id:'alice'},{id:'girl:nikki',name:'Nikki',roots:['C:/Nikki'],character_id:'nikki'}];await f.dom.window.eval('refresh()');assert.equal(f.d.getElementById('collectionPicker').value,'girl:nikki');assert.equal(f.d.getElementById('collectionFolders').disabled,false);f.d.getElementById('collectionFolders').click();assert.equal(f.d.getElementById('foldersDialog').open,true);assert.equal(f.d.getElementById('savedFolders').textContent,'C:/Nikki');assert.deepEqual(f.errors,[]);}finally{f.dom.window.close()}
});
test('folders submit additional paths with the current inventory guard',async()=>{
 const f=await fixture();try{f.state.section_id='girl:nikki';await f.dom.window.eval('refresh()');f.d.getElementById('collectionFolders').click();f.d.getElementById('newFolders').value='D:/New Nikki\nE:/More Nikki';f.d.getElementById('refreshInventory').click();await ready(()=>f.calls.some(c=>c.route==='folders'));const request=f.calls.find(c=>c.route==='folders');assert.equal(request.body.job,'job');assert.deepEqual(request.body.roots,['D:/New Nikki','E:/More Nikki']);await ready(()=>f.calls.some(c=>c.route==='state'));assert.deepEqual(f.errors,[]);}finally{f.dom.window.close()}
});


test('individual image choices save a queue without creating a set',async()=>{
 const f=await fixture({route(route,body,state){
  if(route==='import-catalog')return {character_id:'owner',name:'Nikki',categories:[{id:'ghost',name:'Private',ghost:true}]};
  if(route==='queue_individuals'){state.individuals=[{id:'photo',key:'sha',options:body.options}];state.state.selection=[];state.state.revision++;return state;}
 }});try{
 f.d.querySelector('[data-pick]').click();f.d.getElementById('queueIndividuals').click();await ready(()=>f.d.getElementById('individualImportDialog')?.open);
 assert.match(f.d.getElementById('individualImportDialog').textContent,/Nikki/);f.d.getElementById('individualDestination').value='review';f.d.querySelector('#individualCategories input').checked=true;f.d.querySelector('[aria-label="Favorite"]').checked=true;
 f.d.getElementById('saveIndividualImports').click();await ready(()=>f.calls.some(c=>c.route==='queue_individuals'));
 const call=f.calls.find(c=>c.route==='queue_individuals');assert.deepEqual(call.body.ids,['photo']);assert.equal(call.body.character_id,'owner');assert.equal(call.body.options.destination,'review');assert.equal(call.body.options.favorite,true);assert.deepEqual(call.body.options.categories,['ghost']);assert.equal(f.state.sets.length,0);
 await ready(()=>f.d.getElementById('individualQueue').textContent.includes('1'));assert.ok(!f.calls.some(c=>c.route==='transfer-import'||c.route==='transfer-apply'));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

for(const context of ['forum post','Instagram post','set','import queue'])test('queue save keeps the current page and navigation in a '+context,async()=>{
 const photos=Array.from({length:125},(_,n)=>({id:n?'photo-'+n:'photo',name:n+'.png',path:'/source/'+n+'.png',media_type:'image',sources:['first'],sets:[],origins:[]}));
 const ids=photos.map(p=>p.id),pages={'post:first':ids,'post:second':['photo-124'],'set:shoot':ids};
 const individuals=context==='import queue'?ids.map(id=>({id,key:id,options:{destination:'main',categories:[]}})):[{id:'photo-124',key:'photo-124',options:{destination:'main',categories:[]}}];
 const custom={photos,pages,state:{individuals,sets:[{id:'shoot',name:'Saved shoot',members:ids,count:ids.length}]},route(route,body,state){
  if(route==='import-catalog')return {character_id:'owner',name:'Fixture',categories:[]};
  if(route==='queue_individuals'){
   for(const id of body.ids){const row=state.individuals.find(r=>r.id===id);if(row)row.options=body.options;else state.individuals.push({id,key:id,options:body.options});}
   state.state.selection=[];state.state.revision++;return state;
  }
 }};
 const f=await fixture(custom);try{
  await f.dom.window.eval("open('post','second')");
  const kind=context==='set'?'set':context==='import queue'?'imports':'post',id=kind==='set'?'shoot':kind==='imports'?'imports':'first';
  f.d.getElementById('order').value=context==='Instagram post'?'original':'similar';
  await f.dom.window.eval(`open(${JSON.stringify(kind)},${JSON.stringify(id)},60)`);
  const grid=f.d.getElementById('grid'),nav=f.d.querySelector('.workspace>nav'),nodes=[...grid.children],title=f.d.getElementById('title').textContent,position=f.d.getElementById('position').textContent,history=f.dom.window.sessionStorage.getItem('organizer-back'),pageCalls=f.calls.filter(c=>c.route==='page').length;
  grid.scrollTop=417;nav.scrollTop=181;f.d.getElementById('search').value='Saved filter';
  grid.querySelector('[data-pick]').click();f.d.getElementById('queueIndividuals').click();await ready(()=>f.d.getElementById('individualImportDialog')?.open);
  f.d.getElementById('individualDestination').value='review';f.d.getElementById('saveIndividualImports').click();
  await ready(()=>!f.d.getElementById('individualImportDialog')&&f.d.getElementById('notice').textContent.includes('saved in the import queue'));
  assert.equal(f.d.getElementById('title').textContent,title);assert.equal(f.d.getElementById('position').textContent,position);
  assert.deepEqual([...grid.children],nodes);assert.deepEqual([...grid.querySelectorAll('.card')].map(c=>c.dataset.id),ids.slice(60,120));
  assert.equal(grid.scrollTop,417);assert.equal(nav.scrollTop,181);assert.equal(f.d.getElementById('search').value,'Saved filter');
  assert.equal(f.calls.filter(c=>c.route==='page').length,pageCalls);assert.equal(f.dom.window.sessionStorage.getItem('organizer-back'),history);
  assert.equal(f.d.getElementById('selectionCount').textContent,'0 selected');assert.match(grid.querySelector('[data-id="photo-60"] .individualBadge').textContent,/Review first/);
  assert.equal(f.state.individuals.find(r=>r.id==='photo-60').options.destination,'review');
  await ready(()=>f.state.state.ui?.gridScroll===417);
  assert.deepEqual(f.state.state.ui.view,{kind,id,offset:60});assert.deepEqual(f.state.state.view,{kind,id,offset:60,order:f.d.getElementById('order').value});
  const reopened=await fixture({...custom,state:JSON.parse(JSON.stringify(f.state))});try{
   assert.equal(reopened.d.getElementById('title').textContent,title);assert.equal(reopened.d.getElementById('position').textContent,position);assert.equal(reopened.d.getElementById('grid').scrollTop,417);
  }finally{reopened.dom.window.close();}
  f.d.getElementById('back').click();await ready(()=>f.d.getElementById('title').textContent==='Post 2');
  assert.deepEqual([...f.d.querySelectorAll('#grid .card')].map(c=>c.dataset.id),['photo-124']);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close();}
});

test('queue save from a suggestion keeps the post and the explicitly chosen image through girl selection',async()=>{
 const photos=['photo','suggestion'].map(id=>({id,name:id+'.png',path:'/source/'+id+'.png',media_type:'image',sources:['first'],sets:[],origins:[]}));
 const f=await fixture({photos,pages:{'post:first':['photo']},route(route,body,state){
  if(route==='related')return {images:[photos[1]],posts:[],sets:[],total:1};
  if(route==='edit-read')return {not_imported:true};
  if(route==='import-catalog')return body.character_id?{character_id:'owner',name:'Fixture',categories:[]}:{choose_character:[{id:'owner',name:'Fixture'}]};
  if(route==='queue_individuals'){state.individuals=body.ids.map(id=>({id,key:id,options:body.options}));state.state.selection=[];state.state.revision++;return state;}
 }});try{
  f.d.querySelector('#grid [data-pick]').click();await ready(()=>f.d.querySelector('#suggestions [data-edit-image="suggestion"]'));
  f.d.querySelector('#suggestions [data-edit-image="suggestion"]').click();await ready(()=>f.d.getElementById('individualImportDialog')?.textContent.includes('Choose the destination girl'));
  [...f.d.querySelectorAll('#individualImportDialog button')].find(b=>b.textContent==='Fixture').click();await ready(()=>f.d.getElementById('saveIndividualImports'));
  f.d.getElementById('saveIndividualImports').click();await ready(()=>f.d.getElementById('notice').textContent.includes('saved in the import queue'));
  assert.deepEqual(f.calls.find(c=>c.route==='queue_individuals').body.ids,['suggestion']);assert.equal(f.d.getElementById('title').textContent,'Post 1');
  assert.deepEqual([...f.d.querySelectorAll('#grid .card')].map(c=>c.dataset.id),['photo']);assert.match(f.d.querySelector('#suggestions .individualBadge').textContent,/Main/);assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close();}
});

test('solo transfer defaults to individual images and applies without any sets',async()=>{
 const row={id:'photo',key:'sha',options:{destination:'main',categories:[]}};
 const f=await fixture({state:{individuals:[row]},route(route,body,state){
  if(route==='transfer-preview')return {token:'solo',sets:[],individuals:[{...row,name:'Photo.png',status:'new'}],imports:[{id:'photo',name:'Photo.png'}],existing_count:0,conflicts:[],issues:[]};
  if(route==='transfer-import')return {id:'library-photo'};
  if(route==='transfer-apply'){state.individuals=[];return {sets:0,individuals:{photo:{id:'library-photo',destination:'main'}},mapping:{}};}
 }});try{f.d.getElementById('applyDrafts').click();await ready(()=>f.d.getElementById('transferDialog').open);
 const preview=f.calls.find(c=>c.route==='transfer-preview');assert.equal(preview.body.include_sets,false);assert.equal(preview.body.include_individuals,true);
 const confirm=[...f.d.getElementById('transferDialog').querySelectorAll('button')].find(b=>b.textContent==='Apply changes');assert.equal(confirm.disabled,false);confirm.click();
 await ready(()=>f.d.getElementById('transferDialog').textContent.includes('Import complete'));assert.ok(f.calls.findIndex(c=>c.route==='transfer-import')<f.calls.findIndex(c=>c.route==='transfer-apply'));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('stopping transfer waits for the current copy and never applies a partial batch',async()=>{
 let finishCopy;const copied=new Promise(resolve=>finishCopy=resolve),row={id:'photo',options:{destination:'main'}};
 const f=await fixture({state:{individuals:[row]},async route(route){
  if(route==='transfer-preview')return {token:'solo',sets:[],individuals:[row],imports:[{id:'photo',name:'1.png'},{id:'second',name:'2.png'}],existing_count:0,conflicts:[],issues:[]};
  if(route==='transfer-import'){await copied;return {id:'library-photo'};}
 }});try{f.d.getElementById('applyDrafts').click();await ready(()=>f.d.getElementById('transferDialog').open);const dialog=f.d.getElementById('transferDialog');[...dialog.querySelectorAll('button')].find(b=>b.textContent==='Apply changes').click();await ready(()=>f.calls.some(c=>c.route==='transfer-import'));
 [...dialog.querySelectorAll('button')].find(b=>b.textContent==='Stop after current file').click();finishCopy();await ready(()=>dialog.textContent.includes('Stopped.'));
 assert.equal(f.calls.filter(c=>c.route==='transfer-import').length,1);assert.ok(!f.calls.some(c=>c.route==='transfer-apply'));assert.deepEqual(f.errors,[]);
 }finally{finishCopy();f.dom.window.close()}
});

test('range selection keeps full-size viewing separate from thumbnail loading',async()=>{
 const photos=['photo','two','three'].map(id=>({id,name:id+'.png',path:'/source/'+id+'.png',media_type:'image',sources:['first'],sets:[],quarantined:false,discarded:false,origins:[]}));
 const f=await fixture({photos});try{f.d.querySelector('[data-id="photo"] [data-pick]').click();f.d.querySelector('[data-id="three"] [data-pick]').dispatchEvent(new f.dom.window.MouseEvent('click',{bubbles:true,shiftKey:true}));assert.equal(f.d.getElementById('selectionCount').textContent,'3 selected');
 f.d.querySelector('[data-id="photo"] img').click();assert.ok(f.d.getElementById('largeImage').src.includes('/api/organizer/image'));f.d.getElementById('originalQuality').click();assert.ok(f.d.getElementById('largeImage').src.includes('/api/organizer/original?id=photo'));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('manual Workbench search can find an unsuggested library Set and preserve selection',async()=>{
 const f=await fixture({route(route,body,state){
  if(route==='manual-search')return {character_id:'owner',library_instance:'instance',rows:[{id:'newset',name:'White Dress',placement:'Set',cover:'photo',sets:[],count:1}],total:1,categories:[]};
  if(route==='attach-library'){state.sets.push({id:'library:newset',library_id:'newset',name:'White Dress',members:['photo'],count:1});return {target:'library:newset',ids:['photo']};}
 }});try{f.d.querySelector('[data-pick]').click();f.d.getElementById('manualFind').click();await ready(()=>f.d.getElementById('manualBrowser')?.textContent.includes('White Dress'));[...f.d.querySelectorAll('#manualBrowser button')].find(b=>b.textContent==='Use this Set').click();await ready(()=>f.d.getElementById('target').value==='library:newset');assert.ok(f.state.state.selection.includes('photo'));assert.ok(!f.calls.some(c=>c.route==='index'));assert.deepEqual(f.errors,[]);}finally{f.dom.window.close()}
});

test('import comparison saves explicit Keep and refreshes the preview',async()=>{
 const f=await fixture({route(route,body,state){
  if(route==='transfer-preview')return {token:'preview',character_id:'owner',sets:[],individuals:[{id:'photo',options:{destination:'main'}}],imports:[{id:'photo',name:'Photo.png'}],existing_count:0,conflicts:[],issues:[]};
  if(route==='manual-search')return {character_id:'owner',library_instance:'instance',rows:[{id:'existing',name:'Library photo',placement:'Main',sha:'abc',cover:'existing',sets:[],width:1200,height:1600}],total:1,categories:[]};
  if(route==='duplicate-choice'){state.state.duplicate_choices={photo:{action:body.action,target_name:'Library photo'}};state.state.revision++;return {choice:state.state.duplicate_choices.photo};}
 }});try{f.d.getElementById('applyDrafts').click();await ready(()=>f.d.getElementById('compareImportDuplicates'));f.d.getElementById('compareImportDuplicates').click();await ready(()=>f.d.getElementById('duplicateCompare')?.textContent.includes('Library photo'));[...f.d.querySelectorAll('#duplicateCompare button')].find(b=>b.textContent==='Compare').click();await ready(()=>f.d.querySelectorAll('#comparisonImages img').length===2);[...f.d.querySelectorAll('#duplicateCompare button')].find(b=>b.textContent==='Keep existing image').click();await ready(()=>f.calls.some(c=>c.route==='duplicate-choice'));assert.equal(f.calls.find(c=>c.route==='duplicate-choice').body.target,'existing');assert.ok(!f.calls.some(c=>c.route==='transfer-apply'));f.d.getElementById('duplicateCompare').close();await ready(()=>f.d.getElementById('transferDialog').open);assert.deepEqual(f.errors,[]);}finally{f.dom.window.close()}
});

test('placement badges show only actual locations and combine with set membership',async()=>{
 const photo={id:'photo',name:'Photo.png',path:'/source/Photo.png',media_type:'image',sources:['first'],sets:['Existing shoot'],reference:true,library_present:true,in_main:true,in_review:false,in_purgatory:false};
 const f=await fixture({photos:[photo]});try{
  const labels=c=>[...c.querySelectorAll('.badge')].map(b=>b.textContent);
  assert.deepEqual(labels(f.d.querySelector('#grid .card')),['Main','In 1 set']);
  const cases=[
   [{},['Main','In 1 set']],
   [{in_main:false},['In 1 set']],
   [{in_main:null,in_review:null,in_purgatory:null},['In 1 set']],
   [{in_main:false,in_review:true},['Review','In 1 set']],
   [{in_main:false,in_purgatory:true},['Purgatory','In 1 set']],
   [{in_main:false,in_review:true,in_purgatory:true},['Review','Purgatory','In 1 set']],
   [{sets:[]},['Main']],
   [{sets:[],in_main:false,in_review:true},['Review']],
   [{sets:[],in_main:false,in_purgatory:true},['Purgatory']],
   [{sets:[],in_main:false},[]],
   [{sets:[],in_main:null,in_review:null,in_purgatory:null},[]],
   [{sets:['First shoot','Second shoot'],in_main:false},['In 2 sets']],
   [{quarantined:true},['Unresolved · quarantine']],
  ];
  for(const suggestion of [false,true])for(const [changes,expected] of cases){
   f.dom.window.badgePhoto={...photo,...changes};
   const c=f.dom.window.eval('card(window.badgePhoto,'+suggestion+')');
   assert.deepEqual(labels(c),expected);
   const membership=c.querySelector('.membership');
   if(membership)assert.equal(membership.title,f.dom.window.badgePhoto.sets.join(', '));
   if(!expected.length)assert.equal(c.querySelector('.badges'),null);
  }
  assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('failed import preview stays visible and can be retried without applying anything',async()=>{
 let attempts=0;
 const f=await fixture({route(route){if(route==='transfer-preview'&&++attempts===1)throw Error('Import preview: the companion closed the connection.');}});
 try{
  f.d.getElementById('applyDrafts').click();await ready(()=>f.d.getElementById('transferDialog').textContent.includes('Retry preview'));
  const dialog=f.d.getElementById('transferDialog');assert.ok(dialog.open);assert.match(dialog.textContent,/companion closed the connection/);
  [...dialog.querySelectorAll('button')].find(b=>b.textContent==='Retry preview').click();
  await ready(()=>dialog.textContent.includes('Source file missing'));assert.equal(attempts,2);
  assert.ok(!f.calls.some(c=>['transfer-import','transfer-apply'].includes(c.route)));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('image Edit replaces checked library categories and does not import or create a set',async()=>{
 const f=await fixture({route(route){if(route==='edit-read')return {token:'edit-token',kind:'image',location:'library',name:'Photo.png',fields:{categories:['old']},categories:[{id:'old',name:'Old'},{id:'new',name:'New'}]};if(route==='edit-save')return {ok:true};}});
 try{
  f.d.querySelector('[data-edit-image="photo"]').click();await ready(()=>f.d.getElementById('saveLibraryMetadata'));
  const panel=f.d.getElementById('libraryMetadataEditor');panel.querySelector('input[value="old"]').checked=false;panel.querySelector('input[value="new"]').checked=true;
  f.d.getElementById('saveLibraryMetadata').click();await ready(()=>!f.d.getElementById('libraryMetadataEditor'));
  const saved=f.calls.find(c=>c.route==='edit-save');assert.deepEqual(saved.body,{job:'job',token:'edit-token',fields:{categories:['new']}});
  assert.ok(!f.calls.some(c=>['save','queue_individuals','transfer-import','transfer-apply'].includes(c.route)));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('queued image Edit reopens its own saved import choices without changing library metadata',async()=>{
 const row={id:'photo',key:'hash',options:{destination:'review',categories:['old'],favorite:true}};
 const f=await fixture({state:{individuals:[row]},route(route,body,state){if(route==='import-catalog')return {character_id:'owner',library_instance:'instance',name:'Fixture',categories:[{id:'old',name:'Old'},{id:'new',name:'New'}]};if(route==='queue_individuals'){state.individuals=[{...row,options:body.options}];return state;}}});
 try{
  f.d.getElementById('individualQueue').click();await ready(()=>f.d.getElementById('title').textContent==='Individual import queue');
  f.d.querySelector('[data-edit-image="photo"]').click();await ready(()=>f.d.getElementById('individualImportDialog'));
  assert.equal(f.d.getElementById('individualDestination').value,'review');assert.ok(f.d.querySelector('#individualCategories input[value="old"]').checked);
  f.d.querySelector('#individualCategories input[value="old"]').checked=false;f.d.querySelector('#individualCategories input[value="new"]').checked=true;
  f.d.getElementById('saveIndividualImports').click();await ready(()=>f.calls.some(c=>c.route==='queue_individuals'));
  const saved=f.calls.find(c=>c.route==='queue_individuals');assert.deepEqual(saved.body.ids,['photo']);assert.deepEqual(saved.body.options.categories,['new']);assert.equal(saved.body.options.favorite,true);assert.equal(saved.body.options.destination,'review');
  assert.ok(!f.calls.some(c=>['edit-save','transfer-apply'].includes(c.route)));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});

test('Edit set renames the library record and never submits replacement membership',async()=>{
 const group={id:'library:set',library_id:'set',name:'Old set',members:['photo'],count:1,colors:[],categories:[],favorite:false,saved:false};
 const f=await fixture({state:{sets:[group]},route(route){if(route==='edit-read')return {token:'set-token',kind:'set',location:'library',name:'Old set',fields:{name:'Old set',colors:[],categories:[],favorite:false,in_purgatory:false},categories:[]};if(route==='edit-save')return {ok:true};}});
 try{
  await f.dom.window.eval("open('set','library:set',0,false)");f.d.getElementById('editSetColors').click();await ready(()=>f.d.getElementById('saveLibraryMetadata'));
  f.d.getElementById('metadata-name').value='New set';f.d.getElementById('saveLibraryMetadata').click();await ready(()=>!f.d.getElementById('libraryMetadataEditor'));
  const saved=f.calls.find(c=>c.route==='edit-save');assert.equal(saved.body.fields.name,'New set');assert.ok(!('members' in saved.body.fields));assert.ok(!('media_ids' in saved.body.fields));
  assert.ok(!f.calls.some(c=>['set_details','transfer-apply'].includes(c.route)));assert.deepEqual(f.errors,[]);
 }finally{f.dom.window.close()}
});
