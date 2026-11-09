import hashlib
import http.client
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from PIL import Image
from game.library_snapshot import runtime


class CompanionRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.lib=self.root/'library';self.lib.mkdir()
        Image.new('RGB',(96,128),'steelblue').save(self.lib/'photo.png')
        self.data={'_tracking_store':'integration-fixture','characters':[{'id':'a','name':'A'},{'id':'b','name':'B'},{'id':'c','name':'C'}],
                   'media':[{'id':p,'character_id':p,'stored_rel':'photo.png','thumb_rel':'photo.png','in_all':True,'media_type':'image'} for p in ('a','b','c')]}
        (self.lib/'library.json').write_text(json.dumps(self.data));(self.lib/'battles.json').write_text('{"boards":{}}')
        self.before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.lib.iterdir()}
        self.env=patch.dict(os.environ,{'AFTER_HOURS_DATA':str(self.root/'game-data')});self.env.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),runtime().MediaHandler)
        self.server.store=SimpleNamespace(root=self.lib)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.token=None
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.env.stop();self.tmp.cleanup()
    def req(self,method,path,data=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        headers=dict(headers or {})
        if data is not None:
            headers.update({'Content-Type':'application/json','X-Game-Token':self.token or ''});data=json.dumps(data)
        connection.request(method,path,data,headers);r=connection.getresponse();body=r.read();status=r.status;connection.close()
        return status,body
    def boot(self):
        status,body=self.req('GET','/game/api/bootstrap');self.assertEqual(status,200)
        b=json.loads(body);self.token=b['token'];return b
    def action(self,kind,body,revision,ident):
        status,result=self.req('POST','/game/api/action',{'action':kind,'body':body,'revision':revision,'id':ident})
        self.assertEqual(status,200,result);return json.loads(result)

    def test_companion_whole_boundary_owned_media_and_renderer(self):
        b=self.boot();self.assertEqual(b['revision'],0)
        self.assertEqual(self.req('GET','/game/')[0],200)
        self.assertEqual(self.req('GET','/game/api/image/a?original=1')[0],403)
        r=self.action('new',{'selected':['a','b']},0,'choose-founders')
        status,photo=self.req('GET','/game/api/image/a?original=1');self.assertEqual(status,200)
        self.assertEqual(photo,(self.lib/'photo.png').read_bytes())
        self.assertEqual(self.req('GET','/game/api/image/c')[0],403)
        self.assertEqual(self.req('GET','/game/renderer/base.js')[0],200)
        assets=json.loads(self.req('GET','/game/api/renderer')[1]);self.assertIn('base',assets)
        self.assertEqual(self.req('GET','/game/assets/cards/../../game/store.py')[0],404)
        self.assertEqual(self.req('GET','/game/api/bootstrap',headers={'Host':'attacker.invalid'})[0],403)
        status,_=self.req('POST','/game/api/action',{'action':'start','body':{},'id':'bad-origin','revision':r['revision']},headers={'Origin':'https://attacker.invalid'})
        self.assertEqual(status,403)
        self.assertEqual(self.before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.lib.iterdir()})

    def test_http_restore_changes_token_preserves_old_save_and_reload(self):
        b=self.boot();self.action('new',{'selected':['a','b']},0,'choose-founders')
        exported=json.loads(self.req('GET','/game/api/export')[1]);old_path=self.server.after_hours.store.path
        r=self.action('pack',{'pack':'standard'},1,'buy-one-pack')
        status,body=self.req('POST','/game/api/restore',{'revision':r['revision'],'export':exported})
        self.assertEqual(status,200,body);restored=json.loads(body)
        self.assertTrue(old_path.exists());self.assertNotEqual(self.server.after_hours.store.path,old_path)
        status,_=self.req('POST','/game/api/action',{'revision':restored['revision'],'action':'start','body':{},'id':'stale-token'})
        self.assertEqual(status,403)
        self.assertTrue(self.server.after_hours.save_origin.with_suffix('.active.json').exists())

    def test_catalog_refresh_new_character_and_missing_original(self):
        self.boot();self.action('new',{'selected':['a','b']},0,'choose-founders')
        self.data['characters'].append({'id':'d','name':'D'});self.data['media'].append({'id':'d','character_id':'d','in_all':True,'stored_rel':'photo.png'})
        self.data['media'][0]['stored_rel']='missing.png';self.data['media'][0]['thumb_rel']='photo.png'
        (self.lib/'library.json').write_text(json.dumps(self.data))
        status,body=self.req('POST','/game/api/refresh',{'revision':1});self.assertEqual(status,200,body)
        result=json.loads(body);self.assertIn('d',result['catalog']['people']);self.assertNotIn('d',result['state']['people'])
        self.assertEqual(self.req('GET','/game/api/image/a?original=1')[0],404)
        self.assertEqual(self.req('GET','/game/api/image/a')[0],200)

    def test_queued_old_session_cannot_mutate_a_switched_save(self):
        self.boot();self.action('new',{'selected':['a','b']},0,'choose-founders')
        service=self.server.after_hours
        class SwitchWhileWaiting:
            def __enter__(self):service.token='a-new-session-after-restore'
            def __exit__(self,*args):pass
        service.operation_lock=SwitchWhileWaiting()
        before=service.store.read()
        status,_=self.req('POST','/game/api/action',{'revision':1,'action':'start','body':{},'id':'queued-old-session'})
        self.assertEqual(status,403);self.assertEqual(service.store.read(),before)


if __name__=='__main__':unittest.main()
