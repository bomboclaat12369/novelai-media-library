"""Exercise the assembled Set editor against a real disposable companion.

Pass an empty directory to keep the resulting two-character library for the game's reader test.
"""
import argparse
import copy
import gc
import io
import json
import runpy
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def exercise(destination, runtime_path=None):
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError('The fixture needs an empty directory.')
    runtime = runpy.run_path(str(runtime_path or ROOT / 'runtime-src/companion-runtime.pyw'))
    store = runtime['LibraryStore'](destination)
    for count, name in [(3, 'Amber'), (4, 'Indigo')]:
        owner = store.add_character(name)['id']
        main = store.add_category(owner, 'Studio')['id']
        ids = []
        for i in range(count + 1):
            image = Image.new('RGB', (270, 360), (50 * count, 35 + 23 * i, 85))
            draw = ImageDraw.Draw(image)
            draw.ellipse((10 + 20*i, 70, 200, 230), fill=(55, 150, 180))
            draw.text((15, 300), f'{name} / {i + 1}', fill='white')
            encoded = io.BytesIO()
            image.save(encoded, format='PNG')
            item, _ = store.import_bytes(encoded.getvalue(), f'{name} {i + 1}.png', owner,
                                         [main] if i in (0, count - 1) else [], {'kind':'fixture'}, 'image/png')
            ids.append(item['id'])
        group = store.create_set(owner, name + ' Session', ids, ids[0], cover_source='manual')
        def collection(action, **body):
            current = store.collection_request('state', {'character_id':owner})['collection']
            store.collection_request(action, {'character_id':owner, 'revision':current['revision'], **body})
        collection('captain', set_id=group['id'], media_id=ids[count - 1])
        collection('frame', media_id=ids[1], key='image:'+ids[1],
                   frame={'x':6, 'y':-8, 'zoom':1.25, 'fit':'fill'})
    if store._thumbnail_worker is not None:
        store._thumbnail_queue.put(None)
        store._thumbnail_worker.join()
    before = store.public_library()
    server = runtime['MediaHTTPServer'](('127.0.0.1', 0), store)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        subprocess.run(['node', str(ROOT / 'tests/exercise-evolution-editor.cjs'),
                        str(server.server_address[1])], check=True, cwd=ROOT)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
        gc.collect()
    after = store.public_library()
    assert before['characters'] == after['characters']
    for old, new in zip(before['media'], after['media']):
        assert old == new, [key for key in old.keys() | new.keys() if old.get(key) != new.get(key)]
    for count, old, new in zip((3, 4), before['sets'], after['sets']):
        group = copy.deepcopy(new)
        evolution = group.pop('after_hours_evolution')
        original_order = old['media_ids']
        expected = ([original_order[1], original_order[0], original_order[2]] if count == 3 else
                    [original_order[0], original_order[1], original_order[2], original_order[4]])
        assert evolution == {'version':1, 'status':'ready', 'media_ids':expected}
        assert any(not store.media_item(mid)['in_all'] for mid in expected)
        assert {k:v for k,v in group.items() if k != 'updated_at'} == {k:v for k,v in old.items() if k != 'updated_at'}
    print(f'Editor saved verified three- and four-form Sets in {destination}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path)
    parser.add_argument('--runtime', type=Path, help='Use a downloaded companion source for a published-version check.')
    args = parser.parse_args()
    if args.directory:
        exercise(args.directory.resolve(), args.runtime)
    else:
        with tempfile.TemporaryDirectory(prefix='evolution-editor-') as directory:
            exercise(Path(directory), args.runtime)
