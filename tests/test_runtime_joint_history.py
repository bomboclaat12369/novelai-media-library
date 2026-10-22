"""Joint history, fixed priors, linked Undo and migration regression checks."""
import copy
import math
import random
import time
import unittest
from unittest.mock import patch
import test_runtime_stability as fixtures
from test_runtime_battles import BattleTests

class JointHistoryTests(unittest.TestCase):
    setUp=BattleTests.setUp
    tearDown=BattleTests.tearDown
    import_image=BattleTests.import_image
    post=BattleTests.post
    call=BattleTests.call

    def board(self, count=8):
        return {'ratings':{str(i):{'rating':1200.,'rd':350.,'played':1,'wins':0,'losses':0,'ties':0} for i in range(count)},
                'history_priors':{},'history':[]}

    def event(self, board, left, right, outcome):
        board['history'].append({'type':'vote','id':str(len(board['history'])),'left':str(left),'right':str(right),'outcome':outcome})

    def test_all_outcomes_link_to_later_opponent_evidence(self):
        battle=self.store.battles
        for initial in ('left','right','tie'):
            for later,direction in (('left',1),('right',-1)):
                board=self.board()
                self.event(board,0,1,initial);battle._fit_history(board)
                before=board['ratings']['0']['rating']
                for opponent in range(2,8):self.event(board,1,opponent,later)
                battle._fit_history(board)
                self.assertGreater(direction*(board['ratings']['0']['rating']-before),30)
                self.assertGreater(board['ratings']['0']['rd'],140)
                snapshot=copy.deepcopy(board['ratings']);battle._fit_history(board)
                self.assertEqual(board['ratings'],snapshot)
                board['history'].reverse();battle._fit_history(board)
                self.assertEqual(board['ratings'],snapshot)

    def test_contradictions_disconnected_and_undo(self):
        board=self.board();battle=self.store.battles
        self.event(board,0,1,'left');self.event(board,0,1,'right');battle._fit_history(board)
        self.assertAlmostEqual(board['ratings']['0']['rating'],1200)
        before=copy.deepcopy(board['ratings'])
        self.event(board,1,2,'left');battle._fit_history(board)
        self.assertNotEqual(board['ratings']['0']['rating'],1200)
        self.assertEqual(board['ratings']['7'],before['7'])
        board['history'].append({'type':'undo','vote_id':'2'});battle._fit_history(board)
        self.assertEqual(board['ratings'],before)

    def test_uncertainty_includes_opponent_covariance(self):
        board=self.board(2);self.event(board,0,1,'tie')
        self.store.battles._fit_history(board)
        scale=400/math.log(10);precision=(scale/350)**2;weight=.25
        # Exact inverse diagonal of the two-entry Hessian.
        expected=scale*math.sqrt((precision+weight)/(precision*(precision+2*weight)))
        self.assertAlmostEqual(board['ratings']['0']['rd'],expected,places=6)
        self.assertGreater(expected,scale/math.sqrt(precision+weight))

    def test_prior_migration_uses_first_before_not_current_scores(self):
        board=self.board(3);board.pop('history_priors')
        board['ratings']['0'].update(rating=1800,rd=70,played=25)
        self.event(board,0,1,'left')
        board['history'][0]['before']=[{'rating':1500,'rd':100,'played':24},{'rating':1200,'rd':350,'played':0}]
        self.store.battles._fit_history(board)
        self.assertEqual(board['history_priors']['0'],{'rating':1500,'rd':100})
        self.assertLess(board['ratings']['0']['rating'],1550)
        board['history'].append({'type':'undo','vote_id':'0'})
        self.store.battles._fit_history(board)
        self.assertAlmostEqual(board['ratings']['0']['rating'],1500)
        self.assertAlmostEqual(board['ratings']['0']['rd'],100)

    def test_persistent_linked_undo_and_migration_backup(self):
        images=[self.import_image(i) for i in range(6)]
        state=self.call('start',limit=0)
        for _ in range(12):
            previous=state
            state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='left')
        state=self.call('undo',revision=state['revision'])
        self.assertEqual(state['entries'],previous['entries'])
        self.assertEqual(state['recorded_votes'],11)
        owner=self.character['id'];battle=self.store.battles
        legacy=copy.deepcopy(battle._load());legacy['rating_model']='glicko-static-v1'
        legacy['boards'][owner+':images'].pop('history_priors')
        battle._save(legacy)
        reload=fixtures.RUNTIME['LibraryStore'](self.store.root)
        migrated=reload.battles.request('state',{'character_id':owner})
        self.assertEqual(migrated['rating_model'],'joint-history-v1')
        self.assertTrue((self.store.backup_dir/'battles-before-joint-history.json').exists())
        data=reload.battles.path.read_bytes()
        reload.battles.request('state',{'character_id':owner})
        self.assertEqual(data,reload.battles.path.read_bytes())

    def test_220_entry_fit(self):
        board=self.board(220);rng=random.Random(16)
        for _ in range(1600):
            a,b=rng.sample(range(220),2);self.event(board,a,b,'left' if a<b else 'right')
        reference=copy.deepcopy(board)
        start=time.perf_counter();self.store.battles._fit_history(board)
        elapsed=time.perf_counter()-start
        print('220 entries / 1600 comparisons joint fit: %.3fs'%elapsed)
        self.assertLess(elapsed,8)
        self.assertGreater(board['ratings']['0']['rating'],board['ratings']['219']['rating'])
        start=time.perf_counter()
        with patch.object(self.store.battles,'_inverse_diagonal',return_value=None):
            self.store.battles._fit_history(reference)
        print('Reference iterative uncertainty: %.3fs'%(time.perf_counter()-start))
        for ident, score in board['ratings'].items():
            self.assertEqual(score['rating'],reference['ratings'][ident]['rating'])
            self.assertAlmostEqual(score['rd'],reference['ratings'][ident]['rd'],places=6)

    def test_dense_uncertainty_with_ties_repeats_and_disconnected_entries(self):
        board=self.board(64);rng=random.Random(9)
        for i in range(600):
            a,b=rng.sample(range(55),2)
            self.event(board,a,b,('left','right','tie')[i%3])
        reference=copy.deepcopy(board)
        self.store.battles._fit_history(board)
        with patch.object(self.store.battles,'_inverse_diagonal',return_value=None):
            self.store.battles._fit_history(reference)
        for ident,score in board['ratings'].items():
            self.assertEqual(score['rating'],reference['ratings'][ident]['rating'])
            self.assertAlmostEqual(score['rd'],reference['ratings'][ident]['rd'],places=6)
        self.assertIsNone(self.store.battles._inverse_diagonal([1.]*400,[]))
        self.assertIsNone(self.store.battles._inverse_diagonal([1.]*64,[(0,1,.1)]))

if __name__=='__main__':unittest.main()
