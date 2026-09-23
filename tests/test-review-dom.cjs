// Full assembled payload in a DOM, with a fake companion. Install jsdom@26.1.0 to run.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('jsdom');
const repo = path.resolve(__dirname, '..');
const config = JSON.parse(fs.readFileSync(path.join(repo, process.env.NAI_RELEASE_CONFIG || 'release-userscript.json'), 'utf8'));
const assembled = config.parts.map(p => fs.readFileSync(path.join(repo,p),'utf8')).join('');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function fixture({media = [], configure = null} = {}) {
  const errors = [], writes = [], revoked = [], history = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => { if (!e.message.includes('Not implemented:')) errors.push(e); });
  const dom = new JSDOM('<!doctype html><html><head></head><body><main>NovelAI fixture</main></body></html>', {
    url:'https://novelai.net/stories', runScripts:'outside-only', pretendToBeVisual:true, virtualConsole:vc,
  });
  const w = dom.window;
  const library = {characters:[{id:'character',name:'Fixture',categories:[{id:'dress',name:'Dress'}]}], media, sets:[]};
  let blobIndex = 0, frames = 0;
  w.URL.createObjectURL = () => `blob:https://novelai.net/${++blobIndex}`;
  w.URL.revokeObjectURL = url => revoked.push(url);
  w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
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
      if (canceled) return;
      try {
        let value, status = 200;
        if (method !== 'GET') writes.push({route,method});
        if (route === '/api/health') value = {ok:true,version:6,replacement_flags:true,featured_flags:true,undo_history:true};
        else if (route === '/api/library') value = library;
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
          const item = library.media.find(m => m.id === id);
          if (!item) throw new Error(`Saving unknown media ${id}`);
          const body = JSON.parse(options.data);
          history.push({id:'undo-'+history.length,label:'Change '+action,media_id:id,filename:item.original_name,before:JSON.parse(JSON.stringify(item))});
          Object.assign(item, action === 'crop' ? {crop_top:body.top,crop_bottom:body.bottom} : body); value = item;
        } else if (route === '/api/sets' && method === 'POST') {
          value = {id:`set${library.sets.length+1}`,...JSON.parse(options.data)}; library.sets.push(value);
        } else if (route.startsWith('/api/sets/') && method === 'POST') {
          value = library.sets.find(s => s.id === route.split('/')[3]); Object.assign(value,JSON.parse(options.data));
        } else if (options.responseType === 'blob') {
          options.onload({status:200,response:new w.Blob(['fixture'],{type:'image/png'})}); return;
        } else { value = {error:`Unhandled fixture route: ${method} ${route}`}; status = 404; }
        options.onload({status,responseText:JSON.stringify(value)});
      } catch (e) { errors.push(e); options.onerror?.(e); }
    }, 0);
    return {abort() { canceled = true; options.onabort?.({}); }};
  };
  w.document.documentElement.dataset.naiMediaPayloadVersion = config.version;
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
    await delay(70);
  }
  return {dom,w,root,library,writes,errors,revoked,history,open,get frames(){return frames;}};
}

