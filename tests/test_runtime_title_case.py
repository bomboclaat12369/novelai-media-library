import unittest
import test_runtime_stability as fixtures


class TitleCaseTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    post=fixtures.RuntimeStabilityTests.post

    def test_rules_and_idempotence(self):
        convert=fixtures.RUNTIME['title_case_label']
        cases={
            'blue and white outfit':'Blue and White Outfit',
            'black with gold':'Black with Gold',
            'the girl with a pearl earring':'The Girl with a Pearl Earring',
            'a night to remember':'A Night to Remember',
            'red or blue':'Red or Blue',
            'the one to look at':'The One to Look At',
            "girl's night-out: a look in blue":"Girl's Night-Out: A Look in Blue",
            'AI and PVC with LED':'AI and PVC with LED',
            'iPhone with McQueen':'iPhone with McQueen',
            '  café in blue  ':'Café in Blue',
            'blue, white and gold':'Blue, White and Gold',
        }
        for original,expected in cases.items():
            with self.subTest(original=original):
                self.assertEqual(convert(original),expected)
                self.assertEqual(convert(expected),expected)

    def test_api_create_edit_collisions_colors_and_reopen(self):
        owner=self.character['id']
        status,group=self.post('/api/sets',{'character_id':owner,'name':'blue and white outfit','media_ids':[],
                                         'colors':[' blue ','Blue','black with gold'],'aliases':['leave this lowercase'],'notes':'leave this too'})
        self.assertEqual(status,200);self.assertEqual(group['name'],'Blue and White Outfit')
        self.assertEqual(group['colors'],['Blue','Black with Gold']);self.assertEqual(group['aliases'],['leave this lowercase'])
        second=self.store.create_set(owner,'blue and white outfit',[])
        self.assertEqual(second['name'],'Blue and White Outfit 1')
        status,edited=self.post('/api/sets/'+group['id'],{'name':'red or blue','colors':['light blue','white and gold']})
        self.assertEqual(status,200);self.assertEqual(edited['name'],'Red or Blue')
        reloaded=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reloaded.set_item(group['id'])['colors'],['Light Blue','White and Gold'])
        self.assertEqual(reloaded.set_item(group['id'])['notes'],'leave this too')

    def test_existing_data_is_not_bulk_renamed_or_changed_by_unrelated_edits(self):
        group=self.store.create_set(self.character['id'],'Legacy',[])
        group.update(name='legacy lowercase',colors=['old blue']);self.store.save()
        reopened=fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reopened.set_item(group['id'])['name'],'legacy lowercase')
        reopened.update_set(group['id'],favorite=True)
        self.assertEqual(reopened.set_item(group['id'])['name'],'legacy lowercase')
        self.assertEqual(reopened.set_item(group['id'])['colors'],['old blue'])

if __name__=='__main__':unittest.main()
