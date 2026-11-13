"""Use saved Sets and the public battle actions to check Duo identity and ranking."""
import copy
import json
from unittest.mock import patch
import random
import unittest

import test_runtime_stability as fixtures


class BattleDuoTests(unittest.TestCase):
    setUp = fixtures.RuntimeStabilityTests.setUp
    import_image = fixtures.RuntimeStabilityTests.import_image

    tearDown = fixtures.RuntimeStabilityTests.tearDown

    def battle(self, action, state=None, kind='images', **body):
        if state:
            body['revision'] = state['revision']
        return self.store.battles.request(action, {'character_id':self.character['id'], 'kind':kind, **body})

    def pair(self, group, *sides):
        self.store.set_duo(group['id'], {'expected':group.get('after_hours_duo'),
            'duo':{'version':1, 'media_ids':list(sides)} if sides else None})

    @staticmethod
    def duo(state):
        entry, = [e for e in state['entries'] if e.get('duo_side')]
        return entry

    def test_stronger_back_seeds_once_and_each_vote_belongs_to_the_duo(self):
        a, b, c, d, e = [self.import_image(i)['id'] for i in range(5)]
        group = self.store.create_set(self.character['id'], 'Studio', [a,b,c], preserve_placement=True)
        state = self.battle('state')
        opponents = (a,c,d,e)*3
        for index,other in enumerate(opponents):
            state = self.battle('challenge', state, entry_id=b, opponent_id=other)
            state = self.battle('vote', state, pair_id=state['session']['pair']['id'], outcome='tie' if index%3==2 else 'left')
        source = next(row for row in state['entries'] if row['id']==b)
        self.assertGreater(source['rating'], 1200)
        self.assertFalse(source['provisional'])
        first_votes = copy.deepcopy(self.store.battles._active_history(self.store.battles.data['boards'][self.character['id']+':images']))
        stale = self.battle('challenge', state, entry_id=a, opponent_id=b)
        self.pair(group, a, b)
        self.assertFalse(self.battle('state')['session']['available'])
        with self.assertRaises(ValueError):
            self.battle('vote', stale, pair_id=stale['session']['pair']['id'], outcome='left')
        state = self.battle('cards')
        self.assertTrue(state['session']['available'])
        self.assertNotEqual(stale['session']['pair']['id'], state['session']['pair']['id'])
        duo = self.duo(state)
        self.assertEqual({r['id'] for r in state['entries']}, {c,d,e,duo['id']})
        self.assertEqual(duo['images'], [a,b])
        self.assertEqual(state['votes'], len(opponents))
        for k in ('rating','rd','played','wins','opponent_count','provisional'):
            self.assertEqual(duo[k], source[k], k)
        with self.assertRaises(ValueError):
            self.battle('challenge', state, entry_id=a, opponent_id=b)
        state = self.battle('challenge', state, entry_id=a, opponent_id=c)
        self.assertEqual(state['session']['pair']['left'], duo['id'])
        voted = self.battle('vote', state, pair_id=state['session']['pair']['id'], outcome='right')
        new = self.duo(voted)
        self.assertLess(new['rating'], duo['rating'])
        self.assertEqual(new['played'], source['played']+1)
        self.assertEqual(self.battle('history', entry_id=b)['comparisons'][0]['result'], 'Loss')
        self.pair(group, b, a)
        reopened = type(self.store)(self.store.root)
        swapped = self.duo(reopened.battles.request('summary', {'character_id':self.character['id']}))
        self.assertEqual((swapped['id'],swapped['rating'],swapped['images']), (duo['id'], new['rating'], [b,a]))
        state = self.battle('undo', voted)
        self.assertAlmostEqual(self.duo(state)['rating'], source['rating'], places=5)
        self.assertEqual(self.duo(state)['played'], source['played'])
        board = self.store.battles.data['boards'][self.character['id']+':images']
        self.assertEqual(self.store.battles._active_history(board), first_votes)
        seed, = [event for event in board['history'] if event['type']=='duo_seed']
        self.assertEqual((seed['source_id'], seed['media_ids']), (b, [a,b]))
        self.pair(group)
        singles = {row['id']:row for row in self.battle('cards')['entries']}
        self.assertEqual(set(singles), {a,b,c,d,e})
        self.assertAlmostEqual(singles[b]['rating'], source['rating'])
        self.pair(group, b, a)
        self.assertEqual(self.duo(self.battle('cards'))['id'], duo['id'])
        self.pair(group, b, c)
        self.assertNotEqual(self.duo(self.battle('cards'))['id'], duo['id'])

    def test_seed_evidence_replays_after_interruption_and_survives_restore(self):
        a,b = [self.import_image(i)['id'] for i in range(2)]
        group = self.store.create_set(self.character['id'], 'Night', [a,b], preserve_placement=True)
        self.pair(group, a, b)
        with patch.object(self.store.tracking, 'ingest', side_effect=OSError('journal unavailable')):
            saved = self.battle('cards')
        self.assertTrue(self.duo(saved))
        self.store = type(self.store)(self.store.root)
        state = self.battle('cards')
        self.assertEqual(self.battle('cards')['revision'], state['revision'])
        snapshot = self.store.create_checkpoint({})
        self.pair(self.store.set_item(group['id']))
        self.battle('cards')
        plan = self.store.checkpoint_preview({'id':snapshot['id']})
        self.store.checkpoint_restore({'id':snapshot['id'], 'token':plan['token']})
        self.assertEqual(self.duo(self.battle('cards'))['id'], self.duo(state)['id'])
        evidence = [json.loads(line) for line in self.store.tracking.export().splitlines() if line]
        seed, = [e['payload'] for e in evidence if e['kind']=='battle.duo_seed']
        self.assertEqual(seed['media_ids'], [a,b])
        self.assertEqual(seed['inherited']['rating'], self.duo(state)['rating'])

    def test_main_membership_is_optional_both_originals_must_be_available(self):
        a,b,c,d = [self.import_image(i)['id'] for i in range(4)]
        group = self.store.create_set(self.character['id'], 'Two sides', [a,b,d], preserve_placement=True)
        self.pair(group, a, b)
        for first,second in ((True,True),(True,False),(False,True),(False,False)):
            self.store.media_item(a)['in_all'] = first
            self.store.media_item(b)['in_all'] = second
            state = self.battle('cards')
            row = self.duo(state)
            self.assertEqual({e['id'] for e in state['entries']}, {c,d,row['id']})
            self.assertEqual(row['rating'], 1200)
            state = self.battle('place', state, entry_id=b)
            self.assertIn(row['id'], (state['session']['pair']['left'],state['session']['pair']['right']))
        self.assertEqual(self.battle('summary', kind='sets')['entries'][0]['images'], group['media_ids'])
        self.store.media_item(a)['in_all'] = True
        for obj,key,value in ((self.store.media_item(b),'in_review',True),
                              (self.store.media_item(b),'in_purgatory',True),
                              (self.store.media_item(b),'flagged_for_removal',True),
                              (self.store.media_item(b),'media_type','video'),
                              (group,'in_purgatory',True),(group,'media_ids',[a,d]),
                              (group,'after_hours_duo',{'version':2,'media_ids':[a,b]})):
            with self.subTest(key=key):
                old = obj.get(key)
                obj[key] = value
                self.assertEqual({e['id'] for e in self.battle('summary')['entries']}, {a,c,d})
                obj[key] = old

    def test_refine_top_50_cutoff_after_scope_and_eligibility(self):
        battle = self.store.battles
        ids = [f'photo-{i:02}' for i in range(61)]
        entries = {k:{'id':k, 'count':1, 'categories':['studio']} for k in ids}
        scores = {k:{'rating':2000-i*5.,'rd':90.,'played':8,'wins':5,'losses':3,'ties':0} for i,k in enumerate(ids)}
        entries[ids[0]]['flagged_for_removal'] = True
        entries[ids[1]]['categories'] = []
        scores[ids[2]]['played'] = 0
        for size in (10,25,50):
            board = {'ratings':scores, 'session':{'mode':f'refine{size}', 'minimum':1, 'similar':False, 'category':'studio'}}
            board['session']['target_id'] = ids[size+2]
            pair = battle._pair(board, entries, rng=random.Random(21))
            self.assertIn(board['session']['target_id'], (pair['left'], pair['right']))
            self.assertTrue({pair['left'], pair['right']} <= set(ids[3:size+3]))
            board['session']['target_id'] = ids[size+3]
            self.assertIsNone(battle._pair(board, entries))
