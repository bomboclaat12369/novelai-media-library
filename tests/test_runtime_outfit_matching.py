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
    def encode(self,source,angle=0):
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
        warm=self.run_search(media_id=self.a['id']);self.assertEqual(self.calls,calls)
        self.assertEqual(warm['cached_images'],2);self.assertEqual(warm['new_images'],0)
        self.m.vector_cache.clear()
        self.run_search(media_id=self.a['id']);self.assertEqual(self.calls,calls)
        self.run_search(image_base64=base64.b64encode(b'first').decode());self.assertEqual(self.calls,calls+3)
        self.assertEqual(before,self.store.db_path.read_bytes())
        self.assertEqual((self.store.root/self.a['stored_rel']).read_bytes(),b'first')
        (self.store.root/self.a['stored_rel']).write_bytes(b'changed image')
        self.run_search(media_id=self.a['id']);self.assertEqual(self.calls,calls+6)
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

    def test_sideways_query_uses_cached_orientation(self):
        original=self.m._encode
        def rotated(source,angle=0):
            data=source.read() if hasattr(source,'read') else Path(source).read_bytes()
            if data==b'sideways':
                self.calls+=1
                v=self.np.zeros(768,dtype=self.np.float32);v[0 if angle==90 else 2]=1
                return v
            return original(source,angle)
        self.m._encode=rotated
        body={'image_base64':base64.b64encode(b'sideways').decode()}
        result=self.run_search(**body)
        self.assertEqual(result['results'][0]['set_id'],self.group['id'])
        self.assertEqual(result['results'][0]['score'],1)
        calls=self.calls
        self.run_search(**body);self.assertEqual(self.calls,calls)

    def scan(self):
        job=self.m.start({'character_id':self.owner['id']},scan=True);self.m.thread.join(10)
        result=self.m.status(job['id']);self.assertFalse(result['running']);self.assertNotIn('error',result);return result

    def add_ungrouped(self):
        self.main=self.store.import_bytes(b'ungrouped main','main.jpg',self.owner['id'],[],{},'image/jpeg')[0]
        self.review=self.store.import_bytes(b'ungrouped review','review.jpg',self.owner['id'],[],{},'image/jpeg')[0];self.review['in_review']=True
        self.purgatory=self.store.import_bytes(b'ungrouped purgatory','purgatory.jpg',self.owner['id'],[],{},'image/jpeg')[0];self.purgatory['in_purgatory']=True
        self.foreign=self.store.import_bytes(b'other owner','foreign.jpg',self.other['id'],[],{},'image/jpeg')[0]
        self.video=self.store.import_bytes(b'video','test.mp4',self.owner['id'],[],{},'video/mp4')[0]
        self.store.save()

    def test_individual_scope_and_explicit_creation(self):
        self.add_ungrouped();before=self.store.db_path.read_bytes()
        result=self.run_search(media_id=self.main['id'])
        self.assertEqual({r['media_id'] for r in result['individual_results']},{self.review['id'],self.purgatory['id']})
        self.assertEqual(before,self.store.db_path.read_bytes())
        item=self.m.create_from_matches({'job_id':result['id'],'media_ids':[self.purgatory['id']],'query_media_id':self.main['id'],'name':'Matching outfit'})
        self.assertEqual(set(item['media_ids']),{self.purgatory['id'],self.main['id']})
        self.assertFalse(self.purgatory['in_purgatory']);self.assertFalse(self.purgatory['in_all'])
        self.assertEqual(self.group['media_ids'],[self.a['id']])
        with self.assertRaisesRegex(ValueError,'already belongs'):
            self.m.create_from_matches({'job_id':result['id'],'media_ids':[self.purgatory['id']],'name':'Again'})

    def test_scan_scope_cache_manual_assignment_and_stale_guard(self):
        self.add_ungrouped();before=self.store.db_path.read_bytes();result=self.scan()
        self.assertEqual({r['media_id'] for r in result['scan_results']},{self.main['id'],self.review['id'],self.purgatory['id']})
        self.assertEqual(before,self.store.db_path.read_bytes());calls=self.calls
        self.scan();self.assertEqual(self.calls,calls)
        self.m.assign_scan({'job_id':result['id'],'media_id':self.purgatory['id'],'set_id':self.second['id']})
        self.assertIn(self.purgatory['id'],self.second['media_ids']);self.assertFalse(self.purgatory['in_purgatory'])
        self.assertEqual(self.m.status(result['id'])['assigned_ids'],[self.purgatory['id']])
        with self.assertRaisesRegex(ValueError,'already belongs'):
            self.m.assign_scan({'job_id':result['id'],'media_id':self.purgatory['id'],'set_id':self.group['id']})
        self.store.update_set(self.group['id'],add_media_ids=[self.main['id']])
        with self.assertRaisesRegex(ValueError,'already belongs'):
            self.m.assign_scan({'job_id':result['id'],'media_id':self.main['id'],'set_id':self.second['id']})
        (self.store.root/self.review['stored_rel']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.m.assign_scan({'job_id':result['id'],'media_id':self.review['id'],'set_id':self.second['id']})

    def test_draft_creation_and_crop_anchor(self):
        self.add_ungrouped();count=len(self.store.data['media'])
        result=self.run_search(image_base64=base64.b64encode(b'unsaved query').decode())
        item=self.m.create_from_matches({'job_id':result['id'],'media_ids':[self.review['id']],'name':'For queued image'})
        self.assertEqual(item['media_ids'],[self.review['id']]);self.assertEqual(len(self.store.data['media']),count)
        result=self.run_search(image_base64=base64.b64encode(b'crop').decode(),source_media_id=self.main['id'])
        self.assertNotIn(self.main['id'],[r['media_id'] for r in result['individual_results']])
        item=self.m.create_from_matches({'job_id':result['id'],'query_media_id':self.main['id'],'media_ids':[self.purgatory['id']],'name':'Cropped search'})
        self.assertEqual(set(item['media_ids']),{self.main['id'],self.purgatory['id']})

    def test_weak_leads_and_stop_do_not_assign(self):
        self.assertFalse(self.m._stronger_lead([{'score':.85},{'score':.70}]))
        self.assertFalse(self.m._stronger_lead([{'score':.95},{'score':.94}]))
        self.assertTrue(self.m._stronger_lead([{'score':.95},{'score':.85}]))
        self.add_ungrouped();before=self.store.db_path.read_bytes();ready=threading.Event();release=threading.Event();prepare=self.m._prepare
        def wait(ident):prepare(ident);ready.set();release.wait(5)
        self.m._prepare=wait
        job=self.m.start({'character_id':self.owner['id']},scan=True);self.assertTrue(ready.wait(5))
        self.m.cancel(job['id']);release.set();self.m.thread.join(5)
        result=self.m.status(job['id']);self.assertTrue(result['cancelled']);self.assertEqual(result['scan_results'],[])
        self.assertEqual(before,self.store.db_path.read_bytes())
        with self.assertRaisesRegex(ValueError,'complete search'):
            self.m.assign_scan({'job_id':job['id'],'media_id':self.main['id'],'set_id':self.second['id']})
