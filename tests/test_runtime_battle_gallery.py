"""Continuous sessions, read-only lookahead, focused return and percentile tiers."""
import copy
import unittest
from collections import Counter
from test_runtime_battles import BattleTests

class BattleGalleryTests(unittest.TestCase):
    setUp=BattleTests.setUp
    tearDown=BattleTests.tearDown
    import_image=BattleTests.import_image
    post=BattleTests.post
    call=BattleTests.call

    def test_lookahead_covers_actual_outcomes_without_writing(self):
        for i in range(12):self.import_image(i)
        state=self.call('start',limit=0)
        for mode in ('rank','winner','refine10','refine25'):
            if mode!='rank':state=self.call('start',mode=mode,limit=0,revision=state['revision'])
            for outcome in ('left','right','tie','skip'):
                persisted=self.store.battles.path.read_bytes()
                repeated=self.call('state')
                self.assertEqual(self.store.battles.path.read_bytes(),persisted)
                self.assertEqual(repeated['preload_entries'],state['preload_entries'])
                prepared=set(state['preload_entries']);self.assertLessEqual(len(prepared),8)
                state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome=outcome)
                self.assertTrue({state['session']['pair']['left'],state['session']['pair']['right']}<=prepared)
        self.assertEqual(state['session']['limit'],0)

    def test_focus_returns_to_continuous_and_undo_crosses_sessions(self):
        images=[self.import_image(i) for i in range(8)]
        state=self.call('start',limit=0)
        for _ in range(12):
            state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='left')
        self.assertEqual(state['session']['done'],12);self.assertIsNotNone(state['session']['pair'])
        focused=self.call('place',revision=state['revision'],entry_id=images[0]['id'])
        self.assertEqual({e['id']:e['rating'] for e in focused['entries']},{e['id']:e['rating'] for e in state['entries']})
        for i in range(10):
            pair=focused['session']['pair'];self.assertIn(images[0]['id'],[pair['left'],pair['right']])
            prepared=set(focused['preload_entries'])
            focused=self.call('vote',revision=focused['revision'],pair_id=pair['id'],outcome='right')
            self.assertTrue({focused['session']['pair']['left'],focused['session']['pair']['right']}<=prepared)
        self.assertFalse(focused['session'].get('target_id'));self.assertEqual(focused['session']['limit'],0)
        undone=self.call('undo',revision=focused['revision']);self.assertEqual(undone['session']['target_id'],images[0]['id']);self.assertEqual(undone['session']['done'],9)
        ended=self.call('resume',revision=undone['revision']);self.assertFalse(ended['session'].get('target_id'));self.assertEqual(ended['votes'],undone['votes'])
        restarted=self.call('start',limit=25,revision=ended['revision'])
        restored=self.call('undo',revision=restarted['revision']);self.assertEqual(restored['votes'],ended['votes']-1)

    def test_seven_tiers_exact_ties_and_crown(self):
        battle=self.store.battles
        entries={str(i):{'id':str(i),'name':str(i),'images':[str(i)],'count':1} for i in range(200)}
        ratings={i:{'rating':2000-int(i)*3.,'played':20,'rd':70,'opponents':{str(k):1 for k in range(10)},'wins':10,'losses':10,'ties':0} for i in entries}
        board={'ratings':ratings}
        rows=battle._ranked_rows(board,entries)
        self.assertEqual(Counter(r['tier'] for r in rows),{'Grandmaster':2,'Master':8,'Diamond':10,'Platinum':30,'Gold':50,'Silver':60,'Bronze':40})
        self.assertTrue(rows[0]['leader']);self.assertFalse(any(r['leader'] for r in rows[1:]))
        ratings['1']['rating']=ratings['0']['rating']
        rows=battle._ranked_rows(board,entries)
        self.assertEqual([r['position'] for r in rows[:2]],[1,1]);self.assertFalse(any(r['leader'] for r in rows))
        ratings['0']['played']=0
        rows=battle._ranked_rows(board,entries);self.assertEqual(rows[-1]['tier'],'Unranked');self.assertNotIn('position',rows[-1])

if __name__=='__main__':unittest.main()
