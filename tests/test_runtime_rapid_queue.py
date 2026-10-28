"""Focused durable queue, batch placement, and Set organization checks."""
import unittest
from pathlib import Path
import test_runtime_stability as fixtures

class RapidQueueTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image

    def pending(self,n):
        path=self.store.root/f'pending-{n}.tmp';path.write_bytes(f'pending-{n}'.encode())
        return self.store._register_file(path,f'pending-{n}.jpg',self.character['id'],[],{},'image/jpeg',pending=True)[0]

    def resolve(self,action,items,**fields):
        return self.store.resolve_rapid({'character_id':self.character['id'],'action':action,'media_ids':[m['id'] for m in items],**fields})

    def test_ghost_categories_and_explicit_main_queue_placement(self):
        owner=self.character['id']
        ghost=self.store.add_category(owner,'Ghost')
        regular=self.store.add_category(owner,'Regular')
        self.store.set_category_ghost(ghost['id'],True)
        a,b,c,d=[self.pending(i+100) for i in range(4)]
        self.resolve('save',[a],choices={a['id']:{'categories':[ghost['id']]}})
        self.assertFalse(a['in_all']);self.assertFalse(self.store._in_main(a))
        self.resolve('new_set',[b],name='Explicit Main',choices={b['id']:{'categories':[ghost['id']],'rapid_main':True,'rapid_edited':True}})
        self.assertTrue(b['in_all']);self.assertTrue(b['rapid_edited'])
        self.resolve('purgatory',[c],choices={c['id']:{'categories':[regular['id']]}})
        self.assertTrue(c['in_purgatory']);self.assertFalse(c['in_all']);self.assertFalse(c['in_review'])
        self.store.set_categories(c['id'],[ghost['id']]);self.assertFalse(c['in_purgatory']);self.assertFalse(c['in_all'])
        self.store.set_categories(c['id'],[ghost['id'],regular['id']]);self.assertFalse(c['in_purgatory']);self.assertTrue(c['in_all'])
        self.resolve('main',[d]);self.assertTrue(d['in_all']);self.assertEqual(d['categories'],[])
        self.store.set_category_ghost(regular['id'],True);self.assertFalse(c['in_all']);self.assertTrue(b['in_all'])
        self.store.set_category_ghost(ghost['id'],False);self.assertTrue(a['in_all'])

    def test_set_assignment_from_purgatory_with_only_ghost_categories(self):
        item=self.pending(200);ghost=self.store.add_category(self.character['id'],'Ghost')
        self.store.set_category_ghost(ghost['id'],True)
        self.resolve('purgatory',[item],choices={item['id']:{'categories':[ghost['id']]}})
        self.store.create_set(self.character['id'],'Ghost Set',[item['id']])
        self.assertFalse(item['in_purgatory']);self.assertFalse(item['in_all'])
        self.assertEqual(item['categories'],[ghost['id']])

    def test_queue_survives_restart_without_entering_library(self):
        a,b=self.pending(1),self.pending(2)
        self.store.rapid_state({'character_id':self.character['id'],'choices':{a['id']:{'favorite':True,'crop_top':.1}},'current_id':b['id'],'selected_ids':[b['id']],'scroll_top':700})
        self.assertEqual(self.store.public_library()['media'],[])
        self.assertNotIn('rapid_queue',self.store.public_library())
        self.store._thumbnail_queue.join()
        restored=fixtures.RUNTIME['LibraryStore'](self.store.root)
        queue=restored.rapid_queue(self.character['id'])
        self.assertEqual(len(queue['items']),2);self.assertTrue(queue['items'][0]['favorite'])
        self.assertEqual(queue['state']['current_id'],b['id']);self.assertEqual(queue['state']['scroll_top'],700)
        self.assertTrue(restored.media_path(a['id'])[0].is_file())

    def test_bulk_review_and_create_set_preserve_remaining_queue(self):
        a,b,c=[self.pending(i) for i in range(3)]
        self.resolve('review',[a]);self.assertTrue(self.store.media_item(a['id'])['in_review'])
        result=self.resolve('new_set',[b],name='Blue',colors=['blue','white'])
        group=result['set'];self.assertEqual(group['colors'],['Blue','White']);self.assertEqual(group['media_ids'],[b['id']])
        self.assertFalse(self.store.media_item(b['id'])['in_all']);self.assertIn('set_added_at',self.store.media_item(b['id']))
        self.assertEqual([m['id'] for m in self.store.rapid_queue(self.character['id'])['items']],[c['id']])
        self.resolve('discard',[c]);self.assertFalse((self.store.root/c['stored_rel']).exists())
        self.assertTrue((self.store.root/a['stored_rel']).exists());self.assertTrue((self.store.root/b['stored_rel']).exists())
        with self.assertRaisesRegex(ValueError,'queue changed'):self.resolve('review',[b])

    def test_duplicate_resolution_never_reclassifies_original(self):
        a=self.pending(1)
        existing=self.store.import_bytes(b'pending-1','original.jpg',self.character['id'],[],{},'image/jpeg')[0]
        existing['favorite']=True;self.store.save()
        result=self.resolve('review',[a]);self.assertEqual(result['duplicate_ids'],[a['id']])
        self.assertTrue(existing['in_all']);self.assertFalse(existing['in_review']);self.assertTrue(existing['favorite'])
        self.assertTrue((self.store.root/existing['stored_rel']).exists());self.assertFalse((self.store.root/a['stored_rel']).exists())

    def test_set_details_and_orders_do_not_change_membership_dates(self):
        a,b=[self.import_image(i) for i in range(2)]
        group=self.store.create_set(self.character['id'],'Blue',[a['id'],b['id']],aliases=['Pool'],colors=['blue'],notes='White straps')
        stamp=a['set_added_at'];self.store.reorder_set(group['id'],[b['id'],a['id']])
        self.assertTrue(group['manual_order']);self.assertEqual(a['set_added_at'],stamp)
        self.store.update_set(group['id'],notes='New note');self.assertEqual(group['aliases'],['Pool'])
        image=[self.store.add_category(self.character['id'],n) for n in ['Dress','Bikini','Other']]
        video=self.store.add_category(self.character['id'],'Video','video')
        order=[c['id'] for c in image[1:]+image[:1]]
        self.store.reorder_categories(self.character['id'],'image',order)
        self.assertEqual([c['id'] for c in self.character['categories']],order+[video['id']])
        with self.assertRaisesRegex(ValueError,'contents changed'):self.store.reorder_set(group['id'],[a['id']])

    def test_invalid_batch_is_atomic(self):
        a,b=self.pending(1),self.pending(2)
        with self.assertRaises(ValueError):self.resolve('new_set',[a,b],name='Bad',colors='not a list')
        self.assertEqual(self.store.public_library()['media'],[])
        self.assertEqual(len(self.store.rapid_queue(self.character['id'])['items']),2)

if __name__=='__main__':unittest.main()
