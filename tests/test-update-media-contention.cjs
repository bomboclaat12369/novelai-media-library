// Model the userscript extension's shared connection pool across NovelAI tabs.
// The standalone/native transport does not share this pool.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const dir=path.resolve(__dirname,'..');
async function scenario(browser,configPath){
 const config=JSON.parse(fs.readFileSync(path.join(dir,configPath))),payload=config.parts.map(p=>fs.readFileSync(path.join(dir,p),'utf8')).join('');
 const context=await browser.newContext({viewport:{width:1500,height:900}});
 let active=0,stopped=false,statusHeld=0;const queue=[],timers=new Set(),errors=[];
 const lib={characters:[{id:'c',name:'Fixture',categories:[]}],sets:[],media:Array.from({length:220},(_,i)=>({id:'img'+i,character_id:'c',media_type:'image',original_name:'Image '+i+'.png',sha256:'hash'+i,thumb_rel:'thumb'+i,categories:[],in_all:true,width:900,height:1200}))};
 function pump(){while(!stopped&&active<2&&queue.length){const {o,resolve}=queue.shift(),url=new URL(o.url),route=url.pathname;active++;let delay=20,value={};
  if(route==='/api/health')value={ok:true,version:9,coordinated_updates:true};
  if(route==='/api/library')value=lib;
  if(route.endsWith('/quality'))value={width:900,height:1200,file_bytes:5000};
  if(route==='/api/ui-update/check'||route==='/api/ui-update/status'){value={version:config.version,cursor:'same',activation:''};if(url.searchParams.has('after')){delay=10000;statusHeld++;}}
  const thumb=route.endsWith('/thumb'),original=route.endsWith('/original');
  const body=thumb||original?`<svg xmlns="http://www.w3.org/2000/svg" width="${thumb?64:900}" height="${thumb?96:1200}"><rect width="100%" height="100%" fill="navy"/></svg>`:JSON.stringify(value);
  const timer=setTimeout(()=>{timers.delete(timer);active--;resolve({status:200,body,type:thumb||original?'image/svg+xml':'application/json'});pump();},delay);timers.add(timer);
 }}
 await context.exposeBinding('companionBridge',(_,o)=>new Promise(resolve=>{queue.push({o,resolve});pump();}));
 await context.route('https://novelai.net/**',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Fixture</body>'}));
 await context.addInitScript(({payload,version})=>{
  window.GM_xmlhttpRequest=o=>{let abort=false;window.companionBridge({url:o.url,method:o.method}).then(r=>{if(abort)return;o.onload?.({status:r.status,response:o.responseType==='blob'?new Blob([r.body],{type:r.type}):r.body,responseText:o.responseType==='blob'?'':r.body});o.onloadend?.({});});return{abort(){abort=true;o.onabort?.({});}};};
  document.addEventListener('DOMContentLoaded',()=>{document.documentElement.dataset.naiMediaPayloadVersion=version;eval(payload);});
 },{payload,version:config.version});
 const pages=await Promise.all(Array.from({length:3},async()=>{const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));await p.goto('https://novelai.net/stories');return p;}));
 let completed=false,detail='';
 try{
  await Promise.all(pages.map(async p=>{
   await p.getByText('Local library connected',{exact:true}).waitFor({timeout:7000});
   await p.locator('#grid .tile[data-id="img0"]').click({timeout:7000});
   await p.waitForFunction(()=>{const root=document.getElementById('nai-media-host').shadowRoot;const images=[...root.querySelectorAll('#grid img')];const large=root.querySelector('#stage1 img');return images.length>=10&&images.every(img=>img.complete&&img.naturalWidth>0)&&large?.naturalWidth===900;},{},{timeout:7000});
  }));completed=true;
 }catch(e){detail=e.message.split('\n')[0];}
 stopped=true;for(const t of timers)clearTimeout(t);await context.close();
 assert.deepEqual(errors,[]);
 return {version:config.version,completed,statusHeld,detail};
}
(async()=>{const browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/nai-chromium',headless:true,args:['--no-sandbox','--disable-gpu']});try{
 if(process.env.NAI_COMPARE_OLD){const old=await scenario(browser,'candidate-userscript-2.8.68.json');console.log(old);assert(!old.completed&&old.statusHeld>=2,'old listener should reproduce connection starvation');}
 const current=await scenario(browser,process.env.NAI_RELEASE_CONFIG||'release-userscript.json');console.log(current);assert(current.completed);assert.equal(current.statusHeld,0);
 console.log('PASS: visible thumbnails and full-resolution viewers load in three NovelAI tabs sharing two request slots.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
