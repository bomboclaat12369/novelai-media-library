const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const repo=path.resolve(__dirname,'..');
const config=JSON.parse(fs.readFileSync(path.join(repo,'release-standalone.json'),'utf8'));
const assembled=config.parts.map(p=>fs.readFileSync(path.join(repo,p),'utf8')).join('');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function waitFor(fn,errors=[],ms=2000){const start=Date.now();while(!fn()){if(errors.length)throw errors[0];if(Date.now()-start>ms)throw Error('UI did not become ready');await delay(10)}return fn()}

async function fixture({media = [], configure = null} = {}) {
  const errors = [], writes = [], revoked = [], history = [], queue = [], uploads=new Map();
  let queueState={}, updateVersion=config.version;
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => { if (!e.message.includes('Not implemented:')) errors.push(e); });
  const dom = new JSDOM('<!doctype html><html><head></head><body><main>NovelAI fixture</main></body></html>', {
    url:'https://novelai.net/stories', runScripts:'outside-only', pretendToBeVisual:true, virtualConsole:vc,
  });
  const w = dom.window;
  w.naiCardEditionAssets=JSON.parse(fs.readFileSync(path.join(repo,'assets/cards/editions/catalog.json'),'utf8'));
  w.FontFace=class{load(){return Promise.resolve(this)}};w.document.fonts={add(){}};
  Object.defineProperty(w.crypto,'subtle',{value:require('node:crypto').webcrypto.subtle});
  w.Blob.prototype.arrayBuffer=function(){return new Promise((resolve,reject)=>{const r=new w.FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsArrayBuffer(this)})};
  const library = {characters:[{id:'character',name:'Fixture',categories:[{id:'dress',name:'Dress'}]}], media, sets:[]};
  let blobIndex = 0, frames = 0, mediaIndex=0;
  w.URL.createObjectURL = () => `blob:https://novelai.net/${++blobIndex}`;
  w.URL.revokeObjectURL = url => revoked.push(url);
  w.IntersectionObserver = class { constructor(fn){this.fn=fn} observe(target){queueMicrotask(()=>{if(target.isConnected)this.fn([{target,isIntersecting:true}])})} unobserve(){} disconnect(){} };
  w.HTMLImageElement.prototype.decode=async function(){};
  w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  const raf = w.requestAnimationFrame.bind(w);
  w.requestAnimationFrame = fn => raf(t => { frames++; fn(t); });
  w.alert = message => errors.push(new Error(String(message)));
  w.confirm = () => true;
  w.prompt = () => 'New category';
  w.fetch = async () => { throw new Error('Unexpected native fetch'); };
  w.GM_xmlhttpRequest = options => {
    const url = new URL(options.url), route = url.pathname;
    const method = options.method || 'GET';
    let canceled = false;
    setTimeout(() => {
      if (canceled || !w.document) return; // Closed DOM: abort outstanding fake network callbacks.
      try {
        let value, status = 200;
        if (method !== 'GET' && !['/api/standalone/check','/api/battles/summary','/api/collection/state'].includes(route)) writes.push({route,method});
        if (route === '/api/health') value = {ok:true,version:8,mixed_collections:true,replacement_flags:true,featured_flags:true,undo_history:true,persistent_rapid_review:true,chunked_uploads:true,video_set_only:true};
        else if (route === '/api/library') value = library;
        else if(route==='/api/standalone/check')value={version:updateVersion};
        else if(route==='/api/battles/summary')value={entries:[],votes:0,revision:'fixture'};
        else if(route==='/api/collection/state')value={collection:{captain_id:null,frames:{},name:'Fixture'},name: 'Fixture'};
        else if(route==='/api/rapid-review' && method==='GET')value={items:queue,state:queueState};
        else if(route==='/api/rapid-review/state'){queueState={...queueState,...JSON.parse(options.data)};value={ok:true};}
        else if(route==='/api/rapid-review/resolve'){
          const b=JSON.parse(options.data),ids=b.media_ids,items=queue.filter(m=>ids.includes(m.id));
          for(const item of items){const choice=queueState.choices?.[item.id]||{};Object.assign(item,choice);item.in_all=false;item.in_review=b.action==='review';item.in_purgatory=b.action==='purgatory';if(b.action!=='discard')library.media.push(item);}
          if(b.action==='set'||b.action==='new_set'){
            let g=library.sets.find(g=>g.id===b.set_id);
            if(!g){g={id:'set'+(library.sets.length+1),character_id:'character',name:b.name,media_ids:[],colors:b.colors||[]};library.sets.push(g);}
            g.media_ids=[...new Set([...g.media_ids,...ids])];
          }
          queue.splice(0,queue.length,...queue.filter(m=>!ids.includes(m.id)));value={resolved_ids:ids,duplicate_ids:[]};
        }
        else if(route.startsWith('/api/import/chunked/')){
          const key=route.split('/')[4],action=route.split('/')[5],b=JSON.parse(options.data||'{}');
          if(action==='start'){uploads.set(key,{...b,offset:0});value={offset:0};}
          else if(action==='chunk'){const u=uploads.get(key);u.offset+=Buffer.from(b.data,'base64').length;value={offset:u.offset};}
          else if(action==='finish'){const u=uploads.get(key),item={id:'saved'+(++mediaIndex),character_id:u.character_id,original_name:u.filename,media_type:u.content_type.startsWith('video/')?'video':'image',categories:(u.categories||[]).filter(id=>{const c=library.characters[0].categories.find(c=>c.id===id);return (c?.media_type||'image')===(u.content_type.startsWith('video/')?'video':'image')}),in_all:false,in_review:false};(u.pending_review?queue:library.media).push(item);value={item,duplicate:false};}
          else {uploads.delete(key);value={ok:true};}
        }
        else if (route === '/api/undo' && method === 'GET') value = {entries:[...history].reverse(),limit:20};
        else if (route === '/api/undo' && method === 'POST') {
          const entry=history.pop();
          if (!entry || entry.id!==JSON.parse(options.data).entry_id) throw new Error('Stale history request');
          const item=library.media.find(m=>m.id===entry.media_id);
          if (item) Object.assign(item,entry.before);
          else library.media.splice(entry.index,0,entry.before);
          value={ok:true,item:entry.before};
        }
        else if (route.startsWith('/api/characters/') && method === 'DELETE') {
          const id = route.split('/')[3];
          library.characters = library.characters.filter(c => c.id !== id);
          library.sets = library.sets.filter(s => s.character_id !== id);
          value = {ok:true};
        }
        else if (route.startsWith('/api/media/') && method === 'DELETE') {
          const id = route.split('/')[3];
          const index=library.media.findIndex(m=>m.id===id);
          const item=library.media[index];
          history.push({id:'undo-'+history.length,label:'Delete media',media_id:id,filename:item.original_name,index,before:JSON.parse(JSON.stringify(item))});
          library.media = library.media.filter(m => m.id !== id);
          value = {ok:true};
        } else if (route.startsWith('/api/media/') && method === 'GET' && route.endsWith('/quality')) {
          value = {media_id:route.split('/')[3],media_type:'image',file_bytes:2048,width:1536,height:2048};
        }
        else if (route === '/api/import/file') {
          const file = options.data.get('file');
          const item = {id:`saved${library.media.length+1}`,character_id:'character',original_name:file.name,media_type:'image',categories:[],in_review:false};
          library.media.push(item); value = {item,duplicate:false};
        } else if (route.startsWith('/api/media/') && method === 'POST' && route.endsWith('/replace')) {
          const id = route.split('/')[3];
          const item = library.media.find(m => m.id === id);
          if (!item) throw new Error(`Replacing unknown media ${id}`);
          const file = options.data.get('file');
          Object.assign(item, {original_name:file.name, thumb_rel:null}); value = item;
        } else if (route.startsWith('/api/media/') && method === 'POST') {
          const id = route.split('/')[3], action = route.split('/')[4];
          const item = library.media.find(m => m.id === id)||queue.find(m=>m.id===id);
          if (!item) throw new Error(`Saving unknown media ${id}`);
          const body = JSON.parse(options.data);
          history.push({id:'undo-'+history.length,label:'Change '+action,media_id:id,filename:item.original_name,before:JSON.parse(JSON.stringify(item))});
          if(action==='clear-holding')Object.assign(body,{in_review:false,in_purgatory:false,in_all:true});
          Object.assign(item, action === 'crop' ? {crop_top:body.top,crop_bottom:body.bottom} : body); value = item;
        } else if (route === '/api/sets' && method === 'POST') {
          value = {id:`set${library.sets.length+1}`,...JSON.parse(options.data)}; library.sets.push(value);
        } else if (route.startsWith('/api/sets/') && method === 'POST') {
          value = library.sets.find(s => s.id === route.split('/')[3]);
          const body=JSON.parse(options.data);
          if(body.add_media_ids){body.media_ids=[...new Set([...value.media_ids,...body.add_media_ids])];for(const g of library.sets)if(g!==value)g.media_ids=g.media_ids.filter(id=>!body.add_media_ids.includes(id));}
          Object.assign(value,body);
        } else if (options.responseType === 'blob') {
          options.onload({status:200,response:new w.Blob(['fixture'],{type:'image/png'})}); return;
        } else { value = {error:`Unhandled fixture route: ${method} ${route}`}; status = 404; }
        options.onload({status,responseText:JSON.stringify(value)});
      } catch (e) { errors.push(e); options.onerror?.(e); }
    }, 0);
    return {abort() { canceled = true; options.onabort?.({}); }};
  };
  w.document.documentElement.dataset.naiMediaPayloadVersion = config.version;
  w.document.documentElement.dataset.naiStandalone = '1';
  if (configure) configure(w);
  w.eval(assembled);
  await delay(250);
  const root = w.document.getElementById('nai-media-host').shadowRoot;
  assert.equal(root.getElementById('status').textContent, 'Local library connected');
  async function open(files=[1,2,3,4]) {
    root.getElementById('addMediaBtn').click();
    await delay(40);
    const input = root.getElementById('fileInput');
    Object.defineProperty(input,'files',{value:files.map(n => n instanceof w.File ? n : new w.File(['image'], typeof n === 'object' ? n.name : `Image #${n}.png`,{type:'image/png'}))});
    input.dispatchEvent(new w.Event('change',{bubbles:true}));
    root.getElementById('importReview').click();
    await waitFor(()=>root.querySelector('#reviewStage'),errors,3000);await delay(60);
  }
  return {dom,w,root,library,writes,errors,revoked,history,queue,open,setUpdate(v){updateVersion=v},resetQueue(){queue.length=0;queueState={}},get frames(){return frames;}};
}

module.exports={fixture,waitFor,delay,config,assembled,repo};
