// Exercise the production card decorator with native canvas and a minimal DOM.
// This verifies rendering/data wiring, not browser CSS layout.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto'),{createRequire}=require('module');
const req=process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES?createRequire(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/package.json'):require,{createCanvas,loadImage,GlobalFonts}=req('@napi-rs/canvas');
const pack=JSON.parse(fs.readFileSync('assets/cards/editions/catalog.json')),R=require('../assets/cards/editions/refined/frame-renderer'),G=require('../assets/cards/editions/refined/guide-renderer');
const config=JSON.parse(fs.readFileSync('release-standalone.json'));
const source=fs.readFileSync(config.parts.find(p=>p.endsWith('.editions.txt')),'utf8');
for(const [f,p]of Object.entries(pack.fonts))GlobalFonts.registerFromPath(p,f);
GlobalFonts.registerFromPath(pack.fonts.EditionNumeralsV2,'EditionRankNumeralsV1');
class E{
 constructor(tag){this.tag=tag;this.children=[];this.className='';this.dataset={};this.attrs={};this.style={setProperty(k,v){this[k]=v}};this.classList={add:(...ns)=>{this.className+=' '+ns.join(' ')},contains:n=>this.className.split(' ').includes(n)};this.clientWidth=420;this.isConnected=false;}
 append(...ns){this.children.push(...ns)}setAttribute(k,v){this.attrs[k]=v}querySelector(s){return this.children.find(e=>e.className?.split(' ').includes(s.slice(1)))||null}querySelectorAll(){return []}
}
function canvas(){const c=createCanvas(1,1),e=new E('canvas');for(const k of Object.keys(e))c[k]=e[k];c.setAttribute=e.setAttribute;c.log=[];const ctx=c.getContext('2d'),fill=ctx.fillText.bind(ctx);ctx.fillText=(s,...a)=>{c.log.push(s);return fill(s,...a)};return c;}
const root=new E('root');root.naiGetLibrary=()=>({characters:[{id:'owner',name:'Alexandria Montgomery'}]});root.naiCards={ovr:e=>e.rating,fitBattle:()=>{},lightCard:e=>{const c=new E('div');c.dataset.cardKind=e.testKind||'image';return c},battle:()=>new E('div')};
const context={document:{getElementById:()=>({shadowRoot:root}),createElement:t=>t==='canvas'?canvas():new E(t),createElementNS:(_,t)=>new E(t),fonts:{add(){}}},naiCardEditionAssets:pack,FontFace:class{load(){return Promise.resolve(this)}},ResizeObserver:class{observe(){}unobserve(){}},MutationObserver:class{observe(){}},queueMicrotask(){},localStorage:{getItem(){return null}},console};
vm.runInNewContext(fs.readFileSync('payload/userscript-2.9.15.ranks.txt','utf8'),context);vm.runInNewContext(source,context);
(async()=>{
 assert.equal(Object.keys(pack.editions).length,13);assert.equal(Object.keys(pack.ranks).length,7);assert.equal(root.naiCards.editionNames.length,13);
 const alphas={};for(const [tier,p]of Object.entries(pack.ranks)){
  const im=await loadImage(p),c=createCanvas(im.width,im.height),ctx=c.getContext('2d');ctx.drawImage(im,0,0);const a=ctx.getImageData(0,0,im.width,im.height).data;let l=im.width,t=im.height,r=0,b=0;
  for(let y=0;y<im.height;y++)for(let x=0;x<im.width;x++)if(a[(y*im.width+x)*4+3]>8){l=Math.min(l,x);t=Math.min(t,y);r=Math.max(r,x+1);b=Math.max(b,y+1)}
  alphas[tier]={bounds:[l,t,r,b],width:im.width,height:im.height};assert.deepEqual(pack.rankGeometry[tier].bounds,alphas[tier].bounds);
  const badge=root.naiRanks.badge(tier);assert.equal(badge.children[0].tag,'svg');assert.equal(badge.children[0].children[0].tag,'image');assert.equal(badge.children[0].children[0].attrs.href,p);
 }
 assert.equal(root.naiRanks.emblem('Placement').tag,'svg');
 let count=0;
 for(const [id,e]of Object.entries(pack.editions)){
  const im=await loadImage(e.art);assert.equal(im.width,1050);assert.equal(im.height,1500);assert.equal(parseFloat(e.style['--window-right'])-parseFloat(e.style['--window-left']),80);assert(Math.abs((parseFloat(e.style['--window-bottom'])-13)*15-1120)<1e-8);
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(e.art)).digest('hex'),pack.sha256[e.art]);
  for(const tier of Object.keys(pack.ranks))for(const position of [7,92])for(const rating_style of ['side','number']){
   const entry={edition_id:id,tier,position,rating:99,edition_settings:{rating_style}},card=root.naiCards.lightCard(entry,[],'owner',null,true),letters=card.querySelector('.naiEditionLetters'),rank=card.querySelector('.naiEditionRank');
   assert.equal(rank.src,pack.ranks[tier]);assert.equal(card.querySelector('.naiEditionFrame').src,e.art);
   const a=alphas[tier],[l,t,r,b]=a.bounds,w=parseFloat(rank.style.width)*10.5,h=parseFloat(rank.style.height)*15,x=parseFloat(rank.style.left)*10.5-w/2,y=parseFloat(rank.style.top)*15-h/2,z=e.guides.rank;
   assert(Math.abs(x+(l+r)/2*w/a.width-z.anchor[0])<1e-7);assert(Math.abs(y+(t+b)/2*h/a.height-z.anchor[1])<1e-7);
   const expected=createCanvas(letters.width,letters.height),ctx=expected.getContext('2d');ctx.setTransform(letters.width/1050,0,0,letters.height/1500,0,0);const metrics=G.lettering(ctx,e.refined.layout,e.guides,{name:'Alexandria Montgomery',rating:'99',placing:String(position),ratingStyle:'side',rankTier:e.rankColoredOverall?tier:null},R);
   assert(letters.toBuffer('image/png').equals(expected.toBuffer('image/png')),'Production lettering mismatch: '+id);
   assert.equal(letters.log.includes('OVR'),true);
   for(const [key,v]of Object.entries(metrics)){assert(v);assert(G.fits(e.guides[key],v.width,v.height));assert(Math.abs(v.x+v.width/2-e.guides[key].anchor[0])<.05);assert(Math.abs(v.y+v.height/2-e.guides[key].anchor[1])<.05)}
   count++;
  }
 }
 assert.deepEqual(pack.editions['ass-chrome'].guides.placing.anchor,[525.5,1426.5]);
 const duo=pack.duo;
 assert.equal(crypto.createHash('sha256').update(fs.readFileSync(duo.art)).digest('hex'),pack.sha256[duo.art]);
 const faces=['front','back'].map(side=>{
  const entry={duo_side:side,name:'Nocturne',edition_id:'signature',tier:'Gold',rating:95};
  const card=root.naiCards.lightCard(entry,[],'owner',null,true);
  assert.equal(card.dataset.edition,'duo');assert.equal(card.dataset.duoSide,side);
  assert.equal(card.querySelector('.naiEditionFrame').src,duo.art);
  const letters=card.querySelector('.naiEditionLetters');
  for(const name of ['NOCTURNE','ALEXANDRIA MONTGOMERY',side.toUpperCase()])assert(letters.log.includes(name));
  assert(!letters.log.includes('OVR'));
  return letters.toBuffer('image/png');
 });
 assert(!faces[0].equals(faces[1]));
 console.log(`Passed: ${count} production card renders; 13 native frames, seven actual alpha bounds, 7/92 whole-string centering, long names, OVR forced beside the number for both legacy preferences, fallback ranks and saved Ass anchor.`);
})().catch(e=>{console.error(e);process.exitCode=1});
