const GuideRenderer = (() => {
  function distance(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy||1)));return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);}
  function inside(p,poly){let yes=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])yes=!yes;}return yes;}
  function fits(zone,w,h){
    if(w>zone.fit[0]+.01||h>zone.fit[1]+.01)return false;
    const [cx,cy]=zone.anchor,pts=[];
    for(let i=0;i<=10;i++){const t=i/10;pts.push([cx-w/2+w*t,cy-h/2],[cx-w/2+w*t,cy+h/2],[cx-w/2,cy-h/2+h*t],[cx+w/2,cy-h/2+h*t]);}
    return pts.every(p=>inside(p,zone.outline)&&zone.outline.every((a,i)=>distance(p,a,zone.outline[(i+1)%zone.outline.length])>=zone.padding-.02));
  }
  function measure(ctx,text,size,font){ctx.font='700 '+size+'px '+font;const m=ctx.measureText(text);return {width:m.actualBoundingBoxLeft+m.actualBoundingBoxRight,height:m.actualBoundingBoxAscent+m.actualBoundingBoxDescent};}
  function fittingScale(zone,dimensions){let lo=0,hi=1;for(let i=0;i<25;i++){const mid=(lo+hi)/2,q=dimensions(mid);if(fits(zone,q.width,q.height))lo=mid;else hi=mid;}return lo;}
  function label(ctx,text,z,font,palette,R){
    const scale=fittingScale(z,s=>measure(ctx,text,z.maxFontSize*s,font));
    if(scale<.001)return null;
    const m=measure(ctx,text,z.maxFontSize*scale,font);
    return R.centered(ctx,text,{x:z.anchor[0],y:z.anchor[1],width:m.width+.001,height:m.height+.001},z.maxFontSize*scale,font,palette);
  }
  function lettering(ctx,layout,zones,state,R){
    const p=layout.palette,rp=layout.ratingDark?['#684734','#3e251e','#21130e']:p,z=zones.rating,result={};
    const number=String(state.rating||'0'),font='EditionNumeralsV2';
    function dims(s){const n=measure(ctx,number,z.maxFontSize*s,font),l=measure(ctx,'OVR',z.maxFontSize*32/88*s,font);return {n,l,width:n.width+l.width+10*s,height:Math.max(n.height,l.height),gap:10*s};}
    if(state.ratingStyle==='number'){
      result.rating=label(ctx,number,z,font,rp,R);
    }else{
    const s=fittingScale(z,dims),d=dims(s),left=z.anchor[0]-d.width/2;
    if(s>.001){
      const n=R.centered(ctx,number,{x:left+d.n.width/2,y:z.anchor[1],width:d.n.width+.001,height:d.n.height+.001},z.maxFontSize*s,font,rp);
      const l=R.centered(ctx,'OVR',{x:left+d.n.width+d.gap+d.l.width/2,y:z.anchor[1]+(d.n.height-d.l.height)/2,width:d.l.width+.001,height:d.l.height+.001},z.maxFontSize*32/88*s,font,rp);
      result.rating={x:n.x,y:Math.min(n.y,l.y),width:l.x+l.width-n.x,height:Math.max(n.y+n.height,l.y+l.height)-Math.min(n.y,l.y),box:{x:z.anchor[0],y:z.anchor[1]}};
    }
    }
    result.name=label(ctx,(state.name.trim()||'Untitled').toUpperCase(),zones.name,'EditionDisplayV2',p,R);
    result.placing=label(ctx,String(state.placing||'0'),zones.placing,'EditionDisplayV2',p,R);
    return result;
  }
  function rank(source,z,R){return R.rankRect(source,{x:z.anchor[0],y:z.anchor[1],width:z.fit[0],height:z.fit[1]},1+z.overflowPercent/100);}
  function simple(poly){
    const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
    for(let i=0;i<poly.length;i++)for(let j=i+1;j<poly.length;j++){
      if(j===i+1||(i===0&&j===poly.length-1))continue;
      const a=poly[i],b=poly[(i+1)%poly.length],c=poly[j],d=poly[(j+1)%poly.length];
      if(cross(a,b,c)*cross(a,b,d)<0&&cross(c,d,a)*cross(c,d,b)<0)return false;
    }
    return poly.every((p,i)=>Math.hypot(p[0]-poly[(i+1)%poly.length][0],p[1]-poly[(i+1)%poly.length][1])>.1);
  }
  function validate(doc,baseline){
    const finite=v=>typeof v==='number'&&Number.isFinite(v);
    const point=p=>Array.isArray(p)&&p.length===2&&p.every(finite)&&p[0]>=0&&p[0]<=1050&&p[1]>=0&&p[1]<=1500;
    if(!doc||doc.schemaVersion!==1||doc.canvas?.width!==1050||doc.canvas?.height!==1500||!doc.editions)throw Error('Use a 1050 × 1500 layout-guides export.');
    if(Object.keys(doc.editions).length!==Object.keys(baseline.editions).length)throw Error('The file must contain all '+Object.keys(baseline.editions).length+' editions.');
    for(const [key,original]of Object.entries(baseline.editions)){
      const e=doc.editions[key];if(e?.frameSha256!==original.frameSha256)throw Error('Artwork does not match: '+key);
      if(original.headerSha256&&e.headerSha256!==original.headerSha256)throw Error('Original upper artwork does not match: '+key);
      for(const f of ['rating','rank','name','placing']){const z=e.zones?.[f];
        if(!z||!point(z.anchor)||!Array.isArray(z.outline)||z.outline.length<3||z.outline.length>64||!z.outline.every(point)||!Array.isArray(z.fit)||z.fit.length!==2||!z.fit.every(v=>finite(v)&&v>=1&&v<=1050)||!finite(z.padding)||z.padding<0||z.padding>30||!finite(z.maxFontSize)||z.maxFontSize<0||z.maxFontSize>160||!finite(z.overflowPercent)||z.overflowPercent<0||z.overflowPercent>50)throw Error('Invalid guide: '+key+' / '+f);
        if(!simple(z.outline))throw Error('Outline edges must not cross or collapse: '+key+' / '+f);
        if(f!=='rank'&&(z.maxFontSize<1||!fits(z,1,1)))throw Error('Center must sit inside the usable plaque: '+key+' / '+f);
        if(f==='rank'&&!inside(z.anchor,z.outline))throw Error('Rank center must sit inside its plaque: '+key);
      }
    }
    return true;
  }
  return {inside,fits,distance,measure,fittingScale,label,lettering,rank,validate};
})();
if(typeof module!=='undefined')module.exports=GuideRenderer;
