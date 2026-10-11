"""Set naming, cover provenance and favorites remain consistent across clients."""
import concurrent.futures
import unittest
import test_runtime_stability as fixtures

class SetPreferencesTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post

    def test_name_collisions_create_rename_case_and_concurrent(self):
        owner=self.character['id']
        self.store.create_set(owner,'White Bikini',[])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            groups=list(pool.map(lambda _:self.store.create_set(owner,'White Bikini',[]),range(4)))
        self.assertEqual({g['name'] for g in groups},{f'White Bikini {i}' for i in range(1,5)})
        same=self.store.update_set(groups[0]['id'],name=groups[0]['name'])
        self.assertEqual(same['name'],groups[0]['name'])
        self.assertEqual(self.store.update_set(groups[0]['id'],name=' white bikini ')['name'],'white bikini 5')
        other=self.store.add_character('Another')
        self.assertEqual(self.store.create_set(other['id'],'White Bikini',[])['name'],'White Bikini')

    def test_cover_selection_preserved_until_fallback_and_undo(self):
        a,b=[self.import_image(i) for i in range(2)]
        group=self.store.create_set(self.character['id'],'Auto',[a['id'],b['id']])
        self.assertEqual(group['cover_source'],'auto')
        status,group=self.post('/api/sets/'+group['id'],{'cover_media_id':a['id'],'cover_source':'manual'})
        self.assertEqual(status,200);self.assertEqual(group['cover_source'],'manual')
        self.store.update_set(group['id'],name='Rename',favorite=True)
        self.assertEqual(group['cover_source'],'manual');self.assertTrue(group['favorite'])
        self.assertFalse(a['favorite']);self.assertFalse(b['favorite'])
        self.store.delete_media(a['id'])
        changed=self.store.set_item(group['id'])
        self.assertEqual(changed['cover_source'],'auto');self.assertEqual(changed['cover_media_id'],b['id'])
        self.store.undo_last(self.store.data['undo_history'][-1]['id'])
        restored=self.store.set_item(group['id'])
        self.assertEqual(restored['cover_source'],'manual');self.assertTrue(restored['favorite'])
        self.store.create_set(self.character['id'],'Moved',[a['id']])
        self.assertEqual(restored['cover_source'],'auto')

    def test_legacy_unknown_no_guess_and_api_persistence(self):
        image=self.import_image(4)
        group=self.store.create_set(self.character['id'],'Legacy',[image['id']])
        group.pop('cover_source');group.pop('favorite');self.store.save()
        self.store._thumbnail_queue.join()
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertNotIn('cover_source',reloaded.set_item(group['id']))
        reloaded.update_set(group['id'],favorite=True)
        self.assertEqual(reloaded.set_item(group['id'])['cover_source'],'unknown')
        reloaded.update_set(group['id'],cover_media_id=image['id'],cover_source='manual')
        again=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(again.set_item(group['id'])['cover_source'],'manual')
        self.assertTrue(again.set_item(group['id'])['favorite'])

    def test_auto_import_does_not_confirm_cover_or_rename_each_file(self):
        owner=self.character['id'];self.store.create_set(owner,'White Bikini',[])
        a,b=[self.import_image(i) for i in range(5,7)]
        status,created=self.post('/api/sets',{'character_id':owner,'name':'White Bikini','media_ids':[a['id']],'cover_media_id':a['id'],'cover_source':'auto'})
        self.assertEqual(status,200);self.assertEqual(created['name'],'White Bikini 1')
        status,saved=self.post('/api/sets/'+created['id'],{'name':created['name'],'media_ids':[a['id'],b['id']],'cover_media_id':a['id'],'cover_source':'auto'})
        self.assertEqual(status,200);self.assertEqual(saved['name'],'White Bikini 1');self.assertEqual(saved['cover_source'],'auto')
        status,_=self.post('/api/sets/'+created['id'],{'favorite':True})
        self.assertEqual(status,200)
