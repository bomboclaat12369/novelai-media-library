import copy, tempfile, unittest
from unittest.mock import patch
from test_organizer import fixture
from organizer import Organizer
from bulk.workbench import Workbench

class OrganizerDisplayTests(unittest.TestCase):
    def test_unassigned_is_unique_and_includes_unsorted_but_not_discarded(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            self.assertEqual((org.summary()['unassigned_count'],org.summary()['images']),(16,18))
            org.mutate('unsort',{'job':'fixture-job','revision':0,'ids':[ids[2]],'post':'post:1'})
            self.assertEqual(org.summary()['unsorted_count'],1)
            self.assertEqual(org.summary()['unassigned_count'],16)
            org.mutate('save',{'job':'fixture-job','revision':1,'ids':[ids[2]],'name':'New Set'})
            self.assertEqual(org.summary()['unassigned_count'],15)
            org.mutate('discard',{'job':'fixture-job','revision':2,'ids':[ids[3]]})
            self.assertEqual((org.summary()['unassigned_count'],org.summary()['images']),(14,17))
            org.mutate('undo',{'job':'fixture-job','revision':3})
            self.assertEqual((org.summary()['unassigned_count'],org.summary()['images']),(15,18))

    def test_favorites_preserve_metadata_survive_restart_export_and_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            bulk.current['library_sets']['existing']['favorite']=True
            bulk.persist();before=copy.deepcopy(bulk.current)
            with patch.object(engine.library,'request',side_effect=AssertionError('No library writes or scan')):
                self.assertTrue(org.sets()['library:existing']['favorite'])
                org.mutate('set_details',{'job':'fixture-job','revision':0,'target':'library:existing','favorite':False,'colors':['red']})
                group=org.sets()['library:existing']
                self.assertFalse(group['favorite']);self.assertEqual(group['members'],ids[:2])
                self.assertEqual(group['colors'],['Red'])
                reopened=Organizer(engine,Workbench(engine))
                self.assertFalse(next(g for g in reopened.export()['sets'] if g['id']=='library:existing')['favorite'])
                org.mutate('undo',{'job':'fixture-job','revision':1})
                self.assertTrue(org.sets()['library:existing']['favorite'])
                self.assertEqual(bulk.current,before)

    def test_new_favorite_draft_save_and_existing_addition_preserve_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            org.mutate('draft',{'job':'fixture-job','ids':[ids[2]],'new_favorite':True})
            self.assertTrue(Organizer(engine,Workbench(engine)).summary()['state']['new_favorite'])
            org.mutate('save',{'job':'fixture-job','revision':0,'ids':[ids[2]],'name':'favorite shoot'})
            group=next(g for g in org.sets().values() if g['name']=='Favorite Shoot')
            self.assertTrue(group['favorite']);self.assertFalse(org.state()['new_favorite'])
            org.mutate('save',{'job':'fixture-job','revision':1,'ids':[ids[3]],'target':group['id']})
            self.assertTrue(org.sets()[group['id']]['favorite'])
            with self.assertRaises(ValueError):org.mutate('set_details',{'job':'fixture-job','revision':2,'target':group['id'],'favorite':'false'})
            self.assertTrue(org.sets()[group['id']]['favorite'])

if __name__=='__main__':unittest.main()
