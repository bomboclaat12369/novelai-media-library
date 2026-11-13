"""Durable metadata history: failures, repeated imports, restores and provenance."""
import copy,hashlib,json,os,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import test_runtime_stability as fixtures
R=fixtures.RUNTIME

class TrackingTests(unittest.TestCase):
    setUp=fixtures.RuntimeStabilityTests.setUp
    tearDown=fixtures.RuntimeStabilityTests.tearDown
    import_image=fixtures.RuntimeStabilityTests.import_image
    post=fixtures.RuntimeStabilityTests.post

    def events(self,kind=None):
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            rows=R['TrackingJournal'].rows(db)
        return [r for r in rows if kind is None or r['kind']==kind]

    def test_exact_import_retains_all_origins_once_without_another_item(self):
        args=(b'same','first.png',self.character['id'],[],{'kind':'url','url':'https://example.test/post/1'},'image/png')
        a,_=self.store.import_bytes(*args)
        for _ in range(2):
            b,duplicate=self.store.import_bytes(b'same','renamed.png',self.character['id'],[],{'kind':'url','url':'https://example.test/post/2'},'image/png')
            self.assertTrue(duplicate);self.assertEqual(a['id'],b['id'])
        sources=self.events('source.appearance')
        self.assertEqual(len(sources),2)
        self.assertEqual({r['payload']['source']['url'] for r in sources},{'https://example.test/post/1','https://example.test/post/2'})
        self.assertEqual(len(self.store.data['media']),1)
        self.assertEqual(a['source']['url'],'https://example.test/post/1')

    def test_atomic_json_failure_has_no_committed_history(self):
        a=self.import_image(1);before=self.events();data=self.store.db_path.read_bytes()
        with patch.object(os,'replace',side_effect=OSError('disk locked')):
            with self.assertRaises(OSError):self.store.set_favorite(a['id'],True)
        self.assertEqual(before,self.events());self.assertEqual(data,self.store.db_path.read_bytes())
        self.assertFalse(self.store.media_item(a['id'])['favorite'])

    def test_committed_outbox_replays_after_ledger_failure_without_duplicate_event(self):
        a=self.import_image(1);ingest=self.store.tracking.ingest;calls=0
        def intermittent(events):
            nonlocal calls
            calls+=1
            if calls==1:raise OSError('ledger temporarily locked')
            return ingest(events)
        with patch.object(self.store.tracking,'ingest',side_effect=intermittent):
            self.store.set_favorite(a['id'],True)
        self.assertTrue(json.loads(self.store.db_path.read_bytes())['media'][0]['favorite'])
        pending=self.store.data['_tracking_pending'];self.assertTrue(pending)
        fresh=R['LibraryStore'](self.store.root)
        ids={r['id'] for r in self.events()};self.assertTrue({e['id'] for e in pending}<=ids)
        count=len(ids);R['LibraryStore'](self.store.root)
        self.assertEqual(len(self.events()),count)
        self.assertTrue(fresh.media_item(a['id'])['favorite'])

    def test_unreplayed_outbox_blocks_next_save_safely(self):
        a=self.import_image(2);before=self.store.db_path.read_bytes();self.store._tracking_applied_batch=None
        with patch.object(self.store.tracking,'ingest',side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):self.store.set_favorite(a['id'],True)
        self.assertEqual(before,self.store.db_path.read_bytes())
        self.assertFalse(self.store.media_item(a['id'])['favorite'])

    def test_history_survives_undo_pruning_and_deleted_sets(self):
        a=self.import_image(3)
        group=self.store.create_set(self.character['id'],'White Dress',[a['id']],preserve_placement=True)
        self.store.update_set(group['id'],name='Renamed')
        self.store.delete_set(group['id'])
        for i in range(24):self.store.set_favorite(a['id'],i%2==0)
        self.assertEqual(len(self.store.undo_history()['entries']),20)
        rows=[r for r in self.events('library.sets') if r['entity']==group['id']]
        self.assertTrue(any(r['payload']['change'].get('after','missing') is None for r in rows))
        self.assertIn('White Dress',json.dumps(rows));self.assertIn('Renamed',json.dumps(rows))
        self.assertGreater(len(self.events('library.media')),20)

    def test_checkpoint_restore_retains_later_history_and_current_state(self):
        a=self.import_image(4);checkpoint=self.store.create_checkpoint({})
        self.store.set_favorite(a['id'],True);later={r['id'] for r in self.events()}
        plan=self.store.checkpoint_preview({'id':checkpoint['id']})
        self.store.checkpoint_restore({'id':checkpoint['id'],'token':plan['token']})
        self.assertFalse(self.store.media_item(a['id'])['favorite'])
        self.assertTrue(later<={r['id'] for r in self.events()})
        self.assertTrue(self.events('checkpoint.restore'))
        self.store.set_favorite(a['id'],True)
        self.assertTrue(R['LibraryStore'](self.store.root).media_item(a['id'])['favorite'])
        import zipfile
        with zipfile.ZipFile(checkpoint['path']) as archive:self.assertIn('tracking.jsonl',archive.namelist())

    def test_backup_sidecar_and_hidden_outbox(self):
        self.import_image(5);path=self.store.manual_backup()
        rows=R['TrackingJournal'].decode(path.with_suffix('.tracking.jsonl').read_bytes())
        self.assertTrue(rows);self.assertNotIn('_tracking_pending',self.store.public_library())
        self.assertNotIn('_tracking_store',self.store.public_library())
        self.assertGreater(self.store.diagnostics()['tracking']['events'],0)

    def test_foreign_transfer_is_idempotent_and_fragments_resume(self):
        record={'id':'foreign-event','store':'foreign','at':'2026-11-06','kind':'decision.rejected','entity':'image',
                'payload':{'source':'x'*200000,'actor':'manual'}}
        raw=R['TrackingJournal'].encode(record);digest=hashlib.sha256(raw.encode()).hexdigest()
        chunks=[raw[i:i+64000] for i in range(0,len(raw),64000)]
        for i in [0,0,*range(1,len(chunks))]:
            self.store.tracking_import({'fragment':{'digest':digest,'index':i,'total':len(chunks),'text':chunks[i]}})
        self.store.tracking_import({'events':[record,record]})
        self.assertEqual(len([r for r in self.events() if r['id']==record['id']]),1)
        with self.assertRaises(ValueError):self.store.tracking_import({'fragment':{'digest':'../bad','index':0,'total':1,'text':'x'}})

    def test_legacy_backfill_does_not_invent_manual_decisions(self):
        self.import_image(6)
        # Simulate a pre-tracking install retaining known metadata and undo only.
        self.store.tracking.path.unlink();data=json.loads(self.store.db_path.read_bytes())
        data.pop('_tracking_store');data.pop('_tracking_pending');self.store.db_path.write_text(json.dumps(data))
        self.store=R['LibraryStore'](self.store.root)
        rows=self.events('library.media');self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['payload']['actor'],'unknown')
        self.assertEqual(rows[0]['payload']['provenance'],'legacy_observation')
        self.assertIsNone(rows[0]['payload']['occurred_at'])

    def test_analysis_coverage_keeps_recipe_and_file_version_without_vectors(self):
        record={'media_id':'image','sha256':'a'*64,'stamp':[1,2,3],'recipes':['model-v1'],'status':'completed','retrieval':'cached'}
        self.store.tracking.coverage([record,record])
        self.assertEqual(len(self.events('analysis.library')),1)
        self.store.tracking.coverage([{**record,'recipes':['model-v2'],'status':'failed','error':'missing'}])
        self.assertEqual(len(self.events('analysis.library')),2)
        self.assertNotIn('vector',json.dumps(self.events('analysis.library')))

    def test_small_edit_has_delta_and_manual_provenance(self):
        a=self.import_image(7);self.store.set_favorite(a['id'],True)
        event=self.events('library.media')[-1]
        self.assertEqual(event['payload']['actor'],'manual')
        self.assertIn('set_favorite',event['payload']['operation'])
        self.assertEqual(event['payload']['change']['changes']['favorite']['after'],True)
        self.assertNotIn('source',event['payload']['change']['changes'])

    def test_membership_delta_keeps_add_remove_and_reorder(self):
        delta=R['TrackingJournal'].delta({'members':['a','b','c']},{'members':['c','d','a']})
        self.assertEqual(delta['changes']['members'],{'added':[[1,'d']],'removed':[[1,'b']],'order':['c','d','a']})

    def test_tracking_api_accepts_bounded_history_and_malformed_origins_are_unknown(self):
        event={'id':'legacy-source','store':'legacy','at':'unknown','kind':'source.appearance','entity':'old-image','payload':{'source':{'origins':None},'catalog_record':{'origins':['old raw value',{'original_path':'C:\\Archive\\image.jpg'}]}}}
        code,result=self.post('/api/tracking/import',{'events':[event]})
        self.assertEqual(code,200);self.assertEqual(result['received'],1)
        self.assertTrue(any(r['id']=='legacy-source' for r in self.events()))
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            self.assertTrue(db.execute("SELECT 1 FROM tracking_identities WHERE kind='folder' AND alias=?",('C:\\Archive',)).fetchone())

    def test_stable_library_identity_survives_moving_the_whole_library(self):
        import shutil
        original=self.store.duplicate_catalog()['stable_library_id']
        with tempfile.TemporaryDirectory() as elsewhere:
            moved=Path(elsewhere)/'moved';shutil.copytree(self.store.root,moved)
            reopened=R['LibraryStore'](moved)
            self.assertEqual(reopened.duplicate_catalog()['stable_library_id'],original)
            with closing(sqlite3.connect(reopened.tracking.path)) as db:
                roots=db.execute("SELECT alias FROM tracking_identities WHERE kind='library.root' AND identity=?",(original,)).fetchall()
            self.assertEqual({r[0] for r in roots},{str(self.store.root.resolve()),str(moved.resolve())})
