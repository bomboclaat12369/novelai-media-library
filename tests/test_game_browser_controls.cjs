'use strict';
// Exercise browser-control logic without opening or controlling a real browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../game/web/app.js'), 'utf8');

function fixture() {
  const documentEvents = {};
  const element = {addEventListener() {}, classList: {add() {}, remove() {}}};
  const root = {querySelector: () => element, addEventListener() {}};
  const calls = [];
  const context = vm.createContext({
    document: {hidden: true, documentElement: {dataset: {}},
      getElementById: () => ({attachShadow: () => root}),
      addEventListener: (event, callback) => { documentEvents[event] = callback; }},
    crypto: {randomUUID: () => 'fixture-request'},
    setTimeout: callback => { callback(); return 1; }, clearTimeout() {},
    calls,
  });
  vm.runInContext(source, context);
  vm.runInContext(`save={phase:'night',night:{paused:false,decisions:[]}};
    boot={token:'fixture-token'}; render=()=>{}; notify=()=>{};
    accept=result=>{save=result.state;};
    act=(action,body)=>{calls.push({action,body});return Promise.resolve();};`, context);
  return {context, documentEvents, calls};
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
  console.log('2 background-tab regression cases passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
