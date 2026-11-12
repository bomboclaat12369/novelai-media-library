"""Hosted Windows smoke check against the staged HTML and companion, using real Edge."""
import json
import runpy
import sys
import threading
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[1]
library = Path(sys.argv[1])
runtime = runpy.run_path(str(root / 'runtime-src/companion-runtime.pyw'))
store = runtime['LibraryStore'](library)
group = store.data['sets'][0]
initial = list(group['after_hours_evolution']['media_ids'])
version = json.loads((root / 'release-standalone.json').read_text())['version']
page_bytes = (root / 'payload' / ('standalone-' + version + '.html')).read_bytes()
with runtime['MediaHTTPServer'](('127.0.0.1', 0), store) as server:
    server.standalone.document = lambda *args, **kwargs: page_bytes
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width':1440,'height':1000})
            origin = 'http://127.0.0.1:' + str(server.server_port)
            page.goto(origin + '/library/')
            page.get_by_text('Local library connected', exact=True).wait_for()
            page.locator('#characterSelect').select_option(group['character_id'])
            page.locator('#naiSetsCat').click()
            page.locator('[data-set-id="' + group['id'] + '"]').first.click()
            page.locator('#naiSetRenameBtn').click()
            page.locator('#naiCurateEvolution').click()
            forms = page.locator('.naiEvolutionForms article')
            expect(forms).to_have_count(3)
            forms.nth(0).drag_to(forms.nth(2))
            order = [initial[1], initial[2], initial[0]]
            assert forms.evaluate_all('(tiles) => tiles.map(tile => tile.dataset.formId)') == order
            page.get_by_role('button', name='Preview forms', exact=True).click()
            preview = page.get_by_role('dialog', name='Evolution preview')
            images = preview.locator('img.naiFramedSource')
            expect(images).to_have_count(3)
            for image in images.all():
                expect(image).to_have_js_property('naturalWidth', 270)
                assert image.evaluate('(im) => im.getBoundingClientRect().width') > 0
            preview.get_by_role('button', name='Close').click()
            page.get_by_role('button', name='Mark ready').click()
            expect(page.locator('.naiEvolutionForms')).to_have_count(0)
            page.locator('#naiCurateEvolution').click()
            expect(forms).to_have_count(3)
            assert forms.evaluate_all('(tiles) => tiles.map(tile => tile.dataset.formId)') == order
            assert json.loads(store.db_path.read_text('utf-8'))['sets'][0]['after_hours_evolution']['media_ids'] == order
            print('Edge', browser.version, 'drag, framed originals, ready save and reopen passed.')
            browser.close()
    finally:
        server.shutdown()
        thread.join()
