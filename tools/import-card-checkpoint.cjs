// Import the approved 1050x1500 studio checkpoint without embedding preview photos.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{createRequire}=require('module');
const req=createRequire(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/package.json'),{createCanvas,loadImage}=req('@napi-rs/canvas');
const studio=path.resolve(process.argv[2]),R=require(path.join(studio,'frame-renderer.js')),G=require(path.join(studio,'guide-renderer.js'));
const m=JSON.parse(fs.readFileSync(path.join(studio,'baseline.json'))),g=JSON.parse(fs.readFileSync(path.join(studio,'layout-guides.json')));
const catalogPath='assets/cards/editions/catalog.json',pack=JSON.parse(fs.readFileSync(catalogPath)),dest='assets/cards/editions/refined';
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
(async()=>{
 fs.mkdirSync(dest,{recursive:true});G.validate(g,g);
 for(const [id,layout]of Object.entries(m.layouts)){
  const source=path.join(studio,m.sources[id].file),im=await loadImage(source),upper=m.preservedUpperSources?.[id]?await loadImage(path.join(studio,m.preservedUpperSources[id].file)):null,c=createCanvas(1050,1500);
  R.frame(c.getContext('2d'),im,layout,upper);const art=dest+'/'+id+'.png';fs.writeFileSync(art,c.toBuffer('image/png'));fs.copyFileSync(source,dest+'/'+id+'-source'+path.extname(source));
  if(upper)fs.copyFileSync(path.join(studio,m.preservedUpperSources[id].file),dest+'/'+id+'-original-upper.webp');
  const e=pack.editions[id]||{name:m.names[id],automatic:false,style:{'--mat':'#141414'}};
  if(pack.editions[id]&&!e.legacyWindow){const s=e.style,left=parseFloat(s['--window-left'])/100,top=parseFloat(s['--window-top'])/100;e.legacyWindow={left,top,width:parseFloat(s['--window-right'])/100-left,height:parseFloat(s['--window-bottom'])/100-top};}
  e.art=art;e.refined={sourceWidth:im.width,sourceHeight:im.height,layout};e.guides=g.editions[id].zones;e.layout={};
  for(const name of ['rating','name','placing']){const z=e.guides[name];e.layout[name]=[z.anchor[0]/10.5,z.anchor[1]/15,z.fit[0]/10.5,z.fit[1]/15];}
  const z=e.guides.rank;e.rankDefaultFit={left:z.anchor[0]/10.5,top:z.anchor[1]/15,width:z.fit[0]/10.5,height:z.fit[1]/15};e.rankFits={};
  for(const [tier,geometry]of Object.entries(m.rankGeometry)){const q=G.rank(geometry,z,R);e.rankFits[tier]={left:(q.x+q.width/2)/10.5,top:(q.y+q.height/2)/15,width:q.width/10.5,height:q.height/15};}
  Object.assign(e.style,{'--window-left':'10%','--window-right':'90%','--window-top':'13%','--window-bottom':String(1315/15)+'%','--metal-light':layout.palette[0],'--metal-mid':layout.palette[1],'--metal-low':layout.palette[2]});
  pack.editions[id]=e;pack.sha256[art]=sha(art);
 }
 pack.ranks={};pack.rankGeometry=m.rankGeometry;
 for(const tier of Object.keys(m.rankGeometry)){const p='assets/cards/editions/rank-'+tier.toLowerCase()+'.webp';fs.copyFileSync(path.join(studio,'assets/ranks',tier+'.webp'),p);pack.ranks[tier]=p;pack.sha256[p]=sha(p);}
 for(const f of ['baseline.json','layout-guides.json','frame-renderer.js','guide-renderer.js'])fs.copyFileSync(path.join(studio,f),dest+'/'+f);
 // Keep the production's existing number-only rating preference alongside studio OVR groups.
 const guidePath=dest+'/guide-renderer.js';let guide=fs.readFileSync(guidePath,'utf8');
 guide=guide.replace('    const s=fittingScale(z,dims),d=dims(s),left=z.anchor[0]-d.width/2;',"    if(state.ratingStyle==='number'){\n      result.rating=label(ctx,number,z,font,rp,R);\n    }else{\n    const s=fittingScale(z,dims),d=dims(s),left=z.anchor[0]-d.width/2;").replace('    result.name=label(ctx,','    }\n    result.name=label(ctx,');fs.writeFileSync(guidePath,guide);
 pack.version=3;pack.approved_editions=Object.keys(pack.editions);fs.writeFileSync(catalogPath,JSON.stringify(pack,null,2)+'\n');
 console.log('Imported '+pack.approved_editions.length+' full-resolution frames and '+Object.keys(pack.ranks).length+' ranks; no photos included.');
})().catch(e=>{console.error(e);process.exitCode=1});
