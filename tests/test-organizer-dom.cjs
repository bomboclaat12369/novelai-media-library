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
 w.fetch=async(url,options={})=>{const u=new URL(url,w.location),route=u.pathname.split('/').at(-1),body=JSON.parse(options.body||'{}');calls.push({route,body});let data=state;
 if(route==='page'){const ids=u.searchParams.get('kind')==='up_next'?state.up_next:u.searchParams.get('kind')==='imports'?(state.individuals||[]).map(r=>r.id).filter(Boolean):photos.map(p=>p.id);data={label:u.searchParams.get('kind')==='up_next'?'Up next':state.posts.find(p=>p.id===u.searchParams.get('id'))?.label,total:ids.length,offset:0,ids,images:ids.map(id=>photos.find(p=>p.id===id)||photo),job:'job'};}
 else if(route==='draft'){state.state.selection=body.ids;state.state.new_name=body.new_name;data={ok:true};}
 else if(route==='pin'){state.up_next=body.pinned?['photo']:[];state.state.revision++;}
 else if(route==='post'){state.posts.find(p=>p.id===body.id).status=body.status;state.later_count=state.posts.filter(p=>p.status==='deferred').length;state.state.revision++;}
 else if(route==='related')data={images:[],posts:[],sets:[],total:0};
 else if(route==='transfer-preview')data={token:'preview',sets:[{name:'Draft',action:'Create',count:1}],imports:[],existing_count:1,conflicts:[],issues:['Source file missing']};
 else if(route==='session')data={ok:true};
 if(custom.route){const override=await custom.route(route,body,state,calls);if(override!==undefined)data=override;}
 return {ok:true,json:async()=>JSON.parse(JSON.stringify(data))};};}});
 try{await ready(()=>dom.window.document.querySelector('[data-star="photo"]'))}catch(e){const note=dom.window.document.getElementById('notice').textContent;dom.window.close();throw Error(note+' '+JSON.stringify(errors)+' '+JSON.stringify(calls));}
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
