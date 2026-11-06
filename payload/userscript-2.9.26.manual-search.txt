// Metadata search is independent of visual-model availability and ranking.
(() => {
  const root=document.getElementById('nai-media-host')?.shadowRoot;if(!root)return;
  const el=(tag,text)=>Object.assign(document.createElement(tag),text===undefined?{}:{textContent:text});
  root.naiManualSearch=async({query,onChoose}={})=>{
    const wrap=el('div'),dialog=el('div');wrap.className='naiMatchWrap naiManualSearchWrap';dialog.className='naiMatchDialog';dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-label','Manual Set and image search');wrap.append(dialog);root.append(wrap);
    const head=el('div'),close=el('button','Close'),status=el('p'),form=el('form'),search=el('input'),kind=el('select'),category=el('select'),placement=el('select'),run=el('button','Search'),grid=el('div'),pages=el('div');
    head.className='naiMatchHead';head.append(el('strong','Search Sets or images'),close);dialog.append(head,el('p','Search names, aliases, colors, notes or categories. No automatic matching is required.'));
    const controls=[['sets','Sets'],['images','Images']];for(const [v,t] of controls){const o=el('option',t);o.value=v;kind.append(o);}kind.setAttribute('aria-label','Search type');
    search.type='search';search.placeholder='Name, category or description…';search.setAttribute('aria-label','Manual search');category.setAttribute('aria-label','Search category');placement.setAttribute('aria-label','Search placement');
    for(const [v,t] of [['all','All locations'],['main','Main / normal Sets'],['purgatory','Purgatory'],['review','Review'],['unassigned','Images without a Set']]){const o=el('option',t);o.value=v;placement.append(o);}
    form.style.cssText='display:flex;gap:8px;flex-wrap:wrap';search.style.cssText='flex:1;min-width:180px;padding:9px';form.append(kind,search,category,placement,run);dialog.append(form,status,grid,pages);grid.className='naiMatchGrid';
    let offset=0,serial=0,closed=false,choosing=false;const selected=new Set();const compose=el('div'),name=el('input'),create=el('button','Create Set from selected images');name.placeholder='New Set name';name.setAttribute('aria-label','Manual Set name');compose.className='naiMatchFoot';compose.append(name,create);dialog.append(compose);compose.hidden=true;
    const finish=()=>{closed=true;serial++;wrap.remove();};close.onclick=finish;wrap.onclick=e=>{if(e.target===wrap)finish();};wrap.onkeydown=e=>{if(e.key==='Escape'){e.stopPropagation();finish();}};
    function picture(mid,title){const img=el('img');img.alt=title;img.style.cssText='width:100%;height:205px;object-fit:contain;cursor:zoom-in';root.naiLoadThumbnail(mid,img);img.onclick=async()=>{const zoom=el('div'),large=el('img');zoom.className='naiMatchZoom';zoom.append(large);wrap.append(zoom);let url;zoom.onclick=()=>{zoom.remove();if(url)URL.revokeObjectURL(url);};try{const blob=await root.naiOutfitOriginal(mid);if(zoom.isConnected){url=URL.createObjectURL(blob);large.src=url;}}catch(e){zoom.append(el('p',e.message));}};return img;}
    async function choose(id){if(choosing)return;choosing=true;run.disabled=true;try{await onChoose(id,query);finish();}catch(e){status.textContent=e.message;}finally{run.disabled=false;choosing=false;}}
    async function load(reset=false){const seq=++serial;if(reset){offset=0;selected.clear();}status.textContent='Searching…';run.disabled=true;
      try{const result=await root.naiOutfitRequest('/api/sets/manual-search',{character_id:query.character_id,kind:kind.value,query:search.value,category:category.value,placement:placement.value,offset});if(closed||seq!==serial)return;
        const old=category.value;category.replaceChildren();for(const [v,t] of [['','All categories'],['__none','Uncategorized'],...result.categories.map(c=>[c.id,c.name])]){const o=el('option',t);o.value=v;category.append(o);}category.value=old||'';
        status.textContent=result.total+' results · '+selected.size+' selected';grid.replaceChildren();compose.hidden=kind.value!=='images';create.disabled=!selected.size;
        for(const row of result.rows){const card=el('article');card.className='naiMatchCard';card.dataset.id=row.id;card.append(el('h3',row.name),el('p',row.placement+(row.sets.length?' · '+row.sets.map(s=>s.name).join(', '):'')));if(row.cover)card.append(picture(row.cover,row.name));
          if(kind.value==='sets'){const b=el('button','Use this Set');b.onclick=()=>choose(row.id);card.append(b);}else if(row.sets.length){for(const set of row.sets){const b=el('button','Use '+set.name+(set.in_purgatory?' · Purgatory':''));b.onclick=()=>choose(set.id);card.append(b);}}else if(row.id!==query.id){const label=el('label'),box=el('input');box.type='checkbox';box.checked=selected.has(row.id);box.setAttribute('aria-label','Select '+row.name);box.onchange=()=>{if(box.checked)selected.add(row.id);else selected.delete(row.id);create.disabled=!selected.size;status.textContent=result.total+' results · '+selected.size+' selected';};label.append(box,el('span',' Include in new Set'));card.append(label);}grid.append(card);}
        pages.replaceChildren();for(const [text,delta] of [['Previous',-60],['Next',60]]){const b=el('button',text);b.disabled=offset+delta<0||offset+delta>=result.total;b.onclick=()=>{offset+=delta;load();};pages.append(b);}
      }catch(e){if(seq===serial)status.textContent=e.message;}finally{if(seq===serial)run.disabled=false;}
    }
    create.onclick=async()=>{if(!selected.size)return;if(!name.value.trim()){name.focus();return;}create.disabled=true;try{const ids=[...selected];const lib=await root.naiOutfitRequest('/api/library');const current=lib.media.find(m=>m.id===query.id);const membership=lib.sets.find(s=>s.media_ids.includes(query.id));
      if(current&&!membership)ids.push(query.id);
      const saved=await root.naiOutfitRequest('/api/sets/manual-group',{character_id:query.character_id,media_ids:ids,name:name.value});await root.naiOutfitRefreshLibrary();await onChoose(saved.id,query);finish();
    }catch(e){status.textContent=e.message;create.disabled=false;}};
    form.onsubmit=e=>{e.preventDefault();load(true);};kind.onchange=()=>{category.value='';placement.value='all';load(true);};category.onchange=placement.onchange=()=>load(true);await load();search.focus();
  };
})();
