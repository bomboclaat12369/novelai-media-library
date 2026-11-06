import copy
import tempfile
import unittest
from unittest.mock import patch

from test_organizer import fixture
from bulk.workbench import Workbench
from organizer import Organizer


class CharacterSectionsTests(unittest.TestCase):
    def sync(self,org,names=None,instance='library-a'):
        names=names or [('alice','Alice'),('nikki','Nikki'),('mikayla','Mikayla')]
        def request(path,*args):
            if path=='/api/library':return {'characters':[{'id':i,'name':n} for i,n in names]}
            if path=='/api/tracking/status':return {'instance':instance}
            raise AssertionError(path)
        with patch.object(org.engine.library,'request',side_effect=request):
            return org.refresh_collections({'job':(org.bulk.current or {}).get('id')})

    def test_all_girls_empty_sections_offline_and_rename_without_rescan(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            with patch('organizer.load_image',side_effect=AssertionError('No decode')):
                self.sync(org)
                girls={c['name']:c['id'] for c in bulk.collections()}
                self.assertTrue({'Alice','Nikki','Mikayla'}<=girls.keys())
                result=org.switch_collection({'job':bulk.current['id'],'id':girls['Nikki']})
                self.assertEqual(result['images'],0);nikki_scope=result['scope'];nikki_collection=org.collection_id
                result=org.switch_collection({'job':bulk.current['id'],'id':girls['Alice']})
                self.assertNotEqual(result['scope'],nikki_scope);self.assertNotEqual(org.collection_id,nikki_collection)
                self.sync(org,[('nikki','Nicole'),('alice','Alice')])
                renamed=next(c for c in bulk.collections() if c['name']=='Nicole')
                self.assertEqual(renamed['id'],girls['Nikki'])
                reopened=Workbench(engine);new=Organizer(engine,reopened)
                with patch.object(engine.library,'request',side_effect=ValueError('Offline')):
                    self.assertFalse(new.refresh_collections({'job':reopened.current['id']})['connected'])
                    self.assertEqual(new.switch_collection({'job':reopened.current['id'],'id':renamed['id']})['scope'],nikki_scope)

    def test_adopts_uuid_preserves_scope_draft_stars_analysis_and_combines_batches(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            bulk.current['config'].update(character_id='nikki',person='Wrong inherited name')
            bulk.persist();org.mutate('save',{'job':bulk.current['id'],'revision':0,'name':'Saved outfit','ids':[ids[3]]})
            org.mutate('draft',{'job':bulk.current['id'],'ids':[ids[1]],'new_name':'Unfinished'})
            org.mutate('pin',{'job':bulk.current['id'],'revision':org.state()['revision'],'id':ids[2],'pinned':True})
            old_scope=org.scope;old_state=org.state();old=copy.deepcopy(bulk.current)
            self.sync(org)
            section=bulk.current['id'];self.assertTrue(section.startswith('girl:'))
            self.assertEqual(org.summary()['scope'],old_scope)
            self.assertEqual(org.state(),old_state)
            self.assertEqual(org.summary()['indexed'],18)
            # A second explicitly linked folder, with another saved set, joins Nikki.
            bulk.current=copy.deepcopy(old);bulk.current['id']='second-batch';bulk.current['config']['roots']=['D:/new-batch']
            bulk.current['source_catalog']={ids[4]:copy.deepcopy(old['source_catalog'][ids[4]])}
            bulk.persist();org.bound=None;org.bind()
            org.mutate('save',{'job':'second-batch','revision':0,'name':'New outfit','ids':[ids[4]]})
            self.sync(org)
            result=org.summary();self.assertEqual(result['job'],section)
            self.assertEqual(result['scope'],old_scope)
            self.assertTrue({'saved outfit','new outfit'}<={s['name'].lower() for s in result['sets']},result['sets'])
            self.assertEqual(result['state']['new_name'],'Unfinished')
            self.assertEqual(result['state']['selection'],[ids[1]])
            self.assertEqual(result['images'],18)
            self.assertEqual(set(result['roots']),set(old['config']['roots']+['D:/new-batch']))
            before=copy.deepcopy(result['sets']);self.sync(org)
            self.assertEqual(org.summary()['sets'],before)
            self.assertEqual(org.summary()['indexed'],18)

    def test_does_not_guess_from_name_or_mix_library_namespaces(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);bulk.current['config']['person']='Nikki';bulk.persist()
            self.sync(org);self.assertEqual(bulk.current['id'],'fixture-job')
            old=copy.deepcopy(bulk.current);old['config']['character_id']='nikki';bulk.current=old;bulk.persist();self.sync(org)
            first=bulk.current['id'];self.assertEqual(org.summary()['images'],18)
            self.sync(org,instance='library-b')
            second=next(r['id'] for r in bulk.sections.rows() if r['character_id']=='nikki' and r['library_instance']=='library-b')
            result=org.switch_collection({'job':bulk.current['id'],'id':second})
            self.assertNotEqual(first,second);self.assertEqual(result['images'],0)

    def test_folder_refresh_preserves_section_and_old_inventory_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);bulk.current['config']['character_id']='nikki';bulk.persist();self.sync(org)
            prior=copy.deepcopy(bulk.current)
            with patch.object(bulk,'inventory',side_effect=ValueError('Disconnected')):
                org.collection_folders({'job':prior['id'],'roots':[]});bulk.thread.join(5)
            self.assertFalse(bulk.current['running'])
            self.assertEqual(bulk.current['source_catalog'],prior['source_catalog'])
            self.assertEqual(bulk.current['organizer_scope'],prior['organizer_scope'])
            self.assertEqual(bulk.current['section_id'],prior['id'])
            self.assertEqual(bulk.current['error'],'Disconnected')
            self.assertEqual(org.summary()['images'],18)

    def test_explicit_assignment_keeps_unlabelled_legacy_work(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            org.mutate('save',{'job':bulk.current['id'],'revision':0,'name':'Legacy set','ids':[ids[3]]})
            previous_scope=org.scope;self.sync(org)
            girl=next(c['id'] for c in bulk.collections() if c['name']=='Nikki')
            result=org.assign_collection({'job':'fixture-job','id':girl})
            self.assertEqual(result['scope'],previous_scope)
            self.assertIn('Legacy Set',[s['name'] for s in result['sets']])
            self.assertEqual(result['images'],18)

    def test_process_crash_before_refresh_completion_keeps_previous_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);bulk.current['config']['character_id']='nikki';bulk.persist();self.sync(org)
            old=copy.deepcopy(bulk.current);section=old['id']
            bulk.current=copy.deepcopy(old);bulk.current.update(id='crashed-refresh',running=True,source_catalog={},previous_section_job=section)
            bulk.current['config']['roots'].append('D:/new-batch');bulk.persist()
            reopened=Workbench(engine);new=Organizer(engine,reopened)
            self.sync(new)
            self.assertEqual(new.summary()['images'],18)
            self.assertEqual(new.scope,old['organizer_scope'])

    def test_refresh_reuses_dupe_hashes_and_has_no_visual_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);bulk.current['config']['character_id']='nikki';bulk.persist();self.sync(org)
            def request(path,*args):
                return {'instance':'library-a'} if path=='/api/tracking/status' else {'characters':[{'id':'nikki','name':'Nikki'}],'sets':[]}
            with patch.object(engine.library,'request',side_effect=request),patch.object(engine.library,'catalog',return_value={'root':temp,'files':[]}),patch('bulk.workbench.sha256',side_effect=AssertionError('No repeat hash')),patch('bulk.workbench.pixel_digest',side_effect=AssertionError('No repeat pixel decode')),patch.object(bulk,'encode',side_effect=AssertionError('No model analysis')):
                org.collection_folders({'job':bulk.current['id'],'roots':[]});bulk.thread.join(10)
            self.assertFalse(bulk.current['running']);self.assertNotIn('error',bulk.current)
            self.assertEqual(bulk.current['issues'],[])
            self.assertTrue(bulk.current['inventory_complete'])
            self.assertEqual(org.summary()['images'],18)


if __name__=='__main__':unittest.main()
