import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from test_organizer import fixture
from library_bridge import LibraryClient
from organizer import runtime_helpers


class MainPlacementTests(unittest.TestCase):
    def test_real_companion_identity_and_saved_character_section(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, bulk, org, ids = fixture(temp)
            runtime = runtime_helpers()
            store = runtime['LibraryStore'](Path(temp) / 'library')
            store._queue_image_thumbnail = lambda *args: None
            owner = store.add_character('Patricia')['id']
            items = []
            for ident in ids[:4]:
                path = Path(org.catalog[ident]['path'])
                items.append(store.import_bytes(path.read_bytes(), path.name, owner, [], {}, 'image/jpeg')[0])
            items[1]['in_all'] = False
            group = store.create_set(owner, 'Existing shoot', [item['id'] for item in items], preserve_placement=True)
            store.set_review(items[2]['id'], True)
            store.set_purgatory(items[3]['id'], True)
            store.save()
            for ident in ids[:4]:
                bulk.current['source_catalog'][ident]['existing_sets'] = [group['id']]
            bulk.current['library_sets'] = {group['id']: group}
            bulk.current['config']['character_id'] = owner
            bulk.persist()
            with runtime['MediaHTTPServer'](('127.0.0.1', 0), store) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    # Exercise the real HTTP routes, catalog serializer and section ID binding.
                    engine.library = LibraryClient(server.server_address[1])
                    bulk.sections.sync()
                    section = next(row for row in bulk.sections.rows() if row['character_id'] == owner)
                    bulk.sections.activate(section['id'])
                    org.bind()
                    self.assertEqual(bulk.current['config']['library_instance'], store.tracking.diagnostics()['instance'])
                    self.assertNotEqual(section['library_instance'], store.duplicate_catalog(owner)['stable_library_id'])
                    before_inventory = copy.deepcopy(bulk.current)
                    before_library = store.db_path.read_bytes()
                    org.summary()
                    self.assertEqual([org.image(ident)['in_main'] for ident in ids[:5]], [True, False, False, False, False])
                    self.assertEqual([org.image(ident)['in_review'] for ident in ids[:5]], [False, False, True, False, False])
                    self.assertEqual([org.image(ident)['in_purgatory'] for ident in ids[:5]], [False, False, False, True, False])
                    page = org.page('post', 'post:1')
                    photo = next(image for image in page['images'] if image['id'] == ids[0])
                    self.assertTrue(photo['in_main'])
                    self.assertTrue(photo['sets'])
                    for ident, flag in ((ids[2], 'in_review'), (ids[3], 'in_purgatory')):
                        photo = next(image for image in page['images'] if image['id'] == ident)
                        self.assertTrue(photo[flag])
                        self.assertTrue(photo['sets'])
                    self.assertEqual(bulk.current, before_inventory)
                    self.assertEqual(store.db_path.read_bytes(), before_library)
                finally:
                    server.shutdown()
                    worker.join(timeout=5)
                    self.assertFalse(worker.is_alive())

    def test_live_placement_for_saved_inventory_and_refresh_without_rescan(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, bulk, org, ids = fixture(temp)
            bulk.current['config'].update(character_id='patricia', library_instance='library-one')
            before = copy.deepcopy(bulk.current)
            rows = [dict(sha=ids[n], character_id='patricia', in_all=n != 1,
                         in_review=n == 2, in_purgatory=n == 3) for n in range(4)]
            rows.append(dict(sha=ids[4], character_id='other', in_all=True))
            response = dict(stable_library_id='store-one', files=rows)
            with patch.object(engine.library, 'catalog', return_value=response) as catalog, \
                    patch.object(engine.library, 'request', return_value={'instance': 'library-one'}) as request:
                org.summary()
                self.assertEqual([org.image(i)['in_main'] for i in ids[:5]], [True, False, False, False, False])
                self.assertEqual([org.image(i)['in_review'] for i in ids[:5]], [False, False, True, False, False])
                self.assertEqual([org.image(i)['in_purgatory'] for i in ids[:5]], [False, False, False, True, False])
                self.assertTrue(org.image(ids[1])['library_present'])
                self.assertFalse(org.image(ids[4])['library_present'])
                self.assertEqual(catalog.call_count, 1)  # shared across page and suggestions
                request.assert_called_once_with('/api/tracking/status')
                page = org.page('post', 'post:1')
                photo = next(i for i in page['images'] if i['id'] == ids[0])
                self.assertTrue(photo['in_main'])
                self.assertTrue(photo['sets'])
                rows[0]['in_all'] = False
                rows[0]['in_review'] = True
                rows[0]['in_purgatory'] = True
                org.summary()
                self.assertFalse(org.image(ids[0])['in_main'])
                self.assertTrue(org.image(ids[0])['in_review'])
                self.assertTrue(org.image(ids[0])['in_purgatory'])
                rows.clear()
                org.summary()
                self.assertFalse(org.image(ids[0])['library_present'])
                self.assertFalse(org.image(ids[0])['in_review'])
                self.assertFalse(org.image(ids[0])['in_purgatory'])
            self.assertEqual(bulk.current, before)

    def test_unavailable_or_different_library_is_unknown_and_clears_old_status(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, bulk, org, ids = fixture(temp)
            bulk.current['config'].update(character_id='patricia', library_instance='library-one')
            response = dict(stable_library_id='store-one', files=[dict(sha=ids[0], in_all=True), dict(sha=ids[1], in_review=True, in_purgatory=True)])
            with patch.object(engine.library, 'catalog', return_value=response), \
                    patch.object(engine.library, 'request', return_value={'instance': 'library-one'}):
                org.summary()
                self.assertTrue(org.image(ids[0])['in_main'])
                self.assertTrue(org.image(ids[1])['in_review'])
                self.assertTrue(org.image(ids[1])['in_purgatory'])
            with patch.object(engine.library, 'catalog', side_effect=ValueError('Companion unavailable')):
                org.summary()
                self.assertIsNone(org.image(ids[0])['in_main'])
                self.assertIsNone(org.image(ids[0])['library_present'])
                self.assertIsNone(org.image(ids[1])['in_review'])
                self.assertIsNone(org.image(ids[1])['in_purgatory'])
            for status in ({'instance': 'other'}, {}):
                with self.subTest(status=status), patch.object(engine.library, 'catalog', return_value=response), \
                        patch.object(engine.library, 'request', return_value=status):
                    org.summary()
                    self.assertIsNone(org.image(ids[0])['in_main'])
                    self.assertIsNone(org.image(ids[0])['library_present'])
                    self.assertIsNone(org.image(ids[1])['in_review'])
                    self.assertIsNone(org.image(ids[1])['in_purgatory'])
            with patch.object(engine.library, 'catalog', return_value=response), \
                    patch.object(engine.library, 'request', side_effect=ValueError('Companion unavailable')):
                org.summary()
                self.assertIsNone(org.image(ids[0])['in_main'])

    def test_catalog_without_store_id_uses_tracking_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, bulk, org, ids = fixture(temp)
            bulk.current['config'].update(character_id='patricia', library_instance='library-one')
            with patch.object(engine.library, 'catalog', return_value=dict(files=[dict(sha=ids[0], in_all=True)])), \
                    patch.object(engine.library, 'request', return_value={'instance': 'library-one'}):
                org.summary()
                self.assertTrue(org.image(ids[0])['in_main'])
