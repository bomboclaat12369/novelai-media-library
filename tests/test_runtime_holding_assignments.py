"""Assignments leave holding areas without making ghost/set-only media Main."""
import copy
import unittest
import test_runtime_stability as fixtures

class HoldingAssignmentsTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image

    def test_new_category_releases_both_holding_areas_and_undo_restores(self):
        for n,(holding,ghost) in enumerate((('review',False),('review',True),('purgatory',False),('purgatory',True))):
            with self.subTest(holding=holding,ghost=ghost):
                item=self.import_image(n)
                cat=self.store.add_category(self.character['id'],str(n))
                if ghost:self.store.set_category_ghost(cat['id'],True)
                getattr(self.store,'set_'+holding)(item['id'],True)
                before=copy.deepcopy(item)
                self.store.set_categories(item['id'],[cat['id']],in_all=False)
                self.assertFalse(item['in_review']);self.assertFalse(item['in_purgatory'])
                self.assertEqual(item['in_all'],not ghost)
                self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
                self.assertEqual(item,before)

    def test_unchanged_or_removed_categories_do_not_release_review(self):
        item=self.import_image(10);cat=self.store.add_category(self.character['id'],'Dress')
        self.store.set_categories(item['id'],[cat['id']])
        self.store.set_review(item['id'],True)
        self.store.set_categories(item['id'],[cat['id']]);self.assertTrue(item['in_review'])
        self.store.set_categories(item['id'],[]);self.assertTrue(item['in_review'])

    def test_create_and_add_set_release_review_and_purgatory(self):
        for n,(holding,regular) in enumerate((('review',False),('review',True),('purgatory',False),('purgatory',True))):
            for existing in (False,True):
                with self.subTest(holding=holding,regular=regular,existing=existing):
                    item=self.import_image(20+n*2+int(existing))
                    cat=self.store.add_category(self.character['id'],f'{n}-{existing}')
                    if not regular:self.store.set_category_ghost(cat['id'],True)
                    self.store.set_categories(item['id'],[cat['id']])
                    getattr(self.store,'set_'+holding)(item['id'],True)
                    group=self.store.create_set(self.character['id'],f'Set-{n}-{existing}',[] if existing else [item['id']])
                    if existing:self.store.update_set(group['id'],add_media_ids=[item['id']])
                    self.assertFalse(item['in_review']);self.assertFalse(item['in_purgatory'])
                    self.assertEqual(item['in_all'],regular)
                    self.assertIn(item['id'],group['media_ids'])

    def test_other_set_edits_do_not_release_old_members_but_explicit_reassign_does(self):
        a,b=[self.import_image(40+i) for i in range(2)]
        group=self.store.create_set(self.character['id'],'Original',[a['id'],b['id']])
        self.store.set_review(a['id'],True)
        self.store.update_set(group['id'],name='Renamed',media_ids=[b['id'],a['id']])
        self.assertTrue(a['in_review'])
        self.store.update_set(group['id'],add_media_ids=[a['id']])
        self.assertFalse(a['in_review']);self.assertFalse(a['in_all'])

if __name__=='__main__':unittest.main()
