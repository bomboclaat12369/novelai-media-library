"""Disposable regression cases for the local completion build."""
import copy
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest

from game import booking_state, bookings, catalog, engine, evolution, management, migrations, videos, wardrobe, writing
from game.store import GameStore


class Completion(unittest.TestCase):
    def test_group_offers_charge_once_and_keep_each_guests_history(self):
        cat=catalog.demo_catalog()
        for kind,seed in (('second_client',6),('second_worker',17)):
            with self.subTest(kind=kind):
                state=engine.new_game(cat,['demo-0','demo-1'],seed)
                state=engine.command(state,cat,'start')
                found=None
                while state['night']:
                    state=engine.command(state,cat,'advance',{'seconds':180,'stop_at_decision':True})
                    if not state['night']: break
                    n=state['night']
                    d=next(d for d in n['decisions'] if not d['choice'] and d['at']<=n['elapsed']<d['until'])
                    choice='accept' if d.get('meeting_id') else 'decline'
                    if d['kind']==kind:
                        found=d['meeting_id']; m=n['meetings'][d['worker']]
                        prefix=[copy.deepcopy(s) for s in m['segments'] if 'label' in s]
                        end=m['end'];cash=n['revenue']; funds=m['client_funds'];energy=state['people']['demo-1']['energy']
                        declined=engine.command(state,cat,'decision',{'decision':d['id'],'choice':'decline'})
                        self.assertNotIn('group',declined['night']['meetings'][d['worker']])
                        self.assertEqual(declined['night']['revenue'],cash)
                    state=engine.command(state,cat,'decision',{'decision':d['id'],'choice':choice})
                    booking_state.validate(state)
                    if d['kind']==kind:
                        m=state['night']['meetings'][d['worker']]
                        self.assertFalse(state['night']['paused'])
                        self.assertEqual((m['end'],m['segments'][:len(prefix)]),(end,prefix))
                        self.assertEqual(state['night']['revenue']-cash,management.DECISIONS[kind]['revenue'])
                        if kind=='second_client': self.assertEqual(m['client_funds'],funds)
                        else:
                            self.assertEqual(state['people'][d['partner']]['energy'],energy-10)
                            self.assertIsNone(bookings.partner_for(state,m))
                        with self.assertRaises(engine.RuleError):
                            engine.command(state,cat,'decision',{'decision':d['id'],'choice':'accept'})
                self.assertIsNotNone(found)
                booking_state.validate_reports(state)
                m=next(m for m in state['reports'][0]['booking_history'] if m['id']==found)
                guests={s.get('client','original') for s in m['segments'] if s['slot']=='meeting.finishing'}
                self.assertEqual(guests,{'original','joining'} if kind=='second_client' else {'original'})
                if kind=='second_client':
                    invalid=copy.deepcopy(state)
                    bad=next(m for m in invalid['reports'][0]['booking_history'] if m['id']==found)
                    next(s for s in bad['segments'] if s.get('client')=='joining')['activity_id']='missionary__anal'
                    with self.assertRaises(ValueError): booking_state.validate_reports(invalid)

    def test_all_outfit_views_hashes_thresholds_and_receipts(self):
        self.assertEqual(len(wardrobe.OUTFITS),19)
        levels=[];views=0
        for row in wardrobe.OUTFITS.values():
            levels.append(row['career_level'])
            for face in ('front','side','back'):
                if face not in row: continue
                views+=1
                digest=hashlib.sha256((wardrobe.ART_DIR/row[face]).read_bytes()).hexdigest()
                self.assertEqual(digest,row['sha256' if face=='front' else face+'_sha256'])
        self.assertEqual((levels,views),(list(range(20,57,2)),21))
        base=next(iter(wardrobe.OUTFITS.values()))
        owner=base['owner']; state={'people':{owner:{'xp':5500}},'journal':[],'day':10,'owned':{}}
        wardrobe.reconcile(state,{'source_id':'test','cards':{}});wardrobe.validate(state)
        wardrobe.reconcile(state,{'source_id':'test','cards':{}})
        self.assertEqual(len(state['journal']),19)

    def test_voucher_receipts_recover_without_touching_balance(self):
        s={'reports':[{'day':3},{'day':4}],'pack_vouchers':0,'contracts':[{'end':4,'id':7,'department':'studio',
           'status':'completed','success':True,'spec':{'packs':2}}]}
        e={'day':3,'kind':'milestone_earned','milestone':'first_service','standard_vouchers':1}
        for _ in range(2): migrations.recover_reward_receipts(s,[e,e])
        self.assertEqual([r['voucher_rewards'][0]['amount'] for r in s['reports']],[1,2])
        self.assertEqual(s['pack_vouchers'],0)

    def test_old_management_receipts_use_recorded_results_without_repaying(self):
        old={'day':3,'revenue':80,'earnings':{'p':40},'assignments':{'p':'lounge'},
             'decisions':[{'id':'offer','kind':'lounge_round','choice':'accept','worker':'p'}]}
        ambiguous={**copy.deepcopy(old),'day':4,'revenue':81}
        active={**copy.deepcopy(old),'day':5,'energy_spent':{'p':12}}
        paid={'department':'resort','status':'completed','spec':{'rate':155,'expectation':55},'satisfaction':55}
        missed={**copy.deepcopy(paid),'satisfaction':54}
        state={'day':5,'cash':610,'people':{'p':{'energy':33}},'reports':[old,ambiguous],
               'night':active,'contracts':[paid,missed],'journal':[]}
        for _ in range(2):
            migrations.recover_management_receipts(state)
        self.assertEqual([paid['checkout_bonus_paid'],missed['checkout_bonus_paid']],[46,0])
        self.assertEqual([s['earnings']['p'] for s in (old,ambiguous,active)],[80,40,80])
        self.assertEqual(active['energy_spent']['p'],18)
        self.assertEqual((state['cash'],state['people']['p']['energy']),(610,33))
        self.assertEqual([e['day'] for e in state['journal']],[3,5])

    def test_earned_forms_and_exact_manual_video_pairings(self):
        with tempfile.TemporaryDirectory() as tmp:
            book=videos.Pairings(tmp,'test')
            cards={'a':{'source':'library','owner':'p','name':'A','available':True},
                   'other':{'source':'library','owner':'q','name':'Q','available':True},
                   'e':{'source':'evolution','owner':'p','available':True,'forms':[{'media_id':x,'key':x} for x in ('first','target','last')]}}
            cat={'people':{'p':{},'q':{}},'cards':cards,'videos':{'set':{'owner':'p','name':'Clip','photos':['target']},
                 'loose':{'owner':'p','name':'Loose','photos':[]}}}
            s={'day':1,'owned':{'e':{'mastery':0},'other':{}}}
            with self.assertRaises(ValueError): book.set(cat,'loose','other',None)
            book.set(cat,'loose','a',None)
            videos.reconcile(cat,s,book.read())
            self.assertFalse(videos.unlocked(cat,s))
            s['owned']['e']['mastery']=2
            videos.reconcile(cat,s,book.read())
            self.assertEqual(set(videos.unlocked(cat,s)),{'set'})
            s['owned']['a']={}
            videos.reconcile(cat,s,book.read())
            self.assertEqual(set(videos.unlocked(cat,s)),{'loose','set'})
            self.assertEqual(videos.Pairings(tmp,'test').read(),{'loose':'a'})
            self.assertFalse(videos.Pairings(tmp,'other-library').read())
            with self.assertRaises(ValueError): book.set(cat,'loose',None,None)
            book.set(cat,'loose',None,'a');self.assertFalse(book.read())
            videos.reconcile(cat,s,book.read())
            videos.validate_receipts(s,cat)
            self.assertEqual(s['earned_videos']['p']['set'],{'card':'e','photo':'target','via':'set'})
            self.assertEqual(len(s['journal']),2)

    def test_video_rewards_survive_moves_restore_and_only_belong_to_the_earning_career(self):
        cat=catalog.demo_catalog()
        for card in cat['cards'].values():
            card.update(source='library',available=True)
        owner='demo-0'
        starter=engine.starter(cat,owner)
        later=next(k for k,c in cat['cards'].items() if c['owner']==owner and k!=starter)
        cat['videos']={'v':{'owner':owner,'name':'Set clip','photos':[starter]},
                       'loose':{'owner':owner,'name':'Paired clip','photos':[]}}
        creation={'selected':[owner,'demo-1'],'seed':9}
        def available(store):
            return set(videos.unlocked(store.catalog,store.read()['state']))
        def refresh(store,live):
            store.refresh_catalog(live,store.read()['revision'])
        with tempfile.TemporaryDirectory() as tmp:
            store=GameStore(Path(tmp)/'career.sqlite3',cat)
            store.apply('new',creation,'new-career',0)
            self.assertEqual(available(store),{'v'})
            store.set_video_pairing('loose',starter,None)
            store.set_video_pairing('loose',None,starter)
            self.assertEqual(available(store),{'v','loose'})
            self.assertEqual(store.read()['revision'],store.apply('new',creation,'new-career',0)['revision'])
            # The last local catalog is still evidence when upgrading an older career.
            legacy=GameStore(Path(tmp)/'older.sqlite3',cat)
            legacy.apply('new',creation,'old-career',0)
            with legacy.connect() as db:
                db.execute("UPDATE save SET body=json_remove(body,'$.earned_videos')")
                db.execute("DELETE FROM events WHERE json_extract(body,'$.kind')='video_earned'")
            moved=copy.deepcopy(cat)
            moved['videos']['v']['photos']=[later]
            upgraded=GameStore(legacy.path,moved)
            self.assertEqual(available(upgraded),{'v'})
            self.assertEqual(upgraded.read()['state']['cash'],600)
            refresh(store,moved)
            fresh=store.new_career(moved)
            fresh.apply('new',creation,'fresh-start',0)
            self.assertEqual(available(fresh),set())
            # A pairing made from another career is recorded the first time this one sees it.
            fresh.set_video_pairing('loose',starter,None)
            self.assertEqual(available(upgraded),{'v','loose'})
            fresh.set_video_pairing('loose',None,starter)
            self.assertEqual(available(upgraded),{'v','loose'})
            export=store.export()
            self.assertNotIn('videos',export['catalog'])
            self.assertEqual(sum(e.get('kind')=='video_earned' for e in export['history']),2)
            hidden=copy.deepcopy(moved)
            hidden['videos']['v']['owner']='demo-1'
            del hidden['videos']['loose']
            refresh(store,hidden)
            self.assertEqual(available(store),set())
            restored=store.restore(export)
            self.assertEqual(available(restored),set())
            refresh(restored,moved)
            self.assertEqual(available(restored),{'v','loose'})
            self.assertEqual(restored.read()['state']['earned_videos'],export['save']['state']['earned_videos'])
            self.assertEqual(sum(e.get('kind')=='video_earned' for e in restored.export()['history']),2)
            bad=copy.deepcopy(export)
            bad['save']['state']['earned_videos'][owner]['v']['card']=later
            with self.assertRaises(engine.RuleError):store.restore(bad)

    def test_offline_words_cannot_change_participants_or_payments(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=GameStore(Path(tmp)/'career.sqlite3',catalog.demo_catalog())
            slot='event.second_worker'
            pack={'format':'after-hours-writing-pack','schema_version':1,'context_version':3,'pack_id':'sample',
                  'entries':[{'id':'offer.1','slot':slot,'when':{},'dialogue':[],'title':'A group offer','text':'{worker} and {partner} · {payout}'}]}
            store.writing.install(json.dumps(pack).encode())
            d={'kind':'second_worker','worker':'demo-0','partner':'demo-2'}
            store.event(d,store.catalog,random.Random(1))
            self.assertEqual(d['copy']['detail'],'Nikki and Alice · 95')
            missing={'kind':'second_worker','worker':'demo-0'}
            store.event(missing,store.catalog,random.Random(1));self.assertNotIn('copy',missing)
            group={'id':'stage.1','slot':'meeting.stage','text':'{worker} joins {partner}',
                   'when':{'lineup':'two_workers_one_client','workers':'both','clients':'original'}}
            store.writing.install(json.dumps([group]).encode())
            self.assertEqual(store.choose('meeting.stage',group['when'],random.Random(1),[])['id'],'stage.1')
            self.assertIsNone(store.writing.stage('meeting.stage',{},random.Random(1),[]))
            pack['entries'][0]['text']='{change_payout}'
            with self.assertRaises(ValueError): store.writing.install(json.dumps(pack).encode())
            self.assertEqual(store.writing.summary,{'events-sample':1,'group-stages':1})

    def test_set_cards_inherit_highest_selected_main(self):
        forms=[{'media_id':k} for k in ('a','b','c')]
        cards={k:{'rarity':tier,'source':'library','available':True} for k,tier in [('a',3),('b',4),('unselected',4)]}
        for kind in evolution.SET_CARDS: self.assertEqual(evolution.set_rarity(forms,cards,kind),4)
        del cards['b'];self.assertEqual(evolution.set_rarity(forms,cards,'evolution'),3)
