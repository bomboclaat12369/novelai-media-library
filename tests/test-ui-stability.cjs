// Run with node --test tests/test-ui-stability.cjs. No browser/network dependencies.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const prefix = read('payload/userscript-2.8.3.transport-start.txt');
const suffix = read('payload/userscript-2.8.3.transport-end.txt');

function transport() {
  const sent = [];
  const native = options => {
    const request = {options, aborted:false, complete(event='onload', data='{}') {
      options[event]({status:event === 'onload' ? 200 : 0, responseText:data});
    }};
    sent.push(request);
    return {abort() { request.aborted = true; request.complete('onabort'); }};
  };
  const context = vm.createContext({GM_xmlhttpRequest:native, URL, performance, queueMicrotask, console});
  vm.runInContext(prefix + '\nthis.testRequest = GM_xmlhttpRequest;\n' + suffix, context);
  return {request:context.testRequest, sent};
}
function options(path, extra={}) {
  return {method:'GET', url:`http://127.0.0.1:8765/api/${path}`, ...extra};
}

test('a thumbnail burst leaves capacity for import, save and original-image requests', async () => {
  const {request, sent} = transport();
  for (let i=0; i<100; i++) request(options(`media/${i}/thumb`, {responseType:'blob'}));
  await tick();
  assert.equal(sent.length, 2);
  request(options('import/file', {method:'POST', data:'multipart'}));
  request(options('media/a/review', {method:'POST', data:'{}'}));
  request(options('media/a/original', {responseType:'blob'}));
  await tick();
  assert.equal(sent.length, 4);
  assert.match(sent[2].options.url, /import\/file$/);
  assert.match(sent[3].options.url, /\/review$/);
  sent[2].complete();
  await tick();
  assert.match(sent[4].options.url, /\/original$/);
});

test('concurrent library reads coalesce and fan out independent parsed snapshots', async () => {
  const {request, sent} = transport();
  const results = [];
  for (let i=0; i<5; i++) request(options('library', {onload:r => results.push(JSON.parse(r.responseText))}));
  await tick();
  assert.equal(sent.length, 1);
  sent[0].complete('onload', '{"media":[{"id":"a"}]}');
  assert.equal(results.length, 5);
  results[0].media.pop();
  assert.equal(results[1].media.length, 1);
  request(options('library'));
  await tick();
  assert.equal(sent.length, 2, 'completed reads are not cached');
});

test('writes are never deduplicated and post-write reads cannot reuse older snapshots', async () => {
  const {request, sent} = transport();
  request(options('library'));
  request(options('media/a/review', {method:'POST', data:'{"in_review":true}'}));
  request(options('media/a/review', {method:'POST', data:'{"in_review":true}'}));
  request(options('library'));
  await tick();
  assert.equal(sent.length, 4);
  assert.equal(sent.filter(r=>r.options.method === 'POST').length, 2);
  assert.equal(sent.filter(r=>r.options.url.endsWith('/library')).length, 2);
});

test('canceling one coalesced read does not cancel another reader', async () => {
  const {request, sent} = transport();
  let canceled=0, loaded=0;
  const first = request(options('library', {onerror:()=>canceled++}));
  request(options('library', {onload:()=>loaded++}));
  await tick();
  first.abort();
  assert.equal(sent[0].aborted, false);
  sent[0].complete();
  assert.equal(canceled, 1);
  assert.equal(loaded, 1);
});

test('aborting queued uploads sends nothing; active aborts and errors release capacity once', async () => {
  const {request, sent} = transport();
  let canceled=0;
  const queued = request(options('import/file', {method:'POST', onerror:()=>canceled++}));
  queued.abort();
  await tick();
  assert.equal(sent.length, 0);
  assert.equal(canceled, 1);
  const active = request(options('import/file', {method:'POST', onerror:()=>canceled++}));
  await tick();
  active.abort(); active.abort();
  assert.equal(sent[0].aborted, true);
  assert.equal(canceled, 2);
  for (let i=0; i<6; i++) request(options(`media/${i}/original`));
  await tick();
  assert.equal(sent.length, 5);
  sent[1].complete('ontimeout'); sent[1].complete('onerror');
  await tick();
  assert.equal(sent.length, 6);
});

