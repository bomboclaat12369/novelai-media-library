import copy
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import http.client
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from game import engine as g
from game.catalog import demo_catalog,read_library
from game.store import GameStore,Conflict
from game.server import build_server


class Rules(unittest.TestCase):
    def setUp(self):
        self.catalog=demo_catalog();self.state=g.new_game(self.catalog,['demo-0','demo-1'],123)

    def test_same_night_outcome_at_all_tick_sizes(self):
        baseline=None
        for step in (1,2,4,13,50,300):
            state=g.command(self.state,self.catalog,'start')
            while state['phase']=='night': state=g.command(state,self.catalog,'advance',{'seconds':step})
            state['journal']=[]
            if baseline is None:baseline=state
            self.assertEqual(state,baseline)
        self.assertEqual(baseline['day'],2)

    def test_pause_and_equipment_cannot_restore_energy(self):
        s=g.command(self.state,self.catalog,'start');s=g.command(s,self.catalog,'advance',{'seconds':50})
        s=g.command(s,self.catalog,'pause');before=copy.deepcopy(s)
        s=g.command(s,self.catalog,'advance',{'seconds':300});before['journal']=[]
        self.assertEqual(s,before)
        with self.assertRaises(g.RuleError):g.command(s,self.catalog,'equip',{'owner':'demo-0','card':'demo-0-119'})
        s=g.command(s,self.catalog,'finish');energy=s['people']['demo-0']['energy']
        s=g.command(s,self.catalog,'equip',{'owner':'demo-0','card':s['people']['demo-0']['card']})
        self.assertEqual(s['people']['demo-0']['energy'],energy)

    def test_capacities_and_recruitment_cost(self):
        s=g.command(self.state,self.catalog,'plan',{'owner':'demo-1','role':'room'})
        with self.assertRaises(g.RuleError):g.command(s,self.catalog,'start')
        s=g.command(self.state,self.catalog,'hire',{'owner':'demo-2'})
        self.assertEqual(s['cash'],self.state['cash']-220)
        self.assertIn(s['people']['demo-2']['card'],s['owned'])
        with self.assertRaises(g.RuleError):g.command(s,self.catalog,'hire',{'owner':'demo-2'})

    def test_pack_free_recruitment_does_not_auto_hire(self):
        s=g.command(self.state,self.catalog,'pack',{'pack':'spotlight','target':'demo-2'})
        self.assertNotIn('demo-2',s['people'])
        cash=s['cash'];s=g.command(s,self.catalog,'reveal_done')
        s=g.command(s,self.catalog,'hire',{'owner':'demo-2'})
        self.assertEqual(s['cash'],cash)
        self.assertEqual(g.recurring_cost(s)-g.recurring_cost(self.state),30)

    def test_premium_and_collector_guarantees(self):
        for seed in range(60):
            s=g.new_game(self.catalog,['demo-0','demo-1'],seed)
            for kind in ('premium','collector'):
                s['cash']=10000
                s=g.command(s,self.catalog,'pack',{'pack':kind})
                results=s['pending_pack']['results']
                self.assertEqual(len(results),5)
                if kind=='premium':self.assertTrue(any(self.catalog['cards'][r['id']]['rarity']>=3 for r in results))
                else:self.assertTrue(any(r['new'] for r in results))
                s=g.command(s,self.catalog,'reveal_done')
        s['owned']={i:{'copies':1,'xp':0,'mastery':0,'uses':0,'acquired_day':1} for i in self.catalog['cards']}
        with self.assertRaises(g.RuleError):g.command(s,self.catalog,'pack',{'pack':'collector'})

    def test_sparse_premium_pool_is_disabled_not_falsely_guaranteed(self):
        for c in self.catalog['cards'].values():c['rarity']=0
        with self.assertRaises(g.RuleError):g.command(self.state,self.catalog,'pack',{'pack':'premium'})

    def test_duplicates_preserve_first_copy_and_discovery(self):
        ident=next(iter(self.state['owned']))
        with self.assertRaises(g.RuleError):g.command(self.state,self.catalog,'mastery',{'card':ident})
        self.state['owned'][ident]['copies']=2
        s=g.command(self.state,self.catalog,'mastery',{'card':ident})
        self.assertEqual(s['owned'][ident]['copies'],1);self.assertEqual(s['owned'][ident]['xp'],30)
        self.assertEqual(self.state['owned'][ident]['copies'],2)

    def test_character_first_odds_with_unequal_image_counts(self):
        pool=list(self.catalog['cards'].values());rng=random.Random(76);counts={p:0 for p in self.catalog['people']}
        for _ in range(10000):counts[g.draw(pool,rng)['owner']]+=1
        self.assertTrue(all(350<v<650 for v in counts.values()),counts)

    def test_recovery_preserves_assets(self):
        s=copy.deepcopy(self.state);s['cash']=-500;before=copy.deepcopy(s['owned'])
        s=g.command(s,self.catalog,'recovery')
        self.assertEqual(s['owned'],before);self.assertEqual(s['day'],3)
        self.assertGreater(s['cash'],g.recurring_cost(s))


