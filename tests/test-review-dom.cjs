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

async function fixture() {
  const errors = [], writes = [], revoked = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => { if (!e.message.includes('Not implemented:')) errors.push(e); });
  const dom = new JSDOM('<!doctype html><html><head></head><body><main>NovelAI fixture</main></body></html>', {
    url:'https://novelai.net/stories', runScripts:'outside-only', pretendToBeVisual:true, virtualConsole:vc,
  });
  const w = dom.window;
  const library = {characters:[{id:'character',name:'Fixture',categories:[{id:'dress',name:'Dress'}]}], media:[], sets:[]};
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
        if (route === '/api/health') value = {ok:true,version:6};
        else if (route === '/api/library') value = library;
        else if (route === '/api/import/file') {
          const file = options.data.get('file');
          const item = {id:`saved${library.media.length+1}`,character_id:'character',original_name:file.name,media_type:'image',categories:[],in_review:false};
          library.media.push(item); value = {item,duplicate:false};
        } else if (route.startsWith('/api/media/') && method === 'POST') {
          const id = route.split('/')[3], action = route.split('/')[4];
          const item = library.media.find(m => m.id === id);
          if (!item) throw new Error(`Saving unknown media ${id}`);
          const body = JSON.parse(options.data);
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
  w.eval(assembled);
  await delay(250);
  const root = w.document.getElementById('nai-media-host').shadowRoot;
  assert.equal(root.getElementById('status').textContent, 'Local library connected');
  async function open(files=[15,10,2,1]) {
    root.getElementById('addMediaBtn').click();
    await delay(40);
    const input = root.getElementById('fileInput');
    Object.defineProperty(input,'files',{value:files.map(n => new w.File(['image'],`Image #${n}.png`,{type:'image/png'}))});
    input.dispatchEvent(new w.Event('change',{bubbles:true}));
    root.getElementById('importReview').click();
    await delay(70);
  }
  return {dom,w,root,library,writes,errors,revoked,open,get frames(){return frames;}};
}

test('assembled UI opens ordered previews without importing, navigates, and discards on X', async () => {
  const f = await fixture();
  try {
    await f.open();
    assert.equal(f.root.querySelector('#reviewStage img').alt,'Image #1.png');
    const previews = [...f.root.querySelectorAll('.naiQueueThumb270 img')];
    assert.equal(previews.length,4);
    assert.ok(previews.every(img => img.src.startsWith('blob:')));
    f.root.querySelectorAll('.naiQueueThumb270')[1].click();
    await delay(50);
    assert.equal(f.root.querySelector('#reviewStage img').alt,'Image #2.png');
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

test('Sets assignment stages drafts; Save commits just one image and X discards the rest', async () => {
  const f = await fixture();
  try {
    await f.open([3,2,1]);
    f.root.getElementById('naiQueueSets270').click();
    await delay(50);
    assert.equal(f.root.querySelectorAll('.naiSetQueueCard270').length,3);
    f.root.getElementById('naiSetQueueNew270').value='Fixture set';
    f.root.getElementById('naiSetQueueSave270').click();
    await delay(60);
    assert.equal(f.library.media.length,0);
    assert.equal(f.library.sets.length,0);
    f.root.getElementById('naiReviewNext270').click();
    f.root.getElementById('naiReviewNext270').click();
    f.root.getElementById('naiReviewClose270').click();
    await delay(100);
    assert.equal(f.library.media.length,1);
    assert.equal(f.library.media[0].original_name,'Image #1.png');
    assert.deepEqual(f.library.sets[0].media_ids,['saved1']);
    assert.equal(f.root.querySelector('#reviewStage img').alt,'Image #2.png');
    f.root.getElementById('naiReviewClose270').click();
    await delay(100);
    assert.equal(f.library.media.length,1);
    assert.equal(f.root.naiReviewDrafts.size,0);
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
    await f.open([9,8,7,6,5,4,3,2,1]);
    const titles = () => [...f.root.querySelectorAll('.naiQueueThumb270')].map(card => card.title);
    const expected = Array.from({length:9}, (_, i) => `${i+1}. Image #${i+1}.png`);
    assert.deepEqual(titles(), expected);
    for (let i = 0; i < 9; i++) {
      f.root.querySelectorAll('.naiQueueThumb270')[i].click();
      await delay(10);
      assert.deepEqual(titles(), expected);
      assert.equal(f.root.querySelector('#reviewStage img').alt, `Image #${i+1}.png`);
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
    assert.equal(cards().length, 24);
    assert.equal(range(), '1–24 of 57');
    assert.equal(f.root.getElementById('naiQueuePagePrev289').disabled, true);
    assert.ok(cards().every(card => card.querySelector('img').loading === 'lazy'));
    f.root.getElementById('naiQueuePageNext289').click();
    assert.equal(cards().length, 24);
    assert.equal(range(), '25–48 of 57');
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'Image #1.png');
    f.root.getElementById('naiQueuePageNext289').click();
    assert.equal(cards().length, 9);
    assert.equal(range(), '49–57 of 57');
    assert.equal(f.root.getElementById('naiQueuePageNext289').disabled, true);
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'Image #1.png');
    f.root.getElementById('naiQueuePagePrev289').click();
    assert.equal(cards().length, 24);
    assert.deepEqual(f.writes, []);
    cards()[23].click();
    await delay(20);
    assert.equal(range(), '25–48 of 57');
    assert.equal(cards().length, 24);
    assert.equal(f.root.querySelector('#reviewStage img').alt, 'Image #48.png');
    f.root.getElementById('naiReviewNext270').click();
    await delay(80);
    assert.equal(f.library.media.length, 1);
    assert.equal(f.library.media[0].original_name, 'Image #48.png');
    assert.equal(range(), '49–57 of 57');
    assert.equal(cards().length, 9);
    f.root.getElementById('naiReviewPrev270').click();
    await delay(20);
    assert.equal(range(), '25–48 of 57');
    assert.equal(cards().length, 24);
    assert.equal(f.library.media.length, 1);
    assert.deepEqual(f.errors, []);
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
  } finally { f.dom.window.close(); }
});
