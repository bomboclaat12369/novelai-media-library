"""Set entry dates and automatic Main-image covers."""
import unittest
import test_runtime_stability as fixtures

class RecentSetsTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image

    def test_membership_dates_only_change_on_real_additions(self):
        a,b=[self.import_image(i) for i in range(2)]
        group=self.store.create_set(self.character['id'],'First',[a['id']])
        first=a['set_added_at']
        self.store.update_set(group['id'],name='Renamed',favorite=True)
        self.store.update_set(group['id'],add_media_ids=[a['id'],b['id']])
        self.assertEqual(a['set_added_at'],first)
        self.assertGreater(b['set_added_at'],first)
        self.store.update_set(group['id'],remove_media_ids=[a['id']])
        self.store.update_set(group['id'],add_media_ids=[a['id']])
        second=a['set_added_at'];self.assertGreater(second,first)
        self.store.create_set(self.character['id'],'Moved',[a['id']])
        self.assertGreater(a['set_added_at'],second)
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reloaded.media_item(a['id'])['set_added_at'],a['set_added_at'])

    def test_auto_cover_follows_main_and_manual_cover_wins(self):
        a,b,c=[self.import_image(i) for i in range(3)]
        group=self.store.create_set(self.character['id'],'Outfit',[a['id'],b['id'],c['id']])
        self.assertEqual(group['cover_media_id'],a['id'])
        self.store.set_categories(b['id'],[],in_all=True)
        self.assertEqual(group['cover_media_id'],b['id']);self.assertEqual(group['cover_source'],'auto')
        self.store.set_categories(c['id'],[],in_all=True)
        self.assertEqual(group['cover_media_id'],b['id'])
        self.store.set_review(b['id'],True)
        self.assertEqual(group['cover_media_id'],c['id'])
        self.store.update_set(group['id'],cover_media_id=a['id'],cover_source='manual')
        self.store.set_review(b['id'],False)
        self.assertEqual(group['cover_media_id'],a['id']);self.assertEqual(group['cover_source'],'manual')

    def test_existing_auto_covers_upgrade_without_inventing_dates(self):
        a,b=[self.import_image(i) for i in range(2)]
        group=self.store.create_set(self.character['id'],'Existing',[a['id'],b['id']],preserve_placement=True)
        a['in_all']=False
        for m in (a,b):m.pop('set_added_at')
        self.store._write_atomic(self.store.data)
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reloaded.set_item(group['id'])['cover_media_id'],b['id'])
        self.assertNotIn('set_added_at',reloaded.media_item(a['id']))
        self.assertNotIn('set_added_at',reloaded.media_item(b['id']))

if __name__=='__main__':unittest.main()
