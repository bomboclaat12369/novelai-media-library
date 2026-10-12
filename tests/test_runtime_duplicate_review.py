"""Reversible companion replacement: persistence, preconditions, and rollback."""
import copy
import hashlib
import io
from pathlib import Path
import runpy
import tempfile
import unittest
import uuid
from unittest.mock import patch
from PIL import Image

RUNTIME=runpy.run_path(str(Path(__file__).resolve().parents[1]/'runtime-src/companion-runtime.pyw'))
def image_bytes(color='red', size=(80,100)):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,format='PNG');return out.getvalue()

class DuplicateReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=RUNTIME['LibraryStore'](Path(self.temp.name))
        self.store._queue_image_thumbnail=lambda *a:None
        self.owner=self.store.add_character('Nikki')
        self.old=image_bytes();self.new=image_bytes('blue',(160,200))
        self.item=self.store.import_bytes(self.old,'old.png',self.owner['id'],[],{},'image/png')[0]
        self.item.update(favorite=True,featured=True,crop={'x':.2},in_all=False)
        self.group=self.store.create_set(self.owner['id'],'White Bikini',[self.item['id']])
        self.store.save();self.lib=self.store.duplicate_catalog()['library_id'];self.op=uuid.uuid4().hex
        self.expected=self.item['sha256']
    def tearDown(self):self.temp.cleanup()
    def replace(self):return self.store.duplicate_replace(self.new,'new.png',self.item['id'],self.expected,self.op,self.lib)
    def test_live_catalog_and_replacement_undo_preserve_metadata(self):
        deleted=self.store.import_bytes(image_bytes('green'),'deleted.png',self.owner['id'],[],{},'image/png')[0]
        self.store.delete_media(deleted['id'])
        catalog=self.store.duplicate_catalog(self.owner['id'])
        self.assertEqual(len(catalog['files']),1);self.assertEqual(catalog['files'][0]['sets'],['White Bikini'])
        original_path=self.store.root/self.item['stored_rel']
        result=self.replace();self.assertEqual(result['state'],'applied')
        self.assertEqual(Path(result['path']).read_bytes(),self.new)
        retained=self.store.root/self.store.data['duplicate_replacements'][self.op]['before']['stored_rel']
        self.assertEqual(retained.read_bytes(),self.old)
        self.assertTrue(self.item['favorite']);self.assertFalse(self.item['in_all']);self.assertEqual(self.item['crop'],{'x':.2})
        self.assertEqual(self.group['media_ids'],[self.item['id']])
        self.assertNotIn('duplicate_replacements',self.store.public_library())
        self.assertEqual(self.replace()['path'],result['path']) # response-loss retry is idempotent
        self.item['favorite']=False;self.store.save()
        self.store=RUNTIME['LibraryStore'](self.store.root);self.store._queue_image_thumbnail=lambda *a:None
        restored=self.store.duplicate_undo(self.op,self.lib)
        self.assertEqual(Path(restored['path']).read_bytes(),self.old)
        self.assertFalse(restored['item']['favorite']);self.assertEqual(self.store.set_item(self.group['id'])['media_ids'],[self.item['id']])
        self.assertEqual(self.store.duplicate_undo(self.op,self.lib)['state'],'undone')
    def test_save_failure_keeps_source_and_does_not_commit_operation(self):
        before=copy.deepcopy(self.item)
        with patch.object(self.store,'save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.replace()
        self.assertEqual(self.item,before);self.assertEqual((self.store.root/self.item['stored_rel']).read_bytes(),self.old)
        self.assertEqual(self.store.duplicate_operation(self.op,self.lib)['state'],'missing')
        self.assertEqual(self.replace()['state'],'applied')
    def test_changed_source_wrong_library_and_invalid_upload_blocked(self):
        with self.assertRaises(ValueError):self.store.duplicate_replace(self.new,'new.png',self.item['id'],'0'*64,self.op,self.lib)
        with self.assertRaises(ValueError):self.store.duplicate_replace(self.new,'new.png',self.item['id'],self.expected,self.op,'other')
        with self.assertRaises(Exception):self.store.duplicate_replace(b'not image','new.png',self.item['id'],self.expected,self.op,self.lib)
        (self.store.root/self.item['stored_rel']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed on disk'):self.replace()
    def test_chained_undo_and_conflict_guard(self):
        first=self.replace();secondop=uuid.uuid4().hex
        self.store.duplicate_replace(image_bytes('green'),'third.png',self.item['id'],first['new_sha'],secondop,self.lib)
        with self.assertRaisesRegex(ValueError,'newer replacement'):self.store.duplicate_undo(self.op,self.lib)
        self.store.duplicate_undo(secondop,self.lib)
        restored=self.store.duplicate_undo(self.op,self.lib)
        self.assertEqual(Path(restored['path']).read_bytes(),self.old)

if __name__=='__main__':unittest.main()
