// Drive the built standalone and the disposable companion through their public controls.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

async function run() {
  const [, , base, channel] = process.argv;
  const library = () => fetch(base + '/api/library').then(response => response.json());
  const initial = await library();
  const browser = await chromium.launch({channel, headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1120, height:840}});
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
      assert(await action(editor, 'Save Duo').isDisabled());
      await pick(a).click();
      assert(await pick(a).isDisabled(), 'the second side must use a different photo');
      await pick(b).click();
      await action(editor, 'Swap sides').click();
      if (i === 1) {
        await page.setViewportSize({width:390,height:720});
        await page.emulateMedia({reducedMotion:'reduce'});
      }
      await action(editor, 'Preview flip').click();
      const preview = page.getByRole('dialog', {name:'Duo preview', exact:true});
      const face = preview.locator('.naiDuoFace[aria-hidden="false"]');
      const original = face.locator('.naiFramedSource[src^="blob:"]');
      async function verifySide(id, side) {
        assert.equal(await preview.locator('.naiDuoTurn').getAttribute('data-side'), side);
        const size = await original.evaluate(async image => {
          await image.decode();
          return [image.naturalWidth, image.naturalHeight];
        });
        assert.deepEqual(size, [360,440]);
        assert.equal(await original.getAttribute('alt'), initial.media.find(row => row.id === id).original_name);
        const rotation = await preview.locator('.naiDuoTurn').evaluate(async node => {
          await Promise.all(node.getAnimations().map(animation => animation.finished));
          const style = getComputedStyle(node).transform;
          return new DOMMatrixReadOnly(style === 'none' ? undefined : style).m11;
        });
        assert.equal(Math.round(rotation), side === 'front' ? 1 : -1);
        const box = await face.boundingBox(), view = page.viewportSize();
        assert(box.width > 150 && box.height > 200 && box.x >= 0 && box.x + box.width <= view.width + 1);
      }
      await verifySide(b, 'front');
      if (i === 0) assert.match(await original.evaluate(image => image.style.transform), /scale\(1\.35\)/);
      await action(preview, 'Flip to back').click();
      await verifySide(a, 'back');
      await action(preview, 'Flip to front').click();
      await verifySide(b, 'front');
      await action(preview, 'Close').click();
      assert.equal(writes.length, i, 'choosing and previewing are read-only');
      await action(editor, 'Save Duo').click();
      await editor.waitFor({state:'detached'});
      const saved = (await library()).sets.find(row => row.id === group.id).after_hours_duo;
      assert.deepEqual(saved, {version:1, media_ids:[b,a]});
      await page.getByRole('button', {name:'Edit Duo', exact:true}).click();
      assert((await action(editor, 'Choose front photo').innerText()).includes(initial.media.find(row => row.id === b).original_name));
      await action(editor, 'Close').click();
    }
    assert.equal(writes.length, 2);
    assert.deepEqual(errors, []);
    console.log('Browser picked, swapped, flipped, saved and reopened two Duos at desktop and phone widths.');
  } finally {
    await browser.close();
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