test('non-companion requests pass through unchanged', () => {
  const {request, sent} = transport();
  const opt = {url:'https://example.invalid/resource'};
  request(opt);
  assert.equal(sent[0].options, opt);
});

// Minimal mutation/rAF model: DOMTokenList.add/remove queues an attribute mutation
// even for an unchanged token. Only production placement functions are evaluated.
// The old payload is a negative control proving that this test detects the loop.
function placementFrames(sourcePath, videoVisible) {
  const source = read(sourcePath);
  function section(start, end) { return source.slice(source.indexOf(start), source.indexOf(end)); }
  const frames=[];
  let mutated=false;
  const tokens=new Set(videoVisible ? ['visible'] : []);
  const parent={};
  const video={isConnected:true, videoWidth:640, videoHeight:480};
  const tools={
    parentNode:parent, isConnected:true, offsetWidth:64, offsetHeight:96,
    style:{removeProperty(){}},
    classList:{contains:t=>tokens.has(t), add(t){tokens.add(t);mutated=true;}, remove(t){tokens.delete(t);mutated=true;}},
  };
  const stage={clientWidth:500,clientHeight:500,querySelector:()=>videoVisible?video:null,appendChild(el){el.parentNode=this;}};
  const context=vm.createContext({
    videoTools:tools, originalToolsParent:parent, originalToolsNext:null,
    stageEls:[stage], normalPlacementQueued:false, activeSlot:()=>0,
    addNormalToolTitles:()=>{}, requestAnimationFrame:callback=>frames.push(callback),
    visibleVideoRect:()=>({left:10,top:10,width:300,height:300}),
  });
  vm.runInContext(section('  function restoreNormalTools()', '  function visibleVideoRect(') +
    section('  function placeNormalTools()', '  new MutationObserver(queueNormalPlacement)'), context);
  context.queueNormalPlacement();
  let total=0;
  for (let turn=0; turn<30 && frames.length; turn++) {
    const batch=frames.splice(0);
    for (const callback of batch) { total++; callback(); }
    if (mutated) { mutated=false; context.queueNormalPlacement(); }
  }
  return {total, pending:frames.length};
}
for (const videoVisible of [false,true]) {
  test(`video control observer settles while ${videoVisible?'video':'images'} are selected`, () => {
    const old=placementFrames('payload/userscript-2.4.3.patch01.txt', videoVisible);
    assert.ok(old.pending > 0 && old.total >= 30, 'negative control must reproduce continuous scheduling');
    const fixed=placementFrames('payload/userscript-2.8.3.video-tools.txt', videoVisible);
    assert.equal(fixed.pending, 0);
    assert.ok(fixed.total <= 4);
  });
}

test('the complete selected userscript and stable loader parse', () => {
  const config=JSON.parse(read(process.env.NAI_RELEASE_CONFIG || 'release-userscript.json'));
  const assembled=config.parts.map(read).join('');
  new vm.Script(assembled, {filename:'assembled-userscript.js'});
  new vm.Script(read('novelai-media.user.js'));
});

test('cached loader startup happens before any GitHub request', () => {
  const storage = new Map([
    ['nai-media-github-payload', "document.documentElement.dataset.fixtureRan = 'yes'"],
    ['nai-media-github-payload-version', '2.8.2'],
  ]);
  const doc={documentElement:{dataset:{}}};
  let checks=0;
  const context=vm.createContext({
    document:doc, console,
    localStorage:{getItem:k=>storage.get(k)||null, setItem:(k,v)=>storage.set(k,v)},
    GM_xmlhttpRequest() { checks++; assert.equal(doc.documentElement.dataset.fixtureRan, 'yes'); },
  });
  vm.runInContext(read('novelai-media.user.js'), context);
  assert.equal(checks, 1);
  assert.equal(doc.documentElement.dataset.fixtureRan, 'yes');
});

test('a second payload execution cannot create a second library host', () => {
  const source = read('payload/userscript-2.8.4.part01.txt');
  assert.match(source, /const existingHost = document\.getElementById\('nai-media-host'\)/);
  assert.match(source, /naiMediaDuplicateSuppressed/);
  assert.match(source, /return;\n  }\n  document\.documentElement\.dataset\.naiMediaPayloadInstance/);
});

