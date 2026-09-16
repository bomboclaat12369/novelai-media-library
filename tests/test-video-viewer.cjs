const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const release = JSON.parse(fs.readFileSync(path.join(root, process.env.NAI_RELEASE_CONFIG || 'release-userscript.json'), 'utf8'));
const source = fs.readFileSync(path.join(root, release.parts.find(p => p.includes('.part01.txt'))), 'utf8');

test('manual thumbnail replaces cached auto preview and wins over a pending old read', async () => {
  const item = {id:'video1', media_type:'video', thumb_rel:'thumb.jpg', video_thumb_automatic:true};
  const state = {thumbCache:new Map()};
  let finishRead;
  const requests = [];
  const context = vm.createContext({state, Map, Date, Promise, console, MAX_THUMB_CACHE:90,
    shadow:{}, grid:{querySelectorAll:()=>[]}, mediaById:()=>item,
    URL:{createObjectURL:blob=>'url:'+blob.name, revokeObjectURL(){}},
    gmRequest:options=>{requests.push(options.path);return new Promise(resolve=>{finishRead=resolve})},
  });
  vm.runInContext(source.slice(source.indexOf('  const videoPreviewJobs ='), source.indexOf('  function renderGrid(')) + '\nthis.api={loadThumb,applyVideoPreview};', context);
  const img = {};
  const pending = context.api.loadThumb(item.id, img);
  context.api.applyVideoPreview({...item,video_thumb_automatic:false}, {name:'manual'});
  finishRead({name:'old-auto'});
  await pending;
  assert.equal(img.src, 'url:manual');
  assert.equal(state.thumbCache.get(item.id), 'url:manual');
  assert.equal(item.video_thumb_automatic, false);
  context.api.applyVideoPreview({...item,video_thumb_automatic:true});
  assert.equal(item.video_thumb_automatic, false);
  state.thumbCache.clear();
  const reload = context.api.loadThumb(item.id, {});
  assert.notEqual(requests[0], requests[1]);
  assert.match(requests[1], /\/thumb\?v=.+-1$/);
  finishRead({name:'manual'});
  await reload;
});

test('viewer arrows seek by three seconds without switching videos or intercepting text editing', () => {
  let handler, navigations=0;
  const video = {readyState:4, currentTime:10, duration:20};
  const context = vm.createContext({document:{addEventListener:(_,fn)=>handler=fn},
    state:{visible:true}, modalRoot:{childElementCount:0}, lightRoot:{childElementCount:0},
    activeVideoElement:()=>video, selectRelative:()=>navigations++,
  });
  vm.runInContext(source.slice(source.indexOf("  document.addEventListener('keydown'"), source.indexOf('  function currentCharacter()')), context);
  let prevented=0, stopped=0;
  const event = key=>({key,composedPath:()=>[],preventDefault:()=>prevented++,stopImmediatePropagation:()=>stopped++});
  handler(event('ArrowRight')); assert.equal(video.currentTime,13);
  handler(event('ArrowLeft')); assert.equal(video.currentTime,10);
  video.currentTime=19;handler(event('ArrowRight'));assert.equal(video.currentTime,20);
  video.currentTime=1;handler(event('ArrowLeft'));assert.equal(video.currentTime,0);
  handler({...event('ArrowRight'),composedPath:()=>[{matches:()=>true}]});assert.equal(video.currentTime,0);
  assert.equal(navigations,0);assert.equal(prevented,4);assert.equal(stopped,4);
});
