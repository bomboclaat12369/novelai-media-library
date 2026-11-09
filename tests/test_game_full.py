"""Expanded-game acceptance invariants, not renderer or visual assertions."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from game import engine as g, management as m
from game.catalog import demo_catalog, read_library
from game.store import GameStore, Conflict, encode


class IntegratedRules(unittest.TestCase):
    def setUp(self):
        self.cat=demo_catalog()
        self.s=g.new_game(self.cat,['demo-0','demo-1'],123)

    def expanded(self):
        s=copy.deepcopy(self.s);s['cash']=10000;s['day']=5;s['totals']['services']=30
        s=g.command(s,self.cat,'department',{'kind':'studio'})
        s['totals']['studio_completed']=2
        s=g.command(s,self.cat,'department',{'kind':'resort'})
        for owner in ('demo-2','demo-3'):s=g.command(s,self.cat,'hire',{'owner':owner})
        return s

    def book(self,s,department,owner,kind,start=None):
        return g.command(s,self.cat,'schedule',{'department':department,'owner':owner,'kind':kind,'start':s['day'] if start is None else start})

    def night(self,s):
        s=g.command(s,self.cat,'auto');s=g.command(s,self.cat,'start')
        return g.command(s,self.cat,'finish')

    def test_department_order_and_small_roster_unlocks(self):
        with self.assertRaises(g.RuleError):g.command(self.s,self.cat,'department',{'kind':'studio'})
        s=copy.deepcopy(self.s);s.update(day=4,cash=3000);s['totals']['services']=18
        with self.assertRaises(g.RuleError):g.command(s,self.cat,'department',{'kind':'resort'})
        s=g.command(s,self.cat,'department',{'kind':'studio'})
        for _ in range(2):s=self.night(self.book(s,'studio','demo-0','portrait'))
        s=g.command(s,self.cat,'department',{'kind':'resort'})
        self.assertEqual(s['departments'],{'studio':1,'resort':1})

    def test_three_departments_advance_one_clock_and_settle_once(self):
        s=self.expanded();day=s['day']
        s=self.book(s,'studio','demo-2','editorial');s=self.book(s,'resort','demo-3','retreat')
        s=self.night(s)
        self.assertEqual(s['day'],day+1)
        self.assertEqual([c['nights'] for c in s['contracts']],[1,1])
        self.assertTrue(all(c['status']=='active' for c in s['contracts']))
        self.assertEqual(s['reports'][-1]['assignments']['demo-2'],'studio')
        s=self.night(s)
        self.assertTrue(all(c['status']=='completed' for c in s['contracts']))
        self.assertEqual(s['totals']['resort_completed'],1)
        self.assertGreater(s['reports'][-1]['department_revenue'],200)
        self.assertGreater(s['pack_vouchers'],0)
        before=s['totals']['contract_revenue'];s=self.night(s)
        self.assertEqual(s['totals']['contract_revenue'],before)
        with self.assertRaises(g.RuleError):g.command(s,self.cat,'finish')

    def test_reservations_reject_cross_department_overlap_and_capacity(self):
        s=self.book(self.expanded(),'studio','demo-2','campaign',7)
        with self.assertRaises(g.RuleError):self.book(s,'resort','demo-2','retreat',8)
        with self.assertRaises(g.RuleError):self.book(s,'studio','demo-3','portrait',9)
        s=self.book(s,'resort','demo-2','retreat',10)
        self.assertEqual(len(s['contracts']),2)

    def test_reserved_worker_cannot_be_assigned_twice(self):
        s=self.book(self.expanded(),'studio','demo-0','editorial')
        with self.assertRaises(g.RuleError):g.command(s,self.cat,'plan',{'owner':'demo-0','role':'room'})
        s=g.command(s,self.cat,'auto');s=g.command(s,self.cat,'start')
        self.assertEqual(s['night']['assignments']['demo-0'],'studio')
        s=g.command(s,self.cat,'finish')
        self.assertEqual(s['people']['demo-0']['skills']['club'],0)
        self.assertEqual(s['people']['demo-0']['skills']['studio'],18)

    def test_night_equipment_locked_department_card_shared_energy(self):
        s=self.book(self.expanded(),'resort','demo-2','retreat');s=g.command(s,self.cat,'start')
        with self.assertRaises(g.RuleError):g.command(s,self.cat,'equip',{'owner':'demo-2','card':s['people']['demo-2']['card']})
        s=g.command(s,self.cat,'advance',{'seconds':50})
        self.assertLess(s['people']['demo-2']['energy'],100)
        self.assertEqual(s['contracts'][0]['card'],s['people']['demo-2']['card'])

    def test_decisions_have_consequences_and_cannot_repeat(self):
        s=g.command(self.s,self.cat,'start');s=g.command(s,self.cat,'advance',{'seconds':100})
        d=s['night']['decisions'][0];old=s['night']['revenue']
        s=g.command(s,self.cat,'decision',{'decision':d['id'],'choice':'accept'})
        self.assertEqual(s['night']['revenue'],old+55)
        with self.assertRaises(g.RuleError):g.command(s,self.cat,'decision',{'decision':d['id'],'choice':'accept'})
        s=g.command(s,self.cat,'advance',{'seconds':100})
        s=g.command(s,self.cat,'pause')
        d=s['night']['decisions'][1]
        s=g.command(s,self.cat,'decision',{'decision':d['id'],'choice':'refresh'})
        self.assertEqual(s['night']['decision_costs'],25)
        self.assertFalse(s['night']['paused'])
        s=g.command(s,self.cat,'advance',{'seconds':1})
        self.assertEqual(s['night']['elapsed'],201)

    def test_event_wording_varies_and_does_not_reroll_during_night(self):
        titles=[]
        for day in range(1,17,2):
            s=copy.deepcopy(self.s);s['day']=day
            s=g.command(s,self.cat,'start')
            presentation=copy.deepcopy(s['night']['decisions'][0]['copy'])
            titles.append(presentation['title'])
            s=g.command(s,self.cat,'advance',{'seconds':100})
            self.assertEqual(s['night']['decisions'][0]['copy'],presentation)
        self.assertEqual(len(set(titles)),8)

    def test_tired_round_replaces_previous_activity(self):
        s=g.command(self.s,self.cat,'start');s=g.command(s,self.cat,'advance',{'seconds':50})
        owner=next(iter(s['people']));s['people'][owner]['energy']=0
        s=g.command(s,self.cat,'advance',{'seconds':50})
        self.assertEqual(s['night']['activities'][owner]['round'],2)
        self.assertNotIn('+$',s['night']['activities'][owner]['status'])

    def test_departments_are_tick_size_independent(self):
        original=self.book(self.book(self.expanded(),'studio','demo-2','editorial'),'resort','demo-3','retreat')
        outcomes=[]
        for step in (1,4,37,50,300):
            s=g.command(original,self.cat,'start')
            while s['phase']=='night':s=g.command(s,self.cat,'advance',{'seconds':step})
            s['journal']=[];outcomes.append(s)
        self.assertTrue(all(s==outcomes[0] for s in outcomes))

    def test_saved_plan_retains_equipment_and_does_not_reset_career(self):
        s=g.command(self.s,self.cat,'save_plan',{'name':'Regular'})
        s=g.command(s,self.cat,'plan',{'owner':'demo-0','role':'train'})
        s=self.night(s);energy=s['people']['demo-0']['energy'];xp=s['people']['demo-0']['xp']
        s=g.command(s,self.cat,'load_plan',{'name':'Regular'})
        self.assertEqual(s['people']['demo-0']['role'],'room')
        self.assertEqual((s['people']['demo-0']['energy'],s['people']['demo-0']['xp']),(energy,xp))

    def test_training_changes_department_skill_not_ownership(self):
        s=g.command(self.s,self.cat,'training',{'owner':'demo-0','value':'studio'})
        s=g.command(s,self.cat,'plan',{'owner':'demo-0','role':'train'})
        owned=copy.deepcopy(s['owned']);s=g.command(s,self.cat,'start');s=g.command(s,self.cat,'finish')
        self.assertEqual(s['people']['demo-0']['skills']['studio'],35)
        self.assertEqual(s['owned'][s['people']['demo-0']['card']],owned[s['people']['demo-0']['card']])

    def test_recovery_moves_active_and_future_reservations(self):
        s=self.book(self.expanded(),'studio','demo-2','campaign');s=self.night(s)
        original=copy.deepcopy(s['contracts'][0]);s['cash']=-100
        s=g.command(s,self.cat,'recovery')
        c=s['contracts'][0];self.assertEqual(c['end'],original['end']+2);self.assertEqual(c['nights'],1)
        s=self.night(self.night(s));self.assertEqual(s['contracts'][0]['status'],'completed')

    def test_cancel_frees_worker_and_preserves_sunk_cost(self):
        s=self.book(self.expanded(),'resort','demo-2','weekend');cash=s['cash']
        s=g.command(s,self.cat,'cancel_contract',{'contract':s['contracts'][0]['id']})
        self.assertEqual(s['cash'],cash);self.assertFalse(m.reservations(s,'demo-2'))

    def test_failed_stay_keeps_loyalty_and_save_valid(self):
        s=self.expanded();s['loyalty']=0
        for w in s['people'].values():w['role']='rest'
        s=self.book(s,'resort','demo-2','retreat')
        for _ in range(2):
            s['people']['demo-2']['energy']=0
            s=g.command(s,self.cat,'start')
            s=g.command(s,self.cat,'finish')
        self.assertEqual(s['contracts'][0]['satisfaction'],0)
        self.assertEqual(s['loyalty'],0)
        from game.migrations import validate
        validate(s,self.cat)

    def test_earned_voucher_reveals_and_preserves_money(self):
        s=copy.deepcopy(self.s);s['pack_vouchers']=1;cash=s['cash']
        s=g.command(s,self.cat,'pack',{'pack':'standard','voucher':True})
        self.assertEqual(s['cash'],cash);self.assertEqual(s['pack_vouchers'],0)
        s=g.command(s,self.cat,'reveal',{'index':2});self.assertEqual(s['pending_pack']['revealed'],[2])
        s=g.command(s,self.cat,'reveal',{'all':True});self.assertEqual(s['pending_pack']['revealed'],[0,1,2,3,4])


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'save.sqlite3';self.cat=demo_catalog()
        self.store=GameStore(self.path,self.cat)
        self.store.apply('new',{'selected':['demo-0','demo-1']},'create-new',0)
    def tearDown(self):self.tmp.cleanup()

    def test_schema_one_migration_preserves_pending_pack(self):
        r=self.store.apply('pack',{'pack':'standard'},'buy-standard',1);old=copy.deepcopy(r['state'])
        old['schema']=1;old['version']='0.1.0'
        for k in ('departments','contracts','narrative','saved_plans','pack_vouchers','reputation','loyalty'):old.pop(k,None)
        with self.store.connect() as db:db.execute('UPDATE save SET body=?',(encode(old),))
        loaded=GameStore(self.path,self.cat);s=loaded.read()['state']
        for k in ('cash','owned','pending_pack','people'):self.assertEqual(s[k],r['state'][k])
        self.assertEqual(s['schema'],2);self.assertTrue(Path(str(self.path)+'.before-schema-2').exists())
        self.assertEqual(sum(e['kind']=='save_migrated' for e in loaded.export()['history']),1)
        again=GameStore(self.path,self.cat)
        self.assertEqual(sum(e['kind']=='save_migrated' for e in again.export()['history']),1)

    def test_export_restore_new_file_and_reveals(self):
        r=self.store.apply('pack',{'pack':'standard'},'buy-standard',1)
        self.store.apply('reveal',{'index':1},'reveal-card',r['revision'])
        old=self.store.read();restored=self.store.restore(self.store.export())
        self.assertNotEqual(restored.path,self.path);self.assertEqual(self.store.read(),old)
        self.assertEqual(restored.read()['state'],old['state'])

    def test_restore_rebinds_paths_and_keeps_source_identity(self):
        data=self.store.export();ident=next(iter(data['catalog']['cards']))
        data['catalog']['cards'][ident]['image']='C:/Windows/secret.txt'
        restored=self.store.restore(data)
        self.assertIsNone(restored.catalog['cards'][ident]['image'])
        before=self.store.read();data['catalog']['source_id']='different-library'
        with self.assertRaises(g.RuleError):self.store.restore(data)
        self.assertEqual(self.store.read(),before)

    def test_invalid_and_future_restore_leave_active_save_intact(self):
        before=self.store.read()
        for field,value in [('schema',99),('cash',float('nan')),('owned',{})]:
            data=self.store.export();data['save']['state'][field]=value
            with self.assertRaises(g.RuleError):self.store.restore(data)
            self.assertEqual(self.store.read(),before)

    def test_backup_restore_keeps_intervening_save(self):
        backup=self.store.backups()[0]['id'];before=self.store.read()
        self.store.apply('pack',{'pack':'standard'},'buy-standard',1)
        current=self.store.read();restored=self.store.restore(backup=backup)
        self.assertEqual(restored.read()['state'],before['state']);self.assertEqual(self.store.read(),current)
        with self.assertRaises(g.RuleError):self.store.restore(backup='../save.sqlite3')

    def test_refresh_preserves_rarity_and_adds_optional_recruit(self):
        changed=copy.deepcopy(self.cat);ident=next(iter(self.store.read()['state']['owned']))
        old=changed['cards'][ident]['rarity'];changed['cards'][ident]['rarity']=4
        new=copy.deepcopy(changed['cards'][ident]);new.update(id='arrival',owner='new-person')
        changed['cards']['arrival']=new;changed['people']['new-person']={'id':'new-person','name':'New person','color':0}
        self.store.refresh_catalog(changed,1)
        self.assertEqual(self.store.catalog['cards'][ident]['rarity'],old)
        self.assertNotIn('new-person',self.store.read()['state']['people'])
        self.assertIn('arrival',self.store.catalog['cards'])
        with self.assertRaises(Conflict):self.store.apply('pack',{'pack':'standard'},'stale-window',1)

    def test_two_stores_share_persisted_clock(self):
        second=GameStore(self.path,self.cat)
        with patch('game.store.time.monotonic',return_value=100):self.store.apply('start',{},'start-night',1)
        with patch('game.store.time.monotonic',return_value=105):
            a=self.store.apply('tick',{},'window-one',2);b=second.apply('tick',{},'window-two',3)
        self.assertEqual(a['state']['night']['elapsed'],5);self.assertEqual(b['state']['night']['elapsed'],5)

    def test_answering_paused_event_resumes_without_counting_pause_time(self):
        with patch('game.store.time.monotonic',return_value=100):
            r=self.store.apply('start',{},'event-start',1)
            r=self.store.apply('speed',{'speed':4},'event-speed',r['revision'])
        for i in range(1,4):
            with patch('game.store.time.monotonic',return_value=100+i*10):
                r=self.store.apply('tick',{},f'event-tick-{i}',r['revision'])
        r=self.store.apply('pause',{'paused':True},'event-pause',r['revision'])
        decision=r['state']['night']['decisions'][0]
        reopened=GameStore(self.path,self.cat)
        r=reopened.read()
        self.assertEqual(r['state']['night']['decisions'][0]['copy'],decision['copy'])
        with self.assertRaises(g.RuleError):
            reopened.apply('decision',{'decision':decision['id'],'choice':'invalid'},'invalid-answer',r['revision'])
        self.assertEqual(reopened.read(),r)
        body={'decision':decision['id'],'choice':'accept'}
        with patch('game.store.time.monotonic',return_value=1000):
            r=reopened.apply('decision',body,'answer-event',r['revision'])
        self.assertFalse(r['state']['night']['paused']);self.assertEqual(r['state']['night']['speed'],4)
        self.assertEqual(r['state']['night']['elapsed'],120)
        cash=r['state']['night']['revenue']
        replay=reopened.apply('decision',body,'answer-event',r['revision'])
        self.assertTrue(replay['replayed']);self.assertEqual(replay['state']['night']['revenue'],cash)
        with patch('game.store.time.monotonic',return_value=1001):
            r=reopened.apply('tick',{},'tick-after-event',r['revision'])
        self.assertEqual(r['state']['night']['elapsed'],124)

    def test_catalog_refresh_reaches_another_store(self):
        second=GameStore(self.path,self.cat)
        changed=copy.deepcopy(self.cat)
        changed['people']['arrival']={'id':'arrival','name':'Arrival','color':0}
        changed['cards']['arrival']={**next(iter(changed['cards'].values())),'id':'arrival','owner':'arrival'}
        self.store.refresh_catalog(changed,1)
        result=second.apply('hire',{'owner':'arrival'},'hire-new-arrival',2)
        self.assertIn('arrival',result['state']['people'])

    def test_recovery_from_actual_overspending_keeps_purchases(self):
        r=self.store.read()
        for i in range(6):
            r=self.store.apply('pack',{'pack':'standard'},f'spend-pack-{i}',r['revision'])
            r=self.store.apply('reveal_done',{},f'ack-pack-{i}',r['revision'])
        self.assertEqual(r['state']['cash'],0);owned=copy.deepcopy(r['state']['owned'])
        r=self.store.apply('recovery',{},'recover-budget',r['revision'])
        self.assertEqual(r['state']['day'],3);self.assertEqual(r['state']['owned'],owned)
        r=self.store.apply('start',{},'reopen-recovered',r['revision'])
        r=self.store.apply('finish',{},'settle-recovered',r['revision'])
        self.assertEqual(r['state']['day'],4)

    def test_restore_rejects_corrupt_plan_and_contract(self):
        r=self.store.apply('save_plan',{'name':'Rotation'},'save-rotation',1)
        data=self.store.export();owner=next(iter(data['save']['state']['people']))
        data['save']['state']['saved_plans']['Rotation']['people'][owner]['role']='invalid'
        with self.assertRaises(g.RuleError):self.store.restore(data)
        data=self.store.export();data['save']['state']['contracts']=[{'department':'studio','owner':owner,'status':'active','start':1,'end':2,'kind':'editorial','id':1}]
        with self.assertRaises(g.RuleError):self.store.restore(data)
        self.assertEqual(self.store.read(),r)


if __name__=='__main__':unittest.main()
