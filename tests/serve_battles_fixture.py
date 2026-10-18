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
    for i in range(16):
        data=io.BytesIO();Image.new('RGB',(400+i,600),['#4182be','#f29463','#7a97bf','#61b18f'][i%4]).save(data,'PNG')
        items.append(store.import_bytes(data.getvalue(),f'Image {i}.png',owner['id'],[],{},'image/png')[0])
        items[-1]['in_all']=i<4
    store.create_set(owner['id'],'Blue dress',[items[i]['id'] for i in [0,4,5,6,7]],preserve_placement=True)
    store.create_set(owner['id'],'White dress',[items[i]['id'] for i in [1,8,9,10,11,12]],preserve_placement=True)
    store.create_set(owner['id'],'Small set',[items[i]['id'] for i in [2,13]],preserve_placement=True)
    if os.environ.get('NAI_RANKS_DEMO') == '1':
        for item in items:
            item['in_all'] = True
        owner['profile'] = {'photos':[m['id'] for m in items[:5]], 'measurements':{'height':{'value':'67.5','status':'confirmed'},'bust':{'value':'35','status':'estimated'},'waist':{'value':'26','status':'confirmed'},'hips':{'value':'37','status':'estimated'},'bra':{'value':'34D (US)','status':'estimated'}}, 'notes':'Example profile for layout checks.', 'revision':'fixture'}
        board={'revision':'fixture', 'ratings':{m['id']:{'rating':1600-i*24.,'played':20,'wins':15-i//2,'losses':5+i//2,'ties':0,'streak':0,'best_streak':5 if i==0 else 0} for i,m in enumerate(items)}, 'recent':[], 'undo':[], 'votes':160, 'session':None}
        board['trophies']=store.battles._awards(board,store.battles._ranked_rows(board,store.battles._entries(owner['id'],'images')))
        store.battles._save({'version':1,'boards':{owner['id']+':images':board}})
    store.save()
    server=runtime['MediaHTTPServer'](('127.0.0.1',8765),store);server.RequestHandlerClass=Handler
    def download(url,*args):
        current_html=html.replace(f'data-nai-media-payload-version="{base_version}"'.encode(),f'data-nai-media-payload-version="{release["version"]}"'.encode())
        if 'manifest.json' in url:
            return json.dumps({'userscript_payload_version':release['version'],'userscript_sha256':hashlib.sha256(code).hexdigest(),'userscript_parts':[server.standalone.BASE+'payload/code'], 'standalone_url':server.standalone.BASE+'html','standalone_sha256':hashlib.sha256(current_html).hexdigest()}).encode()
        return code if url.endswith('code') else current_html
    server.standalone._download=download
    print('READY',flush=True);server.serve_forever()
