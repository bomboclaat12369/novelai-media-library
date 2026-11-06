const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const code=fs.readFileSync(path.join(__dirname,'../duplicate-review/missing-files.js'),'utf8');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function ready(fn){for(let i=0;i<100;i++){if(fn())return;await delay(10)}throw Error('Finder did not update')}
function fixture(shadow=false){const dom=new JSDOM('<button id="launch">Open</button>',{url:'http://127.0.0.1:8844/',runScripts:'outside-only',pretendToBeVisual:true});const w=dom.window;w.eval(code);w.confirm=()=>true;let job=null;const calls=[];const host=shadow?w.document.body.appendChild(w.document.createElement('div')).attachShadow({mode:'open'}):w.document.body;
 const request=async(action,body)=>{calls.push({action,body});if(action==='start'){job={id:'job',running:false,phase:'Scan complete',checked:2,total:2,missing:1,searched:4,recoverable:1,total_issues:1,errors:[],issues:[{id:'photo',name:'<b>Photo</b>.jpg',collection:'Fixture',path:'C:\\originals\\photo.jpg',problem:'Missing original',candidate:'D:\\moved\\renamed.jpg',recovered:false}]};}
 else if(action==='recover'){job.issues[0].recovered=true;job.missing=0;job.recoverable=0;return {recovered:true}}
 else if(action==='stop'){job.running=false;job.cancelled=true;job.phase='Stopped'}
 if(!job)throw Error('Start a new missing-file scan.');return JSON.parse(JSON.stringify(job));};
 const control=w.naiOpenMissingFiles({host,request});return {dom,w,host,calls,control,setJob:value=>job=value};}
function button(host,text){const b=[...host.querySelectorAll('button')].find(b=>b.textContent===text);assert.ok(b,text);b.click();return b}

for(const shadow of [false,true])test('Finder scans and explicitly recovers a selected hash match '+(shadow?'in the library':'in the organizer'),async()=>{const f=fixture(shadow);try{
 const recover=[...f.host.querySelectorAll('button')].find(b=>b.textContent==='Recover selected');assert.ok(recover.disabled);
 f.host.querySelector('textarea').value='C:\\moved\nD:\\archive';button(f.host,'Scan originals / find copies');await ready(()=>f.host.querySelector('article'));
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls.find(c=>c.action==='start').body.search_roots)),['C:\\moved','D:\\archive']);assert.equal(f.host.querySelector('article b'),null,'File names are text, not markup');
 assert.ok(recover.disabled);const check=f.host.querySelector('input[type=checkbox]');check.click();assert.equal(recover.disabled,false);recover.click();await ready(()=>f.host.textContent.includes('Recovered to the expected location.'));
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls.find(c=>c.action==='recover').body)),{job_id:'job',id:'photo'});assert.ok(recover.disabled);button(f.host,'Close');await ready(()=>!f.host.querySelector('.naiMissingOverlay'));assert.equal(f.host.querySelector('.naiMissingOverlay'),null);
 }finally{f.dom.window.close()}});

test('Closing stops status polling and cancelled scans cannot recover',async()=>{const f=fixture();try{
 f.setJob({id:'job',running:true,phase:'Checking originals',checked:0,total:1,missing:0,searched:0,recoverable:0,total_issues:0,issues:[]});
 button(f.host,'Scan originals / find copies');await ready(()=>f.host.querySelector('article'));
 f.setJob({id:'job',running:false,cancelled:true,phase:'Stopped',checked:0,total:1,missing:1,searched:0,recoverable:1,total_issues:1,issues:[{id:'x',name:'X',path:'/x',problem:'Missing',candidate:'/found'}]});
 button(f.host,'Close');await ready(()=>!f.host.querySelector('.naiMissingOverlay'));f.w.naiOpenMissingFiles({host:f.host,request:async()=>({id:'cancelled',running:false,cancelled:true,phase:'Stopped',checked:0,total:1,missing:1,recoverable:1,total_issues:1,issues:[{id:'x',name:'X',path:'/x',problem:'Missing',candidate:'/found'}]})});
 await ready(()=>f.host.querySelector('input'));assert.ok(f.host.querySelector('input').disabled);button(f.host,'Close');await ready(()=>!f.host.querySelector('.naiMissingOverlay'));const count=f.calls.length;await delay(800);assert.equal(f.calls.length,count);
 }finally{f.dom.window.close()}});
