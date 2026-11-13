// Drive the built standalone and the disposable companion through their public controls.
const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require('playwright');

async function checkEditorSize(editor, view) {
  const workspace = await editor.locator('.naiDuoWorkspace').boundingBox();
  assert(workspace.width >= view.width * .94 && workspace.height >= view.height * .85,
    'the editor should fill the viewport');
  const first = await editor.locator('.naiDuoSlotPhoto img').first().boundingBox();
  const tile = await editor.locator('[data-photo-id] img').first().boundingBox();
  const heading = await editor.locator('.naiDuoLibrary h3').boundingBox();
  const search = await editor.getByLabel('Find a Set photo', {exact:true}).boundingBox();
  assert(search.y - (heading.y + heading.height) < 24 && tile.y - (search.y + search.height) < 24,
    'search and photos should sit immediately below the picker heading');
  assert(first.width >= Math.min(275, view.width * .42) && first.height >= Math.min(255, view.height * .23),
    'selected photo at ' + view.width + ' × ' + view.height + ' measured ' + first.width + ' × ' + first.height);
  assert(tile.width >= Math.min(150, view.width * .40) && tile.height >= 150,
    'the eligible photos should have large thumbnails');
  for (const label of ['Preview flip','Save Duo']) {
    const box = await editor.getByRole('button', {name:label, exact:true}).boundingBox();
    assert(box.y >= 0 && box.y + box.height <= view.height + 1, label + ' should stay in view');
  }
  assert(await editor.evaluate(node => node.scrollWidth <= node.clientWidth + 1));
}

