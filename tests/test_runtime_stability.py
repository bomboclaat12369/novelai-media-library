"""Run with python -m unittest discover -s tests -p 'test_runtime_*.py'."""
import io
import json
import runpy
import tempfile
import threading
import unittest
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
        self.assertEqual(self.post(f"/api/media/{video['id']}/review", {'in_review':True})[0], 400)
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


if __name__ == '__main__':
    unittest.main()
