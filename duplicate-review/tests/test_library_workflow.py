"""Real HTTP integration; skipped when companion source is unavailable."""
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import Engine,sha256
from library_bridge import LibraryClient
from test_engine import artwork

SOURCE=Path(os.environ.get('NAI_RUNTIME_SOURCE',Path(__file__).resolve().parents[2]/'runtime-src/companion-runtime.pyw'))
RUNTIME=runpy.run_path(str(SOURCE)) if SOURCE.exists() else None

@unittest.skipUnless(RUNTIME,'Companion source required for integration tests')
class LibraryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.source=self.base/'downloads';self.source.mkdir()
        self.store=RUNTIME['LibraryStore'](self.base/'library');self.store._queue_image_thumbnail=lambda *a:None
        self.owner=self.store.add_character('Nikki');im=artwork();old=io.BytesIO();im.resize((320,420)).save(old,'JPEG',quality=70)
        self.item=self.store.import_bytes(old.getvalue(),'old.jpg',self.owner['id'],[],{},'image/jpeg')[0]
        self.item.update(favorite=True,in_all=False);self.group=self.store.create_set(self.owner['id'],'Blue Dress',[self.item['id']]);self.store.save()
        self.oldsha=self.item['sha256'];self.new=self.source/'better.png';im.save(self.new)
        deleted=self.store.import_bytes(b'leftover','deleted.png',self.owner['id'],[],{},'image/png')[0];self.store.delete_media(deleted['id'])
        self.server=ThreadingHTTPServer(('127.0.0.1',0),RUNTIME['MediaHandler']);self.server.store=self.store
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.client=LibraryClient(self.server.server_port);self.engine=Engine(self.base/'state');self.engine.library=self.client
        self.catalog=self.client.catalog(self.owner['id']);self.scan()
    def tearDown(self):
        if self.engine.thread:self.engine.thread.join(20)
        self.server.shutdown();self.server.server_close();self.worker.join();self.temp.cleanup()
    def scan(self):
        self.engine.start([str(self.source)],[],'balanced',self.owner['id'],self.catalog['library_id']);self.engine.thread.join(20)
        self.assertEqual(self.engine.status['phase'],'Scan complete')
    def choices(self):
        group=self.engine.groups()['groups'][0];files=self.engine.groups(group['id'])['files']
        return group['id'],next(r for r in files if not r['reference']),next(r for r in files if r['library'])
    def replace(self):
        group,source,target=self.choices();return self.engine.replace_library(group,source['id'],target['id'],self.engine.revision)
    def test_compare_replace_quarantine_undo_through_http(self):
        self.assertEqual(self.engine.view()['stats']['total'],2)
        group,source,target=self.choices();self.assertEqual(json.loads(target['library'])['sets'],['Blue Dress'])
        self.replace();self.assertFalse(self.new.exists());self.assertEqual(self.item['sha256'],source['sha'])
        self.assertTrue(self.item['favorite']);self.assertFalse(self.item['in_all']);self.assertEqual(self.group['media_ids'],[self.item['id']])
        self.engine.undo();self.assertTrue(self.new.exists());self.assertEqual(self.item['sha256'],self.oldsha)
        self.assertEqual(self.engine.view()['stats']['moved'],0)
    def test_lost_response_retry_after_restart_is_idempotent(self):
        actual=self.client.replace
        def lost(*args,**kwargs):actual(*args,**kwargs);raise OSError('response lost')
        with patch.object(self.client,'replace',side_effect=lost):
            with self.assertRaisesRegex(OSError,'response lost'):self.replace()
        self.assertTrue(self.new.exists());self.assertEqual(len(self.store.data['duplicate_replacements']),1)
        self.engine=Engine(self.base/'state');self.engine.library=self.client
        self.engine.resume_replacements();self.assertFalse(self.new.exists());self.assertEqual(len(self.store.data['duplicate_replacements']),1)
        self.engine.undo();self.assertTrue(self.new.exists());self.assertEqual(self.item['sha256'],self.oldsha)
    def test_quarantine_failure_recovery_and_occupied_undo(self):
        with patch.object(self.engine,'_move_records',side_effect=OSError('locked download')):
            with self.assertRaisesRegex(OSError,'locked'):self.replace()
        self.assertTrue(self.new.exists());self.assertEqual(self.item['sha256'],sha256(self.new))
        self.engine.resume_replacements();self.assertFalse(self.new.exists())
        self.new.write_bytes(b'new download occupies path')
        with self.assertRaisesRegex(ValueError,'occupied'):self.engine.undo()
        self.assertNotEqual(self.item['sha256'],self.oldsha)
        self.new.unlink();self.engine.resume_replacements();self.assertTrue(self.new.exists());self.assertEqual(self.item['sha256'],self.oldsha)
    def test_deleted_reference_blocks_actions(self):
        self.store.delete_media(self.item['id'])
        with self.assertRaisesRegex(ValueError,'no longer in the library'):self.replace()
        self.assertTrue(self.new.exists());self.assertEqual(self.engine.view()['stats']['moved'],0)

if __name__=='__main__':unittest.main()
