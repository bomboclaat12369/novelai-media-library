import copy
import hashlib
import unittest
from unittest.mock import patch
import test_runtime_stability as fixtures

class ReplacementUndoTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post_multipart=fixtures.RuntimeStabilityTests.post_multipart

    def prepare(self):
        self.store._queue_image_thumbnail=lambda *a:None
        a,b=[self.import_image(i) for i in range(2)]
        a.update(favorite=True,featured=True,crop_top=.1,in_all=False)
        group=self.store.create_set(self.character['id'],'Set',[a['id']])
        self.store.delete_media(b['id'])
        return a,group

    def test_latest_replacement_preserves_deletion_and_survives_restart(self):
        a,group=self.prepare();before=copy.deepcopy(a);old=self.store.root/a['stored_rel']
        status,replaced=self.post_multipart('/api/media/'+a['id']+'/replace',a['original_name'],b'new-image')
        self.assertEqual(status,200);self.assertTrue(old.exists());self.assertNotEqual(old,self.store.root/replaced['stored_rel'])
        self.assertEqual([e['label'] for e in self.store.undo_history()['entries']],['Replace image source','Delete media'])
        restored=fixtures.RUNTIME['LibraryStore'](self.store.root);restored._queue_image_thumbnail=lambda *a:None
        restored.undo_last(restored.undo_history()['entries'][0]['id'])
        actual=restored.media_item(a['id'])
        for key in ['sha256','original_name','favorite','featured','crop_top','in_all']:self.assertEqual(actual[key],before[key])
        self.assertEqual(restored.set_item(group['id'])['media_ids'],[a['id']])
        self.assertEqual((restored.root/actual['stored_rel']).read_bytes(),old.read_bytes())
        self.assertEqual(restored.undo_history()['entries'][0]['label'],'Delete media')

    def test_chained_same_filename_replacements_and_later_deletion(self):
        a,_=self.prepare();original=a['sha256']
        for payload in [b'first source',b'second source']:
            self.store.replace_media_bytes(payload,'same.png',a['id'],'image/png')
        self.store.delete_media(a['id'])
        self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
        self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
        self.assertEqual(self.store.media_item(a['id'])['sha256'],hashlib.sha256(b'first source').hexdigest())
        self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
        self.assertEqual(self.store.media_item(a['id'])['sha256'],original)

    def test_save_failure_and_changed_original_do_not_destroy_source(self):
        a,_=self.prepare();before=copy.deepcopy(a);history=copy.deepcopy(self.store.data['undo_history']);path=self.store.root/a['stored_rel']
        with patch.object(self.store,'save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.store.replace_media_bytes(b'new','same.png',a['id'],'image/png')
        self.assertEqual(a,before);self.assertEqual(self.store.data['undo_history'],history);self.assertTrue(path.exists())
        self.store.replace_media_bytes(b'new','same.png',a['id'],'image/png')
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'retained original'):self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
        self.assertEqual(a['sha256'],hashlib.sha256(b'new').hexdigest())

    def test_multi_set_removal_only_changes_selected_set(self):
        a,_=self.prepare();b=self.import_image(8)
        first=self.store.create_set(self.character['id'],'First',[a['id'],b['id']])
        second=self.store.create_set(self.character['id'],'Second',[])
        second['media_ids']=[a['id'],b['id']];second['cover_media_id']=a['id'];self.store.save()
        original=copy.deepcopy(second)
        self.store.update_set(first['id'],remove_media_ids=[a['id']])
        self.assertEqual(second,original);self.assertFalse(a['in_all'])
        self.store.update_set(second['id'],remove_media_ids=[a['id']]);self.assertTrue(a['in_all'])
