"""Real local API with an in-memory release source; no GitHub traffic."""
import hashlib
import copy
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
standalone_config=json.loads((root/'release-standalone.json').read_text())
standalone_version=standalone_config['version']
html=(root/f'payload/standalone-{standalone_version}.html').read_bytes()
release={'version':base_version,'standalone_version':standalone_version}
class Handler(runtime['MediaHandler']):
    def do_GET(self):
        if self.path.startswith('/test/release/'):
            body=download(self.server.standalone.BASE+self.path.split('/test/release/',1)[1])
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        super().do_GET()

    def do_POST(self):
        if self.path=='/test/card-arrival' and os.environ.get('NAI_CARD_FEATURES_DEMO')=='1':
            self._read_json()
            with self.store.lock:
                item=copy.deepcopy(self.store.data['media'][0]);item.update(id='new-arrival',original_name='New arrival fixture.png',in_all=True)
                self.store.data['media'].append(item);self.store.save()
            self._send_json(200,{'id':item['id']});return
        if self.path=='/test/advance':
            release.update(self._read_json());self.server.ui_updates.checked_at=0
            self._send_json(200,{'ok':True});return
        super().do_POST()
with tempfile.TemporaryDirectory() as directory:
    store=runtime['LibraryStore'](Path(directory));store._queue_image_thumbnail=lambda *a:None
    owner=store.add_character('Nikki fixture');items=[]
    for i in range(16):
        data=io.BytesIO();size=(1600+i,2400)
        if os.environ.get('NAI_LANDSCAPE_DEMO')=='1':
            if i%4==1:size=(2400,1600+i)
            elif i%4==2:size=(1800+i,1800+i)
        image=Image.new('RGB',size,['#4182be','#f29463','#7a97bf','#61b18f'][i%4]);fmt='PNG';mime='image/png'
        if os.environ.get('NAI_LANDSCAPE_DEMO')=='1' and i==3:
            image=Image.new('RGB',(2403,1600),'#61b18f');exif=Image.Exif();exif[274]=6;image.save(data,'JPEG',exif=exif);fmt='JPEG';mime='image/jpeg'
        else:image.save(data,'PNG')
        items.append(store.import_bytes(data.getvalue(),f'Image {i}.{fmt.lower()}',owner['id'],[],{},mime)[0])
        items[-1]['in_all']=i<4
    store.create_set(owner['id'],'Blue dress',[items[i]['id'] for i in [0,4,5,6,7]],preserve_placement=True)
    store.create_set(owner['id'],'White dress',[items[i]['id'] for i in [1,8,9,10,11,12]],preserve_placement=True)
    store.create_set(owner['id'],'Small set',[items[i]['id'] for i in [2,13]],preserve_placement=True)
    owner['categories']=[{'id':'dress','name':'Dress','media_type':'image'},{'id':'bikini','name':'Bikini','media_type':'image'}]
    owner['set_categories']=[{'id':'dresses','name':'Dresses'}]
    for i,item in enumerate(items):item['categories']=['dress' if i%2==0 else 'bikini']
    for group in store.data['sets']:group['categories']=['dresses']
    if os.environ.get('NAI_RAPID_DEMO') == '1':
        owner['categories'] += [{'id':name.lower(),'name':name,'media_type':'image','ghost':name=='Old'} for name in ['Lingerie','Other','Ass','Naked','Old']]
        for i in range(60):
            data=io.BytesIO();Image.new('RGB',(200,260),(40+i*3,80+i,120+i)).save(data,'PNG')
            pending=Path(directory)/f'queue-{i}.tmp';pending.write_bytes(data.getvalue())
            queued=store._register_file(pending,f'Queue {i:02d}.png',owner['id'],[],{},'image/png',pending=True)[0]
            thumb=store.thumb_dir/(queued['id']+'.jpg');Image.open(io.BytesIO(data.getvalue())).save(thumb,'JPEG');queued['thumb_rel']=thumb.relative_to(store.root).as_posix()
    if os.environ.get('NAI_VIEWER_DEMO') == '1':
        import subprocess
        clip=Path(directory)/'fixture-video.webm'
        subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','color=c=blue:s=320x240:d=2','-c:v','libvpx','-y',str(clip)],check=True)
        store.import_bytes(clip.read_bytes(),'Fixture video.webm',owner['id'],[],{},'video/webm')
    if os.environ.get('NAI_RANKS_DEMO') == '1':
        if os.environ.get('NAI_CARD_FEATURES_DEMO') == '1':
            for i in range(16,360):
                item=copy.deepcopy(items[i%16]);item.update(id='card-fixture-'+str(i),original_name=f'Card fixture {i:03d}.png')
                store.data['media'].append(item);items.append(item)
        for item in items:
            item['in_all'] = True
        owner['profile'] = {'photos':[m['id'] for m in items[:5]], 'measurements':{'height':{'value':'67.5','status':'confirmed'},'bust':{'value':'35','status':'estimated'},'waist':{'value':'26','status':'confirmed'},'hips':{'value':'37','status':'estimated'},'bra':{'value':'34D (US)','status':'estimated'}}, 'notes':'Example profile for layout checks.', 'revision':'fixture'}
        board={'revision':'fixture', 'ratings':{m['id']:{'rating':1600-i*24.,'played':20,'rd':80.,'opponents':{o['id']:1 for o in items if o['id']!=m['id']},'wins':15-i//2,'losses':5+i//2,'ties':0,'streak':0,'best_streak':5 if i==0 else 0} for i,m in enumerate(items)}, 'recent':[], 'undo':[], 'votes':160, 'session':None}
        board['trophies']=store.battles._awards(board,store.battles._ranked_rows(board,store.battles._entries(owner['id'],'images')))
        if os.environ.get('NAI_CARD_FEATURES_DEMO') == '1':
            for score in board['ratings'].values():
                score['opponents']=dict(list(score['opponents'].items())[:8]);score['wins']=15;score['losses']=5
            board['cards']={'started_at':'2026-10-22T00:00:00Z','eligible':[m['id'] for m in items],'arrivals':{},'leaders':{items[1]['id']:'2026-10-22T00:00:00Z'},'best':{}}
        store.battles._save({'version':1,'boards':{owner['id']+':images':board}})
    if os.environ.get('NAI_CARD_LAYOUT_DEMO') == '1':
        video=copy.deepcopy(items[0]);video.update(id='f'*32,media_type='video',original_name='Set video.webm')
        image=Image.new('RGB',(1280,720),'#503e8a');target=store.thumb_dir/'video-fixture.jpg';image.save(target)
        video['thumb_rel']=target.relative_to(store.root).as_posix();store.data['media'].append(video)
        # Six stills plus a video, and a larger set that must scroll after two rows.
        store.data['sets'][0]['media_ids'].append(video['id'])
        extra=[]
        for i,original in enumerate(items):
            item=copy.deepcopy(original);item.update(id=f'{0xf0000000+i:032x}',in_all=False,categories=[]);store.data['media'].append(item);extra.append(item['id'])
        store.create_set(owner['id'],'Large set',extra,preserve_placement=True)
        owner['collection']={'revision':'legacy','captains':{g['id']:g['media_ids'][0] for g in store.data['sets']}}
    elif os.environ.get('NAI_CARD_FEATURES_DEMO') == '1':
        owner['collection']={'revision':'chosen','captain_schema':2,'captains':{g['id']:g['media_ids'][0] for g in store.data['sets']}}
    store.save()
    server=runtime['MediaHTTPServer'](('127.0.0.1',8765),store);server.RequestHandlerClass=Handler
    def download(url,*args):
        current_html=html.replace(f'data-nai-media-payload-version="{standalone_version}"'.encode(),f'data-nai-media-payload-version="{release["standalone_version"]}"'.encode())
        if 'manifest.json' in url:
            return json.dumps({'userscript_payload_version':release['version'],'userscript_sha256':hashlib.sha256(code).hexdigest(),'userscript_parts':[server.standalone.BASE+'payload/code'], 'standalone_version':release['standalone_version'],'standalone_url':server.standalone.BASE+'html','standalone_sha256':hashlib.sha256(current_html).hexdigest()}).encode()
        return code if url.endswith('code') else current_html
    server.standalone._download=download
    print('READY',flush=True);server.serve_forever()
