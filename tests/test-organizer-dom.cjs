const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const repo=path.resolve(__dirname,'..'),delay=ms=>new Promise(r=>setTimeout(r,ms));
async function ready(fn){for(let i=0;i<100;i++){if(fn())return;await delay(10)}throw Error('Organizer did not become ready')}
async function fixture(){
 const errors=[],calls=[];
 const photo={id:'photo',name:'Photo.png',path:'/source/Photo.png',media_type:'image',sources:['first'],sets:[],quarantined:false,discarded:false};
 const state={job:'job',scope:'fixture',collections:[{id:'job',name:'Fixture',roots:['/source']}],posts:[{id:'first',label:'Post 1',count:1,remaining:1,kind:'folder',status:'pending'},{id:'second',label:'Post 2',count:1,remaining:1,kind:'folder',status:'pending'}],sets:[],up_next:[],later_count:0,category_catalog:{categories:[],character_id:'owner'},state:{revision:1,selection:[],new_name:'',new_colors:[],new_categories:[]},images:2,indexed:2,unresolved:0,unassigned_count:2,unsorted_count:0,discarded_count:0,progress:{running:false,done:2,total:2},inventory_complete:true};
 const code=fs.readFileSync(path.join(repo,'duplicate-review/organizer.html'),'utf8').replaceAll('__TOKEN__','fixture').replace('__ORGANIZER_WORKFLOW__',fs.readFileSync(path.join(repo,'duplicate-review/missing-files.js'),'utf8')+'\n'+fs.readFileSync(path.join(repo,'duplicate-review/organizer-workflow.js'),'utf8')).replace('__ORGANIZER_SESSION__',fs.readFileSync(path.join(repo,'duplicate-review/organizer-session.js'),'utf8')).replace('__UPDATER__','');
 const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('Not implemented:'))errors.push(e.message)});
 const dom=new JSDOM(code,{url:'http://127.0.0.1:8844/organizer',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'))};w.HTMLElement.prototype.scrollIntoView=function(){};w.ResizeObserver=class{observe(){}disconnect(){}};
 w.fetch=async(url,options={})=>{const u=new URL(url,w.location),route=u.pathname.split('/').at(-1),body=JSON.parse(options.body||'{}');calls.push({route,body});let data=state;
 if(route==='page'){const ids=u.searchParams.get('kind')==='up_next'?state.up_next:['photo'];data={label:u.searchParams.get('kind')==='up_next'?'Up next':state.posts.find(p=>p.id===u.searchParams.get('id'))?.label,total:ids.length,offset:0,ids,images:ids.map(()=>photo),job:'job'};}
 else if(route==='draft'){state.state.selection=body.ids;state.state.new_name=body.new_name;data={ok:true};}
 else if(route==='pin'){state.up_next=body.pinned?['photo']:[];state.state.revision++;}
 else if(route==='post'){state.posts.find(p=>p.id===body.id).status=body.status;state.later_count=state.posts.filter(p=>p.status==='deferred').length;state.state.revision++;}
 else if(route==='related')data={images:[],posts:[],sets:[],total:0};
 else if(route==='transfer-preview')data={token:'preview',sets:[{name:'Draft',action:'Create',count:1}],imports:[],existing_count:1,conflicts:[],issues:['Source file missing']};
 else if(route==='session')data={ok:true};
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
