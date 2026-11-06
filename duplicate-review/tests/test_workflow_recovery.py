import copy,io,json,runpy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from test_organizer import fixture
from organizer import Organizer,runtime_helpers
from checkpoints import Checkpoints

class OrganizerWorkflowTests(unittest.TestCase):
    def call(self,org,action,**fields):return org.mutate(action,{'job':org.bound[0],'revision':org.state().get('revision',0),**fields})

    def test_stars_survive_save_reopen_switch_and_follow_keeper(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            self.call(org,'pin',id=ids[3],pinned=True)
            self.call(org,'save',name='First set',ids=[ids[2]])
            self.assertEqual(org.summary()['up_next'],[ids[3]])
            reopened=Organizer(engine,bulk);reopened.bind();self.assertEqual(reopened.page('up_next','up_next')['ids'],[ids[3]])
            root=bulk.current['config']['roots'];bulk.current['config']['roots']=['other'];bulk.current['id']='other';reopened.bound=None
            self.assertEqual(reopened.summary()['up_next'],[])
            bulk.current['config']['roots']=root;bulk.current['id']='original';reopened.bound=None
            record=bulk.current['source_catalog'].pop(ids[3]);record=copy.deepcopy(record);record['sha']='a'*64;record['id']='a'*64;record['copies'].append({'sha':ids[3]});bulk.current['source_catalog'][record['id']]=record
            self.assertEqual(reopened.summary()['up_next'],['a'*64])

    def test_move_updates_library_overlay_and_multistep_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp)
            result=self.call(org,'save',name='Destination',ids=[ids[0],ids[3]])
            self.assertTrue(result['confirmation_required'])
            self.call(org,'save',name='Destination',ids=[ids[0],ids[3]],membership_confirmation=result['membership_confirmation'])
            target=next(g['id'] for g in org.sets().values() if g['name']=='Destination')
            self.assertNotIn(ids[0],org.sets()['library:existing']['members'])
            self.call(org,'post',id='post:2',status='deferred');self.call(org,'pin',id=ids[4],pinned=True)
            self.call(org,'undo');self.assertEqual(next(p for p in org.summary()['posts'] if p['id']=='post:2')['status'],'pending')
            self.call(org,'undo');self.assertNotIn(target,org.sets());self.assertIn(ids[0],org.sets()['library:existing']['members'])
            self.assertEqual(org.summary()['up_next'],[ids[4]])

    def test_later_changes_queue_only_not_suggestions_or_contexts(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);before=org.related({'ids':[ids[2]]})
            self.call(org,'post',id='post:1',status='deferred')
            self.assertEqual(org.summary()['later_count'],1);self.assertEqual(org.related({'ids':[ids[2]]}),before)
            self.assertIn(ids[2],org.page('post','post:1')['ids'])

    def test_video_frame_stays_video_and_never_enters_duplicate_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,bulk,org,ids=fixture(temp);path=Path(temp)/'images'/'Post 1'/'clip.mp4';path.write_bytes(b'test video')
            queue=org.video_queue()['videos'];self.assertEqual(len(queue),1)
            image=io.BytesIO();Image.new('RGB',(320,240),'blue').save(image,'JPEG')
            before=copy.deepcopy(bulk.current['source_catalog'])
            with patch.dict(runtime_helpers(),{'video_frame_data':lambda *a,**k:{'seconds':.25,'image':image.getvalue(),'exact':True}}):
                result=org.video_action('frame',{'job':org.bound[0],'id':queue[0]['id'],'seconds':.25})
            self.assertEqual(bulk.current['source_catalog'],before)
            record=org.catalog[result['id']];self.assertEqual(record['media_type'],'video');self.assertEqual(record['path'],str(path))
            self.assertNotEqual(record['sha'],record['analysis_sha']);self.assertTrue(org.preview(result['id'],600))
            self.call(org,'save',name='Video shoot',ids=[result['id'],ids[4]])
            reopened=Organizer(engine,bulk);self.assertEqual(reopened.summary()['reference_image']['id'],result['id'])
            self.assertEqual(reopened.summary()['reference_image']['frame_seconds'],.25)
            self.assertTrue(org.video_queue()['videos'][0]['assigned'])

class CoordinatedCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.engine,self.bulk,self.org,self.ids=fixture(self.temp.name)
        self.runtime=runtime_helpers();self.store=self.runtime['LibraryStore'](Path(self.temp.name)/'library');self.store.add_character('Fixture')
        self.engine.library.request=self.request;self.manager=Checkpoints(self.engine,self.bulk,self.org)
    def tearDown(self):self.temp.cleanup()
    def request(self,path,body=None):
        if path=='/api/health':return {'library_root':str(self.store.root)}
        actions={'/api/checkpoints/create':self.store.create_checkpoint,'/api/checkpoints/preview':self.store.checkpoint_preview,'/api/checkpoints/restore':self.store.checkpoint_restore}
        return actions[path](body)
    def pin(self):self.org.mutate('pin',{'job':self.org.bound[0],'revision':self.org.state()['revision'],'id':self.ids[3],'pinned':True})
    def test_complete_snapshot_restores_all_collections_and_stars(self):
        saved=self.manager.create({});self.pin();self.store.add_character('Later')
        plan=self.manager.preview({'id':saved['id']});self.assertFalse(plan['missing_files']);self.assertFalse(plan['changed_files'])
        result=self.manager.restore({'id':saved['id'],'token':plan['token']})
        self.assertEqual(self.org.summary()['up_next'],[]);self.assertEqual(len(self.store.data['characters']),1)
        self.assertTrue((self.manager.root/result['rollback']/'checkpoint.json').exists())
    def test_snapshot_with_sources_restores_missing_original(self):
        saved=self.manager.create({'include_media':True});path=Path(self.org.catalog[self.ids[4]]['path']);content=path.read_bytes();path.unlink()
        plan=self.manager.preview({'id':saved['id']});self.assertEqual(plan['missing_files'],[])
        self.manager.restore({'id':saved['id'],'token':plan['token']});self.assertEqual(path.read_bytes(),content)
    def test_stale_restore_and_failed_install_preserve_both_apps(self):
        saved=self.manager.create({});plan=self.manager.preview({'id':saved['id']});self.pin()
        with self.assertRaisesRegex(ValueError,'Project changed'):self.manager.restore({'id':saved['id'],'token':plan['token']})
        self.store.add_character('Keep after failure');plan=self.manager.preview({'id':saved['id']});original=self.manager.install_databases;calls=[]
        def fail_once(directory):
            calls.append(1)
            if len(calls)==1:raise OSError('simulated disk failure')
            return original(directory)
        with patch.object(self.manager,'install_databases',side_effect=fail_once):
            with self.assertRaises(OSError):self.manager.restore({'id':saved['id'],'token':plan['token']})
        self.assertEqual(len(self.store.data['characters']),2);self.assertEqual(self.org.summary()['up_next'],[self.ids[3]]);self.assertFalse(self.manager.journal.exists())

if __name__=='__main__':unittest.main()

class MissingOriginalFinderTests(unittest.TestCase):
    def test_organizer_recovery_keeps_stars_sets_and_saved_inventory(self):
        from test_organizer import fixture
        with tempfile.TemporaryDirectory() as folder:
            engine,bulk,org,ids=fixture(folder)
            item=org.catalog[ids[0]];path=Path(item['path']);content=path.read_bytes()
            org.mutate('pin',{'job':bulk.current['id'],'revision':org.state().get('revision',0),'id':ids[0],'pinned':True})
            state=org.state();sets=org.sets();inventory=copy.deepcopy(bulk.current)
            moved=Path(folder)/'moved';moved.mkdir();source=moved/'new-name.jpg';source.write_bytes(content);path.unlink()
            finder=org.file_finder();job=finder.start({'search_roots':[str(moved)]});finder.thread.join(10)
            report=finder.status(job['id']);self.assertEqual(report['missing'],1);self.assertEqual(report['recoverable'],1)
            finder.recover({'job_id':job['id'],'id':report['issues'][0]['id']})
            self.assertEqual(path.read_bytes(),content)
            self.assertTrue(org.preview(ids[0],240))
            self.assertEqual(engine.validate(item),path)
            from engine import Engine
            reopened=Engine(engine.state_dir)
            self.assertEqual(reopened.validate(item),path)
            self.assertEqual(org.state(),state);self.assertEqual(org.sets(),sets);self.assertEqual(bulk.current,inventory)
