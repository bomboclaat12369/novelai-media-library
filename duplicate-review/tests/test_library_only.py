"""Library-only scanning and guarded, durable cleanup through the real companion."""
import copy
import io
import json
import unittest
from unittest.mock import patch
import test_library_workflow as fixtures
RUNTIME=fixtures.RUNTIME
from engine import Engine, sha256
from test_engine import artwork

@unittest.skipUnless(RUNTIME,'Companion source required')
class LibraryOnlyTests(unittest.TestCase):
    setUp=fixtures.LibraryWorkflowTests.setUp
    tearDown=fixtures.LibraryWorkflowTests.tearDown
    scan=fixtures.LibraryWorkflowTests.scan

    def prepare_library(self):
        other=self.store.add_character('Other character')
        data=self.new.read_bytes()
        second=self.store.import_bytes(data,'full.png',self.owner['id'],[],{},'image/png')[0]
        third=self.store.import_bytes(data,'other.png',other['id'],[],{},'image/png')[0]
        second.update(in_purgatory=True,in_all=False)
        third.update(in_review=True,in_all=False)
        self.store.save()
        self.engine.start([],[],'broad','*',self.catalog['library_id'],4,'library');self.engine.thread.join(25)
        self.assertEqual(self.engine.status['phase'],'Scan complete',self.engine.view()['errors'])
        self.assertEqual(self.engine.view()['coverage']['library_scanned'],3)
        self.assertEqual(self.engine.view()['coverage']['review'],1)
        self.assertEqual(self.engine.view()['coverage']['purgatory'],1)
        groups=self.engine.groups()['groups'];self.assertEqual(len(groups),1)
        group=groups[0];files=self.engine.groups(group['id'])['files']
        self.assertEqual(len(files),3);self.assertTrue(all(not r['keep'] and not r['protected'] for r in files))
        records={json.loads(r['library'])['id']:r for r in files}
        return group,records,second,third

    def test_library_scan_finish_and_durable_undo(self):
        group,records,second,third=self.prepare_library()
        before=copy.deepcopy(self.store.data['sets']);removed=copy.deepcopy(self.item)
        keeper=records[second['id']]
        self.engine.mark_keep(group['id'],keeper['id'],True,self.engine.revision)
        with self.assertRaisesRegex(ValueError,'manually'):self.engine.preview_exact()
        self.engine.finish_group(group['id'],self.engine.revision)
        self.assertIsNone(self.store.media_item(removed['id']));self.assertIsNone(self.store.media_item(third['id']))
        self.assertIsNotNone(self.store.media_item(second['id']))
        self.assertEqual(self.store.set_item(self.group['id'])['media_ids'],[])
        self.assertTrue((self.store.root/removed['stored_rel']).exists())
        self.assertEqual(self.engine.view()['stats']['library_removed'],2)
        self.assertTrue(self.new.exists(),'download folders are untouched')
        self.engine=Engine(self.base/'state');self.engine.library=self.client
        self.store=RUNTIME['LibraryStore'](self.store.root);self.server.store=self.store
        self.engine.undo()
        self.assertEqual(self.store.media_item(removed['id']),removed)
        self.assertEqual(self.store.data['sets'],before)
        self.assertEqual(self.engine.view()['stats']['library_removed'],0)
        self.assertEqual(len(self.engine.groups()['groups']),1)

    def test_lost_response_resume_and_undo_conflict(self):
        group,records,second,third=self.prepare_library()
        a,b=records[self.item['id']],records[second['id']]
        actual=self.client.cleanup
        def lost(*args):actual(*args);raise OSError('response lost')
        with patch.object(self.client,'cleanup',side_effect=lost):
            with self.assertRaisesRegex(OSError,'response lost'):
                self.engine.move_selection([dict(target=a['id'],keeper=b['id'])],self.engine.revision)
        self.assertEqual(self.engine.view()['stats']['pending_cleanups'],1)
        self.engine=Engine(self.base/'state');self.engine.library=self.client;self.engine.resume_library_cleanup()
        self.assertEqual(len(self.store.data['duplicate_cleanups']),1)
        self.store.update_set(self.group['id'],name='Later edit')
        with self.assertRaisesRegex(ValueError,'Set changed'):self.engine.undo()
        self.assertIsNone(self.store.media_item(self.item['id']))
        self.assertEqual(self.store.set_item(self.group['id'])['name'],'Later edit')

    def test_changed_original_rejected_without_partial_removal(self):
        group,records,second,third=self.prepare_library()
        old=list(self.store.data['media'])
        (self.store.root/second['stored_rel']).write_bytes(b'changed since scan')
        with self.assertRaisesRegex(ValueError,'changed on disk'):
            self.engine.move_selection([dict(target=records[self.item['id']]['id'],keeper=records[second['id']]['id'])],self.engine.revision)
        self.assertEqual(self.store.data['media'],old)
        self.engine.undo() # cancel the pending, unapplied operation
        self.assertEqual(self.engine.view()['stats']['pending_cleanups'],0)

    def test_quarantine_group_protects_library_and_rejects_library_only(self):
        group=self.engine.groups()['groups'][0]
        self.engine.quarantine_group(group['id'],self.engine.revision);self.engine.thread.join(20)
        self.assertFalse(self.new.exists())
        self.assertIsNotNone(self.store.media_item(self.item['id']))
        self.assertTrue((self.store.root/self.item['stored_rel']).exists())
        self.engine.undo();self.engine.thread.join(20)
        self.assertTrue(self.new.exists())
        group,records,second,third=self.prepare_library()
        with self.assertRaisesRegex(ValueError,'only available for incoming'):
            self.engine.quarantine_group(group['id'],self.engine.revision)
        self.assertEqual(self.engine.view()['stats']['library_removed'],0)

    def test_normal_comparison_still_protects_library(self):
        group=self.engine.groups()['groups'][0];files=self.engine.groups(group['id'])['files']
        self.assertTrue(next(r for r in files if r['library'])['protected'])
        imported=next(r for r in files if r['library']);incoming=next(r for r in files if not r['library'])
        with self.assertRaisesRegex(ValueError,'protected'):
            self.engine.move_selection([dict(target=imported['id'],keeper=incoming['id'])],self.engine.revision)
        self.assertIsNotNone(self.store.media_item(self.item['id']))