class Persistence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'save.sqlite3';self.cat=demo_catalog()
        self.store=GameStore(self.path,self.cat)
        self.store.apply('new',{'selected':['demo-0','demo-1'],'seed':123},'request-new',0)

    def tearDown(self):self.tmp.cleanup()

    def test_retry_reload_and_reveal_are_one_transaction(self):
        r=self.store.apply('pack',{'pack':'standard'},'pack-once',1)
        repeat=self.store.apply('pack',{'pack':'standard'},'pack-once',1)
        self.assertTrue(repeat['replayed']);self.assertEqual(r['state'],repeat['state'])
        reopened=GameStore(self.path,self.cat).read()
        self.assertEqual(reopened['state']['pending_pack'],r['state']['pending_pack'])
        self.assertEqual(reopened['state']['cash'],500)
        with self.assertRaises(Conflict):self.store.apply('pack',{'pack':'premium'},'pack-once',2)
        with self.assertRaises(g.RuleError):self.store.apply('pack',{'pack':'standard'},'pack-twice',2)

    def test_stale_window_rejected_and_second_settlement_rejected(self):
        r=self.store.apply('start',{},'night-start',1)
        with self.assertRaises(Conflict):self.store.apply('price',{'pricing':'premium'},'other-window',1)
        r=self.store.apply('finish',{},'night-end',r['revision'])
        self.assertEqual(r['state']['day'],2)
        with self.assertRaises(g.RuleError):self.store.apply('finish',{},'night-again',r['revision'])
        self.assertEqual(self.store.read()['state']['cash'],r['state']['cash'])

    def test_failed_save_rolls_back_money_inventory_and_request(self):
        before=self.store.read()
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER fail_write BEFORE INSERT ON requests BEGIN SELECT RAISE(FAIL,'disk failure fixture'); END")
        with self.assertRaises(sqlite3.DatabaseError):self.store.apply('pack',{'pack':'standard'},'will-rollback',1)
        self.assertEqual(self.store.read(),before)
        with self.store.connect() as db:db.execute('DROP TRIGGER fail_write')
        after=self.store.apply('pack',{'pack':'standard'},'will-rollback',1)
        self.assertEqual(after['state']['cash'],500)

    def test_restart_pauses_midnight_and_catalog_changes_preserve_owned(self):
        r=self.store.apply('start',{},'begin-night',1)
        loaded=GameStore(self.path,self.cat)
        self.assertTrue(loaded.read()['state']['night']['paused'])
        old=next(iter(r['state']['owned']));old_rarity=self.cat['cards'][old]['rarity']
        changed=copy.deepcopy(self.cat);changed['cards'][old]['rarity']=4
        loaded=GameStore(self.path,changed)
        self.assertEqual(loaded.catalog['cards'][old]['rarity'],old_rarity)
        del changed['cards'][old]
        loaded=GameStore(self.path,changed)
        self.assertIn(old,loaded.read()['state']['owned'])
        self.assertFalse(loaded.catalog['cards'][old]['available'])

    def test_different_library_cannot_overwrite_save(self):
        cat=copy.deepcopy(self.cat);cat['source_id']='other-library'
        with self.assertRaises(g.RuleError):GameStore(self.path,cat)
        self.assertIsNotNone(self.store.read()['state'])

    def test_multiple_windows_share_one_clock_and_background_pause_is_idempotent(self):
        with patch('game.store.time.monotonic',return_value=100):
            self.store.apply('start',{},'clock-start',1)
        with patch('game.store.time.monotonic',return_value=103):
            one=self.store.apply('tick',{},'clock-tick-1',2)
            two=self.store.apply('tick',{},'clock-tick-2',3)
        self.assertEqual(one['state']['night']['elapsed'],3)
        self.assertEqual(two['state']['night']['elapsed'],3)
        self.store.apply('pause',{'paused':True},'clock-pause-1',4)
        paused=self.store.apply('pause',{'paused':True},'clock-pause-2',5)
        self.assertTrue(paused['state']['night']['paused'])


