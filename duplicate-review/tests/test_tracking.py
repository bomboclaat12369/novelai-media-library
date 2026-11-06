"""History is atomic, typed, resumable, and independent of caches and Undo."""
import copy,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_organizer import fixture
import test_workflow_recovery as recovery
from organizer import Organizer,runtime_helpers
import tracking

class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.engine,self.bulk,self.org,self.ids=fixture(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def events(self,owner,kind=None):
        with owner.db() as db:rows=tracking.journal().rows(db)
        return [r for r in rows if kind is None or r['kind']==kind]
    def call(self,action,**fields):
        return self.org.mutate(action,{'job':self.org.bound[0],'revision':self.org.state()['revision'],**fields})

    def test_transaction_rollback_and_replace_negative_decision(self):
        before=len(self.events(self.bulk))
        with self.assertRaises(ValueError):
            with self.bulk.db() as db:
                db.execute('INSERT INTO aliases VALUES (?,?,?,?)',('a','b','recipe-1',0));raise ValueError('rollback')
        self.assertEqual(len(self.events(self.bulk)),before)
        with self.bulk.db() as db:
            for _ in range(2):db.execute('INSERT OR REPLACE INTO aliases VALUES (?,?,?,?)',('a','b','recipe-1',0))
            db.execute('DELETE FROM aliases WHERE target=?',('a',))
        rows=self.events(self.bulk,'relationship.same_photo');self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['payload']['change']['after']['accepted'],0)
        self.assertIsNone(rows[1]['payload']['change']['after'])

    def test_scan_reset_does_not_erase_coverage_or_claim_deletion(self):
        before=self.events(self.engine,'analysis.image');self.assertTrue(before)
        with self.engine.db() as db:db.execute('DELETE FROM cache')
        self.assertEqual(before,self.events(self.engine,'analysis.image'))
        self.assertNotIn('sketch',json.dumps(before))

    def test_inventory_persist_is_idempotent_and_preserves_new_origins(self):
        before=len(self.events(self.bulk));self.bulk.persist();self.bulk.persist()
        self.assertEqual(before,len(self.events(self.bulk)))
        self.bulk.current['source_catalog'][self.ids[0]]['origins'].append({'path':'C:\\Archive\\new.jpg','kind':'instagram','key':'instagram:post-2'})
        self.bulk.persist();count=len(self.events(self.bulk));self.bulk.persist()
        self.assertEqual(count,len(self.events(self.bulk)))
        self.assertIn('instagram:post-2',json.dumps(self.events(self.bulk,'source.catalog')))
        with self.bulk.db() as db:
            self.assertTrue(db.execute("SELECT 1 FROM tracking_identities WHERE kind='folder' AND alias=?",('C:\\Archive',)).fetchone())

    def test_background_session_preferences_do_not_create_history(self):
        self.call('pin',id=self.ids[3],pinned=True);before=self.events(self.org)
        self.call('draft',ids=[self.ids[1]],new_name='Draft only')
        self.assertEqual(before,self.events(self.org))
        row=self.events(self.org,'organizer.evidence')[-1]
        self.assertEqual(row['payload']['actor'],'manual');self.assertIn(self.ids[3],json.dumps(row))

    def test_collection_switch_isolated_and_old_scope_preserved(self):
        self.call('pin',id=self.ids[3],pinned=True)
        scope=self.org.scope;collection=self.org.collection_id;job=copy.deepcopy(self.bulk.current)
        self.bulk.current['id']='different';self.bulk.current['config']['roots']=['other-folder'];self.bulk.persist()
        self.org.bound=None;self.org.bind()
        self.assertNotEqual(self.org.collection_id,collection);self.assertNotEqual(self.org.scope,scope)
        self.assertEqual(self.org.summary()['up_next'],[])
        self.bulk.current=job;self.bulk.persist();self.org.bound=None;self.org.bind()
        self.assertEqual(self.org.scope,scope);self.assertEqual(self.org.collection_id,collection)
        self.assertEqual(self.org.summary()['up_next'],[self.ids[3]])

    def test_export_and_resumable_transfer_keep_historical_evidence(self):
        self.call('post',id='post:1',status='deferred')
        exported=self.org.export();self.assertTrue(exported['tracking']['events'])
        store=runtime_helpers()['LibraryStore'](Path(self.temp.name)/'library');calls=[]
        def request(path,body=None):
            calls.append(path)
            if path=='/api/tracking/status':return store.tracking.diagnostics()
            return store.tracking_import(body)
        self.engine.library.request=request
        tracking.transfer(self.engine,self.bulk,self.org);first=store.tracking.diagnostics()['events']
        calls.clear();tracking.transfer(self.engine,self.bulk,self.org)
        self.assertEqual(store.tracking.diagnostics()['events'],first)
        self.assertEqual(calls,['/api/tracking/status'])
        self.call('post',id='post:1',status='pending');tracking.transfer(self.engine,self.bulk,self.org)
        self.assertGreater(store.tracking.diagnostics()['events'],first)

class CheckpointHistoryTests(unittest.TestCase):
    setUp=recovery.CoordinatedCheckpointTests.setUp
    tearDown=recovery.CoordinatedCheckpointTests.tearDown
    request=recovery.CoordinatedCheckpointTests.request
    pin=recovery.CoordinatedCheckpointTests.pin
    def test_restore_keeps_history_after_checkpoint(self):
        saved=self.manager.create({});self.pin()
        with self.org.db() as db:before={r['id'] for r in tracking.journal().rows(db)}
        plan=self.manager.preview({'id':saved['id']});self.manager.restore({'id':saved['id'],'token':plan['token']})
        with self.org.db() as db:after={r['id'] for r in tracking.journal().rows(db)}
        self.assertTrue(before<=after);self.assertEqual(self.org.summary()['up_next'],[])
