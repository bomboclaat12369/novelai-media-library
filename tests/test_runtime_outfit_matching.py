"""Focused cache, scope and metadata-safety checks; no model/network required."""
import base64
import importlib.util
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import test_runtime_stability as fixtures

@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Optional matching dependencies required')
class OutfitTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np=np
        self.temp=tempfile.TemporaryDirectory();self.store=fixtures.RUNTIME['LibraryStore'](Path(self.temp.name))
        self.owner=self.store.add_character('Nikki');self.other=self.store.add_character('Other')
        self.a=self.store.import_bytes(b'first', 'a.jpg', self.owner['id'], [], {}, 'image/jpeg')[0]
        self.b=self.store.import_bytes(b'second', 'b.jpg', self.owner['id'], [], {}, 'image/jpeg')[0]
        self.group=self.store.create_set(self.owner['id'],'Blue',[self.a['id']],preserve_placement=True)
        self.second=self.store.create_set(self.owner['id'],'White',[self.b['id']],preserve_placement=True)
        self.store.create_set(self.other['id'],'Other character',[])
        self.m=self.store.outfit_matcher;self.calls=0
        self.m._prepare=self.prepare;self.m._encode=self.encode
    def prepare(self,ident):
        self.m.cache.mkdir(exist_ok=True);self.m.np=self.np
    def encode(self,source):
        self.calls+=1
        b=source.read() if hasattr(source,'read') else Path(source).read_bytes()
        v=self.np.zeros(768,dtype=self.np.float32);v[0 if b==b'first' else 1]=1
        return v
    def tearDown(self):
        if self.m.thread:self.m.thread.join(10)
        if self.store._thumbnail_worker:
            self.store._thumbnail_queue.put(None);self.store._thumbnail_worker.join(5)
        self.temp.cleanup()
    def run_search(self,**query):
        job=self.m.start({'character_id':self.owner['id'],**query});self.m.thread.join(10)
        result=self.m.status(job['id']);self.assertFalse(result['running']);self.assertNotIn('error',result);return result
    def test_saved_and_draft_cache_no_library_changes(self):
        before=self.store.db_path.read_bytes()
        result=self.run_search(media_id=self.a['id']);self.assertEqual(result['results'][0]['set_id'],self.group['id'])
        self.assertEqual(len(result['results']),2);calls=self.calls
        self.run_search(media_id=self.a['id']);self.assertEqual(self.calls,calls)
        self.run_search(image_base64=base64.b64encode(b'first').decode());self.assertEqual(self.calls,calls+1)
        self.assertEqual(before,self.store.db_path.read_bytes())
        self.assertEqual((self.store.root/self.a['stored_rel']).read_bytes(),b'first')
        (self.store.root/self.a['stored_rel']).write_bytes(b'changed image')
        self.run_search(media_id=self.a['id']);self.assertEqual(self.calls,calls+2)
        with self.assertRaisesRegex(ValueError,'this character'):
            self.m.start({'character_id':self.other['id'],'media_id':self.a['id']})
    def test_membership_refresh_missing_original_and_stale_search(self):
        self.run_search(media_id=self.a['id'])
        self.store.update_set(self.group['id'],name='Renamed')
        (self.store.root/self.b['stored_rel']).unlink()
        result=self.run_search(media_id=self.a['id'])
        self.assertEqual(result['results'][0]['name'],'Renamed');self.assertEqual(len(result['issues']),1)
        self.assertEqual(result['unsearchable_sets'],1)
        original=self.m._prepare
        def changing(ident):original(ident);self.store.update_set(self.group['id'],name='Later')
        self.m._prepare=changing
        job=self.m.start({'character_id':self.owner['id'],'media_id':self.a['id']});self.m.thread.join(10)
        self.assertIn('Set images changed',self.m.status(job['id'])['error'])
