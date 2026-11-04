import copy,tempfile,unittest
from test_organizer import fixture
from test_organizer_evidence import add_large_post
from organizer import Organizer
from bulk.workbench import Workbench

class ResumeTests(unittest.TestCase):
 def test_session_survives_restart_and_stale_saves_without_touching_drafts(self):
  with tempfile.TemporaryDirectory() as temp:
   engine,bulk,org,ids=fixture(temp)
   org.mutate('draft',{'job':'fixture-job','ids':[ids[2]],'new_name':'Unfinished'})
   before=copy.deepcopy(org.state());inventory=copy.deepcopy(bulk.current)
   ui={'tab':'sets','search':'blue','filter':'all','postSort':'most','setFilter':'favorites','setSort':'createdDesc','sourceFilter':'instagram','order':'filename','columns':4,'limit':160,'gridScroll':333,'navScroll':222,'suggestionsScroll':444,'sidebarWidth':650,'sidebarSet':'library:existing','sidebarOffset':60,'relatedOffset':30,'relatedVisible':True,'unassignedOnly':True,'highlight':True,'savedAt':100,'view':{'kind':'set','id':'library:existing','offset':0}}
   org.mutate('session',{'job':'fixture-job','ui':ui})
   self.assertEqual(org.state(),dict(before,ui=ui));self.assertEqual(bulk.current,inventory)
   reopened=Organizer(engine,Workbench(engine));self.assertEqual(reopened.summary()['state']['ui'],ui)
   self.assertTrue(org.mutate('session',{'job':'fixture-job','ui':dict(ui,search='stale',savedAt=99)})['stale'])
   self.assertEqual(org.state()['ui'],ui)
   bulk.current=copy.deepcopy(inventory);bulk.current['id']='alice';bulk.current['config']['roots']=['Alice'];bulk.persist();org.bound=None
   self.assertNotIn('ui',org.summary()['state'])
   with self.assertRaisesRegex(ValueError,'Inventory changed'):org.mutate('session',{'job':'fixture-job','ui':ui})
   org.mutate('session',{'job':'alice','ui':dict(ui,search='Alice',savedAt=101)})
   org.switch_collection({'job':'alice','id':'fixture-job'})
   self.assertEqual(org.state()['ui'],ui)

 def test_unassigned_filter_counts_pages_and_preserves_source_context(self):
  with tempfile.TemporaryDirectory() as temp:
   engine,bulk,org,ids=fixture(temp);add_large_post(bulk,ids);org.bound=None;org.bind()
   params={'ids':[ids[2]]}
   all_results=org.related(params)
   assigned=[i['id'] for i in all_results['images'][:12] if not i['sets']]
   org.mutate('save',{'job':'fixture-job','revision':0,'name':'Assigned elsewhere','ids':assigned})
   before=copy.deepcopy(bulk.current);sets=copy.deepcopy(org.sets())
   all_results=org.related(params);filtered=org.related(dict(params,unassigned_only=True))
   assigned_all={i for g in org.sets().values() for i in g['members']}
   self.assertEqual(len(filtered['images']),30)
   self.assertFalse(assigned_all&{i['id'] for i in filtered['images']})
   self.assertLess(filtered['total'],all_results['total'])
   self.assertEqual(filtered['posts'],all_results['posts']);self.assertEqual(filtered['sets'],all_results['sets'])
   last=org.related(dict(params,unassigned_only=True,offset=999999))
   self.assertEqual(last['offset'],(filtered['total']-1)//30*30)
   self.assertTrue(last['images']);self.assertFalse(any(i['sets'] for i in last['images']))
   self.assertEqual(bulk.current,before);self.assertEqual(org.sets(),sets)
   # Filtering works when a single-image reference or existing destination supplies the seeds.
   for extra in ({'suggestion_reference':ids[3]},{'target':'library:existing'}):
    result=org.related(dict(params,unassigned_only=True,**extra));self.assertFalse(any(i['sets'] for i in result['images']))

if __name__=='__main__':unittest.main()
