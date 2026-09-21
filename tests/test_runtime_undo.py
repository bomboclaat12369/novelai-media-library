"""Focused persistence and failure tests for replacement flags and recent-action undo."""
import copy
import io
import json
import os
from types import SimpleNamespace
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RUNTIME = runpy.run_path(str(Path(os.environ.get('NAI_RUNTIME_SOURCE', Path(__file__).resolve().parents[1] / 'runtime-src/companion-runtime.pyw'))))


class UndoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RUNTIME['LibraryStore'](Path(self.temp.name))
        self.store._queue_image_thumbnail = lambda *args: None
        self.owner = self.store.add_character('Fixture')

    def tearDown(self):
        self.temp.cleanup()

    def image(self, name='one'):
        return self.store.import_bytes(name.encode(), name+'.png', self.owner['id'], [], {'kind':'local'}, 'image/png')[0]

    def undo(self):
        return self.store.undo_last(self.store.undo_history()['entries'][0]['id'])

    def test_flags_and_category_undo_persist_and_leave_original_untouched(self):
        image = self.image()
        cat = self.store.add_category(self.owner['id'], 'Dress')
        self.store.set_needs_replacement(image['id'], True)
        self.store.set_categories(image['id'], [cat['id']], in_all=False)
        self.assertNotIn('undo_history', self.store.public_library())
        self.store = RUNTIME['LibraryStore'](self.store.root)
        self.store._queue_image_thumbnail = lambda *args: None
        self.assertTrue(self.store.media_item(image['id'])['needs_replacement'])
        self.undo()
        restored = self.store.media_item(image['id'])
        self.assertEqual(restored['categories'], [])
        self.assertTrue(restored['in_all'])
        self.undo()
        self.assertFalse(restored.get('needs_replacement', False))
        self.assertEqual((self.store.root / restored['stored_rel']).read_bytes(), b'one')

    def test_featured_is_image_only_and_undoable(self):
        image = self.image('featured')
        self.store.set_featured(image['id'], True)
        self.assertTrue(self.store.media_item(image['id'])['featured'])
        self.undo()
        self.assertFalse(self.store.media_item(image['id'])['featured'])
        video = self.store.import_bytes(b'clip', 'clip.mp4', self.owner['id'], [], {}, 'video/mp4')[0]
        with self.assertRaises(ValueError):
            self.store.set_featured(video['id'], True)

    def test_delete_undo_restores_order_set_membership_cover_and_file_bytes(self):
        images = [self.image(str(i)) for i in range(3)]
        ids = [m['id'] for m in images]
        group = self.store.create_set(self.owner['id'], 'Set', ids, ids[1])
        cat = self.store.add_category(self.owner['id'], 'Dress')
        self.store.set_categories(ids[1], [cat['id']])
        original = copy.deepcopy(images[1])
        self.store.delete_media(ids[1])
        self.assertIsNone(self.store.media_item(ids[1]))
        self.assertTrue((self.store.root / original['stored_rel']).is_file())
        self.assertNotIn(ids[1], self.store.set_item(group['id'])['media_ids'])
        self.store = RUNTIME['LibraryStore'](self.store.root)
        self.store._queue_image_thumbnail = lambda *args: None
        self.undo()
        self.assertEqual([m['id'] for m in self.store.data['media']], ids)
        self.assertEqual(self.store.media_item(ids[1]), original)
        self.assertEqual(self.store.set_item(group['id'])['media_ids'], ids)
        self.assertEqual(self.store.set_item(group['id'])['cover_media_id'], ids[1])
        self.assertEqual((self.store.root / original['stored_rel']).read_bytes(), b'1')

    def test_undo_video_deletion_retains_manual_thumbnail(self):
        video = self.store.import_bytes(b'video', 'clip.mp4', self.owner['id'], [], {}, 'video/mp4')[0]
        self.store.set_video_thumbnail_bytes(video['id'], b'manual cover', 'image/jpeg', 3.5)
        before = copy.deepcopy(video)
        self.store.delete_media(video['id']); self.undo()
        self.assertEqual(self.store.media_item(video['id']), before)
        self.assertEqual((self.store.root / before['thumb_rel']).read_bytes(), b'manual cover')

    def test_history_is_bounded_and_only_expired_deleted_files_are_removed(self):
        deleted, active = self.image('deleted'), self.image('active')
        path = self.store.root / deleted['stored_rel']
        self.store.delete_media(deleted['id'])
        for i in range(20):
            self.store.set_needs_replacement(active['id'], i % 2 == 0)
        self.assertEqual(len(self.store.undo_history()['entries']), 20)
        self.assertFalse(path.exists())
        self.assertTrue((self.store.root / active['stored_rel']).is_file())

    def test_failed_delete_or_undo_save_rolls_back_metadata_and_keeps_files(self):
        image = self.image()
        before = copy.deepcopy(self.store.public_library())
        with patch.object(self.store, '_write_atomic', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.store.delete_media(image['id'])
        self.assertEqual(self.store.public_library()['media'], before['media'])
        self.assertFalse(self.store.undo_history()['entries'])
        self.store.delete_media(image['id'])
        history = copy.deepcopy(self.store.undo_history())
        with patch.object(self.store, '_write_atomic', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.undo()
        self.assertIsNone(self.store.media_item(image['id']))
        self.assertEqual(self.store.undo_history(), history)
        self.assertTrue((self.store.root / image['stored_rel']).is_file())

    def test_stale_id_and_changed_set_cannot_undo_over_newer_work(self):
        image = self.image()
        group = self.store.create_set(self.owner['id'], 'Original', [image['id']])
        self.store.delete_media(image['id'])
        with self.assertRaises(ValueError): self.store.undo_last('stale')
        self.store.update_set(group['id'], name='Renamed')
        with self.assertRaises(ValueError): self.undo()
        self.assertEqual(self.store.set_item(group['id'])['name'], 'Renamed')
        self.assertIsNone(self.store.media_item(image['id']))

    def test_source_replacement_clears_flag_and_its_old_history(self):
        image = self.image()
        self.store.set_needs_replacement(image['id'], True)
        self.store.replace_media_bytes(b'better', 'better.png', image['id'], 'image/png')
        self.assertFalse(image['needs_replacement'])
        self.assertFalse(self.store.undo_history()['entries'])
        self.assertEqual((self.store.root / image['stored_rel']).read_bytes(), b'better')

    def test_clear_history_permanently_removes_only_retained_deleted_files(self):
        deleted, active = self.image('deleted'), self.image('active')
        self.store.delete_media(deleted['id'])
        entry_id = self.store.undo_history()['entries'][0]['id']
        self.store.clear_undo_history(entry_id)
        self.assertFalse((self.store.root / deleted['stored_rel']).exists())
        self.assertTrue((self.store.root / active['stored_rel']).exists())
        self.assertFalse(self.store.undo_history()['entries'])

    def test_http_flag_and_undo_endpoints(self):
        image=self.image()
        def request(method, path, body=None):
            handler=object.__new__(RUNTIME['MediaHandler'])
            handler.server=SimpleNamespace(store=self.store)
            handler.path=path
            raw=json.dumps(body or {}).encode()
            handler.headers={'Origin':'https://novelai.net','Content-Length':str(len(raw))}
            handler.rfile=io.BytesIO(raw)
            responses=[]
            handler._send_json=lambda status,value: responses.append((status,value))
            getattr(handler,'do_'+method)()
            self.assertEqual(responses[0][0],200)
            return responses[0][1]
        self.assertTrue(request('GET','/api/health')['undo_history'])
        result=request('POST',f'/api/media/{image["id"]}/needs-replacement',{'needs_replacement':True})
        self.assertTrue(result['needs_replacement'])
        latest=request('GET','/api/undo')['entries'][0]['id']
        result=request('POST','/api/undo',{'entry_id':latest})
        self.assertEqual(result['item']['id'],image['id'])
        self.assertFalse(result['item'].get('needs_replacement',False))

    def test_failed_flag_save_restores_fields_and_history(self):
        image=self.image()
        before=copy.deepcopy(image)
        with patch.object(self.store,'_write_atomic',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.store.set_needs_replacement(image['id'],True)
        self.assertEqual(image,before)
        self.assertEqual(self.store.undo_history()['entries'],[])

    def test_undo_queues_missing_thumbnail_without_decoding_on_request(self):
        image=self.image()
        self.store.delete_media(image['id'])
        with patch.object(self.store,'_queue_image_thumbnail') as queued, patch.object(self.store,'_make_thumbnail',side_effect=AssertionError('synchronous decode')):
            self.undo()
            queued.assert_called_once()

if __name__ == '__main__': unittest.main()