test('the active drag cleanup layer does not synthesize page-wide drag events', () => {
  const source = read('payload/userscript-2.8.4.drag-safety.txt');
  assert.doesNotMatch(source, /dispatchEvent|DragEvent|dragleave|dragend/);
  assert.match(source, /naiMediaV284DragSafety/);
  const releasePath = process.env.NAI_RELEASE_CONFIG || 'release-userscript.json';
  const release = JSON.parse(read(releasePath));
  assert.equal(release.parts.includes('payload/userscript-2.5.5.patch01.txt'), false);
  assert.equal(release.parts.includes('payload/userscript-2.8.4.drag-safety.txt'), true);
});

test('the UI patches reset viewer state and expose bulk image editing', () => {
  const reset = read('payload/userscript-2.8.5.reset-state.txt');
  assert.match(reset, /saved\.selectedMediaId = null/);
  assert.match(reset, /saved\.slotMediaIds = \[null, null\]/);
  assert.match(reset, /saved\.splitView = false/);
  const ui = read('payload/userscript-2.8.6.ui-updates.txt');
  assert.match(ui, /openBulkEditModal/);
  assert.match(ui, /Delete selected images/);
  assert.match(ui, /All \$\{count\} images in this Rapid Review queue are shown/);
  assert.doesNotMatch(ui, /Permanently delete/);
  const release = JSON.parse(read(process.env.NAI_RELEASE_CONFIG || 'release-userscript.json'));
  const review = read(release.parts.find(p => p.endsWith('.review-core.txt')));
  assert.doesNotMatch(review, /\? Review/);
  assert.match(review, /setTextIfChanged\(review, `Review /);
  assert.doesNotMatch(ui, /cleanReviewLabels|labelCleanupQueued|observe\(catWrap/);
});

// Exercise the production queue functions, including the DOM attachment guard.
function reviewQueueFixture() {
  const release = JSON.parse(read(process.env.NAI_RELEASE_CONFIG || 'release-userscript.json'));
  const source = read(release.parts.find(p => p.endsWith('.review-core.txt')));
  class Element {
    constructor(tag) { this.tagName = tag; this.children = []; this.listeners = {}; }
    get isConnected() { return this.connected === true || !!this.parent?.isConnected; }
    appendChild(child) { child.parent = this; this.children.push(child); return child; }
    replaceChildren() { for (const child of this.children) child.parent = null; this.children = []; }
    querySelector(selector) { return selector === '.current' ? this.children.find(child => child.className.includes(' current')) : null; }
    addEventListener(type, callback) { this.listeners[type] = callback; }
  }
  const strip = new Element('div'); strip.connected = true;
  const media = Array.from({length:10}, (_, i) => ({
    id:`image ${i}`, media_type:i === 2 ? 'video' : 'image', categories:[], in_review:true,
  }));
  const session = {ids:media.map(m => m.id), index:0, saved:new Set(), carry:false};
  const requests = [];
  const drafts = new Map();
  const revoked = [];
  const uploads = [];
  let token = 0;
  const context = vm.createContext({
    API:'http://127.0.0.1:8765', reviewSession:session,
    drafts, queueSetOverlay:null, root:{},
    URL:{createObjectURL:() => `blob:fixture-${++token}`, revokeObjectURL:url => revoked.push(url)},
    importToken274:() => String(++token),
    uploadFileResilient:async (...args) => { uploads.push(args); return {item:{id:`persisted-${uploads.length}`}}; },
    refreshLibrary:async () => ({}), refreshBtn:null, schedulePseudoSync() {}, scheduleMainFilter() {},
    document:{createElement:tag => new Element(tag)},
    modalRoot:{
      querySelector:selector => selector === '#naiQueueStrip270' ? strip : {checked:true},
      querySelectorAll:() => [],
    },
    mediaById:id => drafts.get(id)?.media || media.find(m => m.id === id),
    gmRequest:async options => { requests.push(options); return JSON.parse(options.data); },
    alert:message => { throw new Error(message); },
  });
  const start = source.indexOf('  async function loadQueueThumb(');
  const end = source.indexOf('  async function renderReviewQueue()', start);
  assert.ok(start >= 0 && end > start);
  const helpers = source.slice(source.indexOf('  function orderedReviewFiles('), source.indexOf('  // ----- Review / Rapid Review'));
  const cleanup = source.slice(source.indexOf('  function revokeSessionUrls()'), source.indexOf('  async function openReviewQueue('));
  vm.runInContext(helpers + cleanup + source.slice(start, end) + `
    async function renderReviewQueue() {
      for (const child of strip.children) child.parent = null;
      strip.children = [];
      await renderQueueStrip();
    }
    this.render = renderQueueStrip;
    this.save = saveCurrentReview;
    this.close = finishReviewQueue;
    this.addDraft = addReviewDraft;
    this.sortFiles = orderedReviewFiles;
  `, Object.assign(context, {strip}));
  return {strip, media, session, requests, drafts, revoked, uploads, context,
    render:context.render, save:context.save, close:context.close, addDraft:context.addDraft, sortFiles:context.sortFiles};
}

test('queue image previews get thumbnail URLs on first render and after navigation', async () => {
  const f = reviewQueueFixture();
  await f.render();
  assert.equal(f.strip.children.length, 10);
  function checkPreviews() {
    for (const card of f.strip.children) {
      const index = Number(card.title.split('.')[0]) - 1;
      const img = card.children.find(child => child.tagName === 'img');
      if (f.media[index].media_type === 'video') { assert.equal(img, undefined); continue; }
      assert.equal(img.isConnected, true);
      assert.equal(img.src, `http://127.0.0.1:8765/api/media/${encodeURIComponent(f.media[index].id)}/thumb`);
    }
  }
  checkPreviews();
  await f.strip.children[4].listeners.click();
  assert.equal(f.session.index, 4);
  checkPreviews();
});

