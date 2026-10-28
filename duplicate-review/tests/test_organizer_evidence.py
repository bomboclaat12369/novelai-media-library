import copy, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_organizer import fixture
from organizer import Organizer
from bulk.workbench import Workbench


def add_large_post(bulk,ids,count=1001):
    catalog=bulk.current['source_catalog']
    source={'key':'post:dump','kind':'forum','label':'Mixed dump','path':'original/dump.jpg'}
    for n in range(count):
        ident=f'dump-image-{n:04d}'
        item=copy.deepcopy(catalog[ids[0]])
        item.update(id=ident,sources={source['key']:source},origins=[source],existing_sets=[])
        catalog[ident]=item
    bulk.persist()


class EvidenceTests(unittest.TestCase):
    def test_ignored_post_excludes_all_shared_evidence_but_preserves_visuals_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            before=copy.deepcopy(bulk.current)
            org.mutate('draft',{'job':'fixture-job','ids':[ids[2]],'new_colors':['Blue']})
            with patch.object(org,'scores',return_value={}):
                initial=org.related({'ids':[ids[2]]})
                self.assertIn(ids[0],[i['id'] for i in initial['images']])
                self.assertIn('library:existing',[g['id'] for g in initial['sets']])
                self.assertIn('post:1',[p['id'] for p in initial['posts']])
                org.mutate('post_evidence',{'job':'fixture-job','revision':0,'id':'post:1','ignored':True})
                after=org.related({'ids':[ids[2]]})
                self.assertEqual((after['images'],after['sets'],after['posts']),([],[],[]))
            with patch.object(org,'scores',return_value={ids[0]:.8,ids[7]:.7}):
                after=org.related({'ids':[ids[2]]})
                self.assertEqual([i['id'] for i in after['images']],[ids[0],ids[7]])
                self.assertTrue(all(i['reason']=='Visually similar' for i in after['images']))
                self.assertEqual([s['id'] for s in after['sets']],['library:existing'])
                self.assertEqual(after['posts'],[])
            self.assertEqual(org.state()['selection'],[ids[2]])
            self.assertEqual(org.state()['new_colors'],['Blue'])
            self.assertEqual(org.page('post','post:1')['total'],7)
            self.assertEqual(bulk.current,before)
            reopened=Organizer(engine,Workbench(engine));exported=reopened.export()
            self.assertTrue(exported['state']['post_evidence']['post:1'])
            self.assertEqual(exported['source_catalog'],before['source_catalog'])
            self.assertEqual(reopened.summary()['indexed'],18)
            reopened.mutate('undo',{'job':'fixture-job','revision':1})
            self.assertFalse(reopened.is_mixed('post:1'))
            with patch.object(reopened,'scores',return_value={}):
                self.assertEqual(reopened.related({'ids':[ids[2]]}),initial)

    def test_preferences_survive_new_inventory_and_are_collection_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            org.mutate('post_evidence',{'job':'fixture-job','revision':0,'id':'post:1','ignored':True})
            roots=bulk.current['config']['roots'][:]
            bulk.current['id']='new-inventory';bulk.persist()
            reopened=Organizer(engine,bulk);reopened.bind()
            self.assertTrue(reopened.is_mixed('post:1'))
            bulk.current['id']='other-collection';bulk.current['config']['roots']=['different'];bulk.persist()
            reopened.bind();self.assertFalse(reopened.is_mixed('post:1'))
            bulk.current['id']='back';bulk.current['config']['roots']=roots;bulk.persist()
            reopened.bind();self.assertTrue(reopened.is_mixed('post:1'))
            reopened.mutate('post_evidence',{'job':'back','revision':1,'id':'post:1','ignored':False})
            self.assertFalse(reopened.is_mixed('post:1'))
            reopened.mutate('undo',{'job':'back','revision':2})
            self.assertTrue(reopened.is_mixed('post:1'))

    def test_large_post_flag_is_advisory_and_every_page_remains_available(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            add_large_post(bulk,ids);org.bound=None
            p=next(p for p in org.summary()['posts'] if p['id']=='post:dump')
            self.assertTrue(p['large']);self.assertFalse(p['mixed']);self.assertEqual(p['source_count'],1001)
            org.mutate('post_evidence',{'job':'fixture-job','revision':0,'id':'post:dump','ignored':True})
            pages=[org.page('post','post:dump',offset,order='original') for offset in range(0,1001,60)]
            self.assertTrue(all(p['total']==1001 for p in pages))
            self.assertEqual(len(pages[-1]['images']),41)
            self.assertEqual(len({i['id'] for p in pages for i in p['images']}),1001)
            self.assertTrue(org.is_mixed('forum:smg:603571'))
            self.assertEqual(org.summary()['posts'][0]['status'],'pending')

    def test_invalid_or_stale_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            good={'job':'fixture-job','revision':0,'id':'post:1','ignored':True}
            for change in [{'id':'missing'},{'ignored':'false'},{'revision':100},{'job':'other'}]:
                with self.assertRaises(ValueError):org.mutate('post_evidence',good|change)
            self.assertNotIn('post_evidence',org.state())

if __name__=='__main__':unittest.main()
