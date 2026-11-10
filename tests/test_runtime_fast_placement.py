"""Favorite evidence, fast cold starts, upgrade/Undo and scheduler coverage."""
import copy
import random
import unittest
import test_runtime_battles as battle_fixtures
import test_runtime_stability as fixtures


class FastPlacementTests(unittest.TestCase):
    setUp = battle_fixtures.BattleTests.setUp
    tearDown = battle_fixtures.BattleTests.tearDown
    import_image = battle_fixtures.BattleTests.import_image
    post = battle_fixtures.BattleTests.post
    call = battle_fixtures.BattleTests.call

    def board(self):
        return {'ratings':{}, 'history_priors':{}, 'history':[], 'recent':[], 'votes':0,
                'session':{'mode':'rank', 'minimum':1, 'category':'', 'similar':False, 'limit':0, 'done':0}}

    def entries(self, count=40):
        return {str(i):{'id':str(i), 'name':str(i), 'images':[str(i)], 'count':1, 'favorite':i%4==0}
                for i in range(count)}

    def comparison(self, board, left, right, outcome):
        pair={'left':left, 'right':right}
        before=self.store.battles._apply_comparison(board,pair,outcome)
        board['history'].append({'type':'vote', 'id':str(board['votes']), **pair, 'outcome':outcome,
                                 'before':before, 'at':'2026-11-10T00:00:00Z'})
        board['recent']=(board['recent']+[[left,right]])[-32:]
        self.store.battles._fit_history(board)

    def test_favorite_hint_is_once_and_is_not_a_vote_or_confidence(self):
        images=[self.import_image(i) for i in range(8)]
        self.store.set_favorite(images[0]['id'],True)
        state=self.call('start',limit=0)
        favorite=next(e for e in state['entries'] if e['id']==images[0]['id'])
        self.assertEqual((favorite['rating'],favorite['rd'],favorite['played']),(1360.,350.,0))
        self.assertEqual((favorite['tier'],favorite['rating_status']),('Unranked','Unrated'))
        self.assertEqual((state['votes'],state['recorded_votes'],state['ranked_count']),(0,0,0))
        self.assertTrue(all(e['rating']==1200. for e in state['entries'] if e['id']!=favorite['id']))
        self.store.set_favorite(images[0]['id'],False)
        self.store.set_favorite(images[0]['id'],True)
        self.store.set_favorite(images[1]['id'],True)
        again=self.call('start',revision=state['revision'],limit=0)
        ratings={e['id']:e['rating'] for e in again['entries']}
        self.assertEqual(ratings[images[0]['id']],1360.)
        self.assertEqual(ratings[images[1]['id']],1200.)
        board=self.store.battles._load()['boards'][self.character['id']+':images']
        self.assertEqual(sum(e['type']=='starting_preferences' for e in board['history']),1)

    def test_ties_and_later_opponents_carry_favorite_evidence(self):
        board=self.board();entries=self.entries(8);battle=self.store.battles
        battle._starting_preferences(board,entries,'images')
        self.comparison(board,'0','1','tie')
        self.assertGreater(board['ratings']['1']['rating'],1200.)
        self.assertLess(board['ratings']['0']['rating'],1360.)
        previous=board['ratings']['0']['rating']
        self.comparison(board,'1','2','left')
        self.assertGreater(board['ratings']['0']['rating'],previous)
        self.assertEqual(board['ratings']['0']['played'],1)
        self.assertEqual(len(battle._active_history(board)),2)

    def test_results_can_overturn_an_incorrect_favorite(self):
        board=self.board();entries=self.entries(8);battle=self.store.battles
        battle._starting_preferences(board,entries,'images')
        for other in ('1','2','3','5'):
            self.comparison(board,'0',other,'right')
        self.assertLess(board['ratings']['0']['rating'],1200.)
        before=copy.deepcopy(board)
        battle._starting_preferences(board,entries,'images')
        self.assertEqual(board,before)

    def test_seeded_undo_reload_and_forecast_preserve_the_starting_point(self):
        images=[self.import_image(i) for i in range(8)]
        self.store.set_favorite(images[0]['id'],True)
        state=self.call('challenge',entry_id=images[0]['id'],opponent_id=images[1]['id'])
        before={e['id']:(e['rating'],e['rd'],e['played']) for e in state['entries']}
        after=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='tie')
        undone=self.call('undo',revision=after['revision'])
        self.assertEqual({e['id']:(e['rating'],e['rd'],e['played']) for e in undone['entries']},before)
        self.assertEqual(undone['recorded_votes'],0)
        saved=self.store.battles.path.read_bytes()
        first=self.call('state');second=self.call('state')
        self.assertEqual(first['preload_entries'],second['preload_entries'])
        self.assertEqual(saved,self.store.battles.path.read_bytes())
        reopened=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reopened.battles.request('state',{'character_id':self.character['id']})['entries'],second['entries'])

    def test_upgrade_keeps_existing_votes_and_can_rebuild_seeded_priors(self):
        images=[self.import_image(i) for i in range(8)]
        state=self.call('challenge',entry_id=images[0]['id'],opponent_id=images[1]['id'])
        state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='left')
        state=self.call('challenge',revision=state['revision'],entry_id=images[0]['id'],opponent_id=images[2]['id'])
        state=self.call('vote',revision=state['revision'],pair_id=state['session']['pair']['id'],outcome='tie')
        battle=self.store.battles;key=self.character['id']+':images';legacy=copy.deepcopy(battle._load())
        legacy['boards'][key].pop('starting_preferences')
        before=copy.deepcopy(legacy['boards'][key]);battle._save(legacy)
        self.store.set_favorite(images[0]['id'],True)
        updated=self.call('start',revision=state['revision'],limit=0)
        current=battle._load()['boards'][key]
        self.assertEqual(battle._active_history(current),battle._active_history(before))
        self.assertEqual((updated['votes'],updated['recorded_votes']),(2,2))
        self.assertEqual(current['history_priors'][images[0]['id']],{'rating':1360.,'rd':350.})
        self.assertGreater(current['ratings'][images[0]['id']]['rating'],before['ratings'][images[0]['id']]['rating'])
        for ident,score in before['ratings'].items():
            for field in ('played','wins','losses','ties','opponents'):
                self.assertEqual(current['ratings'][ident][field],score[field])
        rebuilt=copy.deepcopy(current);rebuilt.pop('history_priors');battle._fit_history(rebuilt)
        self.assertEqual(rebuilt['history_priors'],current['history_priors'])
        self.assertEqual(rebuilt['ratings'],current['ratings'])

    def test_legacy_and_developed_priors_are_not_overwritten(self):
        board=self.board();entries=self.entries(3)
        entries['1']['favorite']=True
        board['ratings']={'0':{'rating':1200.,'rd':80.,'played':20,'opponents':{str(i):1 for i in range(8)}},
                          '1':{'rating':1530.,'rd':110.,'played':1}}
        board['history_priors']={'0':{'rating':1200.,'rd':350.},'1':{'rating':1500.,'rd':120.}}
        before=copy.deepcopy(board)
        self.assertFalse(self.store.battles._starting_preferences(board,entries,'images'))
        self.assertEqual(board['ratings'],before['ratings'])
        self.assertEqual(board['history_priors'],before['history_priors'])

    def test_starter_mixes_favorites_and_ordinary_images_and_reuses_progress(self):
        battle=self.store.battles;board=self.board();entries=self.entries(60)
        battle._starting_preferences(board,entries,'images')
        first=battle._pair(board,entries,rng=random.Random(4));starter=board['scheduler']['starter']
        self.assertEqual(len(starter),12)
        self.assertEqual(sum(entries[i]['favorite'] for i in starter),4)
        self.assertTrue({first['left'],first['right']}<=set(starter))
        prior=list(starter)
        battle._pair(board,entries,rng=random.Random(9))
        self.assertEqual(board['scheduler']['starter'],prior)
        existing=self.board()
        existing['ratings']['59']={'rating':1250.,'rd':225.,'played':3,'opponents':{'1':1,'2':1,'3':1}}
        battle._pair(existing,entries,rng=random.Random(4))
        self.assertIn('59',existing['scheduler']['starter'])

    def test_fast_start_reaches_real_placements_without_weakening_confidence(self):
        battle=self.store.battles;board=self.board();entries=self.entries(120)
        truth={i:random.Random(10+int(i)).gauss(1200,220) for i in entries}
        for ident,entry in entries.items():entry['favorite']=truth[ident]>1350
        battle._starting_preferences(board,entries,'images');rng=random.Random(8);first_five=None
        for n in range(75):
            pair=battle._pair(board,entries,rng=rng);difference=truth[pair['left']]-truth[pair['right']]
            self.comparison(board,pair['left'],pair['right'],'left' if difference>25 else 'right' if difference<-25 else 'tie')
            placed=[e for e in battle._ranked_rows(board,entries) if not e['provisional']]
            if len(placed)>=5 and first_five is None:first_five=n+1
        self.assertIsNotNone(first_five);self.assertLessEqual(first_five,35)
        self.assertGreaterEqual(len(placed),20)
        for entry in placed:
            self.assertGreaterEqual(entry['played'],3);self.assertGreaterEqual(entry['opponent_count'],3);self.assertLessEqual(entry['rd'],220.)

    def test_difficult_images_rotate_so_new_entries_are_not_starved(self):
        battle=self.store.battles;entries=self.entries(40);board=self.board()
        scores={i:{'rating':1200.,'rd':80. if int(i)<8 else 300.,'played':20 if int(i)<8 else 0,
                   'opponents':{str(j):1 for j in range(8)} if int(i)<8 else {},'last_seen':0} for i in entries}
        waiting=list(entries)[8:];visited=set();rng=random.Random(6)
        for _ in range(220):
            candidates,anchors,calibrating=battle._placement_candidates(board,list(entries.values()),scores,waiting,rng)
            self.assertFalse(calibrating);self.assertEqual(anchors,set(entries)-set(waiting))
            ident=candidates[0];visited.add(ident);scores[ident]['played']+=1;board['votes']+=1;scores[ident]['last_seen']=board['votes']
        self.assertEqual(visited,set(waiting))

    def test_filters_and_removal_flags_still_limit_fast_matchups(self):
        battle=self.store.battles;board=self.board();entries=self.entries(30)
        for i,e in entries.items():e.update(categories=['wanted'] if int(i)<15 else ['other'],flagged_for_removal=int(i)<5)
        board['session']['category']='wanted'
        for n in range(20):
            pair=battle._pair(board,entries,rng=random.Random(n))
            self.assertTrue({pair['left'],pair['right']}<=set(map(str,range(5,15))))
        board['session'].update(category='',similar=True,minimum=10)
        for i,e in entries.items():e['count']=10 if int(i)<15 else 30
        pair=battle._pair(board,entries,rng=random.Random(4))
        self.assertEqual(entries[pair['left']]['count'],entries[pair['right']]['count'])

    def test_image_favorites_do_not_seed_set_rankings(self):
        images=[self.import_image(i) for i in range(4)]
        self.store.set_favorite(images[0]['id'],True)
        for n in range(2):self.store.create_set(self.character['id'],str(n),[i['id'] for i in images[n*2:n*2+2]])
        state=self.call('start',kind='sets',minimum=1,limit=0)
        self.assertTrue(all(e['rating']==1200. for e in state['entries']))
        self.assertNotIn('starting_preferences',self.store.battles._load()['boards'][self.character['id']+':sets'])


if __name__=='__main__':unittest.main()
