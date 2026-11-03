"""Tier eligibility, legacy records, persistent trophies and undo semantics."""
import unittest
from test_runtime_battles import BattleTests
import test_runtime_stability as fixtures

class RankTests(unittest.TestCase):
    setUp=BattleTests.setUp
    tearDown=BattleTests.tearDown
    import_image=BattleTests.import_image
    post=BattleTests.post
    call=BattleTests.call

    def test_earlier_placement_keeps_confidence_and_diversity_guards(self):
        quality=self.store.battles._quality
        score={'played':3,'rd':220.,'opponents':{'a':1,'b':1,'c':1}}
        self.assertEqual(quality(score),'Developing')
        for changes in ({'played':2},{'opponents':{'a':2,'b':1}},{'rd':220.01}):
            self.assertEqual(quality({**score,**changes}),'Provisional')
        self.assertEqual(quality({**score,'played':0}),'Unrated')
        established={**score,'played':12,'rd':85.,'opponents':{str(i):1 for i in range(8)}}
        self.assertEqual(quality(established),'Established')
        for changes in ({'played':11},{'rd':85.01},{'opponents':score['opponents']}):
            self.assertEqual(quality({**established,**changes}),'Developing')

    def test_existing_records_rank_on_reopen_without_rewriting_history_or_mmr(self):
        images=[self.import_image(i) for i in range(6)]
        battle=self.store.battles;key=self.character['id']+':images'
        ratings={m['id']:{'rating':1500-i*30.,'played':3,'rd':220.,'wins':2,'losses':1,'ties':0,
                         'opponents':{images[(i+j)%6]['id']:1 for j in (1,2,3)}}
                 for i,m in enumerate(images)}
        board={'revision':'existing','ratings':ratings,'recent':[],'undo':[],
               'history':[],'votes':9,'session':None,'trophies':{}}
        battle._save({'version':1,'rating_model':battle.MODEL,'boards':{key:board}})
        before=battle.path.read_bytes()
        reopened=fixtures.RUNTIME['LibraryStore'](self.store.root)
        state=reopened.battles.request('summary',{'character_id':self.character['id'],'kind':'images'})
        self.assertEqual(state['ranked_count'],6)
        self.assertTrue(all(e['rating_status']=='Developing' for e in state['entries']))
        self.assertEqual({e['id']:e['rating'] for e in state['entries']},{i:s['rating'] for i,s in ratings.items()})
        self.assertEqual(state['votes'],9)
        self.assertEqual(battle.path.read_bytes(),before)

    def test_rank_cutoffs_ties_and_legacy_records(self):
        images=[self.import_image(i) for i in range(20)]
        battle=self.store.battles;key=self.character['id']+':images'
        board={'revision':'legacy','ratings':{m['id']:{'rating':1600-i*10.,'played':6,'wins':4,'losses':2,'ties':0,'rd':100.,'opponents':{o['id']:1 for o in images if o['id']!=m['id']}} for i,m in enumerate(images)},'recent':[],'undo':[],'votes':50,'session':None}
        battle._save({'version':1,'boards':{key:board}})
        state=self.call('state');tiers=[r['tier'] for r in state['entries']]
        self.assertEqual(tiers,['Grandmaster','Master']+['Diamond']*2+['Platinum']*5+['Gold']*5+['Silver']*4+['Bronze']*2)
        self.assertTrue(all(t['legacy'] and t['earned_at'] is None for t in state['trophies']))
        self.assertFalse(any(t['id'].startswith('streak:') for t in state['trophies']))
        board['ratings'][images[1]['id']]['rating']=1600
        battle._save({'version':1,'boards':{key:board}})
        self.assertEqual([e['tier'] for e in self.call('state')['entries'][:2]],['Grandmaster','Grandmaster'])
        for m in images[4:]:m['in_review']=True
        self.assertTrue(all(e['tier']=='Placement' for e in self.call('state')['entries']))
        board['ratings'][images[0]['id']]['played']=2
        battle._save({'version':1,'boards':{key:board}})
        self.assertEqual(next(e for e in self.call('state')['entries'] if e['id']==images[0]['id'])['tier'],'Provisional')

    def test_progress_trophy_persistence_and_undo_without_streak_spam(self):
        for i in range(3):self.import_image(i)
        state=self.call('start',mode='winner',limit=10)
        winner=state['session']['pair']['left']
        for i in range(5):
            pair=state['session']['pair'];outcome='left' if pair['left']==winner else 'right'
            state=self.call('vote',revision=state['revision'],pair_id=pair['id'],outcome=outcome)
        trophy='streak:5:'+winner
        self.assertNotIn(trophy,[t['id'] for t in state['trophies']])
        self.assertIn('progress:votes:1',[t['id'] for t in state['trophies']])
        restored=fixtures.RUNTIME['LibraryStore'](self.store.root).battles.request('state',{'character_id':self.character['id']})
        self.assertEqual(restored['trophies'],state['trophies'])
        undone=self.call('undo',revision=state['revision'])
        self.assertNotIn(trophy,[t['id'] for t in undone['trophies']])
        self.assertEqual(next(e for e in undone['entries'] if e['id']==winner)['streak'],4)
        skipped=self.call('vote',revision=undone['revision'],pair_id=undone['session']['pair']['id'],outcome='skip')
        self.assertEqual(skipped['trophies'],undone['trophies'])
        tied=self.call('vote',revision=skipped['revision'],pair_id=skipped['session']['pair']['id'],outcome='tie')
        self.assertTrue(all(e.get('streak',0)==0 for e in tied['entries'] if e['id'] in (skipped['session']['pair']['left'],skipped['session']['pair']['right'])))
        for _ in range(5):tied=self.call('undo',revision=tied['revision'])
        self.assertEqual(tied['votes'],0);self.assertEqual(tied['trophies'],[])

if __name__=='__main__':unittest.main()
