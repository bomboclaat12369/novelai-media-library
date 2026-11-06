import copy,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from test_organizer import fixture
from organizer import Organizer,runtime_helpers
from library_bridge import LibraryClient
from app import make_server

class IndividualQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.engine,self.bulk,self.org,self.ids=fixture(self.temp.name)
        self.bulk.current['config']['character_id']='nikki';self.bulk.persist();self.org.bind()
    def tearDown(self):self.temp.cleanup()
    def call(self,action,**body):return self.org.mutate(action,{'job':self.bulk.current['id'],'revision':self.org.state().get('revision',0),**body})
    def queue(self,ids=None,**options):return self.call('queue_individuals',ids=ids or [self.ids[3]],options={'destination':'main',**options},character_id='nikki')

    def test_individual_queue_is_not_set_membership_and_persists_with_undo(self):
        before=self.org.sets();self.queue();self.assertEqual(self.org.sets(),before)
        reopened=Organizer(self.engine,self.bulk);self.assertEqual(reopened.summary()['individuals'][0]['id'],self.ids[3])
        self.assertEqual(reopened.page('imports','imports')['ids'],[self.ids[3]])
        self.call('remove_individuals',ids=[self.ids[3]]);self.assertFalse(self.org.summary()['individuals'])
        self.call('undo');self.assertEqual(self.org.summary()['individuals'][0]['id'],self.ids[3])
        self.call('undo');self.assertFalse(self.org.summary()['individuals'])

    def test_queue_follows_verified_keeper_and_records_history(self):
        self.queue(favorite=True);original=self.ids[3]
        record=self.bulk.current['source_catalog'].pop(original);record=copy.deepcopy(record);record.update(id='b'*64,sha='b'*64);record['copies'].append({'sha':original});self.bulk.current['source_catalog'][record['id']]=record
        self.org.bound=None;result=self.org.summary()['individuals'];self.assertEqual(result[0]['id'],'b'*64);self.assertTrue(result[0]['options']['favorite'])
        export=self.org.export();self.assertTrue(export['individuals'])
        with self.org.db() as db:
            self.assertTrue(any(r['kind']=='organizer.individual_import' for r in runtime_helpers()['TrackingJournal'].rows(db)))

    def test_unavailable_entry_explicit_removal_and_restore(self):
        self.queue();self.call('discard',ids=[self.ids[3]])
        row=self.org.summary()['individuals'][0];self.assertIsNone(row['id'])
        self.call('remove_individuals',ids=[],keys=[row['key']]);self.assertFalse(self.org.summary()['individuals'])
        self.call('undo');self.assertIsNone(self.org.summary()['individuals'][0]['id'])
        self.call('restore_discard',ids=[self.ids[3]]);self.assertEqual(self.org.page('imports','imports')['ids'],[self.ids[3]])

    def test_girl_isolation_and_stale_revision(self):
        self.queue();self.bulk.current['id']='other';self.bulk.current['config']['roots']=['other'];self.bulk.current['config']['character_id']='alice';self.org.bound=None
        self.assertEqual(self.org.summary()['individuals'],[])
        with self.assertRaisesRegex(ValueError,'another girl'):self.queue()
        with self.assertRaisesRegex(ValueError,'another window'):self.org.mutate('queue_individuals',{'job':'other','revision':999,'ids':[self.ids[3]],'options':{}})

    def test_all_images_and_original_resolution_are_read_only(self):
        before=self.org.sets();page=self.org.page('all_images','all_images');self.assertEqual(len(page['ids']),18)
        path=self.org.original_path(self.ids[3]);self.assertEqual(path.read_bytes(),Path(self.org.catalog[self.ids[3]]['path']).read_bytes());self.assertEqual(self.org.sets(),before)
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):self.org.original_path(self.ids[3])

    def test_pre_queue_checkpoint_restores_empty_queue_and_retains_history(self):
        import sqlite3
        from checkpoints import Checkpoints
        directory=Path(self.temp.name)/'old-snapshot';directory.mkdir()
        with sqlite3.connect(self.org.path) as src,sqlite3.connect(directory/'organizer.sqlite3') as dst:
            src.backup(dst);dst.execute('DROP TABLE individual_imports')
        self.queue();Checkpoints(self.engine,self.bulk,self.org).install_databases(directory)
        self.assertFalse(self.org.summary()['individuals']);self.queue();self.assertEqual(len(self.org.summary()['individuals']),1)

class IndividualHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.engine,bulk,org,self.ids=fixture(self.temp.name)
        runtime=runtime_helpers();self.store=runtime['LibraryStore'](Path(self.temp.name)/'library');self.owner=self.store.add_character('Nikki')
        handler=type('Handler',(runtime['MediaHandler'],),{'store':self.store})
        self.library_server=ThreadingHTTPServer(('127.0.0.1',0),handler);self.library_thread=threading.Thread(target=self.library_server.serve_forever,daemon=True);self.library_thread.start()
        self.engine.library=LibraryClient(self.library_server.server_port);bulk.current['config']['character_id']=self.owner['id'];bulk.persist()
        self.server=make_server(self.engine,token='test-solo');self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.library_server.shutdown();self.library_server.server_close();self.library_thread.join();self.temp.cleanup()
    def request(self,route,body=None,raw=False):
        request=Request('http://127.0.0.1:'+str(self.server.server_port)+'/api/organizer/'+route,data=json.dumps(body).encode() if body is not None else None,headers={'X-Review-Token':'test-solo','Content-Type':'application/json'})
        with urlopen(request) as response:return response.read() if raw else json.load(response)

    def test_solo_main_over_real_http_and_checkpoint_receipt(self):
        state=self.request('state');job=state['job'];catalog=self.request('import-catalog',{'job':job});self.assertEqual(catalog['name'],'Nikki')
        created=self.request('import-category-create',{'job':job,'character_id':self.owner['id'],'name':'New category'});self.assertIn(created['id'],[c['id'] for c in self.store.character(self.owner['id'])['categories']])
        state=self.request('queue_individuals',{'job':job,'revision':state['state']['revision'],'ids':self.ids[2:5],'options':{'destination':'main','favorite':True},'character_id':self.owner['id'],'library_instance':catalog['library_instance']})
        before=self.request('original?id='+self.ids[2],raw=True);self.assertEqual(before,Path(self.server.organizer.catalog[self.ids[2]]['path']).read_bytes())
        plan=self.request('transfer-preview',{'job':job,'include_sets':False});self.assertEqual(len(plan['individuals']),3)
        for row in plan['imports']:self.request('transfer-import',{'job':job,'token':plan['token'],'id':row['id']})
        result=self.request('transfer-apply',{'job':job,'token':plan['token']});self.assertEqual(result['sets'],0);self.assertEqual(len(self.store.data['media']),3)
        self.assertTrue(all(m['in_all'] and m['favorite'] for m in self.store.data['media']));self.assertFalse(self.request('state')['individuals'])
        self.assertTrue(self.server.organizer.individual_imports(include_applied=True)[0]['applied_at']);self.assertTrue(result['checkpoint'])
        self.assertTrue(all(Path(self.server.organizer.catalog[i]['path']).is_file() for i in self.ids[2:5]))

    def test_missing_runtime_capability_blocks_before_copy(self):
        org=self.server.organizer;state=org.summary();org.mutate('queue_individuals',{'job':state['job'],'revision':state['state']['revision'],'ids':[self.ids[3]],'options':{},'character_id':self.owner['id']})
        real=self.engine.library.request
        def older(path,body=None,**kw):
            if path=='/api/organizer/preview':return {'token':'old','sets':[],'imports':[],'issues':[],'conflicts':[],'existing_count':0}
            return real(path,body,**kw)
        with patch.object(self.engine.library,'request',side_effect=older):
            with self.assertRaisesRegex(ValueError,'Update the Media Library companion'):org.transfer('preview',{'job':state['job'],'include_sets':False})
        self.assertFalse(self.store.data['media']);self.assertTrue(org.summary()['individuals'])
