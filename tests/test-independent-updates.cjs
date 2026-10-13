const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('payload/userscript-2.8.73.update-status.txt','utf8');
(async()=>{
 for(const standalone of [false,true]){
  const pending=[],buttons=[],observers=[],events={};let reloads=0,busy=false;
  const node=()=>({style:{},append(){},insertAdjacentElement(){},setAttribute(){},addEventListener(n,fn){events[n]=fn;}});
  const root={getElementById:()=>node(),querySelector:()=>busy?{}:null,host:{}};
  const html={dataset:{naiStandalone:standalone?'1':'',naiMediaPayloadVersion:'2.8.73'}};
  const cache=new Map(),context={document:{getElementById:()=>({shadowRoot:root}),documentElement:html,createElement:tag=>{const e=node();if(tag==='button')buttons.push(e);return e;},addEventListener(){}},console:{info(){}},MutationObserver:class{constructor(fn){observers.push(fn);}observe(){}},GM_xmlhttpRequest:o=>pending.push(o),location:{reload(){reloads++;}},localStorage:{getItem:k=>cache.get(k)},confirm:()=>true};
  vm.runInNewContext(source,context);
  if(standalone){assert.equal(pending.length,1);assert(pending[0].url.endsWith('/api/standalone/check'));pending.shift().onload({status:200,responseText:'{"version":"2.8.74"}'});await new Promise(r=>setImmediate(r));}
  else {assert.equal(pending.length,0);cache.set('nai-media-github-payload-version','2.8.74');cache.set('nai-media-github-payload','code');observers.forEach(fn=>fn());}
  assert.equal(reloads,0,'check never reloads either interface');assert.equal(buttons[0].hidden,false);
  busy=true;observers.forEach(fn=>fn());buttons[0].onclick();assert.equal(reloads,0);
  busy=false;observers.forEach(fn=>fn());buttons[0].onclick();assert.equal(reloads,1);assert.equal(pending.length,0,'Update does no downloading or shared activation');
 }
 console.log('PASS: independent update readiness, editor guard, immediate cached reload, no activation requests.');
})().catch(e=>{console.error(e);process.exitCode=1;});
