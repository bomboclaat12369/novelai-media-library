"""Mixed collections preserve placement and independent relationships."""
import copy
import unittest
import test_runtime_stability as fixtures


class GroupsTests(unittest.TestCase):
    setUp = fixtures.RuntimeStabilityTests.setUp
    tearDown = fixtures.RuntimeStabilityTests.tearDown
    import_image = fixtures.RuntimeStabilityTests.import_image
    post = fixtures.RuntimeStabilityTests.post

    def test_connection_and_set_http_memberships_survive_reload_and_undo(self):
        video, _ = self.store.import_bytes(b'video', 'pink.mp4', self.character['id'], [], {'kind':'local'}, 'video/mp4')
        image = self.import_image(99)
        second = self.import_image(100)
        base = {'character_id':self.character['id'], 'name':'Pink bikini', 'media_ids':[image['id'],video['id']]}
        before = copy.deepcopy(self.store.data['media'])
        status, connection = self.post('/api/sets', dict(base,kind='connection'))
        self.assertEqual(status,200)
        self.assertEqual(self.store.data['media'],before)
        status, group = self.post('/api/sets',dict(base,kind='set',preserve_placement=True))
        self.assertEqual(status,200)
        self.assertEqual(self.store.data['media'],before)
        self.assertEqual(connection['media_ids'],group['media_ids'])
        status, updated = self.post('/api/sets/'+connection['id'],{'add_media_ids':[second['id']], 'preserve_placement':True})
        self.assertEqual(status,200)
        self.assertEqual(len(updated['media_ids']),3)
        self.assertEqual(len(group['media_ids']),2)
        self.store.create_set(self.character['id'],'Another set',[image['id']],preserve_placement=True)
        self.assertNotIn(image['id'],group['media_ids'])
        self.assertIn(image['id'],connection['media_ids'])
        self.assertTrue(image['in_all'])
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reloaded.set_item(connection['id'])['kind'],'connection')
        self.store.delete_media(image['id'])
        self.assertNotIn(image['id'],self.store.set_item(connection['id'])['media_ids'])
        self.store.undo_last(self.store.data['undo_history'][-1]['id'])
        self.assertIn(image['id'],self.store.set_item(connection['id'])['media_ids'])

    def test_legacy_set_placement_and_connection_validation(self):
        image=self.import_image(101)
        old=self.store.create_set(self.character['id'],'Old',[image['id']])
        old.pop('kind')
        self.assertFalse(image['in_all'])
        c=self.store.create_set(self.character['id'],'Link',[image['id']],kind='connection')
        self.assertFalse(image['in_all'])
        self.assertEqual(old['media_ids'],[image['id']])
        self.store.update_set(c['id'],name='New link')
        self.assertEqual(old['media_ids'],[image['id']])
        with self.assertRaises(ValueError):
            self.store.create_set(self.character['id'],'Bad',[],kind='other')