class ReadOnlyCatalog(unittest.TestCase):
    def test_filtering_rank_order_and_no_source_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);people=[{'id':'a','name':'A','categories':[{'id':'cat1','name':'Evening'}]},{'id':'b','name':'B'}]
            media=[{'id':f'{p}{i}','character_id':p,'in_all':True} for p in ('a','b') for i in range(10)]
            for key,i in [('in_review',1),('in_purgatory',2),('flagged_for_removal',3)]:media[i][key]=True
            media[4]['in_all']=False;media[5]['media_type']='video'
            media[6]['stored_rel']='../outside.jpg'
            media[0]['categories']=['cat1']
            (root/'image.jpg').write_bytes(b'fixture-image')
            media[0].update(stored_rel='image.jpg',thumb_rel='missing-thumbnail.jpg')
            (root/'library.json').write_text(json.dumps({'characters':people,'media':media,'_tracking_store':'fixture'}))
            (root/'battles.json').write_text(json.dumps({'boards':{'b:images':{'ratings':{f'b{i}':{'rating':2000-i*10,'played':10} for i in range(10)}}}}))
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            cat=read_library(root)
            self.assertEqual(len(cat['cards']),15)
            self.assertGreater(cat['cards']['b0']['rarity'],cat['cards']['b9']['rarity'])
            self.assertIsNone(cat['cards']['a6']['original'])
            self.assertFalse(cat['cards']['a0']['ranked'])
            self.assertEqual(cat['cards']['a0']['categories'],['Evening'])
            self.assertEqual(cat['cards']['a0']['source_categories'],['cat1'])
            self.assertEqual(cat['cards']['a0']['image'],str(root/'image.jpg'))
            self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()})


class LocalHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=build_server(0,Path(self.tmp.name)/'game.sqlite3')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        conn.request(method,path,body=body,headers=headers or {})
        response=conn.getresponse();status=response.status;data=response.read();conn.close()
        return status,data

    def test_request_boundary_and_public_catalog(self):
        status,raw=self.request('GET','/api/bootstrap');self.assertEqual(status,200)
        boot=json.loads(raw);self.assertIsNone(boot['state']);self.assertNotIn('original',next(iter(boot['catalog']['cards'].values())))
        body=json.dumps({'action':'new','body':{'selected':['demo-0','demo-1']},'id':'http-new-01','revision':0})
        headers={'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/action',body,headers)[0],403)
        headers['X-Game-Token']=boot['token']
        headers['Host']='other.example'
        self.assertEqual(self.request('POST','/api/action',body,headers)[0],403)
        headers.pop('Host')
        self.assertEqual(self.request('POST','/api/action',body,headers)[0],200)
        self.assertEqual(self.request('GET','/../store.py')[0],404)
        self.assertEqual(self.request('POST','/api/action','[]',headers)[0],400)
        status,export=self.request('GET','/api/export');self.assertEqual(status,200)
        self.assertEqual(json.loads(export)['save']['state']['day'],1)


if __name__=='__main__':unittest.main()