async function run() {
  const [, , base, channel, previewDir] = process.argv;
  const library = () => fetch(base + '/api/library').then(response => response.json());
  const initial = await library();
  const browser = await chromium.launch({channel, headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440, height:900},deviceScaleFactor:previewDir ? 3 : 1});
    page.setDefaultTimeout(10000);
    const writes = [];
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/duo')) writes.push(request.postDataJSON());
    });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const [i, group] of initial.sets.entries()) {
      await page.goto(base + '/library/');
      await page.locator('#characterSelect').selectOption(group.character_id);
      await page.locator('#naiSetsCat').click();
      await page.locator('.naiSetTile[data-set-id="' + group.id + '"]').click();
      await page.locator('#naiSetRenameBtn').click();
      await page.getByRole('button', {name:'Create Duo', exact:true}).click();
      const editor = page.getByRole('dialog', {name:'Duo · ' + group.name, exact:true});
      const action = (inside, name) => inside.getByRole('button', {name, exact:true});
      const [a,b] = group.media_ids;
      const pick = id => editor.locator('[data-photo-id="' + id + '"]');
      if (i === 1) {
        await page.setViewportSize({width:390,height:720});
        await page.emulateMedia({reducedMotion:'reduce'});
      }
      assert(await action(editor, 'Save Duo').isDisabled());
      if (group.media_ids.length > 24) {
        const grid = editor.locator('.naiEvolutionPicker');
        assert(await grid.evaluate(el => el.scrollHeight > el.clientHeight));
        await action(editor, 'Next').click();
        await pick(group.media_ids[24]).waitFor();
        await action(editor, 'Previous').click();
        await editor.getByLabel('Find a Set photo', {exact:true}).fill(initial.media.find(item => item.id === a).original_name);
        assert.equal(await grid.locator('button').count(), 1);
        await action(editor, 'Clear search').click();
        assert(await grid.evaluate(node => {
          const boxes = [...node.children].map(tile => tile.getBoundingClientRect());
          const nextRow = boxes.find(box => box.top > boxes[0].top + 1);
          return nextRow && nextRow.top >= boxes[0].bottom;
        }), 'scrollable rows must not overlap the photos above them');
      }
      await pick(a).click();
      assert(await pick(a).isDisabled(), 'the second side must use a different photo');
      await pick(b).click();
      await action(editor, 'Swap sides').click();
      await checkEditorSize(editor, page.viewportSize());
      if (previewDir) await editor.screenshot({scale:'css', path:path.join(previewDir, i === 0 ? 'Duo-editor.png' : 'Duo-editor-phone.png')});
      for (const [slot, id] of [[0, b], [1, a]]) {
        const src = await editor.locator('.naiDuoSlotPhoto img').nth(slot).evaluate(async image => {
          await image.decode();
          return new URL(image.src).pathname;
        });
        assert.equal(src, '/api/media/' + id + '/original');
      }
      await action(editor, 'Preview flip').click();
      const preview = page.getByRole('dialog', {name:'Duo preview', exact:true});
      const face = preview.locator('.naiDuoFace[aria-hidden="false"]');
      const original = face.locator('.naiFramedSource[src^="blob:"]');
      async function verifySide(id, side) {
        assert.equal(await preview.locator('.naiDuoTurn').getAttribute('data-side'), side);
        const digest = await original.evaluate(async image => {
          await image.decode();
          const bytes = await (await fetch(image.src)).arrayBuffer();
          const sha = await crypto.subtle.digest('SHA-256', bytes);
          return Array.from(new Uint8Array(sha), value => value.toString(16).padStart(2,'0')).join('');
        });
        assert.equal(digest, initial.media.find(row => row.id === id).sha256);
        const card = face.locator('.naiEdition[data-edition="duo"][data-duo-side="' + side + '"]');
        const frame = card.locator('.naiEditionFrame');
        assert.deepEqual(await frame.evaluate(async image => {
          await image.decode();
          const canvas = document.createElement('canvas');
          canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(image, 0, 0);
          return [canvas.width, canvas.height, ctx.getImageData(525,750,1,1).data[3],
            ctx.getImageData(220,100,1,1).data[3] >= 250, image.src.startsWith('data:image/webp;')];
        }), [1050,1500,0,true,true]);
        const front = side === 'front';
        const person = initial.characters.find(row => row.id === group.character_id).name;
        assert.equal(await card.locator('.naiEditionLetters').getAttribute('aria-label'),
          [person,group.name,'Duo',front?'Front':'Back','— OVR'].join(' · '));
        assert.equal(await original.getAttribute('alt'), initial.media.find(row => row.id === id).original_name);
        const rotation = await preview.locator('.naiDuoTurn').evaluate(async node => {
          await Promise.all(node.getAnimations().map(animation => animation.finished));
          const style = getComputedStyle(node).transform;
          return new DOMMatrixReadOnly(style === 'none' ? undefined : style).m11;
        });
        assert.equal(Math.round(rotation), side === 'front' ? 1 : -1);
        const box = await card.boundingBox(), view = page.viewportSize();
        assert(box.width >= .90 * Math.min(view.width, (view.height - 44) * .7),
          'the visible artwork should fill the space below its controls');
        assert(box.x >= 0 && box.x + box.width <= view.width + 1 && box.y >= 0 && box.y + box.height <= view.height + 1);
        assert(Math.abs(box.width / box.height - .7) < .005);
        assert(await preview.evaluate(node => node.scrollHeight <= node.clientHeight + 1 && node.scrollWidth <= node.clientWidth + 1));
        if (previewDir && i === 0) await card.screenshot({path:path.join(previewDir,'Duo-'+side+'.png')});
        if (previewDir && side === 'front') await preview.screenshot({
          scale:'css', path:path.join(previewDir, i === 0 ? 'Duo-preview.png' : 'Duo-preview-phone.png')
        });
      }
      await verifySide(b, 'front');
      if (i === 0) {
        const owner = initial.characters.find(row => row.id === group.character_id);
        const zoom = owner.collection.frames['image:' + b].zoom;
        assert((await original.evaluate(image => image.style.transform)).includes('scale(' + zoom + ')'));
      }
      await action(preview, 'Flip to back photo').click();
      await verifySide(a, 'back');
      await action(preview, 'Flip to front photo').press('Enter');
      await verifySide(b, 'front');
      await action(preview, 'Flip to back').click();
      await verifySide(a, 'back');
      await action(preview, 'Close').click();
      assert.equal(writes.length, i === 0 ? 0 : 2, 'choosing and previewing are read-only');
      if (i === 0) {
        // An independently updated Library page can still be connected to the previous companion.
        await page.route('**/api/sets/' + group.id + '/duo', route => route.fulfill({
          status:404, contentType:'application/json', body:JSON.stringify({error:'Not found'})
        }), {times:1});
        await action(editor, 'Save Duo').click();
        await editor.getByRole('alert').filter({hasText:'companion 2.7.82 or later'}).waitFor();
        assert.equal((await library()).sets.find(row => row.id === group.id).after_hours_duo, undefined);
        assert(await action(editor, 'Save Duo').isEnabled());
      }
      await action(editor, 'Save Duo').click();
      await editor.waitFor({state:'detached'});
      const saved = (await library()).sets.find(row => row.id === group.id).after_hours_duo;
      assert.deepEqual(saved, {version:1, media_ids:[b,a]});
      await page.getByRole('button', {name:'Edit Duo', exact:true}).click();
      assert((await action(editor, 'Choose front photo').innerText()).includes(initial.media.find(row => row.id === b).original_name));
      const boardRequest=page.waitForResponse(response=>response.url().endsWith('/api/battles/summary'));
      await action(editor,'Preview flip').click();
      const snapshot=await (await boardRequest).json();
      const overall=await page.evaluate(({snapshot,id})=>{
        const row=snapshot.entries.find(e=>e.duo_side&&e.sets.some(set=>set.id===id));
        return document.getElementById('nai-media-host').shadowRoot.naiCards.ovr(row,snapshot.entries);
      },{snapshot,id:group.id});
      if(i===0)assert(Number.isFinite(overall));
      else assert.equal(overall,null);
      for(const side of ['front','back']){
        const label=await preview.locator('[data-duo-side="'+side+'"] .naiEditionLetters').getAttribute('aria-label');
        assert(label.endsWith(' · '+(overall??'—')+' OVR'));
      }
      await action(preview,'Close').click();
      await action(editor, 'Close').click();
    }
    await page.evaluate(() => document.getElementById('nai-media-host').shadowRoot.naiCards.openEditionGallery());
    await page.getByRole('button', {name:'Preview Duo frame',exact:true}).click();
    assert.equal(await page.locator('.naiEditionFramePreview').evaluate(async image => {
      await image.decode();
      return image.naturalWidth;
    }),1050);
    assert.equal(writes.length, 3);
    assert.deepEqual(writes[0], writes[1], 'retry must keep both original choices');
    assert.deepEqual(errors, []);
    console.log('Browser picked, swapped, flipped, saved and reopened two Duos at desktop and phone widths.');
  } finally {
    await browser.close();
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
