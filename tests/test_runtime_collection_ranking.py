"""Placement coverage, category isolation, flags, rating paths and achievements."""
import copy
import random
import unittest
from test_runtime_battles import BattleTests

class CollectionRankingTests(unittest.TestCase):
    setUp=BattleTests.setUp
    tearDown=BattleTests.tearDown
    import_image=BattleTests.import_image
    post=BattleTests.post
    call=BattleTests.call

    def test_initial_coverage_and_finish_placements(self):
        images=[self.import_image(i) for i in range(20)]
        self.store.battles.rng=random.Random(42)
        state=self.call('start',mode='placements',limit=0)
        for _ in range(20):
            state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='tie')
        self.assertTrue(all(e['played']>=1 for e in state['entries']))
        self.assertGreater(state['unfinished_count'],0)
        data=copy.deepcopy(self.store.battles._load());board=data['boards'][self.character['id']+':images']
        for m in images:
            board['ratings'][m['id']]={'rating':1200.,'rd':80.,'played':20,'opponents':{o['id']:1 for o in images if o!=m}}
        self.store.battles._save(data)
        done=self.call('start',mode='placements',revision=state['revision'])
        self.assertEqual(done['unfinished_count'],0);self.assertIsNone(done['session']['pair'])

    def test_category_scope_keeps_global_board_and_focus_returns(self):
        images=[self.import_image(i) for i in range(8)]
        self.character['categories']=[{'id':'dress','name':'Dress','media_type':'image'}]
        for m in images[:3]:m['categories']=['dress']
        state=self.call('start',category='dress',limit=0)
        for _ in range(5):
            self.assertTrue({state['session']['pair']['left'],state['session']['pair']['right']}<={m['id'] for m in images[:3]})
            state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='left')
        self.assertEqual(len(state['entries']),8);self.assertEqual(state['scope_count'],3)
        ratings={e['id']:(e['rating'],e['tier']) for e in state['entries']}
        focus=self.call('place',entry_id=images[-1]['id'],revision=state['revision'])
        self.assertEqual(focus['session']['category'],'')
        resume=self.call('resume',revision=focus['revision'])
        self.assertEqual(resume['session']['category'],'dress')
        self.assertEqual({e['id']:(e['rating'],e['tier']) for e in resume['entries']},ratings)

    def test_removal_flags_preserve_current_vote_and_ratings(self):
        for i in range(4):self.import_image(i)
        state=self.call('start');pair=state['session']['pair'];ident=pair['left']
        status,media=self.post('/api/media/'+ident+'/removal-flag',{'flagged':True})
        self.assertEqual(status,200);self.assertTrue(media['in_all']);self.assertTrue(media['flagged_for_removal'])
        view=self.call('summary');self.assertTrue(view['session']['available']);self.assertEqual(view['votes'],0)
        self.assertTrue(all(e['rating']==1200 for e in view['entries']))
        state=self.call('vote',revision=state['revision'],pair_id=pair['id'],outcome='left')
        self.assertNotIn(ident,(state['session']['pair']['left'],state['session']['pair']['right']))
        self.assertEqual(next(e for e in state['entries'] if e['id']==ident)['played'],1)
        self.post('/api/media/'+ident+'/removal-flag',{'flagged':False})
        self.assertEqual(self.call('summary')['scope_count'],4)

    def test_history_direct_indirect_undo_and_read_only(self):
        for i in range(6):self.import_image(i)
        self.store.battles.rng=random.Random(12)
        state=self.call('start',limit=0)
        for _ in range(8):state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='left')
        kinds=set()
        for e in state['entries']:
            history=self.call('history',entry_id=e['id']);kinds.update(p[-1] for p in history['points'])
            if history['points']:self.assertEqual(history['points'][-1][2],round(e['rating'],1))
        self.assertTrue({'direct','indirect','baseline'}<=kinds)
        state=self.call('undo',revision=state['revision'])
        self.assertTrue(any(self.call('history',entry_id=e['id'])['points'][-1][-1]=='undo' for e in state['entries']))
        before=self.store.battles.path.read_bytes();self.call('summary');self.call('history',entry_id=state['entries'][0]['id'])
        self.assertEqual(before,self.store.battles.path.read_bytes())
        self.assertTrue(all(t['id'].startswith('progress:') for t in state['trophies']))
        self.assertEqual(len(state['achievements']),5)

if __name__=='__main__':unittest.main()