test('jumping does not save; an explicit Save marks the item while allowing it to remain in Review', async () => {
  const f = reviewQueueFixture();
  await f.render();
  await f.strip.children[1].listeners.click();
  assert.deepEqual([...f.session.saved], []);
  assert.equal(f.requests.length, 0);
  await f.save();
  assert.deepEqual([...f.session.saved], ['image 1']);
  assert.equal(f.requests.length, 2);
  assert.match(f.requests[1].path, /\/review$/);
  assert.equal(f.media[1].in_review, true);
});

test('Rapid Review keeps the supplied file order instead of sorting by filename', () => {
  const f = reviewQueueFixture();
  const files = Array.from({length:15}, (_, i) => ({name:`Image #${15-i}.jpg`}));
  assert.deepEqual(Array.from(f.sortFiles(files), x => x.name), files.map(file => file.name));
  assert.equal(files[0].name, 'Image #15.jpg');
});

test('previewing and closing draft imports writes nothing and releases all preview URLs', async () => {
  const f = reviewQueueFixture();
  const ids = [1,2,3].map(i => f.addDraft({name:`image-${i}.jpg`,type:'image/jpeg'}, 'character', []));
  f.session.ids = ids;
  await f.render();
  assert.ok(f.strip.children[0].children[0].src.startsWith('blob:'));
  await f.strip.children[1].listeners.click();
  await f.close();
  assert.equal(f.uploads.length, 0);
  assert.equal(f.requests.length, 0);
  assert.equal(f.drafts.size, 0);
  assert.equal(f.revoked.length, 3);
});

test('saving one draft imports only it, commits its crop, and does not re-upload on retry', async () => {
  const f = reviewQueueFixture();
  const ids = [1,2].map(i => f.addDraft({name:`image-${i}.jpg`,type:'image/jpeg'}, 'character', []));
  f.session.ids = ids;
  const draft = f.drafts.get(ids[0]);
  draft.media.crop_top = .1; draft.cropDirty = true;
  await f.save();
  assert.equal(f.uploads.length, 1);
  assert.equal(f.uploads[0][0].name, 'image-1.jpg');
  assert.ok(f.requests.some(r => r.path.endsWith('/crop') && JSON.parse(r.data).top === .1));
  assert.equal(draft.cropDirty, false);
  await f.save();
  assert.equal(f.uploads.length, 1);
  await f.close();
  assert.equal(f.uploads.length, 1);
  assert.equal(f.drafts.size, 0);
});
