// The production editor sends real requests to the disposable companion started by evolution_editor_fixture.py.
const assert = require('node:assert/strict');
const {fixture, waitFor, delay} = require('./ui-fixture.cjs');
const base = 'http://127.0.0.1:' + Number(process.argv[2]);
const library = async () => (await fetch(base + '/api/library')).json();
const findButton = (root, text) => [...root.querySelectorAll('button')].find(button => button.textContent === text);

async function run() {
  const initial = await library();
  const writes = [], originals = [];
  const f = await fixture({configure(w) {
    const normal = w.GM_xmlhttpRequest;
    w.GM_xmlhttpRequest = options => {
      const path = new URL(options.url).pathname;
      if (path !== '/api/library' && !path.endsWith('/evolution') && !path.endsWith('/original')) return normal(options);
      const method = options.method || 'GET';
      if (path.endsWith('/evolution')) writes.push(JSON.parse(options.data));
      if (path.endsWith('/original')) originals.push(path.split('/')[3]);
      fetch(base + path, {method, headers:options.headers, body:method === 'POST' ? options.data : undefined}).then(async response => {
        if (!w.document) return;
        if (options.responseType === 'blob') {
          options.onload({status:response.status, response:new w.Blob([await response.arrayBuffer()])});
        } else options.onload({status:response.status, responseText:await response.text()});
      }).catch(error => options.onerror?.(error));
      return {abort() {}};
    };
  }});
  const {root, w, errors} = f;
  const wait = fn => waitFor(fn, errors, 5000);
  try {
    for (const [which, group] of initial.sets.entries()) {
      const choices = group.media_ids;
      const count = which === 0 ? 3 : 4;
      const owner = root.getElementById('characterSelect');
      owner.value = group.character_id;
      owner.dispatchEvent(new w.Event('change', {bubbles:true}));
      const open = async () => {
        (await wait(() => root.getElementById('naiSetsCat'))).click();
        const tile = await wait(() => root.querySelector('.naiSetTile[data-set-id="' + group.id + '"]'));
        tile.click();
        (await wait(() => root.getElementById('naiSetRenameBtn'))).click();
        (await wait(() => root.getElementById('naiCurateEvolution'))).click();
        return wait(() => root.querySelector('.naiEvolution'));
      };
      let editor = await open();
      const ids = () => [...editor.querySelectorAll('[data-form-id]')].map(tile => tile.dataset.formId);
      const choose = index => editor.querySelector('[data-photo-id="' + choices[index] + '"]').click();
      assert.deepEqual(ids(), [choices[count - 1]], 'Designated captain prefilled the final slot');
      assert.equal(findButton(editor, 'Mark ready').disabled, true);
      findButton(editor, 'Save candidate').click();
      await wait(() => !editor.isConnected);
      assert.equal((await library()).sets[which].after_hours_evolution.status, 'candidate');
      const parent = root.getElementById('naiCurateEvolution').closest('.modalWrap');
      parent.querySelector('[data-close]').click();
      root.getElementById('naiManageSetsBtn').click();
      const filter = await wait(() => root.querySelector('[aria-label="Filter Sets by evolution status"]'));
      filter.value = 'candidate';
      filter.dispatchEvent(new w.Event('change'));
      findButton(root.getElementById('naiSetToolsList'), 'Curate evolution').click();
      editor = await wait(() => root.querySelector('.naiEvolution'));
      for (let i = 0; i < count - 1; i++) choose(i);
      if (count === 3) editor.querySelector('[aria-label="Move form 2 earlier"]').click();
      else {
        findButton(editor.querySelector('[data-form-id="' + choices[3] + '"]'), 'Change').click();
        choose(4);
      }
      const expected = count === 3 ? [choices[1], choices[0], choices[2]] : [choices[0], choices[1], choices[2], choices[4]];
      assert.deepEqual(ids(), expected);
      const beforePreview = writes.length;
      findButton(editor, 'Preview forms').click();
      const preview = await wait(() => root.querySelector('[aria-label="Evolution preview"]'));
      await wait(() => [...preview.querySelectorAll('.naiFramedSource')].filter(image => image.src.startsWith('blob:')).length === count);
      assert.deepEqual(originals.slice(-count).sort(), [...expected].sort());
      assert.equal(writes.length, beforePreview);
      findButton(preview, 'Close').click();
      findButton(editor, 'Mark ready').click();
      await wait(() => !editor.isConnected);
      assert.deepEqual((await library()).sets[which].after_hours_evolution, {version:1,status:'ready',media_ids:expected});
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(writes.map(change => change.evolution.status), ['candidate','ready','candidate','ready']);
  } catch (error) {
    console.error('Editor check failed after', writes.map(change => change.evolution?.status), error);
    throw error;
  } finally { await delay(80); f.dom.window.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
