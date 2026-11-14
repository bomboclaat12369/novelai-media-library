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
from game.server import build_server


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

    def test_new_career_preserves_paid_pack_and_reopens_fresh_catalog(self):
        self.boot();self.action('new',{'selected':['a','b']},0,'choose-founders')
        original=self.action('pack',{'pack':'standard'},1,'buy-one-pack')['state']
        service=self.server.after_hours
        previous=service.store;origin=service.save_origin
        self.data['characters'].append({'id':'d','name':'D'})
        self.data['media'].append({'id':'d','character_id':'d','in_all':True,'stored_rel':'photo.png'})
        (self.lib/'library.json').write_text(json.dumps(self.data))
        status,body=self.req('POST','/game/api/new-career',{'revision':2})
        self.assertEqual(status,200,body)
        self.assertTrue(json.loads(body)['new_career']);self.assertIsNone(json.loads(body)['state'])
        self.assertEqual(previous.read()['state'],original)
        self.assertNotEqual(service.store.path,previous.path)
        # Both a queued action and a repeated reset from the old session fail.
        self.assertEqual(self.req('POST','/game/api/new-career',{'revision':0})[0],403)
        self.assertEqual(self.req('POST','/game/api/action',{'revision':0,'action':'new','body':{'selected':['a','b']},'id':'old-tab-new'})[0],403)
        boot=self.boot();self.assertIn('d',boot['catalog']['people'])
        self.assertEqual(boot['revision'],0)
        service.store.backup()
        self.assertEqual([b['id'] for b in service.store.backups()],['previous-career.sqlite3'])
        # A restart before choosing founders must retain the new empty save and recovery.
        reopened=build_server(0,save=origin,library=self.lib)
        try:
            self.assertEqual(reopened.store.path,service.store.path)
            self.assertIsNone(reopened.store.read()['state'])
            self.assertEqual(reopened.store.backups()[0]['label'],'Previous career')
        finally:reopened.server_close()
        fresh=self.action('new',{'selected':['b','d']},0,'new-founders')['state']
        self.assertEqual((fresh['day'],fresh['cash'],fresh['totals']['packs']),(1,600,0))
        self.assertEqual(set(fresh['people']),{'b','d'});self.assertEqual(len(fresh['owned']),2)
        self.assertIsNone(fresh['pending_pack'])
        reopened=build_server(0,save=origin,library=self.lib)
        try:self.assertEqual(reopened.store.read()['state'],fresh)
        finally:reopened.server_close()
        status,body=self.req('POST','/game/api/restore',{'revision':1,'backup':'previous-career.sqlite3'})
        self.assertEqual(status,200,body);self.assertEqual(json.loads(body)['state'],original)

    def test_new_career_failure_keeps_active_career(self):
        self.boot()
        self.assertEqual(self.req('POST','/game/api/new-career',{'revision':0})[0],400)
        self.action('new',{'selected':['a','b']},0,'choose-founders')
        service=self.server.after_hours;previous=service.store
        original=previous.read();token=service.token
        self.assertEqual(self.req('POST','/game/api/new-career',{'revision':0})[0],409)
        with patch.object(previous,'backup',side_effect=OSError('disk full')):
            self.assertEqual(self.req('POST','/game/api/new-career',{'revision':1})[0],500)
        with patch('game.server.os.replace',side_effect=OSError('pointer unavailable')):
            self.assertEqual(self.req('POST','/game/api/new-career',{'revision':1})[0],500)
        self.assertIs(service.store,previous);self.assertEqual(service.token,token)
        self.assertEqual(previous.read(),original)
        self.assertFalse(service.save_origin.with_suffix('.active.json').exists())
        # The normal retry still creates exactly one active fresh career.
        self.assertEqual(self.req('POST','/game/api/new-career',{'revision':1})[0],200)
        self.assertIsNone(service.store.read()['state'])

    def test_previous_career_survives_backup_rotation(self):
        self.boot();self.action('new',{'selected':['a','b']},0,'choose-founders')
        original=self.action('start',{},1,'open-old-night')['state']
        self.assertEqual(self.req('POST','/game/api/new-career',{'revision':2})[0],200)
        self.boot();self.action('new',{'selected':['b','c']},0,'new-founders')
        for revision in range(1,15):
            self.action('price',{'pricing':'standard'},revision,'price-change-'+str(revision))
            self.server.after_hours.store.backup()
        backups=self.server.after_hours.store.backups()
        self.assertEqual(len(backups),13);self.assertEqual(backups[0]['id'],'previous-career.sqlite3')
        status,body=self.req('POST','/game/api/restore',{'revision':15,'backup':'previous-career.sqlite3'})
        self.assertEqual(status,200,body)
        original['night']['paused']=True
        self.assertEqual(json.loads(body)['state'],original)
        self.assertEqual(self.before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.lib.iterdir()})

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
