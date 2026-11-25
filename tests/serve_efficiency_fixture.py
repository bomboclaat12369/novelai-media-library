"""Real local API with an in-memory release source; no GitHub traffic."""
import hashlib
import io
import json
import os
import runpy
import tempfile
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parents[1]
runtime=runpy.run_path(str(root/'runtime-src/companion-runtime.pyw'))
config=json.loads((root/os.environ.get('NAI_RELEASE_CONFIG','release-userscript.json')).read_text())
code=b''.join((root/p).read_bytes() for p in config['parts'])
base_version=config['version']
html=(root/f'payload/standalone-{base_version}.html').read_bytes()
release={'version':base_version}
class Handler(runtime['MediaHandler']):
    def do_GET(self):
        if self.path.startswith('/test/release/'):
            body=download(self.server.standalone.BASE+self.path.split('/test/release/',1)[1])
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        super().do_GET()

    def do_POST(self):
        if self.path=='/test/advance':
            release['version']=self._read_json()['version'];self.server.ui_updates.checked_at=0
            self._send_json(200,{'ok':True});return
        super().do_POST()
with tempfile.TemporaryDirectory() as directory:
    store=runtime['LibraryStore'](Path(directory));store._queue_image_thumbnail=lambda *a:None
    owner=store.add_character('Nikki fixture');items=[]
    for i,size in enumerate([(400,800),(1000,1000),(800,900)]):
        data=io.BytesIO();Image.new('RGB',size,['#4182be','#f29463','#7a97bf'][i]).save(data,'PNG')
        items.append(store.import_bytes(data.getvalue(),f'Image {i}.png',owner['id'],[],{},'image/png')[0])
    store.create_set(owner['id'],'Blue dress',[items[0]['id'],items[1]['id']],preserve_placement=True)
    if os.environ.get('NAI_POST_HISTORY_FIXTURE'):
        from test_runtime_post_history import add_fixture
        add_fixture(store, owner['id'], items, Path(directory) / 'original-post')
        for n in range(3):
            blob=io.BytesIO()
            Image.new('RGB',(640,800),(114,81,50+n*20)).save(blob,'PNG')
            store.import_bytes(blob.getvalue(),f'Crop example {n+1}.png',owner['id'],[],{},'image/png')
    if os.environ.get('NAI_LIVE_POST_NAVIGATION'):
        import sys, threading
        from unittest.mock import patch
        sys.path[:0] = [str(root/'duplicate-review/tests'), str(root/'duplicate-review')]
        from test_organizer import fixture
        from library_bridge import LibraryClient
        from app import make_server
        import tracking
        # These two local programs share only disposable data.
        patch.object(LibraryClient, 'request', side_effect=ValueError('Offline test library')).start()
        engine, bulk, organizer, ids = fixture(Path(directory)/'workbench')
        record = bulk.current['source_catalog'][ids[4]]
        store.import_bytes(Path(record['path']).read_bytes(), 'Workbench link.jpg', owner['id'], [], {'kind':'local'}, 'image/jpeg')
        store.tracking.ingest(tracking.export_history(engine, bulk, organizer)['events'])
        workbench = make_server(engine)
        os.environ['LOCALAPPDATA'] = str(Path(directory)/'profile')
        address = Path(os.environ['LOCALAPPDATA'])/'LocalDuplicateReview'/'running-url.txt'
        address.parent.mkdir(parents=True)
        address.write_text(f'http://127.0.0.1:{workbench.server_port}/organizer')
        threading.Thread(target=workbench.serve_forever, daemon=True).start()
    server=runtime['MediaHTTPServer'](('127.0.0.1',int(os.environ.get('NAI_TEST_PORT','8765'))),store);server.RequestHandlerClass=Handler
    def download(url,*args):
        current_html=html.replace(f'data-nai-media-payload-version="{base_version}"'.encode(),f'data-nai-media-payload-version="{release["version"]}"'.encode())
        if 'manifest.json' in url:
            return json.dumps({'userscript_payload_version':release['version'],'userscript_sha256':hashlib.sha256(code).hexdigest(),'userscript_parts':[server.standalone.BASE+'payload/code'], 'standalone_url':server.standalone.BASE+'html','standalone_sha256':hashlib.sha256(current_html).hexdigest()}).encode()
        return code if url.endswith('code') else current_html
    server.standalone._download=download
    print('READY',server.server_port,flush=True);server.serve_forever()
