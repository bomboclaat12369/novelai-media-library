import unittest
import test_runtime_stability as fixtures

class SetRemovalTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post

    def test_remove_restores_main_preserves_file_metadata_and_cover_fallback(self):
        a,b=[self.import_image(i) for i in range(2)]
        category=self.store.add_category(self.character['id'],'Dress')
        a.update(categories=[category['id']],favorite=True,in_all=False)
        group=self.store.create_set(self.character['id'],'Set',[a['id'],b['id']],a['id'],cover_source='manual')
        b.update(in_review=True,in_purgatory=True);self.store.save()
        status,saved=self.post('/api/sets/'+group['id'],{'remove_media_ids':[a['id']]})
        self.assertEqual(status,200);self.assertEqual(saved['media_ids'],[b['id']])
        self.assertEqual(saved['cover_media_id'],b['id']);self.assertEqual(saved['cover_source'],'auto')
        self.assertTrue(a['in_all']);self.assertTrue(a['favorite']);self.assertEqual(a['categories'],[category['id']])
        self.assertTrue(b['in_purgatory']);self.assertTrue(b['in_review'])
        self.assertTrue((self.store.root/a['stored_rel']).exists())
        self.store.update_set(group['id'],remove_media_ids=[b['id']])
        self.assertFalse(b['in_all']);self.assertTrue(b['in_purgatory'])

    def test_manager_deselection_and_delete_last_set_release_members(self):
        a,b=[self.import_image(i) for i in range(2)]
        group=self.store.create_set(self.character['id'],'Set',[a['id'],b['id']])
        self.assertFalse(a['in_all'])
        self.store.update_set(group['id'],media_ids=[b['id']])
        self.assertTrue(a['in_all'])
        self.store.delete_set(group['id']);self.assertTrue(b['in_all'])
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertTrue(reloaded.media_item(a['id'])['in_all'])

    def test_video_set_only_and_invalid_removal(self):
        video=self.store.import_bytes(b'video','clip.mp4',self.character['id'],[],{},'video/mp4')[0]
        group=self.store.create_set(self.character['id'],'Video',[video['id']])
        self.assertFalse(video['in_videos'])
        status,_=self.post('/api/sets/'+group['id'],{'remove_media_ids':[video['id']], 'add_media_ids':[]})
        self.assertEqual(status,400);self.assertEqual(group['media_ids'],[video['id']])
        self.store.update_set(group['id'],remove_media_ids=[video['id']]);self.assertTrue(video['in_videos'])
