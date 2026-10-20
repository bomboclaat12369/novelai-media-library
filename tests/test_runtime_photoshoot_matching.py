"""Mode, retrieval, coverage and cache regressions without downloading models."""
import base64
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
import test_runtime_outfit_matching as outfit


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Optional matching dependencies required')
class PhotoshootTests(unittest.TestCase):
    prepare = outfit.OutfitTests.prepare
    encode = outfit.OutfitTests.encode
    tearDown = outfit.OutfitTests.tearDown
    run_search = outfit.OutfitTests.run_search
    add_ungrouped = outfit.OutfitTests.add_ungrouped

    def setUp(self):
        outfit.OutfitTests.setUp(self)
        self.scene_calls = 0
        self.m._prepare_scene = lambda ident: None
        self.m._encode_scene = self.scene_encode

    def scene_encode(self, source, angle=0):
        self.scene_calls += 1
        data = source.read() if hasattr(source, 'read') else Path(source).read_bytes()
        value = self.np.zeros((2, 768), dtype=self.np.float32)
        value[:, 1 if data == b'second' else 0] = 1
        return value

    def test_same_scene_with_changed_outfit_and_separate_persistent_caches(self):
        before = self.store.db_path.read_bytes()
        query = {'image_base64': base64.b64encode(b'changed outfit in first scene').decode()}
        self.assertEqual(self.run_search(**query)['results'][0]['set_id'], self.second['id'])
        photo = self.run_search(**query, matching_mode='photoshoot')
        self.assertEqual(photo['matching_mode'], 'photoshoot')
        self.assertEqual(photo['results'][0]['set_id'], self.group['id'])
        self.assertAlmostEqual(photo['results'][0]['score'], .9, places=5)
        self.assertEqual((photo['new_images'], photo['cached_images']), (2, 0))
        calls = (self.calls, self.scene_calls)
        self.m.vector_cache.clear(); self.m.scene_vector_cache.clear()
        warm = self.run_search(**query, matching_mode='photoshoot')
        self.assertEqual((self.calls, self.scene_calls), calls)
        self.assertEqual((warm['new_images'], warm['cached_images']), (0, 2))
        self.assertEqual(self.run_search(**query)['results'][0]['set_id'], self.second['id'])
        self.assertEqual(before, self.store.db_path.read_bytes())
        (self.store.root / self.a['stored_rel']).write_bytes(b'updated scene')
        changed = self.run_search(**query, matching_mode='photoshoot')
        self.assertEqual(changed['new_images'], 1)
        self.assertEqual(self.scene_calls, calls[1] + 1)
        self.m.SCENE_RECIPE += ':changed-recipe'
        self.assertEqual(self.run_search(**query, matching_mode='photoshoot')['new_images'], 2)

    def test_person_defaults_saved_preference_and_invalid_modes(self):
        mikayla = self.store.add_character('Mikayla')
        before = self.store.db_path.read_bytes()
        self.assertEqual(self.store.matching_preferences(mikayla['id'])['mode'], 'photoshoot')
        self.assertEqual(self.store.matching_preferences(self.owner['id'])['mode'], 'outfit')
        self.assertEqual(before, self.store.db_path.read_bytes())
        self.store.matching_preferences(self.owner['id'], 'photoshoot')
        self.assertEqual(self.run_search(media_id=self.a['id'])['matching_mode'], 'photoshoot')
        reopened = type(self.store)(self.store.root)
        self.assertEqual(reopened.matching_preferences(self.owner['id'])['mode'], 'photoshoot')
        self.assertEqual(self.store.matching_preferences(self.other['id'])['mode'], 'outfit')
        with self.assertRaises(ValueError):
            self.m.start({'character_id': self.owner['id'], 'media_id': self.a['id'], 'matching_mode': 'invalid'})
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.matching_preferences(self.owner['id'], 'outfit')
        self.assertEqual(self.store.matching_preferences(self.owner['id'])['mode'], 'photoshoot')

    def test_all_members_individuals_scan_and_reverse_scan_remain_manual(self):
        self.add_ungrouped()
        # The best matching member is not the cover/first member.
        self.store.update_set(self.second['id'], add_media_ids=[self.a['id']])
        before = self.store.db_path.read_bytes()
        body = {'matching_mode': 'photoshoot', 'media_id': self.main['id']}
        result = self.run_search(**body, example_media_ids=[self.review['id']])
        self.assertIn(self.a['id'], next(r for r in result['results'] if r['set_id'] == self.second['id'])['matches'])
        self.assertEqual({r['media_id'] for r in result['individual_results']}, {self.purgatory['id']})
        for target in (None, self.second['id']):
            job = self.m.start({'character_id': self.owner['id'], 'matching_mode': 'photoshoot', **({'target_set_id': target} if target else {})}, scan=True)
            self.m.thread.join(10); result = self.m.status(job['id'])
            self.assertNotIn('error', result)
            self.assertEqual({r['media_id'] for r in result['scan_results']}, {self.main['id'], self.review['id'], self.purgatory['id']})
            if target:
                self.assertTrue(all([s['set_id'] for s in r['results']] == [target] for r in result['scan_results']))
        self.assertEqual(before, self.store.db_path.read_bytes())
        self.m.assign_scan({'job_id': result['id'], 'media_id': self.purgatory['id'], 'set_id': self.second['id']})
        self.assertFalse(self.purgatory['in_purgatory'])
        self.assertIn(self.purgatory['id'], self.second['media_ids'])

    def test_scene_failures_are_visible_not_silent_outfit_fallback(self):
        with patch.object(self.m, '_prepare_scene', side_effect=ValueError('Scene model unavailable')):
            job = self.m.start({'character_id': self.owner['id'], 'media_id': self.a['id'], 'matching_mode': 'photoshoot'})
            self.m.thread.join(10); result = self.m.status(job['id'])
            self.assertIn('Scene model unavailable', result['error'])
            self.assertEqual(result['results'], [])
        original = self.m._encode_scene
        def broken(source, angle=0):
            if not hasattr(source, 'read') and Path(source).read_bytes() == b'second':
                raise ValueError('Unreadable scene')
            return original(source, angle)
        self.m._encode_scene = broken
        result = self.run_search(media_id=self.a['id'], matching_mode='photoshoot')
        self.assertEqual(result['unsearchable_sets'], 1)
        self.assertEqual(result['issues'][0]['media_id'], self.b['id'])
        self.assertEqual(result['indexed_images'], 1)

    def test_sideways_scene_uses_coherent_cached_views(self):
        def sideways(source, angle=0):
            data = source.read() if hasattr(source, 'read') else Path(source).read_bytes()
            if data == b'sideways':
                self.scene_calls += 1
                vector = self.np.zeros((2, 768), dtype=self.np.float32)
                vector[:, 0 if angle == 90 else 2] = 1
                return vector
            return self.scene_encode(source, angle)
        self.m._encode_scene = sideways
        query = {'image_base64': base64.b64encode(b'sideways').decode(), 'matching_mode': 'photoshoot'}
        result = self.run_search(**query)
        self.assertEqual(result['results'][0]['set_id'], self.group['id'])
        calls = self.scene_calls
        self.run_search(**query)
        self.assertEqual(self.scene_calls, calls)


if __name__ == '__main__':
    unittest.main()
