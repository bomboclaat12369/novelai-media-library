import copy
import tempfile
import unittest
from unittest.mock import patch
from test_organizer import fixture


class MainPlacementTests(unittest.TestCase):
    def test_live_placement_for_saved_inventory_and_refresh_without_rescan(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, bulk, org, ids = fixture(temp)
            bulk.current['config'].update(character_id='patricia', library_instance='library-one')
            before = copy.deepcopy(bulk.current)
            rows = [dict(sha=ids[n], character_id='patricia', in_all=n != 1,
                         in_review=n == 2, in_purgatory=n == 3) for n in range(4)]
            rows.append(dict(sha=ids[4], character_id='other', in_all=True))
            response = dict(stable_library_id='library-one', files=rows)
            with patch.object(engine.library, 'catalog', return_value=response) as catalog:
                org.summary()
                self.assertEqual([org.image(i)['in_main'] for i in ids[:5]], [True, False, False, False, False])
                self.assertTrue(org.image(ids[1])['library_present'])
                self.assertFalse(org.image(ids[4])['library_present'])
                self.assertEqual(catalog.call_count, 1)  # shared across page and suggestions
                page = org.page('post', 'post:1')
                photo = next(i for i in page['images'] if i['id'] == ids[0])
                self.assertTrue(photo['in_main'])
                self.assertTrue(photo['sets'])
                rows[0]['in_all'] = False
                org.summary()
                self.assertFalse(org.image(ids[0])['in_main'])
                rows.clear()
                org.summary()
                self.assertFalse(org.image(ids[0])['library_present'])
            self.assertEqual(bulk.current, before)

    def test_unavailable_or_different_library_is_unknown_and_clears_old_status(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, bulk, org, ids = fixture(temp)
            bulk.current['config'].update(character_id='patricia', library_instance='library-one')
            with patch.object(engine.library, 'catalog', return_value=dict(stable_library_id='library-one', files=[dict(sha=ids[0],in_all=True)])):
                org.summary()
                self.assertTrue(org.image(ids[0])['in_main'])
            with patch.object(engine.library, 'catalog', side_effect=ValueError('Companion unavailable')):
                org.summary()
                self.assertIsNone(org.image(ids[0])['in_main'])
                self.assertIsNone(org.image(ids[0])['library_present'])
            with patch.object(engine.library, 'catalog', return_value=dict(stable_library_id='other',files=[dict(sha=ids[0],in_all=True)])):
                org.summary()
                self.assertIsNone(org.image(ids[0])['in_main'])
