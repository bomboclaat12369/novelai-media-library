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

    def test_rank_cutoffs_ties_and_legacy_records(self):
        images=[self.import_image(i) for i in range(20)]
        battle=self.store.battles;key=self.character['id']+':images'
        board={'revision':'legacy','ratings':{m['id']:{'rating':1600-i*10.,'played':6,'wins':4,'losses':2,'ties':0,'rd':100.,'opponents':{o['id']:1 for o in images if o['id']!=m['id']}} for i,m in enumerate(images)},'recent':[],'undo':[],'votes':50,'session':None}
        battle._save({'version':1,'boards':{key:board}})
        state=self.call('state');tiers=[r['tier'] for r in state['entries']]
        self.assertEqual(tiers,['Champion','Diamond']+['Gold']*3+['Silver']*5+['Bronze']*10)
        self.assertTrue(all(t['legacy'] and t['earned_at'] is None for t in state['trophies']))
        self.assertFalse(any(t['id'].startswith('streak:') for t in state['trophies']))
        board['ratings'][images[1]['id']]['rating']=1600
        battle._save({'version':1,'boards':{key:board}})
        self.assertEqual([e['tier'] for e in self.call('state')['entries'][:2]],['Diamond','Diamond'])
        for m in images[4:]:m['in_review']=True
        self.assertTrue(all(e['tier']=='Placement' for e in self.call('state')['entries']))
        board['ratings'][images[0]['id']]['played']=4
        battle._save({'version':1,'boards':{key:board}})
        self.assertEqual(next(e for e in self.call('state')['entries'] if e['id']==images[0]['id'])['tier'],'Provisional')

    def test_trophy_streak_persistence_and_undo(self):
        for i in range(3):self.import_image(i)
        state=self.call('start',mode='winner',limit=10)
        winner=state['session']['pair']['left']
        for i in range(5):
            pair=state['session']['pair'];outcome='left' if pair['left']==winner else 'right'
            state=self.call('vote',revision=state['revision'],pair_id=pair['id'],outcome=outcome)
        trophy='streak:5:'+winner
        self.assertIn(trophy,[t['id'] for t in state['trophies']])
        self.assertIn('votes:1',[t['id'] for t in state['trophies']])
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
