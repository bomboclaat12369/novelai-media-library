const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const catalog=JSON.parse(fs.readFileSync('assets/cards/editions/catalog.json'));
const extract=p=>{const s=fs.readFileSync(p,'utf8');return s.slice(s.indexOf('function layoutPhoto(im)'),s.indexOf('function apply(im,frame)'));};
const old=extract('payload/userscript-2.9.12.collection.txt'),current=extract('payload/userscript-2.9.13.collection.txt');
function render(code,window,frame,{width=420,size=[1080,1439],legacy,hidden}={}){
 const card={clientWidth:width,clientHeight:width*10/7},box={clientWidth:width*window.width,clientHeight:card.clientHeight*window.height,offsetLeft:width*window.left,offsetTop:card.clientHeight*window.top,closest:()=>card},style={};
 const im={parentElement:box,naturalWidth:size[0],naturalHeight:size[1],naiLegacyFramingReference:legacy,naiFramingReference:hidden,dataset:{},style:{setProperty:(k,v)=>style[k]=v}},state=new Map([[im,frame]]);
 vm.runInNewContext(code+'\nlayoutPhoto(im);',{im,frameState:state});
 const w=parseFloat(style.width)/100*box.clientWidth*frame.zoom,h=parseFloat(style.height)/100*box.clientHeight*frame.zoom;
 return [(box.offsetLeft+parseFloat(style.left)/100*box.clientWidth-w/2)/width,(box.offsetTop+parseFloat(style.top)/100*box.clientHeight-h/2)/card.clientHeight,w/width,h/card.clientHeight];
}
const near=(a,b)=>a.forEach((n,i)=>assert(Math.abs(n-b[i])<1e-9,`${n} != ${b[i]}`));
const modern={left:.1,top:.13,width:.8,height:1120/1500},base={left:.05,top:.038,width:.9,height:.84};
for(const id of Object.keys(catalog.editions).filter(id=>catalog.editions[id].legacyWindow)){
 const e=catalog.editions[id];assert(e.refined);assert.equal(parseFloat(e.style['--window-right'])-parseFloat(e.style['--window-left']),80);
 for(const width of [240,420,1050])for(const size of [[1080,1439],[2400,800]])for(const fit of ['contain','fill']){
  const custom={x:12,y:-9,zoom:1.7,fit},opts={width,size};
  const previous=render(old,e.legacyWindow,custom,opts);
  near(previous,render(current,modern,custom,{...opts,legacy:e.legacyWindow}));
  near(previous,render(current,modern,{...custom,reference:e.legacyWindow},opts));
  near(previous,render(current,base,custom,{...opts,legacy:e.legacyWindow,hidden:modern}));
  const reset={x:0,y:0,zoom:1,fit};
  near(render(old,modern,reset,opts),render(current,modern,reset,{...opts,legacy:e.legacyWindow}));
  const fresh={...custom,reference:modern};near(render(old,modern,custom,opts),render(current,modern,fresh,{...opts,legacy:e.legacyWindow}));
 }
}
console.log('Passed: all twelve previously published editions; portrait/landscape Fit/Fill; legacy and saved composition; reset/new geometry; display-only toggle; three card sizes.');
