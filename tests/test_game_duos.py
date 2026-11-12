"""Duo catalog, recovery and duplicate-pull edge cases."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

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
