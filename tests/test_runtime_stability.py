"""Run with python -m unittest discover -s tests -p 'test_runtime_*.py'."""
import io
import json
import runpy
import tempfile
import threading
import unittest
from email.message import Message
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = runpy.run_path(str(ROOT / 'runtime-src/companion-runtime.pyw'))


class RuntimeStabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RUNTIME['LibraryStore'](Path(self.temp.name))
        self.character = self.store.add_character('Fixture')
        self.release_worker = threading.Event()

    def tearDown(self):
        self.release_worker.set()
        worker = self.store._thumbnail_worker
        if worker is not None:
            self.store._thumbnail_queue.put(None)
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), 'background worker did not finish')
        self.temp.cleanup()

    def import_image(self, index):
        return self.store.import_bytes(
            f'fixture-{index}'.encode(), f'fixture-{index}.png',
            self.character['id'], [], {'kind':'local'}, 'image/png',
        )[0]

    def test_automatic_video_preview_cannot_overwrite_manual_thumbnail(self):
        item, _ = self.store.import_bytes(
            b'video fixture', 'preview.mp4', self.character['id'], [],
            {'kind': 'local'}, 'video/mp4',
        )
        mid = item['id']
        automatic = self.store.set_video_thumbnail_bytes(mid, b'auto', 'image/jpeg', automatic=True)
        self.assertTrue(automatic['video_thumb_automatic'])
        manual = self.store.set_video_thumbnail_bytes(mid, b'manual', 'image/jpeg', 2.5)
        self.assertFalse(manual['video_thumb_automatic'])
        self.store.set_video_thumbnail_bytes(mid, b'late auto', 'image/jpeg', automatic=True)
        self.assertEqual((self.store.root / manual['thumb_rel']).read_bytes(), b'manual')
        self.assertEqual(manual['video_thumb_seconds'], 2.5)
        legacy = dict(manual)
        legacy.pop('video_thumb_automatic')
        item.pop('video_thumb_automatic')
        self.store.set_video_thumbnail_bytes(mid, b'late auto', 'image/jpeg', automatic=True)
        self.assertEqual((self.store.root / legacy['thumb_rel']).read_bytes(), b'manual')

    def post(self, path, body):
        handler = object.__new__(RUNTIME['MediaHandler'])
        handler.server = SimpleNamespace(store=self.store)
        handler.path = path
        payload = json.dumps(body).encode()
        handler.headers = {'Content-Length':str(len(payload)), 'Origin':'https://novelai.net'}
        handler.rfile = io.BytesIO(payload)
        responses = []
        handler._send_json = lambda status, value: responses.append((status, value))
        handler.do_POST()
        self.assertEqual(len(responses), 1)
        return responses[0]

    def post_multipart(self, path, filename, payload, content_type='image/png'):
        handler = object.__new__(RUNTIME['MediaHandler'])
        handler.server = SimpleNamespace(store=self.store)
        handler.path = path
        handler.headers = {'Origin':'https://novelai.net'}
        handler._read_multipart = lambda: {
            'file': [(filename, payload, content_type)],
        }
        responses = []
        handler._send_json = lambda status, value: responses.append((status, value))
        handler.do_POST()
        self.assertEqual(len(responses), 1)
        return responses[0]

    def test_empty_sets_create_update_reload_and_retain_empty_membership(self):
        status, empty = self.post('/api/sets', {'character_id': self.character['id'], 'name': 'Empty', 'media_ids': []})
        self.assertEqual(status, 200)
        self.assertEqual(empty['media_ids'], [])
        self.assertIsNone(empty['cover_media_id'])
        restored = RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(restored.set_item(empty['id'])['media_ids'], [])
        image = self.import_image(1)
        updated = self.store.update_set(empty['id'], media_ids=[image['id']])
        self.assertEqual(updated['cover_media_id'], image['id'])
        other = self.store.create_set(self.character['id'], 'Other', [image['id']])
        self.assertEqual(self.store.set_item(empty['id'])['media_ids'], [])
        self.assertIsNone(self.store.set_item(empty['id'])['cover_media_id'])
        self.store.delete_media(image['id'])
        self.assertEqual(self.store.set_item(other['id'])['media_ids'], [])
        self.assertIsNone(self.store.set_item(other['id'])['cover_media_id'])
        self.assertEqual(self.store.update_set(empty['id'], name='Renamed')['name'], 'Renamed')
        with self.assertRaises(ValueError):
            self.store.create_set(self.character['id'], 'renamed', [])
        with self.assertRaises((KeyError, ValueError)):
            self.store.update_set(empty['id'], media_ids=['missing'])

    def test_delete_empty_character_route_and_preserve_other_characters(self):
        self.store.create_set(self.character['id'], 'Empty', [])
        other = self.store.add_character('Keep')
        handler = object.__new__(RUNTIME['MediaHandler'])
        handler.server = SimpleNamespace(store=self.store)
        handler.path = '/api/characters/' + self.character['id']
        handler.headers = {'Origin': 'https://novelai.net'}
        responses = []
        handler._send_json = lambda status, value: responses.append((status, value))
        handler.do_DELETE()
        self.assertEqual(responses[0][0], 200)
        self.assertEqual(self.store.data['characters'], [other])
        self.assertEqual(self.store.data['sets'], [])
        self.assertEqual(RUNTIME['LibraryStore'](self.store.root).data['characters'], [other])

    def test_delete_character_refuses_review_images_and_videos(self):
        image = self.import_image(1)
        image['in_review'] = True
        for media_type in ('image', 'video'):
            image['media_type'] = media_type
            with self.assertRaises(ValueError):
                self.store.delete_character(self.character['id'])
            self.assertIsNotNone(self.store.character(self.character['id']))
            self.assertTrue((self.store.root / image['stored_rel']).exists())

    def test_batch_import_and_review_do_not_wait_for_thumbnail_decoder(self):
        entered = threading.Event()
        decoded = []
        def slow_thumbnail(original, media_id, character_name):
            decoded.append(media_id)
            entered.set()
            self.release_worker.wait(timeout=4)
            return None
        with patch.object(self.store, '_make_thumbnail', side_effect=slow_thumbnail):
            first = self.import_image(0)
            self.assertTrue(entered.wait(timeout=1))
            worker = self.store._thumbnail_worker
            with ThreadPoolExecutor(max_workers=1) as executor:
                batch = executor.submit(lambda: [self.import_image(i) for i in range(1, 13)]).result(timeout=1.5)
                result = executor.submit(self.post, f"/api/media/{first['id']}/review", {'in_review':True}).result(timeout=1)
            self.assertEqual(result[0], 200)
            self.assertTrue(result[1]['in_review'])
            self.assertIs(self.store._thumbnail_worker, worker)
            self.assertTrue(worker.daemon)
            self.assertEqual(len(decoded), 1, 'a batch must not spawn parallel decoders')
            saved = json.loads(self.store.db_path.read_text())
            self.assertEqual(len(saved['media']), 13)
            for item in [first, *batch]:
                self.assertTrue((self.store.root / item['stored_rel']).exists())
                self.assertIsNone(item['thumb_rel'])
            # Until ready, the thumbnail endpoint can serve the original.
            self.assertEqual(self.store.media_path(first['id'], thumb=True)[0], self.store.root / first['stored_rel'])
            self.release_worker.set()
            self.store._thumbnail_queue.join()
            self.assertEqual(len(decoded), 13)

    def test_large_duplicate_hash_does_not_hold_library_lock(self):
        source = self.store.root / 'duplicate-video.mp4'
        source.write_bytes(b'video-bytes')
        entered = threading.Event()
        release = threading.Event()
        original_hash = self.store._hash_file

        def blocked_hash(path):
            entered.set()
            self.assertTrue(release.wait(timeout=3))
            return original_hash(path)

        with patch.object(self.store, '_hash_file', side_effect=blocked_hash):
            worker = threading.Thread(target=lambda: self.store.import_bytes(
                source.read_bytes(), source.name, self.character['id'], [],
                {'kind':'local'}, 'video/mp4'))
            worker.start()
            self.assertTrue(entered.wait(timeout=1))
            # Metadata reads must remain responsive while the upload is hashed.
            snapshot = self.store.public_library()
            self.assertEqual(snapshot['characters'][0]['id'], self.character['id'])
            release.set()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())

    def test_replace_source_preserves_relationships_and_position(self):
        category = self.store.add_category(self.character['id'], 'Dress')
        with patch.object(self.store, '_queue_image_thumbnail'):
            first = self.import_image(1)
            second = self.import_image(2)
        first['categories'] = [category['id']]
        first['favorite'] = True
        first['in_review'] = True
        first['crop_top'] = 0.12
        first['crop_bottom'] = 0.07
        set_item = self.store.create_set(self.character['id'], 'Keep me', [first['id']], first['id'])
        self.store.save()
        old_path = self.store.root / first['stored_rel']
        old_path.write_bytes(b'old-source')
        with patch.object(self.store, '_queue_image_thumbnail') as queue:
            status, replaced = self.post_multipart(
                f"/api/media/{first['id']}/replace", 'higher-quality.png', b'new-source'
            )
        self.assertEqual(status, 200)
        self.assertEqual(replaced['id'], first['id'])
        self.assertEqual(self.store.data['media'][0]['id'], first['id'])
        self.assertEqual(self.store.data['media'][1]['id'], second['id'])
        self.assertEqual(replaced['categories'], [category['id']])
        self.assertTrue(replaced['favorite'])
        self.assertTrue(replaced['in_review'])
        self.assertEqual(replaced['crop_top'], 0.12)
        self.assertEqual(replaced['crop_bottom'], 0.07)
        self.assertEqual(self.store.set_item(set_item['id'])['media_ids'], [first['id']])
        self.assertEqual(self.store.set_item(set_item['id'])['cover_media_id'], first['id'])
        self.assertEqual(replaced['original_name'], 'higher-quality.png')
        self.assertEqual((self.store.root / replaced['stored_rel']).read_bytes(), b'new-source')
        self.assertFalse(old_path.exists())
        self.assertIsNone(replaced['thumb_rel'])
        queue.assert_called_once()

    def test_replace_source_rejects_duplicate_image_without_changing_original(self):
        with patch.object(self.store, '_queue_image_thumbnail'):
            first = self.import_image(1)
            second = self.import_image(2)
        original_path = self.store.root / first['stored_rel']
        original_bytes = original_path.read_bytes()
        second_bytes = (self.store.root / second['stored_rel']).read_bytes()
        status, body = self.post_multipart(f"/api/media/{first['id']}/replace", 'duplicate.png', second_bytes)
        self.assertEqual(status, 400)
        self.assertIn('already in this character', body['error'])
        self.assertEqual(original_path.read_bytes(), original_bytes)

    def test_all_membership_is_per_image_and_quality_endpoint_reports_source_size(self):
        category = self.store.add_category(self.character['id'], 'Dress')
        with patch.object(self.store, '_queue_image_thumbnail'):
            first = self.import_image(1)
            second = self.import_image(2)
        self.assertTrue(first['in_all'])
        self.assertTrue(second['in_all'])
        updated = self.store.set_categories(first['id'], [category['id']], in_all=False)
        self.assertEqual(updated['categories'], [category['id']])
        self.assertFalse(updated['in_all'])
        # Explicitly assigning a category must not implicitly re-add an image to All.
        self.assertFalse(self.store.set_categories(first['id'], [category['id']], in_all=False)['in_all'])
        set_item = self.store.create_set(self.character['id'], 'Set only', [first['id'], second['id']])
        self.assertEqual(set_item['media_ids'], [first['id'], second['id']])
        self.assertFalse(self.store.data['media'][0]['in_all'])
        self.assertFalse(self.store.data['media'][1]['in_all'])
        quality = self.store.media_quality(second['id'])
        self.assertEqual(quality['media_id'], second['id'])
        self.assertEqual(quality['media_type'], 'image')
        self.assertEqual(quality['file_bytes'], len(b'fixture-2'))

    def test_rename_category_preserves_id_assignments_and_media_type(self):
        image_category = self.store.add_category(self.character['id'], 'Dres')
        video_category = self.store.add_category(self.character['id'], 'Dres', 'video')
        other_image_category = self.store.add_category(self.character['id'], 'Other')
        with patch.object(self.store, '_queue_image_thumbnail'):
            image = self.import_image(1)
        image['categories'] = [image_category['id']]
        renamed = self.store.rename_category(image_category['id'], 'Dress')
        self.assertEqual(renamed['id'], image_category['id'])
        self.assertEqual(renamed['name'], 'Dress')
        self.assertEqual(renamed['media_type'], 'image')
        self.assertEqual(image['categories'], [image_category['id']])
        self.assertEqual(video_category['name'], 'Dres')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.store.rename_category(image_category['id'], other_image_category['name'])
        with self.assertRaisesRegex(ValueError, 'automatic'):
            self.store.rename_category(image_category['id'], 'All')

    def test_deleted_queued_media_is_not_decoded_or_resurrected(self):
        entered = threading.Event()
        decoded = []
        def thumbnail(original, media_id, character_name):
            decoded.append(media_id)
            entered.set()
            self.release_worker.wait(timeout=3)
            target = self.store.thumb_dir / (media_id + '.webp')
            target.write_bytes(b'fixture thumbnail')
            return target.relative_to(self.store.root).as_posix()
        with patch.object(self.store, '_make_thumbnail', side_effect=thumbnail):
            active = self.import_image(0)
            self.assertTrue(entered.wait(timeout=1))
            queued = self.import_image(1)
            self.store.delete_media(active['id'])
            self.store.delete_media(queued['id'])
            self.release_worker.set()
            self.store._thumbnail_queue.join()
        self.assertEqual(decoded, [active['id']])
        self.assertEqual(self.store.public_library()['media'], [])
        self.assertEqual(list(self.store.thumb_dir.glob('*.webp')), [])

    def test_thumbnail_error_does_not_stop_queue(self):
        with patch.object(self.store, '_make_thumbnail', side_effect=[ValueError('bad image'), None]) as generate:
            with patch('traceback.print_exc'):
                self.import_image(0)
                self.import_image(1)
                self.store._thumbnail_queue.join()
        self.assertEqual(generate.call_count, 2)

    def test_unchanged_review_category_and_favorite_saves_do_not_rewrite_database(self):
        with patch.object(self.store, '_queue_image_thumbnail'):
            item = self.import_image(0)
        with patch.object(self.store, '_write_atomic', wraps=self.store._write_atomic) as write:
            self.assertEqual(self.post(f"/api/media/{item['id']}/categories", {'categories':[]})[0], 200)
            self.assertEqual(self.post(f"/api/media/{item['id']}/review", {'in_review':False})[0], 200)
            self.assertEqual(self.post(f"/api/media/{item['id']}/favorite", {'favorite':False})[0], 200)
            self.assertEqual(write.call_count, 0)
            self.post(f"/api/media/{item['id']}/review", {'in_review':True})
            self.post(f"/api/media/{item['id']}/favorite", {'favorite':True})
            self.assertEqual(write.call_count, 2)
        saved = json.loads(self.store.db_path.read_text())['media'][0]
        self.assertTrue(saved['in_review'])
        self.assertTrue(saved['favorite'])

    def test_review_video_favorites_sets_and_metadata_crop_remain_supported(self):
        with patch.object(self.store, '_queue_image_thumbnail'):
            image = self.import_image(0)
        video = self.store.import_bytes(b'video fixture', 'fixture.mp4', self.character['id'], [], {'kind':'local'}, 'video/mp4')[0]
        self.assertEqual(self.post(f"/api/media/{video['id']}/favorite", {'favorite':True})[0], 200)
        self.assertEqual(self.post(f"/api/media/{video['id']}/review", {'in_review':True})[0], 200)
        self.assertTrue(video['in_review'])
        original = (self.store.root / image['stored_rel']).read_bytes()
        self.assertEqual(self.post(f"/api/media/{image['id']}/crop", {'top':0.1, 'bottom':0.2})[0], 200)
        self.assertEqual((self.store.root / image['stored_rel']).read_bytes(), original)
        self.assertEqual(image['crop_top'], 0.1)
        status, image_set = self.post('/api/sets', {'character_id':self.character['id'], 'name':'Fixture Set', 'media_ids':[image['id']], 'cover_media_id':image['id']})
        self.assertEqual(status, 200)
        self.assertEqual(image_set['media_ids'], [image['id']])
        self.assertEqual(len(list(self.store.media_dir.rglob('*.*'))), 2)

    def test_server_accepts_bursts_without_legacy_five_connection_backlog(self):
        self.assertGreaterEqual(RUNTIME['MediaHTTPServer'].request_queue_size, 64)

    def preview_response(self, content_type='image/png'):
        response = io.BytesIO(b'preview-original-bytes')
        response.headers = Message()
        response.headers['Content-Type'] = content_type
        response.headers['Content-Disposition'] = 'inline; filename="image 1.png"'
        return response

    def test_url_preview_does_not_register_media_and_always_removes_temporary_file(self):
        before = self.store.db_path.read_bytes()
        for fail_send in (False, True):
            handler = object.__new__(RUNTIME['MediaHandler'])
            handler.server = SimpleNamespace(store=self.store)
            handler.path = '/api/preview/url'
            handler.headers = {'Origin':'https://novelai.net'}
            handler._read_json = lambda: {'url':'https://example.test/image.png'}
            sent, errors = [], []
            def send_file(path, content_type, preview_name=None):
                sent.append((path.read_bytes(), content_type, preview_name))
                if fail_send:
                    raise ConnectionResetError('fixture disconnected')
            handler._send_file_with_range = send_file
            handler._send_json = lambda status, body: errors.append(status)
            with patch('urllib.request.urlopen', return_value=self.preview_response()):
                handler.do_POST()
            self.assertEqual(sent, [(b'preview-original-bytes', 'image/png', 'image 1.png')])
            self.assertEqual(errors, [500] if fail_send else [])
            self.assertEqual(self.store.db_path.read_bytes(), before)
            self.assertEqual(self.store.data['media'], [])
            self.assertEqual(list((self.store.root / '.incoming').iterdir()), [])
            self.assertIsNone(self.store._thumbnail_worker)

    def test_url_preview_rejects_non_media_and_cleans_up(self):
        with patch('urllib.request.urlopen', return_value=self.preview_response('text/html')):
            with self.assertRaises(ValueError):
                self.store.download_url_preview('https://example.test/page')
        self.assertEqual(self.store.data['media'], [])
        self.assertEqual(list((self.store.root / '.incoming').iterdir()), [])

    def test_direct_url_import_still_registers_original_and_source(self):
        with patch('urllib.request.urlopen', return_value=self.preview_response()), patch.object(self.store, '_queue_image_thumbnail') as queue:
            item, duplicate = self.store.import_url('https://example.test/image.png', self.character['id'], [])
        self.assertFalse(duplicate)
        self.assertEqual(item['source'], {'kind':'url', 'url':'https://example.test/image.png'})
        self.assertEqual((self.store.root / item['stored_rel']).read_bytes(), b'preview-original-bytes')
        queue.assert_called_once()

    def test_saving_downloaded_preview_retains_its_source_url(self):
        handler = object.__new__(RUNTIME['MediaHandler'])
        handler.server = SimpleNamespace(store=self.store)
        handler.path = '/api/import/file'
        handler.headers = {'Origin':'https://novelai.net'}
        handler._read_multipart = lambda: {
            'character_id':[(None, self.character['id'].encode(), None)],
            'categories':[(None, b'[]', None)],
            'source_url':[(None, b'https://example.test/original.png', None)],
            'file':[('original.png', b'original-image-data', 'image/png')],
        }
        sent = []
        handler._send_json = lambda status, data: sent.append((status, data))
        with patch.object(self.store, '_queue_image_thumbnail'):
            handler.do_POST()
        self.assertEqual(sent[0][0], 200)
        self.assertEqual(sent[0][1]['item']['source'], {'kind':'url', 'url':'https://example.test/original.png'})


if __name__ == '__main__':
    unittest.main()
