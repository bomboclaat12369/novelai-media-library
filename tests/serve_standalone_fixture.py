"""Isolated real companion for the standalone browser integration check."""
import base64
import hashlib
import io
import json
import os
import uuid
import runpy
import subprocess
import tempfile
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parent.parent
runtime = runpy.run_path(str(root / 'runtime-src/companion-runtime.pyw'))
with tempfile.TemporaryDirectory(prefix='nai-standalone-') as directory:
    store = runtime['LibraryStore'](Path(directory))
    c = store.add_character('Standalone fixture')
    cat = store.add_category(c['id'], 'Dress')
    items = []
    for i, size in enumerate([(800,1000),(900,1200),(1200,800),(1000,1000),(800,1000),(800,1000)]):
        data = io.BytesIO()
        Image.new('RGB', size, ['#ab708b','#536ea4','#4c9188','#988052','#796391','#4c6670'][i]).save(data, format='JPEG')
        m, _ = store.import_bytes(data.getvalue(), f'Portrait {i+1}.jpg', c['id'], [cat['id']], {'kind':'local'}, 'image/jpeg')
        items.append(m)
    video_path = Path(directory)/'fixture.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=navy:s=320x480:d=2','-c:v','libx264','-pix_fmt','yuv420p',str(video_path)],check=True)
    video,_=store.import_bytes(video_path.read_bytes(),'Video.mp4',c['id'],[],{'kind':'local'},'video/mp4')
    store.create_set(c['id'],'Mixed set',[items[0]['id'],video['id']],preserve_placement=True)
    for i,m in enumerate(items):m['created_at']=f'2020-01-01T00:00:{i:02d}Z'
    for i in range(int(os.environ.get('NAI_FIXTURE_EXTRA_IMAGES','0'))):
        m=dict(items[i % len(items)]);m['id']=uuid.uuid4().hex;m['original_name']=f'Grid {i}.jpg';m['created_at']=f'2021-01-01T00:{i//60:02d}:{i%60:02d}Z'
        store.data['media'].append(m)
    store.save()
    server=runtime['MediaHTTPServer'](('127.0.0.1',8765),store)
    version=os.environ.get('NAI_UI_VERSION',json.loads((root/'release-userscript.json').read_text())['version'])
    html=(root/f'payload/standalone-{version}.html').read_bytes()
    manifest={'standalone_url':server.standalone.BASE+f'payload/standalone-{version}.html','standalone_sha256':hashlib.sha256(html).hexdigest()}
    server.standalone._download=lambda url,*args:json.dumps(manifest).encode() if url.endswith('manifest.json') else html
    # Exercise verified download, persistent offline fallback, and tamper rejection.
    assert server.standalone.document()==html
    offline=runtime['StandaloneUI'](store.root)
    def fail(*args):raise OSError('offline')
    offline._download=fail
    assert offline.document()==html
    bad=runtime['StandaloneUI'](Path(directory)/'bad-cache')
    bad._download=lambda url,*args:json.dumps(manifest).encode() if url.endswith('manifest.json') else b'bad'
    try:bad.document();raise AssertionError('invalid digest accepted')
    except ValueError:pass
    print(json.dumps({'ready':True,'character':c['id'],'images':[m['id'] for m in items],'video':video['id']}),flush=True)
    server.serve_forever()