test('assembled UI opens ordered previews without importing, navigates, and discards on X', async () => {
  const f = await fixture();
  try {
    await f.open();
    assert.equal(f.root.querySelector('#reviewStage img').alt,'Image #4.png');
    const previews = [...f.root.querySelectorAll('.naiQueueThumb270 img')];
    assert.equal(previews.length,4);
    assert.ok(previews.every(img => img.src.startsWith('blob:')));
    f.root.querySelectorAll('.naiQueueThumb270')[1].click();
    await delay(50);
    assert.equal(f.root.querySelector('#reviewStage img').alt,'Image #3.png');
    assert.equal(f.library.media.length,0);
    f.root.getElementById('naiReviewClose270').click();
    await delay(120);
    assert.equal(f.library.media.length,0);
    assert.equal(f.root.naiReviewDrafts.size,0);
    assert.equal(f.revoked.length,4);
    assert.deepEqual(f.writes,[]);
    const before = f.frames;
    await delay(120);
    assert.ok(f.frames-before < 10,'observers should settle');
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('viewer delete button sits with navigation controls and deletes the active media', async () => {
  const f = await fixture();
  try {
    f.library.media.push({id:'saved-viewer',character_id:'character',original_name:'Viewer image.png',media_type:'image',categories:[],in_review:false,thumb_rel:'fixture/thumb.webp'});
    f.root.getElementById('refreshBtn').click();
    await delay(160);
    const tile = f.root.querySelector('.tile[data-id="saved-viewer"]');
    assert.ok(tile);
    tile.click();
    await delay(100);
    const nav = f.root.querySelector('.viewerNav');
    const deleteButton = f.root.getElementById('deleteBtn');
    assert.ok(nav?.contains(deleteButton));
    assert.equal(deleteButton.disabled,false);
    f.w.confirm = () => false;
    deleteButton.click();
    await delay(40);
    assert.ok(f.library.media.some(m => m.id === 'saved-viewer'));
    f.w.confirm = () => true;
    deleteButton.click();
    await delay(170);
    assert.equal(f.library.media.some(m => m.id === 'saved-viewer'),false);
    assert.deepEqual(f.writes,[{route:'/api/media/saved-viewer',method:'DELETE'}]);
    assert.equal(f.root.getElementById('deleteBtn').disabled,true);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('viewer edit button assigns categories and replaces an image without changing its set membership', async () => {
  const f = await fixture();
  try {
    const item = {id:'saved-edit',character_id:'character',original_name:'old.png',media_type:'image',categories:[],in_review:false,in_all:true,thumb_rel:'fixture/thumb.webp'};
    f.library.media.push(item);
    f.root.getElementById('refreshBtn').click();
    await delay(160);
    f.root.querySelector('.tile[data-id="saved-edit"]').click();
    await delay(100);
    assert.equal(f.root.getElementById('qualityInfo').textContent, 'Source quality: 1536 × 2048 · 2.0 KB');
    const editButton = f.root.getElementById('editBtn');
    assert.ok(f.root.querySelector('.viewerNav')?.contains(editButton));
    assert.equal(editButton.disabled, false);
    editButton.click();
    await delay(20);
    const category = f.root.querySelector('#editMediaCats input[data-catid="dress"]');
    assert.ok(category);
    assert.equal(f.root.getElementById('editAllMedia').checked, true);
    category.click();
    f.root.getElementById('saveMediaCats').click();
    await delay(170);
    assert.deepEqual(item.categories, ['dress']);
    f.library.media.push({id:'saved-other',character_id:'character',original_name:'other.png',media_type:'image',categories:[],in_review:false,in_all:false});
    f.library.sets.push({id:'set-edit',character_id:'character',name:'Set',media_ids:['saved-edit','saved-other'],cover_media_id:'saved-edit'});
    f.root.getElementById('refreshBtn').click();
    await delay(170);
    assert.ok(f.root.querySelector('.tile[data-id="saved-edit"]'));
    assert.equal(f.root.querySelector('.naiSetTile[data-set-id="set-edit"]'), null);
    assert.deepEqual(f.library.sets[0].media_ids, ['saved-edit','saved-other']);

    editButton.click();
    await delay(20);
    const input = f.root.getElementById('replaceSourceInput');
    Object.defineProperty(input, 'files', {value:[new f.w.File(['new'], 'higher-quality.png', {type:'image/png'})]});
    input.dispatchEvent(new f.w.Event('change', {bubbles:true}));
    await delay(220);
    assert.equal(item.original_name, 'higher-quality.png');
    assert.deepEqual(item.categories, ['dress']);
    assert.deepEqual(f.library.sets[0].media_ids, ['saved-edit','saved-other']);
    assert.deepEqual(f.writes, [
      {route:'/api/media/saved-edit/categories',method:'POST'},
      {route:'/api/media/saved-edit/replace',method:'POST'},
    ]);
    assert.deepEqual(f.errors, []);
  } finally { f.dom.window.close(); }
});

test('Sets assignment saves selected drafts, adds them to the set, and removes them from the queue', async () => {
  const f = await fixture();
  try {
    await f.open([1,2,3]);
    f.library.sets.push({id:'set-existing',character_id:'character',name:'Existing set',media_ids:['saved0'],cover_media_id:'saved0'});
    f.root.getElementById('naiQueueSets270').click();
    await delay(50);
    assert.equal(f.root.querySelectorAll('.naiSetQueueCard270').length,3);
    assert.ok(f.root.getElementById('naiSetQueueCreate270'));
    assert.ok(f.root.getElementById('naiSetQueueNew270'));
    f.root.getElementById('naiSetQueueExisting270').value='set-existing';
    f.root.querySelectorAll('.naiSetQueueCard270 input')[2].click();
    f.root.getElementById('naiSetQueueSave270').click();
    await delay(180);
    assert.equal(f.library.media.length,2);
    assert.deepEqual(f.library.media.map(m => m.original_name),['Image #3.png','Image #2.png']);
    assert.deepEqual(f.library.sets[0].media_ids,['saved0','saved1','saved2']);
    assert.equal(f.root.querySelectorAll('.naiQueueThumb270').length,1);
    assert.equal(f.root.querySelector('#reviewStage img').alt,'Image #1.png');
    f.root.getElementById('naiReviewClose270').click();
    await delay(100);
    assert.equal(f.library.media.length,2);
    assert.equal(f.root.naiReviewDrafts.size,0);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('Create set in Rapid Review keeps unsaved queue and creates a separate empty set', async () => {
  const f = await fixture();
  try {
    await f.open([1,2]);
    f.root.getElementById('naiQueueSets270').click();
    await delay(50);
    f.root.getElementById('naiSetQueueNew270').value = 'New empty set';
    f.root.getElementById('naiSetQueueCreate270').click();
    assert.equal(f.root.getElementById('naiSetQueueClose270').disabled,true);
    await delay(180);
    assert.equal(f.library.sets.length,1);
    assert.deepEqual(f.library.sets[0].media_ids,[]);
    assert.equal(f.library.sets[0].cover_media_id,null);
    assert.equal(f.library.media.length,0);
    assert.equal(f.root.naiReviewDrafts.size,2);
    assert.equal(f.root.querySelectorAll('.naiSetQueueCard270').length,2);
    assert.equal(f.root.getElementById('naiSetQueueExisting270').value,f.library.sets[0].id);
    assert.ok(f.root.querySelector('[data-nai-review-v270]'));
    f.root.getElementById('naiSetQueueCancel270').click();
    f.root.getElementById('naiQueueSets270').click();
    await delay(50);
    f.root.getElementById('naiSetQueueExisting270').value=f.library.sets[0].id;
    f.root.getElementById('naiSetQueueSave270').click();
    await delay(260);
    assert.equal(f.library.media.length,2);
    assert.equal(f.library.sets[0].media_ids.length,2);
    assert.equal(f.root.naiReviewDrafts.size,0);
    assert.equal(f.root.querySelector('[data-nai-review-v270]'),null);
    // The queue completion refreshes the normal library view asynchronously; let
    // that final render settle before tearing down the JSDOM window.
    await delay(800);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('normal Sets manager can create and display a set without saved images', async () => {
  const f = await fixture();
  try {
    f.root.getElementById('naiManageSetsBtn').click();
    await delay(60);
    f.root.getElementById('naiSetNameInput').value='Empty';
    f.root.getElementById('naiSaveSetBtn').click();
    await delay(90);
    assert.deepEqual(f.library.sets[0].media_ids,[]);
    assert.equal(f.library.media.length,0);
    const setsTab = f.root.getElementById('naiSetsCat');
    assert.ok(setsTab);
    setsTab.click();
    await delay(90);
    assert.equal(f.root.querySelectorAll('.naiSetTile').length,1);
    assert.match(f.root.querySelector('.naiSetTile').textContent,/Empty set/);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('set-only members open from Sets, remain available after selection, and save a cover independently', async () => {
  const f = await fixture();
  try {
    f.library.media.push(...[1,2,3].map(i=>({id:`member${i}`,character_id:'character',media_type:'image',original_name:`Image ${i}.png`,categories:[],in_review:i===3,thumb_rel:null})));
    f.library.sets.push({id:'set-only',character_id:'character',name:'Set only',media_ids:['member1','member2','member3'],cover_media_id:'member1'});
    f.root.getElementById('refreshBtn').click();
    await delay(650);
    assert.equal(f.root.querySelectorAll('#grid .tile').length,0,'All intentionally excludes uncategorized set-only images');
    f.root.getElementById('naiSetsCat').click();
    await delay(60);
    f.root.querySelector('.naiSetTile').click();
    await delay(200);
    const ids=()=>[...f.root.querySelectorAll('#grid .tile')].map(tile=>tile.dataset.id);
    assert.deepEqual(ids(),['member1','member2'],'set membership must not depend on visible All tiles');
    assert.equal(f.root.getElementById('counter').textContent, '— / 2');
    assert.ok(f.root.querySelector('.tile[data-id="member2"] img'),'pending thumbnails still render an image element');
    const before=f.root.getElementById('stages').innerHTML;
    f.root.querySelector('.tile[data-id="member2"] .naiSetCover216').click();
    await delay(100);
    assert.equal(f.library.sets[0].cover_media_id,'member2');
    assert.deepEqual(f.library.sets[0].media_ids,['member1','member2','member3']);
    assert.equal(f.library.media[1].favorite,undefined);
    assert.equal(f.root.getElementById('stages').innerHTML,before,'cover button must not select an image');
    assert.equal(f.root.querySelector('.tile[data-id="member2"] .naiSetCover216').getAttribute('aria-pressed'),'true');
    f.root.querySelector('.tile[data-id="member1"]').click();
    await delay(200);
    assert.equal(f.root.getElementById('counter').textContent, '1 / 2');
    f.root.getElementById('counter').textContent = '— / 1';
    await delay(20);
    assert.equal(f.root.getElementById('counter').textContent, '1 / 2','late base viewer updates must not replace set-relative numbering');
    assert.deepEqual(ids(),['member1','member2']);
    f.root.getElementById('naiSetBackBtn').click();
    await delay(100);
    assert.equal(f.root.querySelector('.naiSetTile').dataset.coverId,'member2');
    f.root.querySelector('.naiSetTile').click();
    await delay(200);
    assert.deepEqual(ids(),['member1','member2']);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('videos in Review stay out of Videos and can be promoted from the video Review queue', async () => {
  const f = await fixture();
  try {
    f.library.media.push(
      {id:'video-published',character_id:'character',original_name:'Published.mp4',media_type:'video',categories:[],favorite:false,in_review:false},
      {id:'video-review',character_id:'character',original_name:'Review.mp4',media_type:'video',categories:[],favorite:false,in_review:true},
    );
    f.root.getElementById('refreshBtn').click();
    await delay(220);
    const videoTab = [...f.root.querySelectorAll('#categories .cat:not(.naiSetsCat)')][2];
    assert.equal(videoTab.textContent,'All 1');
    videoTab.click();
    await delay(100);
    assert.deepEqual([...f.root.querySelectorAll('#grid .tile[data-id]')].map(tile => tile.dataset.id),['video-published']);
    const reviewVideos = f.root.getElementById('naiReviewVideoFilter270');
    assert.equal(reviewVideos.textContent,'Review videos 1');
    assert.equal(reviewVideos.classList.contains('hidden'),false);
    reviewVideos.click();
    await delay(100);
    assert.equal(f.root.querySelector('#reviewStage video') !== null,true);
    const hold = f.root.getElementById('naiReviewHold270');
    assert.equal(hold.checked,true);
    hold.checked = false;
    f.root.getElementById('naiReviewNext270').click();
    await delay(220);
    assert.equal(f.library.media.find(m => m.id === 'video-review').in_review,false);
    assert.equal([...f.root.querySelectorAll('#categories .cat:not(.naiSetsCat)')][2].textContent,'All 2');
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('a set-only image can be promoted directly into All without exposing its whole set', async () => {
  const f = await fixture();
  try {
    f.library.media.push(...[1,2].map(i=>({id:`all-member${i}`,character_id:'character',media_type:'image',original_name:`All image ${i}.png`,categories:[],in_review:false,in_all:false,thumb_rel:null})));
    f.library.sets.push({id:'set-all',character_id:'character',name:'All promotion',media_ids:['all-member1','all-member2'],cover_media_id:'all-member1'});
    f.root.getElementById('refreshBtn').click();
    await delay(500);
    f.root.getElementById('naiSetsCat').click();
    await delay(60);
    f.root.querySelector('.naiSetTile').click();
    await delay(180);
    f.root.querySelector('.tile[data-id="all-member1"]').click();
    await delay(120);
    f.root.getElementById('editBtn').click();
    await delay(20);
    const all = f.root.getElementById('editAllMedia');
    assert.equal(all.checked, false);
    all.click();
    f.root.getElementById('saveMediaCats').click();
    await delay(220);
    assert.equal(f.library.media.find(m=>m.id==='all-member1').in_all, true);
    assert.equal(f.library.media.find(m=>m.id==='all-member2').in_all, false);
    f.root.getElementById('naiSetBackBtn').click();
    await delay(180);
    f.root.querySelector('.cat:not(.naiSetsCat)').click();
    await delay(120);
    assert.ok(f.root.querySelector('.tile[data-id="all-member1"]'), `grid=${f.root.getElementById('grid').innerHTML}`);
    assert.equal(f.root.querySelector('.tile[data-id="all-member2"]'), null);
    assert.equal(f.root.getElementById('counter').textContent, '1 / 1');
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('character deletion respects cancel and deletes an empty last character without media calls', async () => {
  const f = await fixture();
  try {
    assert.equal(f.root.getElementById('naiDeleteCharacter215'),null);
    f.root.getElementById('addMediaBtn').click();
    f.root.getElementById('modalEditImages').click();
    await delay(60);
    const options=f.root.getElementById('naiCharacterOptions216');
    assert.equal(options.open,false);
    options.open=true;
    f.w.confirm=()=>false;
    f.root.getElementById('naiDeleteCharacter215').click();
    await delay(50);
    assert.equal(f.library.characters.length,1);
    assert.deepEqual(f.writes,[]);
    f.w.confirm=()=>true;
    f.root.getElementById('naiDeleteCharacter215').click();
    await delay(180);
    assert.equal(f.library.characters.length,0);
    assert.equal(f.root.getElementById('characterSelect').value,'');
    assert.deepEqual(f.writes,[{method:'DELETE',route:'/api/characters/character'}]);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('character deletion refuses even a hidden review image', async () => {
  const f = await fixture();
  try {
    f.library.media.push({id:'hidden',character_id:'character',media_type:'image',in_review:true});
    f.root.getElementById('addMediaBtn').click();
    f.root.getElementById('modalEditImages').click();
    await delay(60);
    f.root.getElementById('naiCharacterOptions216').open=true;
    f.root.getElementById('naiDeleteCharacter215').click();
    await delay(50);
    assert.equal(f.library.characters.length,1);
    assert.deepEqual(f.writes,[]);
    assert.match(f.root.getElementById('naiBulkStatus285').textContent,/contains images or videos/);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('canonical crop editor stores draft crop without importing and commits it on Save', async () => {
  const f = await fixture();
  try {
    f.w.createImageBitmap = async () => ({width:100,height:100,close(){}});
    f.w.HTMLCanvasElement.prototype.getContext = () => ({drawImage(){}});
    f.w.HTMLCanvasElement.prototype.toBlob = callback => callback(new f.w.Blob(['cropped preview'],{type:'image/png'}));
    await f.open([2,1]);
    f.root.getElementById('naiReviewCropBtnV254').click();
    await delay(120);
    const box = f.root.querySelector('.naiCropBox');
    assert.ok(box,'the existing crop editor opens for an unsaved draft');
    box.getBoundingClientRect = () => ({top:0,height:100,width:100});
    box.querySelector('.naiCropHandle.top').dispatchEvent(new f.w.MouseEvent('pointerdown',{bubbles:true,clientY:10}));
    f.root.querySelector('.naiCropSave').click();
    await delay(90);
    assert.equal(f.library.media.length,0);
    assert.deepEqual(f.writes,[]);
    assert.equal([...f.root.naiReviewDrafts.values()][0].media.crop_top,.1);
    f.root.getElementById('naiReviewNext270').click();
    await delay(90);
    assert.equal(f.library.media.length,1);
    assert.equal(f.library.media[0].crop_top,.1);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('update indicator distinguishes active and ready versions and blocks reload during review', async () => {
  const f = await fixture();
  try {
    const status=f.root.getElementById('naiUpdateStatus');
    assert.match(status.textContent,new RegExp(`v${config.version} active`));
    assert.equal(status.querySelector('button').hidden,true);
    f.w.document.documentElement.dataset.naiMediaUpdateReady='9.9.9';
    await delay(20);
    assert.match(status.textContent,/v9.9.9 ready/);
    assert.equal(status.querySelector('button').hidden,false);
    assert.equal(status.querySelector('button').disabled,false);
    await f.open([1]);
    assert.equal(status.querySelector('button').disabled,true);
    f.root.getElementById('naiReviewClose270').click();
    await delay(30);
    assert.equal(status.querySelector('button').disabled,false);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('a nine-image queue keeps the same nine previews at every selected position', async () => {
  const f = await fixture();
  try {
    await f.open([1,2,3,4,5,6,7,8,9]);
    const titles = () => [...f.root.querySelectorAll('.naiQueueThumb270')].map(card => card.title);
    const expected = Array.from({length:9}, (_, i) => `${i+1}. Image #${9-i}.png`);
    assert.deepEqual(titles(), expected);
    for (let i = 0; i < 9; i++) {
      f.root.querySelectorAll('.naiQueueThumb270')[i].click();
      await delay(10);
      assert.deepEqual(titles(), expected);
      assert.equal(f.root.querySelector('#reviewStage img').alt, `Image #${9-i}.png`);
      assert.equal(f.root.getElementById('naiQueueRange289').textContent, '1–9 of 9');
      assert.equal(f.root.getElementById('naiQueuePager289').hidden, true);
    }
    assert.deepEqual(f.writes, []);
    assert.deepEqual(f.errors, []);
  } finally { f.dom.window.close(); }
});

test('large queues use bounded stable pages; paging never selects or saves media', async () => {
  const f = await fixture();
  try {
    await f.open(Array.from({length:57}, (_, i) => i+1));
    const cards = () => [...f.root.querySelectorAll('.naiQueueThumb270')];
    const range = () => f.root.getElementById('naiQueueRange289').textContent;
    assert.equal(cards().length, 14);
    assert.equal(range(), '1–14 of 57');
    assert.equal(f.root.getElementById('naiQueuePagePrev289').disabled, true);
    assert.ok(cards().every(card => card.querySelector('img').loading === 'lazy'));
    f.root.getElementById('naiQueuePageNext289').click();
    assert.equal(cards().length, 14);
    assert.equal(range(), '15–28 of 57');
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'Image #57.png');
    f.root.getElementById('naiQueuePageNext289').click();
    assert.equal(cards().length, 14);
    assert.equal(range(), '29–42 of 57');
    f.root.getElementById('naiQueuePageNext289').click();
    assert.equal(cards().length, 14);
    assert.equal(range(), '43–56 of 57');
    f.root.getElementById('naiQueuePageNext289').click();
    assert.equal(cards().length, 1);
    assert.equal(range(), '57–57 of 57');
    assert.equal(f.root.getElementById('naiQueuePageNext289').disabled, true);
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'Image #57.png');
    f.root.getElementById('naiQueuePagePrev289').click();
    assert.equal(cards().length, 14);
    assert.deepEqual(f.writes, []);
    cards()[13].click();
    await delay(20);
    assert.equal(range(), '43–56 of 57');
    assert.equal(cards().length, 14);
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'Image #2.png');
    f.root.getElementById('naiReviewNext270').click();
    await delay(80);
    assert.equal(f.library.media.length, 1);
    assert.equal(f.library.media[0].original_name, 'Image #2.png');
    assert.equal(range(), '57–57 of 57');
    assert.equal(cards().length, 1);
    f.root.getElementById('naiReviewPrev270').click();
    await delay(20);
    assert.equal(range(), '43–56 of 57');
    assert.equal(cards().length, 14);
    assert.equal(f.library.media.length, 1);
    assert.deepEqual(f.errors, []);
  } finally { f.dom.window.close(); }
});

test('Rapid Review sorts uploaded filenames in descending natural order', async () => {
  const f = await fixture();
  try {
    await f.open([{name:'zeta.jpg'},{name:'alpha.jpg'},{name:'middle.jpg'}]);
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'zeta.jpg');
    f.root.querySelectorAll('.naiQueueThumb270')[1].click();
    await delay(20);
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'middle.jpg');
    f.root.getElementById('naiReviewClose270').click();
    await delay(30);
    await f.open([3,2,1]);
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'Image #3.png');
    f.root.getElementById('naiReviewClose270').click();
    await delay(30);
    await f.open([{name:'Image_998.jpg'},{name:'Image_1000.jpg'},{name:'Image_999.jpg'}]);
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'Image_1000.jpg');
  } finally { f.dom.window.close(); }
});

test('Rapid Review keeps a large but bounded workspace for portrait and landscape media', async () => {
  const f = await fixture();
  try {
    await f.open([1]);
    const modal = f.root.querySelector('[data-nai-review-v270] > .modal.large');
    const styles = [...f.root.querySelectorAll('style')].map(node => node.textContent).join('\n');
    assert.match(styles, /width:min\(1500px,94vw\)/);
    assert.match(styles, /height:min\(96vh,980px\)/);
    assert.equal(modal.classList.contains('large'), true);
  } finally { f.dom.window.close(); }
});

test('Rapid Review uses the full available webpage height without changing its width', async () => {
  const f = await fixture();
  try {
    await f.open([1]);
    const styles = [...f.root.querySelectorAll('style')].map(node => node.textContent).join('\n');
    assert.match(styles, /\.modalWrap \{ padding:0!important; \}/);
    assert.match(styles, /height:100vh!important/);
    assert.match(styles, /max-height:none!important/);
    assert.match(styles, /width:min\(1500px,94vw\)/);
    assert.match(assembled, /inline:'center'/);
  } finally { f.dom.window.close(); }
});


test('large library selection preserves thumbnail nodes and scroll position', async () => {
  const f = await fixture();
  try {
    const count = Number(process.env.NAI_GRID_FIXTURE_SIZE || 1000);
    f.library.media.push(...Array.from({length:count}, (_,i) => ({
      id:`scale-${i}`, character_id:'character', original_name:`Image ${i}.png`,
      media_type:'image', categories:[], in_review:false, in_all:true, thumb_rel:'fixture/thumb.webp',
    })));
    f.root.getElementById('refreshBtn').click();
    await delay(750);
    const grid = f.root.getElementById('grid');
    const tiles = [...grid.querySelectorAll('.tile[data-id]')];
    assert.ok(tiles.length<=60, `Expected a viewport-sized grid, got ${tiles.length} tiles`);
    assert.ok(tiles.length<count);
    const images = tiles.map(tile=>tile.querySelector('img'));
    grid.scrollTop=0;
    let replaced=0;
    const observer=new f.w.MutationObserver(records=>{
      for(const r of records) replaced+=r.addedNodes.length+r.removedNodes.length;
    });
    observer.observe(grid,{childList:true});
    for(const index of [0,Math.floor(count/2),count-1]) {
      await f.root.naiSelectMedia(`scale-${index}`);
      await delay(180);
      if(index<tiles.length) assert.equal(f.root.querySelector('#grid .tile.active')?.dataset.id,`scale-${index}`);
      assert.match(f.root.getElementById('counter').textContent,new RegExp(`^\\d+ / ${count}$`));
      assert.equal(grid.scrollTop,0);
    }
    observer.disconnect();
    assert.equal(replaced,0,'selection must not remove/reinsert grid tiles');
    const after=[...grid.querySelectorAll('.tile[data-id]')];
    for(let i=0;i<tiles.length;i++){
      assert.equal(after[i],tiles[i]);
      assert.equal(after[i].querySelector('img'),images[i]);
    }
    grid.scrollTop=1e9;
    grid.dispatchEvent(new f.w.Event('scroll'));
    await delay(60);
    const bottom=[...grid.querySelectorAll('.tile[data-id]')];
    assert.ok(bottom.length<=65);
    assert.equal(bottom.at(-1).dataset.id,`scale-${count-1}`);
    assert.equal(tiles[0].isConnected,false,'offscreen tiles must be removed');
    grid.scrollTop=0;
    grid.dispatchEvent(new f.w.Event('scroll'));
    await delay(60);
    assert.equal(grid.querySelector('.tile[data-id]').dataset.id,'scale-0');
    assert.ok(grid.querySelectorAll('.tile[data-id]').length<=60);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

for (const mode of ['display', 'navigate', 'error']) {
  test(`cold cropped viewer clips the original without encoding: ${mode}`, async () => {
    let extraWork=0;
    const media = ['cropped','plain'].map(id=>({id,character_id:'character',original_name:id+'.png',media_type:'image',categories:[],in_all:true,in_review:false,thumb_rel:'thumb.png',crop_top:id==='cropped'?.2:0,crop_bottom:0}));
    const f = await fixture({media, configure(w) {
      w.createImageBitmap = () => { extraWork++; throw new Error('Unexpected bitmap crop'); };
      w.HTMLCanvasElement.prototype.toBlob = () => { extraWork++; throw new Error('Unexpected crop encoding'); };
    }});
    try {
      const stage=f.root.getElementById('stage1');
      Object.defineProperties(stage,{clientWidth:{value:100},clientHeight:{value:100}});
      const exposed=[];
      const observer=new f.w.MutationObserver(records=>{
        for(const r of records) for(const node of r.addedNodes) if(node.tagName==='IMG' && node.alt==='cropped.png') exposed.push(node.style.visibility);
      });
      observer.observe(stage,{childList:true});
      f.root.querySelector('.tile[data-id="cropped"]').click();
      await delay(120);
      const img=stage.querySelector('img'), original=img.src;
      assert.equal(img.style.visibility,'hidden','hide only while original dimensions are unavailable');
      assert.deepEqual(exposed,['hidden'],'never attach a visible uncropped original');
      assert.equal(extraWork,0);
      if(mode==='navigate') {
        f.root.querySelector('.tile[data-id="plain"]').click();
        await delay(70);
      }
      Object.defineProperties(img,{naturalWidth:{value:100},naturalHeight:{value:100}});
      img.dispatchEvent(new f.w.Event(mode==='error'?'error':'load'));
      await delay(40);
      if(mode==='display') {
        assert.equal(stage.querySelector('img'),img);
        assert.equal(img.src,original,'use the original URL without a second image');
        assert.equal(img.style.visibility,'visible');
        assert.equal(img.style.clipPath,'inset(20% 0 0% 0)');
        assert.equal(img.style.width,'100px');
        assert.equal(img.style.height,'100px');
        assert.equal(img.style.top,'-10px');
        let mutations=0;
        const styles=new f.w.MutationObserver(rs=>{mutations+=rs.length;});
        styles.observe(img,{attributes:true,attributeFilter:['style']});
        f.root.naiPrepareViewerImage(img,media[0]);
        await delay(20); styles.disconnect();
        assert.equal(mutations,0,'unchanged crop must not keep writing layout styles');
      } else if(mode==='navigate') {
        assert.equal(stage.querySelector('img').alt,'plain.png','late image load must not replace the new selection');
      } else {
        assert.equal(stage.querySelector('img'),null);
        assert.match(stage.textContent,/Image could not be loaded/);
      }
      assert.equal(extraWork,0);
      observer.disconnect();
      assert.deepEqual(f.errors,[]);
    } finally { f.dom.window.close(); }
  });
}


test('replacement flag finds set-only images and can be undone from the viewer', async () => {
  const media=['first','second'].map(id=>({id,character_id:'character',original_name:id+'.png',media_type:'image',in_all:false,in_review:false,needs_replacement:false,categories:[],thumb_rel:'thumb.png'}));
  const f=await fixture({media});
  try {
    f.library.sets.push({id:'flag-set',character_id:'character',name:'Flag set',media_ids:['first','second'],cover_media_id:'first'});
    f.root.getElementById('refreshBtn').click(); await delay(250);
    f.root.getElementById('naiSetsCat').click();
    f.root.querySelector('.naiSetTile').click(); await delay(250);
    f.root.querySelector('.tile[data-id="first"]').click(); await delay(120);
    const button=f.root.getElementById('replacementBtn');
    assert.equal(button.disabled,false);
    button.click(); await delay(150);
    assert.equal(f.library.media[0].needs_replacement,true);
    assert.equal(button.getAttribute('aria-pressed'),'true');
    assert.equal(f.library.media[0].in_all,false);
    assert.deepEqual(f.library.sets[0].media_ids,['first','second']);
    f.root.querySelector('.naiReplacementCat').click(); await delay(150);
    assert.equal(f.root.querySelector('.naiSetBreadcrumb'),null);
    assert.deepEqual([...f.root.querySelectorAll('#grid .tile[data-id]')].map(t=>t.dataset.id),['first']);
    assert.ok(f.root.querySelector('#grid .naiReplacementBadge'));
    button.click(); await delay(150);
    assert.equal(f.root.querySelectorAll('#grid .tile[data-id]').length,0);
    f.root.getElementById('undoBtn').click(); await delay(60);
    assert.ok(f.root.getElementById('undoLatestBtn'));
    f.root.getElementById('undoLatestBtn').click(); await delay(200);
    assert.equal(f.library.media[0].needs_replacement,true);
    assert.ok(f.root.querySelector('#grid .tile[data-id="first"]'));
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('viewer Undo restores a deleted image at its original list position', async () => {
  const media=['first','second','third'].map(id=>({id,character_id:'character',original_name:id+'.png',media_type:'image',in_all:true,in_review:false,categories:[],thumb_rel:'thumb.png'}));
  const f=await fixture({media});
  try {
    f.root.querySelector('.tile[data-id="second"]').click(); await delay(80);
    f.root.getElementById('deleteBtn').click(); await delay(140);
    assert.deepEqual(f.library.media.map(m=>m.id),['first','third']);
    f.root.getElementById('undoBtn').click(); await delay(60);
    f.root.getElementById('undoLatestBtn').click(); await delay(180);
    assert.deepEqual(f.library.media.map(m=>m.id),['first','second','third']);
    assert.deepEqual([...f.root.querySelectorAll('#grid .tile[data-id]')].map(t=>t.dataset.id),['first','second','third']);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});


test('undo restores saved crop metadata missing from the initial page snapshot', async () => {
  const f=await fixture();
  try {
    const restored={id:'restored',character_id:'character',original_name:'restored.png',media_type:'image',in_all:true,in_review:false,categories:[],crop_top:.2,crop_bottom:.1,thumb_rel:'thumb.png'};
    f.history.push({id:'prior-session-delete',label:'Delete media',media_id:restored.id,filename:restored.original_name,index:0,before:restored});
    f.root.getElementById('undoBtn').click(); await delay(60);
    f.root.getElementById('undoLatestBtn').click(); await delay(180);
    f.root.querySelector('#modalRoot [data-close]').click();
    f.root.querySelector('.tile[data-id="restored"]').click(); await delay(80);
    assert.equal(f.root.querySelector('#stage1 img').dataset.naiCropKey,'restored:0.200000:0.100000');
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('Rapid Review saves Favorite, Featured, and replacement flags, and Featured is cross-library', async () => {
  const item={id:'best',character_id:'character',original_name:'best.png',media_type:'image',in_all:true,in_review:false,categories:[],thumb_rel:'thumb.png'};
  const f=await fixture({media:[item]});
  try {
    f.root.querySelector('.tile[data-id="best"]').click(); await delay(80);
    f.root.getElementById('featuredBtn').click(); await delay(80);
    assert.equal(item.featured,true);
    const select=f.root.getElementById('characterSelect');
    select.value='__nai_featured__'; select.dispatchEvent(new f.w.Event('change',{bubbles:true})); await delay(80);
    assert.ok(f.root.querySelector('.tile[data-id="best"]'));
    select.value='character'; select.dispatchEvent(new f.w.Event('change',{bubbles:true})); await delay(60);
    await f.open([new f.w.File(['image'],'rapid.png',{type:'image/png'})]);
    f.root.getElementById('naiReviewFavorite270').checked=true;
    f.root.getElementById('naiReviewFeatured270').checked=true;
    f.root.getElementById('naiReviewReplacement270').checked=true;
    f.root.getElementById('naiReviewNext270').click(); await delay(180);
    const saved=f.library.media.find(m=>m.original_name==='rapid.png');
    assert.equal(saved.favorite,true); assert.equal(saved.featured,true); assert.equal(saved.needs_replacement,true);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('video categories stay separate in navigation, import, and Rapid Review saves', async () => {
  const f = await fixture();
  try {
    f.library.characters[0].categories.push({id:'clips',name:'Clips',media_type:'video'});
    f.library.media.push({id:'clip',character_id:'character',original_name:'clip.mp4',media_type:'video',categories:[],in_review:true});
    f.root.getElementById('refreshBtn').click();
    await delay(220);
    assert.equal(f.root.querySelector('#categories [data-cat-id="clips"]'),null);
    f.root.getElementById('addMediaBtn').click();
    await delay(50);
    assert.equal(f.root.querySelector('#importImageCats [data-catid="clips"]'),null);
    assert.ok(f.root.querySelector('#importImageCats [data-catid="dress"]'));
    assert.ok(f.root.querySelector('#importVideoCats [data-catid="clips"]'));
    assert.equal(f.root.querySelector('#importVideoCats [data-catid="dress"]'),null);
    f.root.querySelector('#importCancelBtn').click();
    [...f.root.querySelectorAll('#categories .cat:not(.naiSetsCat)')][2].click();
    await delay(100);
    f.root.getElementById('naiReviewVideoFilter270').click();
    await delay(100);
    assert.equal(f.root.querySelector('#reviewCats [data-catid="dress"]'),null);
    f.root.querySelector('#reviewCats [data-catid="clips"]').checked = true;
    f.root.getElementById('naiReviewNext270').click();
    await delay(220);
    assert.deepEqual(f.library.media.find(m => m.id === 'clip').categories,['clips']);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});

test('mixed review imports retain only the categories matching each file type', async () => {
  const f = await fixture();
  try {
    f.library.characters[0].categories.push({id:'clips',name:'Clips',media_type:'video'});
    f.root.getElementById('refreshBtn').click();
    await delay(220);
    f.root.getElementById('addMediaBtn').click();
    await delay(40);
    f.root.querySelector('#importCats [data-catid="dress"]').checked = true;
    f.root.querySelector('#importCats [data-catid="clips"]').checked = true;
    const input = f.root.getElementById('fileInput');
    Object.defineProperty(input,'files',{value:[new f.w.File(['image'],'1.png',{type:'image/png'}),new f.w.File(['video'],'2.mp4',{type:'video/mp4'})]});
    input.dispatchEvent(new f.w.Event('change',{bubbles:true}));
    f.root.getElementById('importReview').click();
    await delay(100);
    const drafts = [...f.root.naiReviewDrafts.values()];
    assert.equal(drafts.length,2);
    assert.deepEqual(Array.from(drafts.find(d=>d.media.media_type==='video').media.categories),['clips']);
    assert.deepEqual(Array.from(drafts.find(d=>d.media.media_type==='image').media.categories),['dress']);
    assert.deepEqual(f.errors,[]);
  } finally { f.dom.window.close(); }
});
