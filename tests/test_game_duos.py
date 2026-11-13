"""Duo catalog, recovery and duplicate-pull edge cases."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from game import engine, migrations
from game.catalog import public_catalog, read_library
from game.store import merge_catalog
from tests.test_game_evolutions import pack_seed, write_fixture


class Duos(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / 'library'
        self.data = write_fixture(self.root)
        self.group = self.data['sets'][0]
        self.pair = {'version': 1, 'media_ids': ['a-photo-1', 'a-photo-0']}
        self.key = 'duo:' + self.group['id']

    def read(self):
        (self.root / 'library.json').write_text(json.dumps(self.data), encoding='utf-8')
        return read_library(self.root)

    def test_overall_uses_one_live_battle_competitor_for_either_side(self):
        self.group['after_hours_duo'] = self.pair
        sides = self.pair['media_ids']
        pair_id = 'duo:' + uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(sorted(sides))).hex
        def score(rating):
            return dict(rating=rating, played=8, rd=90, opponents={'x':1,'y':1,'z':1})
        ratings = {sides[0]:score(1730), sides[1]:score(1400)}
        for n in range(5):
            ident = 'peer-' + str(n)
            self.data['media'].append(dict(self.data['media'][0], id=ident, in_all=True))
            ratings[ident] = score(1100 + 60*n)
        battles = self.root / 'battles.json'
        def save_board():
            battles.write_text(json.dumps({'boards':{'a:images':{'ratings':ratings}}}))
            return battles.read_bytes()
        seed_board = save_board()
        initial = self.read()
        self.assertEqual(initial['cards'][self.key]['presentation']['rating'],1730)
        self.assertEqual(battles.read_bytes(),seed_board)
        ratings[pair_id] = score(1300)
        live_board = save_board()
        self.group['after_hours_duo']['media_ids'] = list(reversed(sides))
        live = self.read()
        self.assertEqual(live['cards'][self.key]['presentation']['rating'],1300)
        self.assertEqual(sorted(r['rating'] for r in live['people']['a']['duo_rating_rows']),[1100,1160,1220,1280,1300,1340])
        self.assertEqual(battles.read_bytes(),live_board)
        self.assertNotIn('images',public_catalog(live)['cards'][self.key]['presentation'])
        owned = {self.key:{'duo_side':'front'}}
        self.assertEqual(merge_catalog(initial,live,owned)['cards'][self.key]['presentation']['rating'],1300)
        self.group['after_hours_duo']['media_ids'] = ['a-photo-1','a-photo-2']
        self.assertNotIn('presentation',merge_catalog(live,self.read(),owned)['cards'][self.key])

    def test_eligibility_and_frozen_career_rarity(self):
        prior = self.read()
        prior['cards']['a-photo-0']['rarity'] = 4
        self.group['after_hours_duo'] = self.pair
        fresh = self.read()
        card = fresh['cards'][self.key]
        self.assertEqual([f['media_id'] for f in card['forms']], self.pair['media_ids'])
        self.assertEqual(card['rarity'], 0)
        merged = merge_catalog(prior, fresh, {})
        self.assertEqual(merged['cards'][self.key]['rarity'], 4)
        self.assertIn('evolution:a-set', merged['cards'])
        self.assertNotIn('a-photo-1', merged['cards'])
        self.assertNotIn('forms', public_catalog(merged)['cards'][self.key])

        self.group['after_hours_duo'] = {**self.pair, 'media_ids': ['a-photo-2', 'a-photo-1']}
        set_only = merge_catalog(prior, self.read(), {})
        self.assertEqual(set_only['cards'][self.key]['rarity'], 0)
        for recipe in ({**self.pair, 'version': 2}, {**self.pair, 'version': True},
                       {**self.pair, 'media_ids': ['a-photo-1'] * 2},
                       {**self.pair, 'media_ids': ['a-photo-1', 'b-photo-0']}):
            self.group['after_hours_duo'] = recipe
            self.assertNotIn(self.key, self.read()['cards'])
        self.group['after_hours_duo'] = self.pair
        self.group['media_ids'].remove('a-photo-1')
        withdrawn = self.read()
        self.assertNotIn(self.key, withdrawn['cards'])
        owned = {self.key: {'duo_side': 'back'}}
        held = merge_catalog(merged, withdrawn, owned)['cards'][self.key]
        self.assertFalse(held['available'])
        self.assertTrue(all(set(f) == {'key'} for f in held['forms']))
        self.group['media_ids'].append('a-photo-1')
        self.assertTrue(merge_catalog(merged, self.read(), owned)['cards'][self.key]['available'])
        (self.root / 'a-photo-1.png').unlink()
        self.assertNotIn(self.key, self.read()['cards'])

    def test_duplicate_slots_and_invalid_recovery(self):
        self.group['after_hours_duo'] = self.pair
        cat = self.read()
        state = engine.new_game(cat, ['a', 'b'], pack_seed(cat, cat['cards'][self.key]))
        self.assertNotIn(self.key, state['owned'])
        state = engine.command(state, cat, 'pack', {'pack': 'spotlight', 'target': 'a'})
        slots = [i for i, row in enumerate(state['pending_pack']['results']) if row['id'] == self.key]
        flip = {'card': self.key, 'side': 'back', 'index': slots[0]}
        with self.assertRaises(engine.RuleError):
            engine.command(state, cat, 'duo_side', flip)
        state = engine.command(state, cat, 'reveal', {'all': True})
        before = state['owned'][self.key]
        state = engine.command(state, cat, 'duo_side', flip)
        self.assertEqual(state['owned'][self.key], {**before, 'duo_side': 'back'})
        self.assertEqual(state['pending_pack']['results'][slots[1]].get('duo_side', 'front'), 'front')
        with self.assertRaises(engine.RuleError):
            engine.command(state, cat, 'duo_side', {'card': 'a-photo-0', 'side': 'back'})
        state['owned'][self.key]['duo_side'] = 'bogus'
        with self.assertRaises(engine.RuleError):
            migrations.validate(state, cat)
        exported = copy.deepcopy(cat)
        exported['cards'][self.key]['forms'][0].update(original='untrusted', image='untrusted')
        recovered = merge_catalog(exported, cat, {self.key: {}})
        self.assertEqual(recovered['cards'][self.key]['forms'], cat['cards'][self.key]['forms'])


if __name__ == '__main__':
    unittest.main()
