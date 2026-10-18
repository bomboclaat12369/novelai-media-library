// Focused regression check of the actual UI functions without a browser/server.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../ui.html'),'utf8');
const script=html.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
new vm.Script(script); // Check the complete shipped script's syntax.
const elements=new Map();
function element(){return {value:'',children:[],attrs:{},style:{},classList:{toggle(){}},replaceChildren(){this.children=[]},append(child){this.children.push(child)},getAttribute(k){return this.attrs[k]??null},set src(v){this.attrs.src=v},showModal(){this.open=true}}}
const context=vm.createContext({Number,Math,$:id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)},document:{createElement:element},folder:()=>'/fixture',name:p=>p,token:'test',busy:false,snapshot:null,members:[],zoom(){},refreshComparisonResolution(){}});
vm.runInContext(script.slice(script.indexOf('function openCompare('),script.indexOf('function refreshComparisonResolution(')),context);
const run=s=>vm.runInContext(s,context);
function expectPair(ids){
 assert.deepEqual(['left','right'].map(s=>Number(elements.get(s+'Choice').value)),ids);
 for(let i=0;i<2;i++)assert.equal(elements.get(['left','right'][i]+'Image').attrs.src,`/api/preview?id=${ids[i]}&size=2000&token=test`);
}
// IDs deliberately differ from grid indexes and numeric sorting order.
for(const ids of [[91,7],[91,7,44],[91,7,44,12]]){
 context.members=ids.map(id=>({id,path:`${id}.jpg`}));
 run('openCompare()');expectPair(ids.slice(0,2));
 for(let i=0;i<ids.length;i++){
  run(`openCompare(${ids[i]})`);
  const start=Math.min(i,ids.length-2);expectPair(ids.slice(start,start+2));
  assert.deepEqual(elements.get('leftChoice').children.map(o=>o.value),ids);
  assert(elements.get('leftChoice').children.every((o,j)=>o.textContent.startsWith(`${j+1}. `)));
 }
}
// Changing either dropdown cannot reverse the pair or compare a file to itself.
run("openCompare(); $('leftChoice').value=12; updateCompare('left')");expectPair([7,12]);
run("$('rightChoice').value=91; updateCompare('right')");expectPair([91,7]);
run("$('leftChoice').value=7; updateCompare('left')");expectPair([7,44]);
run("$('rightChoice').value=7; updateCompare('right')");expectPair([91,7]);
// Keep/open actions resolve the ID visible in each pane after normalization.
let kept;
context.keepOnly=r=>{kept=r.id};
const handler=script.split('\n').find(l=>l.startsWith("for(const side of ['Left','Right'])$('keep'+side).onclick"));
run(handler);elements.get('keepLeft').onclick();assert.equal(kept,91);elements.get('keepRight').onclick();assert.equal(kept,7);
context.members=[];elements.get('compareDialog').open=false;run('openCompare()');assert.equal(elements.get('compareDialog').open,false);
assert(script.includes('image.onclick=()=>openCompare(r.id)'));
console.log('Passed: two/multiple-image order, every clicked member, dropdown changes, preview IDs, keep targets, empty groups and shipped JS syntax.');
