// Per-collection presentation state. No scans or changes to set membership.
let sessionReady=false,sessionTimer,sessionFlight=Promise.resolve(),unassignedOnly=false;
const sessionKey=()=>data?.scope?'organizer-session:'+data.scope:null;
function captureSession(){
 const ui={savedAt:Date.now(),tab,limit,columns:Number($('columns').value),sidebarWidth:sidebarWidth||defaultSidebarWidth(),
  highlight:$('workspace').classList.contains('highlight-unassigned'),relatedVisible:$('workspace').classList.contains('show-related'),
  sidebarSet:sidebarSet||'',sidebarOffset,relatedOffset,unassignedOnly,
  gridScroll:$('grid').scrollTop,navScroll:document.querySelector('.workspace>nav').scrollTop,suggestionsScroll:$('suggestions').scrollTop};
 for(const id of ['search','sourceFilter','filter','postSort','setFilter','setSort','order'])ui[id]=$(id).value;
 if(view)ui.view={kind:currentKind,id:currentId,offset};
 return ui;
}
function saveSession(leaving=false){
 clearTimeout(sessionTimer);if(!sessionReady||!data?.job)return Promise.resolve();
 const ui=captureSession(),payload={job:data.job,ui};
 try{if(sessionKey())localStorage.setItem(sessionKey(),JSON.stringify(ui))}catch{}
 if(leaving){fetch('/api/organizer/session',{method:'POST',keepalive:true,headers:{'X-Review-Token':TOKEN,'Content-Type':'application/json'},body:JSON.stringify(payload)}).catch(()=>{});return Promise.resolve()}
 sessionFlight=sessionFlight.catch(()=>{}).then(()=>api('session',payload));return sessionFlight;
}
function scheduleSession(){if(!sessionReady)return;clearTimeout(sessionTimer);sessionTimer=setTimeout(()=>saveSession().catch(e=>toast(e.message)),250)}
function restoreSession(){
 let ui=data.state.ui||{};
 try{const cached=JSON.parse(localStorage.getItem(sessionKey())||'null');if(cached&&Number(cached.savedAt)>Number(ui.savedAt||0))ui=cached}catch{}
 tab=ui.tab==='sets'?'sets':ui.tab==='posts'?'posts':tab;
 for(const id of ['search','sourceFilter','filter','postSort','setFilter','setSort','order'])if(typeof ui[id]==='string'){
  if(id==='search'||[...$(id).options].some(o=>o.value===ui[id]))$(id).value=ui[id];
 }
 limit=Math.max(80,Number(ui.limit)||80);
 if(ui.columns){$('columns').value=Math.max(2,Math.min(8,ui.columns));$('grid').style.setProperty('--cols',$('columns').value)}
 if(typeof ui.highlight==='boolean')applyHighlight(ui.highlight);
 if(ui.sidebarWidth){sidebarWidth=ui.sidebarWidth;applySidebarWidth()}
 $('workspace').classList.toggle('show-related',!!ui.relatedVisible);
 sidebarSet=data.sets.some(g=>g.id===ui.sidebarSet)?ui.sidebarSet:null;
 sidebarOffset=Number(ui.sidebarOffset)||0;relatedOffset=Number(ui.relatedOffset)||0;
 unassignedOnly=ui.unassignedOnly===true;$('unassignedOnly').checked=unassignedOnly;
 if(ui.view){currentKind=ui.view.kind;currentId=ui.view.id;offset=Number(ui.view.offset)||0}
 return ui;
}
async function restoreScroll(ui){
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 $('grid').scrollTop=ui.gridScroll||0;document.querySelector('.workspace>nav').scrollTop=ui.navScroll||0;$('suggestions').scrollTop=ui.suggestionsScroll||0;
}
$('unassignedOnly').onchange=()=>task(async()=>{
 unassignedOnly=$('unassignedOnly').checked;relatedOffset=0;sidebarSet=null;++sidebarSerial;
 await related();$('suggestions').scrollTop=0;await saveSession();
});
// Event listeners run after the existing controls, and async navigation also saves on completion.
for(const event of ['input','change','click','pointerup','keyup'])document.addEventListener(event,e=>{
 if(e.target.closest('header,nav,main,.right'))scheduleSession();
});
for(const target of [$('grid'),document.querySelector('.workspace>nav'),$('suggestions')])target.addEventListener('scroll',scheduleSession,{passive:true});
addEventListener('pagehide',()=>saveSession(true));
document.addEventListener('visibilitychange',()=>{if(document.hidden)saveSession(true)});
