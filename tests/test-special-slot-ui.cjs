const assert=require('assert/strict'),fs=require('fs'),{spawn}=require('child_process');
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
(async()=>{
 const server=spawn('python3',['tests/serve_battles_fixture.py'],{env:{...process.env,NAI_RANKS_DEMO:'1'}});let browser,stderr='';server.stderr.on('data',b=>stderr+=b);
 try{
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('exit',c=>reject(Error(stderr+c)))});
  browser=await chromium.launch({executablePath:process.env.NAI_CHROMIUM||'/tmp/chromium',headless:true,args:['--no-sandbox','--disable-gpu']});
  const page=await browser.newPage({viewport:{width:1500,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765/library/');await page.getByText('Local library connected',{exact:true}).waitFor();
  const photo=process.env.NAI_CARD_REVIEW_PHOTO?'data:image/webp;base64,'+fs.readFileSync(process.env.NAI_CARD_REVIEW_PHOTO).toString('base64'):null;
  const result=await page.evaluate(async photo=>{
   const root=document.getElementById('nai-media-host').shadowRoot,cards=root.naiCards,pack=naiCardEditionAssets,{guide:G,refined:R,ready}=cards.frameTypography;
   await ready;if(!document.fonts.check('700 80px EditionRankNumeralsV1'))throw Error('Card fonts not ready: '+JSON.stringify({ready:await ready,faces:[...document.fonts].map(f=>({family:f.family,status:f.status,weight:f.weight}))}));const owner=root.naiGetLibrary().characters[0].id;await cards.load(owner);
   const panel=document.createElement('div');panel.id='special-slot-test';panel.style.cssText='position:fixed;inset:0;overflow:auto;z-index:2147483647;background:#101722;padding:20px;display:grid;grid-template-columns:repeat(4,320px);gap:22px;align-content:start;justify-content:center';root.append(panel);
   const source=document.createElement('canvas');source.width=840;source.height=1120;source.getContext('2d').fillStyle='#527e8d';source.getContext('2d').fillRect(0,0,840,1120);
   const uri=photo||source.toDataURL(),rows=Array.from({length:100},(_,i)=>({id:'sample'+i,rating:2000-i*10,played:20,provisional:false,rating_status:'Established'})),checks=[];
   let index=0;
   for(const[id,e]of Object.entries(pack.editions)){
    const im=new Image();im.src=uri;await im.decode();const entry={...rows[0],id:'sample0',images:['sample0'],name:'Sample',edition_id:id,tier:'Diamond',position:index%2?92:7};
    const card=cards.lightCard(entry,rows,owner,im,true),wrap=document.createElement('div'),label=document.createElement('div');label.textContent=e.name;label.style='text-align:center;margin-bottom:8px;color:white';wrap.append(label,card);panel.append(wrap);card.style.cssText+=';width:320px!important;height:'+320/.7+'px!important';cards.applyFrame(im,{});
    await Promise.all([...card.querySelectorAll('img')].map(i=>i.decode()));await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const b=card.getBoundingClientRect(),w=card.querySelector('.naiCardPhotoWindow').getBoundingClientRect(),rank=card.querySelector('.naiEditionRank').getBoundingClientRect(),geo=pack.rankGeometry.Diamond;
    const [l,t,r,bt]=geo.bounds,z=e.guides.rank;
    checks.push({id,ratio:w.width/w.height,rankCenter:[(rank.x-b.x+(l+r)/2*rank.width/geo.width)/b.width*1050,(rank.y-b.y+(t+bt)/2*rank.height/geo.height)/b.height*1500],anchor:z.anchor});
    const ctx=document.createElement('canvas').getContext('2d');
    for(let overall=0;overall<=99;overall++){
     const m=G.lettering(ctx,e.refined.layout,e.guides,{name:'Alexandria Montgomery',rating:String(overall),placing:overall%2?'92':'7',ratingStyle:'side',rankTier:e.rankColoredOverall?'Diamond':null},R);
     for(const[k,v]of Object.entries(m))if(!v||!G.fits(e.guides[k],v.width,v.height)||Math.abs(v.x+v.width/2-e.guides[k].anchor[0])>.02||Math.abs(v.y+v.height/2-e.guides[k].anchor[1])>.02)throw Error(id+' '+k+' '+overall);
    }
    for(const[tier,geometry]of Object.entries(pack.rankGeometry)){
     const q=G.rank(geometry,z,R),ref=G.rank(geometry,pack.editions['ass-chrome'].guides.rank,R);
     if(id!=='pregnant-orchid'&&Math.abs(q.visible.height-ref.visible.height)>.02)throw Error(id+' emblem scale '+tier);
    }
    index++;
   }
   return checks;
  },photo);
  for(const c of result){assert(Math.abs(c.ratio-.75)<.001,c.id);c.rankCenter.forEach((v,i)=>assert(Math.abs(v-c.anchor[i])<.15,c.id+' emblem center'));}
  await page.screenshot({path:'/tmp/special-slots-production-top.png'});
  await page.locator('#special-slot-test').evaluate(e=>e.scrollTop=560);await page.screenshot({path:'/tmp/special-slots-production-middle.png'});
  await page.locator('#special-slot-test').evaluate(e=>e.scrollTop=1120);await page.screenshot({path:'/tmp/special-slots-production-bottom.png'});
  assert.deepEqual(errors,[]);console.log('Passed: all 13 production cards, 0–99 OVR and 7/92 placement fits/centering, long names, all seven emblem scales, 3:4 openings, browser rendering without errors.');
 }finally{await browser?.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
