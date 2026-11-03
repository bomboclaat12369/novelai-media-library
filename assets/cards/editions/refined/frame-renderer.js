const RefinedRenderer = (() => {
  const geometry = { width:1050, height:1500, window:{x:105,y:195,width:840,height:1120} };
  function map(value, source, dest) {
    let i = value < source[1] ? 0 : value < source[2] ? 1 : 2;
    return dest[i] + (value-source[i])*(dest[i+1]-dest[i])/(source[i+1]-source[i]);
  }
  function axes(image, layout) {
    const w=geometry.window,drop=layout.headerDrop||0;
    return {sx:[0,layout.opening[0],layout.opening[2],image.width], sy:[0,layout.opening[1],layout.opening[3],image.height], dx:[0,w.x,w.x+w.width,1050],dy:[drop,w.y+drop,w.y+w.height,1500]};
  }
  function frame(ctx,image,layout,preservedUpper) {
    if(layout.renderMode==='preserved-upper'){
      if(!preservedUpper)throw Error('Original upper-frame artwork is required.');
      const cut=layout.footerStart;
      ctx.save();ctx.beginPath();ctx.rect(0,0,1050,cut);ctx.clip();ctx.drawImage(preservedUpper,0,0,1050,1500);ctx.restore();
      ctx.save();ctx.beginPath();ctx.rect(0,cut,1050,1500-cut);ctx.clip();ctx.drawImage(image,0,0,1050,1500);ctx.restore();
      return;
    }
    const {sx,sy,dx,dy}=axes(image,layout);
    for(let row=0;row<3;row++) for(let col=0;col<3;col++) {
      ctx.drawImage(image,sx[col],sy[row],sx[col+1]-sx[col],sy[row+1]-sy[row],dx[col],dy[row],dx[col+1]-dx[col],dy[row+1]-dy[row]);
    }
  }
  function box(sourceBox,image,layout) {
    const {sx,sy,dx,dy}=axes(image,layout),[x,y,w,h]=sourceBox;
    const left=map(x-w/2,sx,dx),right=map(x+w/2,sx,dx),top=map(y-h/2,sy,dy),bottom=map(y+h/2,sy,dy);
    return {x:(left+right)/2,y:(top+bottom)/2,width:right-left,height:bottom-top};
  }
  function centered(ctx,text,b,size,font,palette) {
    ctx.save();ctx.font='700 '+size+'px '+font;
    let m=ctx.measureText(text),iw=m.actualBoundingBoxLeft+m.actualBoundingBoxRight,ih=m.actualBoundingBoxAscent+m.actualBoundingBoxDescent;
    size*=Math.min(1,b.width/Math.max(iw,1),b.height/Math.max(ih,1));
    ctx.font='700 '+size+'px '+font;m=ctx.measureText(text);
    for(let pass=0;pass<6;pass++){
      const mw=m.actualBoundingBoxLeft+m.actualBoundingBoxRight,mh=m.actualBoundingBoxAscent+m.actualBoundingBoxDescent;
      if(mw<=b.width&&mh<=b.height)break;
      size*=Math.min(b.width/Math.max(1,mw),b.height/Math.max(1,mh))*.99;
      ctx.font='700 '+size+'px '+font;m=ctx.measureText(text);
    }
    const asc=m.actualBoundingBoxAscent,desc=m.actualBoundingBoxDescent;
    const x=b.x-(m.actualBoundingBoxRight-m.actualBoundingBoxLeft)/2,y=b.y+(asc-desc)/2;
    const g=ctx.createLinearGradient(0,b.y-b.height/2,0,b.y+b.height/2);
    g.addColorStop(0,palette[0]);g.addColorStop(.42,palette[1]);g.addColorStop(.53,palette[0]);g.addColorStop(1,palette[1]);
    ctx.fillStyle=g;ctx.strokeStyle=palette[2];ctx.lineWidth=palette[3]||.9;ctx.shadowColor='#000b';ctx.shadowBlur=2;ctx.shadowOffsetY=1.8;
    ctx.strokeText(text,x,y);ctx.fillText(text,x,y);ctx.restore();
    return {x:x-m.actualBoundingBoxLeft,y:y-asc,width:m.actualBoundingBoxLeft+m.actualBoundingBoxRight,height:asc+desc,box:b};
  }
  // Fit the visible emblem, rather than its transparent source canvas.
  // Keep the full source image intact and preserve its aspect ratio.
  function rankRect(source,b,emblemScale=1) {
    b={...b,width:b.width*emblemScale,height:b.height*emblemScale};
    const [left,top,right,bottom]=source.bounds;
    const scale=Math.min(b.width/(right-left),b.height/(bottom-top));
    const width=(right-left)*scale,height=(bottom-top)*scale;
    return {x:b.x-width/2-left*scale,y:b.y-height/2-top*scale,
      width:source.width*scale,height:source.height*scale,
      visible:{x:b.x-width/2,y:b.y-height/2,width,height},box:b};
  }
  function lettering(ctx,image,layout,state) {
    const p=layout.palette,rp=layout.ratingDark?['#684734','#3e251e','#21130e']:p, result={};
    const rating=box(layout.rating,image,layout);
    if(state.ratingStyle==='side'){
      const measure=(text,size)=>{ctx.font='700 '+size+'px EditionNumeralsV2';const m=ctx.measureText(text);return {width:m.actualBoundingBoxLeft+m.actualBoundingBoxRight,height:m.actualBoundingBoxAscent+m.actualBoundingBoxDescent};};
      let ns=88,ls=32,gap=10,n=measure(state.rating,ns),l=measure('OVR',ls);
      const scale=Math.min(1,rating.width/(n.width+gap+l.width),rating.height/Math.max(n.height,l.height));
      ns*=scale;ls*=scale;gap*=scale;n=measure(state.rating,ns);l=measure('OVR',ls);
      for(let pass=0;pass<6;pass++){
        if(n.width+gap+l.width<=rating.width&&Math.max(n.height,l.height)<=rating.height)break;
        const correction=Math.min(rating.width/(n.width+gap+l.width),rating.height/Math.max(n.height,l.height))*.99;
        ns*=correction;ls*=correction;gap*=correction;n=measure(state.rating,ns);l=measure('OVR',ls);
      }
      const left=rating.x-(n.width+gap+l.width)/2;
      const rn=centered(ctx,state.rating,{x:left+n.width/2,y:rating.y,width:n.width,height:n.height},ns,'EditionNumeralsV2',rp);
      const rl=centered(ctx,'OVR',{x:left+n.width+gap+l.width/2,y:rating.y+(n.height-l.height)/2,width:l.width,height:l.height},ls,'EditionNumeralsV2',rp);
      const x=Math.min(rn.x,rl.x),y=Math.min(rn.y,rl.y);
      result.rating={x,y,width:Math.max(rn.x+rn.width,rl.x+rl.width)-x,height:Math.max(rn.y+rn.height,rl.y+rl.height)-y,box:rating};
    }else result.rating=centered(ctx,state.rating,rating,88,'EditionNumeralsV2',rp);
    result.name=centered(ctx,(state.name.trim()||'Untitled').toUpperCase(),box(layout.name,image,layout),72,'EditionDisplayV2',p);
    result.placing=centered(ctx,String(state.placing),box(layout.placing,image,layout),60,'EditionDisplayV2',p);
    return result;
  }
  function photoRect(width,height,framing) {
    const w=geometry.window,scale=(framing.fit==='fill'?Math.max(w.width/width,w.height/height):Math.min(w.width/width,w.height/height))*framing.zoom;
    const dw=width*scale,dh=height*scale;
    return {x:w.x+(w.width-dw)/2+w.width*framing.x/100,y:w.y+(w.height-dh)/2+w.height*framing.y/100,width:dw,height:dh};
  }
  return {geometry,map,axes,frame,box,centered,lettering,photoRect,rankRect};
})();
if(typeof module!=='undefined')module.exports=RefinedRenderer;
