"""Numerical reference, targeted placement, evidence tracking and full vote log."""
import random
import unittest
import test_runtime_stability as fixtures
from test_runtime_battles import BattleTests

class PlacementTests(unittest.TestCase):
    setUp=BattleTests.setUp
    tearDown=BattleTests.tearDown
    import_image=BattleTests.import_image
    post=BattleTests.post
    call=BattleTests.call

    def test_published_glicko_example_and_uncertainty(self):
        calc=self.store.battles._glicko
        r,rd=calc(1500,200,[(1400,30,1),(1550,100,0),(1700,300,0)])
        self.assertAlmostEqual(r,1464.106,places=2)
        self.assertAlmostEqual(rd,151.399,places=2)
        fresh,_=calc(1200,350,[(1200,80,1)])
        veteran,_=calc(1200,80,[(1200,350,0)])
        self.assertGreater(fresh-1200,1200-veteran)
        tied,tied_rd=calc(1200,350,[(1200,350,.5)])
        self.assertEqual(tied,1200);self.assertLess(tied_rd,350)

    def test_target_placement_moves_top_entry_and_persists_history(self):
        images=[self.import_image(i) for i in range(12)]
        battle=self.store.battles;battle.rng=random.Random(17)
        owner=self.character['id'];key=owner+':images'
        ratings={m['id']:{'rating':900+i*65.,'played':30,'rd':80.,'wins':15,'losses':15,'ties':0,'opponents':{x['id']:1 for x in images[1:] if x['id']!=m['id']}} for i,m in enumerate(images[1:])}
        board={'revision':'old','ratings':ratings,'recent':[],'undo':[],'votes':165,'session':None}
        battle._save({'version':1,'boards':{key:board}})
        original=dict(ratings[images[1]['id']])
        first=self.call('state');self.assertEqual(next(e for e in first['entries'] if e['id']==images[1]['id'])['rating'],900)
        placed=self.call('place',entry_id=images[0]['id'],revision='old')
        self.assertEqual(placed['session']['target_id'],images[0]['id'])
        self.assertEqual(next(e for e in placed['entries'] if e['id']==images[0]['id'])['rating'],1200)
        for _ in range(8):
            pair=placed['session']['pair'];self.assertIn(images[0]['id'],[pair['left'],pair['right']])
            placed=self.call('vote',revision=placed['revision'],pair_id=pair['id'],outcome='left' if pair['left']==images[0]['id'] else 'right')
        winner=next(e for e in placed['entries'] if e['id']==images[0]['id'])
        self.assertGreater(winner['rating'],1600)  # Old K32 cannot reach this in eight wins.
        self.assertGreaterEqual(winner['opponent_count'],4)
        stored=battle._load()['boards'][key]
        self.assertEqual(len([e for e in stored['history'] if e['type']=='vote']),8)
        self.assertTrue((self.store.backup_dir/'battles-before-placement.json').exists())
        reload=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reload.battles.request('state',{'character_id':owner})['session'],placed['session'])
        before=stored['history'][-1]
        undone=self.call('undo',revision=placed['revision'])
        current=battle._load()['boards'][key]
        self.assertEqual(current['history'][-1]['vote_id'],before['id'])
        for i,ident in enumerate((before['left'],before['right'])):
            self.assertAlmostEqual(battle._score(current,ident)['rating'],before['before'][i]['rating'])
        same=self.call('state');self.assertEqual(same['entries'],undone['entries'])
        status,_=self.post('/api/battles/place',{'character_id':owner,'kind':'images','revision':undone['revision'],'entry_id':'missing'})
        self.assertEqual(status,400)

    def test_batch_persists_and_repeat_opponent_is_not_established(self):
        for i in range(20):self.import_image(i)
        battle=self.store.battles;battle.rng=random.Random(5)
        state=self.call('start',mode='rank',limit=25)
        batch=state['placement_batch'];self.assertEqual(len(batch),8)
        for _ in range(10):
            pair=state['session']['pair']
            state=self.call('vote',revision=state['revision'],pair_id=pair['id'],outcome='tie')
        self.assertTrue(set(batch)&set(state['placement_batch']))
        self.assertEqual(battle._quality({'played':100,'rd':50,'opponents':{'one':100}}),'Provisional')
        self.assertEqual(battle._quality({'played':15,'rd':80,'opponents':{str(i):1 for i in range(8)}}),'Established')

if __name__=='__main__':unittest.main()
