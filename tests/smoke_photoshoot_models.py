"""Optional real-model smoke check with synthetic scenes, not an accuracy benchmark.

Usage: PYTHONPATH=<matching-dependencies> python tests/smoke_photoshoot_models.py <model-dir>
The directory must already contain the two verified ONNX files. No downloads.
"""
import io
import json
import os
import runpy
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw

runtime = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'runtime-src/companion-runtime.pyw'))


def scene(setting, shirt, x=310):
    image = Image.new('RGB', (640, 960), '#cdbf9d' if setting == 'room' else '#98bac7')
    draw = ImageDraw.Draw(image)
    if setting == 'room':
        draw.rectangle((0, 680, 640, 960), fill='#9b7352')
        for y in range(680, 960, 35):
            draw.line((0, y, 640, y), fill='#55402c', width=3)
        for x0 in (15, 430):
            draw.rectangle((x0, 70, x0 + 180, 490), fill='#355872', outline='#eee8db', width=12)
            draw.line((x0 + 90, 70, x0 + 90, 490), fill='#eee8db', width=8)
            draw.line((x0, 280, x0 + 180, 280), fill='#eee8db', width=8)
        draw.rectangle((25, 540, 195, 730), fill='#5f3e29', outline='#332a25', width=8)
        draw.ellipse((45, 460, 160, 560), fill='#386f46')
    else:
        draw.rectangle((0, 540, 640, 960), fill='#506c3e')
        for x0 in (30, 500):
            draw.rectangle((x0 + 30, 160, x0 + 70, 720), fill='#4d3b2d')
            for y in (70, 200, 330):
                draw.ellipse((x0 - 80, y, x0 + 180, y + 190), fill='#254f40')
        draw.polygon(((100, 960), (520, 960), (340, 540), (290, 540)), fill='#c7b89f')
    # Simple fully clothed mannequin; moving it and changing clothing changes the foreground.
    draw.ellipse((x-45, 220, x+45, 320), fill='#cc9e7b')
    draw.polygon(((x-60, 320), (x+60, 320), (x+95, 610), (x-95, 610)), fill=shirt)
    draw.rectangle((x-65, 610, x-10, 845), fill='#293747')
    draw.rectangle((x+10, 610, x+65, 845), fill='#293747')
    output = io.BytesIO(); image.save(output, 'JPEG', quality=94)
    return output.getvalue()


with tempfile.TemporaryDirectory() as directory:
    store = runtime['LibraryStore'](Path(directory)); store._queue_image_thumbnail = lambda *a: None
    owner = store.add_character('Mikayla smoke fixture')
    for setting, color in [('room', '#d74b35'), ('garden', '#405ed7')]:
        ids = [store.import_bytes(scene(setting, color, x), f'{setting}-{x}.jpg', owner['id'], [], {}, 'image/jpeg')[0]['id'] for x in (280, 365)]
        store.create_set(owner['id'], setting, ids)
    matcher = store.outfit_matcher; matcher.cache.mkdir()
    for name in ('fashion-siglip.onnx', 'dinov2-base.onnx'):
        source = Path(sys.argv[1]) / name
        os.link(source, matcher.cache / name)
    import base64
    before = store.db_path.read_bytes()
    report = []
    for setting, color in [('room', '#405ed7'), ('garden', '#d74b35')]:
        body = {'character_id': owner['id'], 'image_base64': base64.b64encode(scene(setting, color, 330)).decode()}
        for warm in (False, True):
            job = matcher.start(body); matcher.thread.join(90); result = matcher.status(job['id'])
            assert not result['running'] and not result.get('error'), result
            assert result['matching_mode'] == 'photoshoot' and not result['issues'], result
            assert result['results'][0]['name'] == setting, result['results']
            if warm:
                assert result['new_images'] == 0 and result['cached_images'] == 4, result
            report.append({'scene': setting, 'warm': warm, 'seconds': result['elapsed_seconds'], 'new_images': result['new_images'], 'best': result['results'][0]['name']})
    assert store.db_path.read_bytes() == before
    print(json.dumps(report, indent=2))
