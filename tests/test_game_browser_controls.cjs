'use strict';
// Exercise browser-control logic without opening or controlling a real browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../game/web/app.js'), 'utf8');

function fixture() {
  const documentEvents = {};
  const windowEvents = {};
  const window = {addEventListener: (event, callback) => { windowEvents[event] = callback; }};
  window.self = window.top = window;
  const element = {innerHTML: 'original screen', addEventListener() {}, classList: {add() {}, remove() {}}};
  const root = {selectOpen: false,
    querySelector: selector => selector === 'select:open' ? (root.selectOpen ? {} : null) : element,
    addEventListener() {}};
  const calls = [];
  const context = vm.createContext({
    document: {hidden: true, documentElement: {dataset: {}},
      getElementById: () => ({attachShadow: () => root}),
      addEventListener: (event, callback) => { documentEvents[event] = callback; }},
    crypto: {randomUUID: () => 'fixture-request'},
    setTimeout: callback => { callback(); return 1; }, clearTimeout() {},
    calls, studio() {}, resort() {}, saves() {}, expansion() {},
    window,
  });
  vm.runInContext(source, context);
  vm.runInContext(`const actualRender=render;
    save={phase:'night',night:{paused:false,decisions:[],elapsed:0}};
    boot={token:'fixture-token'}; render=()=>{}; notify=()=>{};
    accept=result=>{save=result.state;};
    act=(action,body)=>{calls.push({action,body});return Promise.resolve();};`, context);
  return {context, documentEvents, windowEvents, calls, root, element};
}

(async () => {
  const hidden = fixture();
  hidden.documentEvents.visibilitychange();
  assert.equal(hidden.calls.length, 0, 'Hiding the tab must not pause the night.');
  vm.runInContext('pollGame()', hidden.context);
  assert.equal(hidden.calls.length, 1);
  assert.equal(hidden.calls[0].action, 'tick', 'Hidden tabs still request clock updates.');

  const inFlight = fixture();
  inFlight.context.fetch = async () => ({ok: true,
    json: async () => ({state: {phase: 'night', night: {paused: false, decisions: []}}})});
  await vm.runInContext("performAct('tick',{},true)", inFlight.context);
  assert.equal(inFlight.calls.length, 0, 'Finishing a request while hidden must not enqueue a pause.');
  const picker = fixture();
  vm.runInContext(`render=actualRender; layout=content=>content;
    club=()=>String(save.night.elapsed); hydrateCards=()=>{};`, picker.context);
  picker.root.selectOpen = true;
  for (const elapsed of [1,2,3]) {
    picker.context.fetch = async () => ({ok: true,
      json: async () => ({state: {phase: 'night', night: {paused: false, decisions: [], elapsed}}})});
    await vm.runInContext("performAct('tick',{},true)", picker.context);
    assert.equal(picker.element.innerHTML, 'original screen', 'Clock replies must not replace an open picker.');
    assert.equal(vm.runInContext('save.night.elapsed', picker.context), elapsed, 'The clock still advances.');
  }
  assert.equal(vm.runInContext('renderDeferred', picker.context), true);

  // Dismissing without a change must flush, even if an event paused the clock.
  picker.root.selectOpen = false;
  vm.runInContext('save.night.paused=true;', picker.context);
  picker.context.fetch = async () => ({ok: true, json: async () => ({revision: 0})});
  vm.runInContext('pollGame()', picker.context);
  await vm.runInContext('actionQueue', picker.context);
  assert.equal(picker.element.innerHTML, '3');
  assert.equal(vm.runInContext('renderDeferred', picker.context), false);
  const player = fixture();
  const presence = [];
  player.context.EventSource = class {
    constructor(url) { presence.push(url); }
    close() { presence.push('closed'); }
  };
  vm.runInContext("boot.player_presence='presence-key';connectPlayerPresence();connectPlayerPresence();", player.context);
  assert.deepEqual(presence, ['/game/api/player-presence?key=presence-key']);
  player.windowEvents.pagehide();
  player.windowEvents.pageshow();
  assert.deepEqual(presence.slice(-2), ['closed', '/game/api/player-presence?key=presence-key']);
  player.windowEvents.pagehide();
  player.context.window.top = {};
  player.windowEvents.pageshow();
  assert.equal(presence.at(-1), 'closed', 'The suite shell tracks its own framed tabs.');
  console.log('5 browser-control regression cases passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
