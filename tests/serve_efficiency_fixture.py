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
    server=runtime['MediaHTTPServer'](('127.0.0.1',8765),store);server.RequestHandlerClass=Handler
    def download(url,*args):
        current_html=html.replace(f'data-nai-media-payload-version="{base_version}"'.encode(),f'data-nai-media-payload-version="{release["version"]}"'.encode())
        if 'manifest.json' in url:
            return json.dumps({'userscript_payload_version':release['version'],'userscript_sha256':hashlib.sha256(code).hexdigest(),'userscript_parts':[server.standalone.BASE+'code'], 'standalone_url':server.standalone.BASE+'html','standalone_sha256':hashlib.sha256(current_html).hexdigest()}).encode()
        return code if url.endswith('code') else current_html
    server.standalone._download=download
    print('READY',flush=True);server.serve_forever()
