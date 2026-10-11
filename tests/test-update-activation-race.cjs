// A response issued before clicking Update must not invalidate that activation.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto');
const source=fs.readFileSync(process.env.NAI_UPDATE_PART || 'payload/userscript-2.8.70.update-status.txt','utf8');
(async()=>{
 const pending=[],timers=[],buttons=[];let reloads=0;
 const node=()=>({style:{},append(){},insertAdjacentElement(){},setAttribute(){}});
 const root={getElementById:()=>node(),querySelector:()=>null,host:{}},html={dataset:{naiMediaPayloadVersion:'2.8.69'}};
 const context={document:{getElementById:()=>({shadowRoot:root}),documentElement:html,createElement:tag=>{const e=node();if(tag==='button')buttons.push(e);return e;},addEventListener(){}},window:{addEventListener(){}},MutationObserver:class{observe(){}},GM_xmlhttpRequest:o=>{pending.push(o);return {abort(){}}},setTimeout:fn=>{timers.push(fn);return timers.length},clearTimeout(){},TextEncoder,crypto:crypto.webcrypto,location:{reload(){reloads++}},localStorage:{setItem(){}},confirm:()=>true};
 vm.runInNewContext(source,context);
 const flush=()=>new Promise(r=>setImmediate(r));
 const respond=async(path,value)=>{const index=pending.findIndex(o=>o.url.endsWith(path));assert(index>=0,'request '+path);const [o]=pending.splice(index,1);o.onload({status:200,responseText:JSON.stringify(value)});await flush();};
 await respond('/api/health',{coordinated_updates:true});
 // Old code polls immediately; new code waits until its initial check completes.
 const oldWatch=pending.find(o=>o.url.endsWith('/status'));
 if(oldWatch)await respond('/status',{version:'2.8.69',activation:''});
 await respond('/check',{version:'2.8.69',activation:''});
 timers.shift()();await flush(); // now a status response is in flight
 buttons[0].onclick();await flush();
 await respond('/check',{version:'2.8.70',activation:''});
 await respond('/activate',{version:'2.8.70',activation:'activate-new'});
 await respond('/status',{version:'2.8.69',activation:''}); // stale read arrives while payload loads
 const code='verified new UI';await respond('/payload',{version:'2.8.70',code,sha256:crypto.createHash('sha256').update(code).digest('hex')});
 for(let i=0;i<10&&!reloads;i++)await flush();
 assert.equal(reloads,1,'Update should apply immediately despite a delayed older status response');
 console.log('PASS: stale status cannot overwrite an explicit activation during payload verification.');
})().catch(e=>{console.error(e);process.exitCode=1});
