import copy,json,tempfile,unittest
from unittest.mock import patch
from test_organizer import fixture,add_instagram
from organizer import Organizer
from bulk.workbench import Workbench

class CollectionTests(unittest.TestCase):
    def test_switch_preserves_scoped_sets_drafts_and_analysis_across_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            bulk.current['config']['roots']=[r'C:\SMG\Mikayla'];bulk.persist();org.bound=None;org.bind()
            add_instagram(bulk,ids)
            org.mutate('save',{'job':'fixture-job','revision':0,'name':'Mikayla Shoot','ids':[ids[2]]})
            org.mutate('draft',{'job':'fixture-job','ids':[ids[3]],'new_name':'Unfinished Mikayla','suggestion_reference':ids[3]})
            org.page('set',next(g['id'] for g in org.sets().values() if g['name']=='Mikayla Shoot'))
            mikayla=copy.deepcopy(bulk.current)
            # More than the legacy dropdown's 12 entries, all retained without rescans.
            for n in range(14):
                bulk.current=copy.deepcopy(mikayla);bulk.current['id']='alice-'+str(n)
                bulk.current['config']['roots']=[r'C:\SMG\Alice'];bulk.persist()
            org.bound=None;org.bind()
            org.mutate('save',{'job':'alice-13','revision':0,'name':'Alice Shoot','ids':[ids[4]]})
            org.mutate('draft',{'job':'alice-13','ids':[ids[5]],'new_name':'Unfinished Alice'})
            with org.db() as db:sets_before=db.execute('SELECT * FROM sets ORDER BY scope,id').fetchall();states_before=db.execute('SELECT * FROM state ORDER BY scope').fetchall()
            with bulk.db() as db:jobs_before=db.execute('SELECT * FROM jobs ORDER BY id').fetchall();vectors_before=db.execute('SELECT * FROM vectors').fetchall()
            self.assertEqual([(c['name'],c['id']) for c in bulk.collections()],[('Alice','alice-13'),('Mikayla','fixture-job')])
            with patch.object(Workbench,'start',side_effect=AssertionError('No scan')),patch('organizer.load_image',side_effect=AssertionError('No image decoding')):
                result=org.switch_collection({'job':'alice-13','id':'fixture-job'})
                self.assertEqual(result['state']['new_name'],'Unfinished Mikayla')
                self.assertEqual(result['state']['selection'],[ids[3]])
                self.assertTrue(next(g for g in result['sets'] if g['name']=='Mikayla Shoot')['instagram'])
                self.assertNotIn('Alice Shoot',[g['name'] for g in result['sets']])
                reopened=Workbench(engine);self.assertEqual(reopened.current['id'],'fixture-job')
                self.assertEqual(Organizer(engine,reopened).summary()['state'],result['state'])
                result=org.switch_collection({'job':'fixture-job','id':'alice-13'})
                self.assertEqual(result['state']['new_name'],'Unfinished Alice')
                self.assertEqual(result['state']['selection'],[ids[5]])
            with org.db() as db:
                self.assertEqual(db.execute('SELECT * FROM sets ORDER BY scope,id').fetchall(),sets_before)
                self.assertEqual(db.execute('SELECT * FROM state ORDER BY scope').fetchall(),states_before)
            with bulk.db() as db:
                self.assertEqual(db.execute('SELECT * FROM jobs ORDER BY id').fetchall(),jobs_before)
                self.assertEqual(db.execute('SELECT * FROM vectors').fetchall(),vectors_before)
            with self.assertRaisesRegex(ValueError,'another window'):org.switch_collection({'job':'wrong','id':'fixture-job'})
            org.job['running']=True
            with self.assertRaisesRegex(ValueError,'pause'):org.switch_collection({'job':'alice-13','id':'fixture-job'})

    def test_instagram_uses_recorded_origins_and_recomputes_after_removal(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);add_instagram(bulk,ids)
            before=copy.deepcopy(bulk.current)
            self.assertTrue(org.sets()['library:existing']['instagram']) # linked quarantined IG copies
            self.assertFalse(org.has_instagram({'path':r'C:\Instagram\unproven.jpg'}))
            # Also works when only an original-origin record carries the evidence.
            bulk.current['source_catalog'][ids[3]]['origins'].append({'kind':'instagram','path':'direct.jpg'})
            org.mutate('save',{'job':'fixture-job','revision':0,'name':'Mixed Shoot','ids':[ids[3],ids[4]]})
            group=next(g for g in org.sets().values() if g['name']=='Mixed Shoot');ident=group['id'];created=group['created']
            self.assertTrue(group['instagram'])
            org.mutate('remove',{'job':'fixture-job','revision':1,'target':ident,'ids':[ids[3]]})
            self.assertFalse(org.sets()[ident]['instagram']);self.assertEqual(org.sets()[ident]['created'],created)
            org.mutate('undo',{'job':'fixture-job','revision':2})
            self.assertTrue(org.sets()[ident]['instagram'])
            self.assertTrue(next(g for g in org.export()['sets'] if g['id']==ident)['instagram'])

if __name__=='__main__':unittest.main()
