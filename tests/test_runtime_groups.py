"""Mixed collections preserve placement and independent relationships."""
import copy
import unittest
import test_runtime_stability as fixtures


class GroupsTests(unittest.TestCase):
    setUp = fixtures.RuntimeStabilityTests.setUp
    tearDown = fixtures.RuntimeStabilityTests.tearDown
    import_image = fixtures.RuntimeStabilityTests.import_image
    post = fixtures.RuntimeStabilityTests.post

    def test_connections_retired_without_changing_media_or_sets(self):
        image=self.import_image(99)
        image['in_purgatory']=False
        group=self.store.create_set(self.character['id'],'Keep set',[image['id']])
        # Emulate saved records from the previous runtime, including delete undo.
        legacy={'id':'retired','kind':'connection','character_id':self.character['id'],'name':'Old link','media_ids':[image['id']]}
        self.store.data['sets'].append(legacy)
        before=copy.deepcopy(self.store.data['media'])
        self.store.save()
        self.store._thumbnail_queue.join()
        before=copy.deepcopy(self.store.data['media'])
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reloaded.data['media'],before)
        self.assertEqual(reloaded.data['sets'],[group])
        self.assertEqual(len(list(self.store.backup_dir.glob('library-before-connections-removal-*.json'))),1)
        again=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(again.data['sets'],[group])
        with self.assertRaises(ValueError):
            again.create_set(self.character['id'],'Removed feature',[],kind='connection')

    def test_retired_connection_does_not_block_media_delete_undo(self):
        image=self.import_image(101)
        group=self.store.create_set(self.character['id'],'Set',[image['id']])
        legacy={'id':'retired','kind':'connection','character_id':self.character['id'],'name':'Old link','media_ids':[image['id']]}
        self.store.data['sets'].append(legacy)
        self.store.delete_media(image['id'])
        self.store._thumbnail_queue.join()
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        reloaded.undo_last(reloaded.data['undo_history'][-1]['id'])
        self.assertIsNotNone(reloaded.media_item(image['id']))
        self.assertEqual(reloaded.set_item(group['id'])['media_ids'],[image['id']])
        self.assertIsNone(reloaded.set_item('retired'))

    def test_video_set_only_placement_search_independent_and_legacy_reload(self):
        video, _ = self.store.import_bytes(b'new video', 'set-only.mp4', self.character['id'], [], {'kind':'local'}, 'video/mp4')
        legacy, _ = self.store.import_bytes(b'legacy video', 'legacy.mp4', self.character['id'], [], {'kind':'local'}, 'video/mp4')
        legacy.pop('in_videos', None)
        legacy['in_all'] = False
        image = self.import_image(102)
        group = self.store.create_set(self.character['id'], 'Mixed', [video['id'],image['id']])
        self.assertFalse(video['in_videos'])
        self.assertFalse(image['in_all'])
        self.assertFalse(video['in_videos'])
        self.store.set_categories(video['id'], [])
        self.assertFalse(video['in_videos'])
        category = self.store.add_category(self.character['id'], 'Dress', 'video')
        status, updated = self.post('/api/media/'+video['id']+'/categories', {'categories':[category['id']]})
        self.assertEqual(status,200)
        self.assertTrue(updated['in_videos'])
        self.assertFalse(updated['in_all'])
        self.assertIn(video['id'],group['media_ids'])
        status, updated = self.post('/api/media/'+video['id']+'/categories', {'categories':[], 'in_videos':False})
        self.assertFalse(updated['in_videos'])
        self.store.save()
        reloaded = fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertTrue(reloaded.media_item(legacy['id'])['in_videos'])
        self.assertFalse(reloaded.media_item(video['id'])['in_videos'])
        second, _ = self.store.import_bytes(b'new video 2', 'second.mp4', self.character['id'], [], {'kind':'local'}, 'video/mp4')
        self.store.update_set(group['id'], add_media_ids=[second['id']])
        self.assertFalse(second['in_videos'])
