"""Focused tests for statistics, resolution flags, and coordinated UI releases."""
import hashlib
import io
import json
import runpy
import tempfile
import threading
import unittest
from pathlib import Path
from PIL import Image

runtime = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'runtime-src/companion-runtime.pyw'))

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = runtime['LibraryStore'](Path(self.temp.name))
        self.store._queue_image_thumbnail = lambda *a: None
        self.owner = self.store.add_character('Fixture')
    def tearDown(self):
        self.temp.cleanup()
    def image(self, size, name='source.png'):
        data=io.BytesIO();Image.new('RGB',size).save(data,'PNG')
        return self.store.import_bytes(data.getvalue(),name,self.owner['id'],[],{},'image/png')[0]
    def test_resolution_boundary_overrides_and_source_replacement(self):
        small=self.image((500,800));large=self.image((500,1000))
        self.assertTrue(small['needs_replacement']);self.assertTrue(small['replacement_auto'])
        self.assertFalse(large.get('needs_replacement',False))
        self.store.set_needs_replacement(small['id'],False)
        self.store.start_metadata_index(self.owner['id'],True);self.store._metadata_index_worker.join(3)
        self.assertFalse(small['needs_replacement'])
        reloaded=runtime['LibraryStore'](self.store.root)
        self.assertFalse(reloaded._apply_resolution_flag(reloaded.media_item(small['id'])))
        self.store.set_needs_replacement(large['id'],True)
        self.store.set_quality_settings({'enabled':False,'min_pixels':500000})
        self.store._apply_resolution_flag(large)
        self.assertTrue(large['needs_replacement'],'manual flags are never removed')
        self.store.set_quality_settings({'enabled':True,'min_pixels':500000})
        data=io.BytesIO();Image.new('RGB',(400,500),'red').save(data,'PNG')
        replaced=self.store.replace_media_bytes(data.getvalue(),'replacement.png',small['id'],'image/png')
        self.assertTrue(replaced['needs_replacement']);self.assertEqual(replaced['width'],400)
    def test_stats_count_unique_files_and_separate_pending(self):
        a=self.image((500,800));b=self.image((800,900));c=self.image((1000,1000))
        video=self.store.import_bytes(b'video','clip.mp4',self.owner['id'],[],{},'video/mp4')[0]
        c['in_review']=True
        self.store.create_set(self.owner['id'],'Set',[a['id'],video['id']],preserve_placement=True)
        a['in_all']=True
        stats=self.store.character_stats(self.owner['id'])
        self.assertEqual(stats['saved'],{'images':2,'videos':1})
        self.assertEqual(stats['in_sets'],{'images':1,'videos':1})
        self.assertEqual(stats['outside_sets'],{'images':1,'videos':0})
        self.assertEqual(stats['pending'],{'images':1,'videos':0})
        self.assertEqual(stats['image_bytes'],sum(m['file_bytes'] for m in [a,b,c]))
        self.assertEqual(stats['video_bytes'],5)
        self.assertEqual(stats['unknown_sizes'],0)
    def test_existing_scan_and_threshold(self):
        item=self.image((700,700));item.pop('needs_replacement');item.pop('replacement_auto');item['width']=item['height']=None
        self.store.start_metadata_index(self.owner['id'],True);self.store._metadata_index_worker.join(3)
        self.assertTrue(item['needs_replacement']);self.assertEqual(item['width'],700)
        self.store.set_quality_settings({'enabled':True,'min_pixels':400000})
        self.store.start_metadata_index(self.owner['id'],True);self.store._metadata_index_worker.join(3)
        self.assertFalse(item['needs_replacement'])
        with self.assertRaises(ValueError):self.store.set_quality_settings({'min_pixels':-1})

class UpdateTests(unittest.TestCase):
    def test_verified_prepare_activation_watch_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            ui=runtime['StandaloneUI'](Path(directory));updates=runtime['UIUpdates'](ui)
            code=b'fixture code';html=b'<html data-nai-media-payload-version="2.8.68">'
            manifest={'userscript_payload_version':'2.8.68','userscript_sha256':hashlib.sha256(code).hexdigest(),'userscript_parts':[ui.BASE+'part'], 'standalone_url':ui.BASE+'html','standalone_sha256':hashlib.sha256(html).hexdigest()}
            calls=[]
            def download(url,*a):
                calls.append(url)
                if 'manifest.json' in url:return json.dumps(manifest).encode()
                return code if url.endswith('part') else html
            ui._download=download
            result=updates.check();self.assertEqual(result['version'],'2.8.68');self.assertEqual(ui.cached,html)
            count=len(calls);updates.check();self.assertEqual(len(calls),count,'no repeated remote fetch inside cooldown')
            with self.assertRaises(ValueError):updates.activate('2.8.67')
            received=[];thread=threading.Thread(target=lambda:received.append(updates.status(result['cursor'])));thread.start()
            activated=updates.activate('2.8.68');thread.join(2)
            self.assertEqual(received[0]['activation'],activated['activation'])
            self.assertEqual(updates.payload()['code'],code.decode())
            # A damaged new release must not replace either verified interface.
            updates.checked_at=0;manifest['userscript_payload_version']='2.8.69';manifest['userscript_sha256']='0'*64
            with self.assertRaises(ValueError):updates.check()
            self.assertEqual(updates.version,'2.8.68');self.assertEqual(ui.cached,html)
            self.assertEqual(updates.payload()['code'],code.decode())

if __name__=='__main__':unittest.main()
