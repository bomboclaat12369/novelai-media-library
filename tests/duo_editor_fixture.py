"""Run the Duo editor in a real browser and optionally retain its disposable Library for After Hours."""
import argparse
import copy
import gc
import hashlib
import io
import itertools
import json
import runpy
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def seed(store, preview_dir=None):
    owner = store.add_character('Mara Vale' if preview_dir else 'Duo fixture')['id']
    category = store.add_category(owner, 'Studio')['id']
    ids = []
    ranked = []
    for index in range(29):
        image = Image.new('RGB', (360, 440), (32 + index * 18, 48, 120))
        draw = ImageDraw.Draw(image)
        draw.ellipse((30, 55 + index * 5, 220, 255), fill=(90, 168, 192))
        draw.text((24, 360), f'Studio / {index + 1}', fill='white')
        buf = io.BytesIO()
        if preview_dir and index in (0, 1):
            side = 'back' if index == 0 else 'front'
            buf.write((preview_dir / f'studio-{side}.png').read_bytes())
        else:
            image.save(buf, 'PNG')
        main = index < 9 and index not in (1, 3, 4)
        media, _ = store.import_bytes(buf.getvalue(), f'Studio {index + 1}.png', owner,
                                      [category] if main else [], {'kind':'fixture'}, 'image/png')
        store.set_categories(media['id'], [category] if main else [], in_all=main)
        ids.append(media['id'])
        if main:
            ranked.append(media['id'])
    group = store.create_set(owner, 'Nocturne' if preview_dir else 'Studio', ids[:3] + ids[5:], ids[0],
                             cover_source='manual', preserve_placement=True)
    store.create_set(owner, 'Set only', ids[3:5], preserve_placement=True)
    store.set_evolution(group['id'], {'expected':None, 'evolution':{'version':1, 'status':'ready', 'media_ids':ids[:3]}})
    for action, params in [('captain', {'set_id':group['id'], 'media_id':ids[0]}),
                           ('frame', {'media_id':ids[1], 'key':'image:'+ids[1],
                                      'frame':{'x':1 if preview_dir else 8,'y':-1 if preview_dir else -6,
                                               'zoom':1.02 if preview_dir else 1.35,'fit':'fill'}})]:
        revision = store.collection_request('state', {'character_id':owner})['collection']['revision']
        store.collection_request(action, {'character_id':owner, 'revision':revision, **params})
    def battle(action, **body):
        return store.battles.request(action, {'character_id':owner, 'kind':'images', **body})
    state = battle('summary')
    for left, right in itertools.combinations(ranked, 2):
        state = battle('challenge', revision=state['revision'], entry_id=left, opponent_id=right)
        state = battle('vote', revision=state['revision'], pair_id=state['session']['pair']['id'], outcome='left')
    if store._thumbnail_worker is not None:
        store._thumbnail_queue.put(None)
        store._thumbnail_worker.join()


def exercise(directory, runtime_path, html_path, browser, preview_dir=None):
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError('Choose an empty directory for the Duo fixture.')
    runtime = runpy.run_path(str(runtime_path))
    store = runtime['LibraryStore'](directory)
    seed(store, preview_dir)
    before = copy.deepcopy(store.public_library())
    battles = store.battles.path.read_bytes()
    def hashes():
        return [hashlib.sha256((directory / item['stored_rel']).read_bytes()).hexdigest() for item in store.data['media']]
    originals = hashes()
    server = runtime['MediaHTTPServer'](('127.0.0.1', 0), store)
    server.standalone.document = lambda force=False: html_path.read_bytes()
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        subprocess.run(['node', str(ROOT / 'tests/exercise-duo-editor.cjs'),
                        f'http://127.0.0.1:{server.server_port}', browser,
                        *([str(preview_dir)] if preview_dir else [])], check=True, cwd=ROOT)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
    after = store.public_library()
    assert before['characters'] == after['characters'] and before['media'] == after['media']
    assert originals == hashes() and store.battles.path.read_bytes() == battles
    for old, new in zip(before['sets'], after['sets']):
        expected = list(reversed(old['media_ids'][:2]))
        assert new['after_hours_duo'] == {'version':1, 'media_ids':expected}
        assert {k:v for k,v in new.items() if k not in ('after_hours_duo','updated_at')} == {
            k:v for k,v in old.items() if k != 'updated_at'}
    print('Browser verified both Duos and preserved all originals, frames, ownership, Set contents, captain and rankings.', flush=True)
    gc.collect()


if __name__ == '__main__':
    config = json.loads((ROOT / 'release-standalone.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path)
    parser.add_argument('--runtime', type=Path, default=ROOT / 'runtime-src/companion-runtime.pyw')
    parser.add_argument('--html', type=Path, default=ROOT / 'payload' / f"standalone-{config['version']}.html")
    parser.add_argument('--browser', default='msedge', help='Installed Chromium browser channel')
    parser.add_argument('--preview-dir', type=Path, help='Save front/back proof images beside studio-front.png and studio-back.png')
    args = parser.parse_args()
    if args.directory:
        exercise(args.directory.resolve(), args.runtime.resolve(), args.html.resolve(), args.browser, args.preview_dir)
    else:
        with tempfile.TemporaryDirectory(prefix='duo-editor-') as directory:
            exercise(Path(directory), args.runtime.resolve(), args.html.resolve(), args.browser, args.preview_dir)
