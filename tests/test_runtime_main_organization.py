"""Focused placement/date and category-only Set edits for release 2.7.42."""
import copy
import unittest
from unittest.mock import patch
import test_runtime_stability as fixtures

class MainOrganizationTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post

    def test_category_assignment_exits_purgatory_for_both_types_and_undo_restores(self):
        self.store._queue_image_thumbnail=lambda *a:None
        for kind in ['image','video']:
            with self.subTest(kind=kind):
                item=self.import_image(1) if kind=='image' else self.store.import_bytes(b'video','v.mp4',self.character['id'],[],{},'video/mp4')[0]
                cat=self.store.add_category(self.character['id'],kind,kind)
                item['created_at']='2020-01-01T00:00:00Z';item['main_added_at']=item['created_at']
                self.store.set_purgatory(item['id'],True)
                before=copy.deepcopy(item)
                flag='in_all' if kind=='image' else 'in_videos'
                status,result=self.post('/api/media/'+item['id']+'/categories',{'categories':[cat['id']],flag:False})
                self.assertEqual(status,200);self.assertFalse(result['in_purgatory']);self.assertTrue(result[flag])
                self.assertEqual(result['created_at'],before['created_at']);self.assertGreater(result['main_added_at'],before['main_added_at'])
                stamp=result['main_added_at'];self.store.set_favorite(item['id'],True)
                self.assertEqual(item['main_added_at'],stamp)
                self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
                self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
                self.assertEqual(item,before)

    def test_set_release_and_review_entry_dates_preserve_import_date(self):
        self.store._queue_image_thumbnail=lambda *a:None
        item=self.import_image(0);item['created_at']='2020-01-01T00:00:00Z';item['main_added_at']=item['created_at']
        group=self.store.create_set(self.character['id'],'Only Set',[item['id']])
        self.assertFalse(item['in_all'])
        self.store.update_set(group['id'],remove_media_ids=[item['id']])
        self.assertTrue(item['in_all']);self.assertGreater(item['main_added_at'],item['created_at'])
        self.store.set_review(item['id'],True);self.store.set_review(item['id'],False)
        self.assertEqual(item['created_at'],'2020-01-01T00:00:00Z')
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reloaded.media_item(item['id'])['main_added_at'],item['main_added_at'])

    def test_quick_and_bulk_set_edits_preserve_memberships_and_other_categories(self):
        self.store._queue_image_thumbnail=lambda *a:None
        item=self.import_image(0);first=self.store.create_set(self.character['id'],'One',[item['id']])
        second=self.store.create_set(self.character['id'],'Two',[]);second['media_ids']=[item['id']]
        cat=self.store.add_set_category(self.character['id'],'Clothes');other=self.store.add_set_category(self.character['id'],'Other')
        second['categories']=[other['id']]
        self.store.update_set(first['id'],name='Renamed',categories=[cat['id']])
        self.assertEqual(second['media_ids'],[item['id']]);self.assertFalse(item['in_all'])
        body={'character_id':self.character['id'],'set_ids':[first['id'],second['id']],'categories':[cat['id']],'action':'add'}
        self.assertEqual(self.post('/api/sets/categories-bulk',body)[0],200)
        self.assertEqual(second['categories'],[other['id'],cat['id']])
        before=copy.deepcopy(self.store.data)
        with patch.object(self.store,'save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.store.bulk_set_categories(self.character['id'],body['set_ids'],[cat['id']],'remove')
        self.assertEqual(self.store.data,before)
        self.assertEqual(self.post('/api/sets/categories-bulk',{**body,'set_ids':[first['id'],'missing']})[0],400)
        self.assertEqual(self.store.data,before)
        self.post('/api/sets/categories-bulk',{**body,'action':'remove'})
        self.assertEqual(first['categories'],[]);self.assertEqual(second['categories'],[other['id']])
