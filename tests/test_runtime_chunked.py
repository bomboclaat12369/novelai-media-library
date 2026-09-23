"""Chunk upload integrity, replay, cancellation and real HTTP integration."""
import base64
import hashlib
import json
import runpy
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

R = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'runtime-src/companion-runtime.pyw'))

class ChunkedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = R['LibraryStore'](Path(self.tmp.name))
        self.char = self.store.add_character('Chunk test')
        self.token = 'nai_test_1234567890'

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, size, token=None):
        return self.store.chunk_upload(token or self.token, 'start', {
            'character_id':self.char['id'], 'filename':'original.mp4', 'size':size,
            'content_type':'video/mp4', 'categories':[], 'source_url':''})

    def chunk(self, data, offset=0):
        return {'offset':offset, 'data':base64.b64encode(data).decode(), 'sha256':hashlib.sha256(data).hexdigest()}

    def test_exact_bytes_retry_and_duplicate_registration(self):
        data = bytes(range(256))*8193
        self.start(len(data))
        first = self.chunk(data[:2*1024*1024])
        self.store.chunk_upload(self.token,'chunk',first)
        self.assertEqual(self.store.chunk_upload(self.token,'chunk',first)['offset'],2*1024*1024)
        self.assertEqual(self.start(len(data))['offset'],2*1024*1024)
        self.store.chunk_upload(self.token,'chunk',self.chunk(data[2*1024*1024:],2*1024*1024))
        result = self.store.chunk_upload(self.token,'finish',{})
        self.assertEqual(self.store.chunk_upload(self.token,'finish',{}), result)
        saved = self.store.root/result['item']['stored_rel']
        self.assertEqual(saved.read_bytes(),data)
        self.assertEqual(result['item']['sha256'],hashlib.sha256(data).hexdigest())
        self.assertFalse(list(self.store._upload_dir.glob('*.part')))
        self.token += '_again'
        self.start(len(data))
        self.store.chunk_upload(self.token,'chunk',first)
        self.store.chunk_upload(self.token,'chunk',self.chunk(data[2*1024*1024:],2*1024*1024))
        self.assertTrue(self.store.chunk_upload(self.token,'finish',{})['duplicate'])
        self.assertEqual(len(self.store.data['media']),1)

    def test_corrupt_missing_out_of_order_and_conflicting_retry_rejected(self):
        self.start(6)
        for body in [self.chunk(b'abc',1), {**self.chunk(b'abc'),'sha256':'bad'}]:
            with self.assertRaises(ValueError): self.store.chunk_upload(self.token,'chunk',body)
        with self.assertRaises(ValueError): self.store.chunk_upload(self.token,'finish',{})
        self.store.chunk_upload(self.token,'chunk',self.chunk(b'abc'))
        with self.assertRaises(ValueError): self.store.chunk_upload(self.token,'chunk',self.chunk(b'def'))
        self.assertEqual(len(self.store.data['media']),0)

    def test_cancel_cleans_only_current_and_blocks_delayed_start(self):
        self.start(6)
        other = self.token+'_other'
        self.start(6,other)
        self.store.chunk_upload(self.token,'chunk',self.chunk(b'abc'))
        self.store.chunk_upload(self.token,'cancel',{})
        self.assertFalse((self.store._upload_dir/f'{self.token}.part').exists())
        self.assertTrue((self.store._upload_dir/f'{other}.part').exists())
        with self.assertRaises(ValueError): self.start(6)
        with self.assertRaises(ValueError): self.store.chunk_upload(self.token,'chunk',self.chunk(b'def',3))
        late = self.token+'_late'
        self.store.chunk_upload(late,'cancel',{})
        with self.assertRaises(ValueError): self.start(6,late)
        self.assertEqual(len(self.store.data['media']),0)

    def test_startup_cleanup_preserves_saved_media_and_other_incoming_files(self):
        self.store._upload_dir.mkdir(parents=True,exist_ok=True)
        orphan = self.store._upload_dir/'orphan.part'; orphan.write_bytes(b'partial')
        unrelated = self.store.root/'.incoming'/'other.part'; unrelated.write_bytes(b'other')
        server = R['MediaHTTPServer'](('127.0.0.1',0),self.store)
        try:
            self.assertFalse(orphan.exists())
            self.assertTrue(unrelated.exists())
        finally: server.server_close()

    def test_real_http_upload_exceeding_extension_limit_preserves_checksum(self):
        server = R['MediaHTTPServer'](('127.0.0.1',0),self.store)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}/api/import/chunked/{self.token}/'
        def post(action, body):
            raw = json.dumps(body).encode()
            self.assertLess(len(raw),24*1024*1024)
            req=urllib.request.Request(base+action,data=raw,headers={'Content-Type':'application/json','Origin':'https://novelai.net'})
            with urllib.request.urlopen(req,timeout=10) as res: return json.load(res)
        try:
            data = bytes(range(256))*65536
            size = len(data)*5  # 80 MiB file, while every request stays under 24 MiB.
            post('start', {'character_id':self.char['id'],'filename':'large.mp4','size':size,'content_type':'video/mp4','categories':[],'source_url':''})
            expected=hashlib.sha256()
            for i in range(5):
                expected.update(data)
                self.assertEqual(post('chunk',self.chunk(data,i*len(data)))['offset'],(i+1)*len(data))
            result=post('finish',{})
            self.assertEqual(result['item']['sha256'],expected.hexdigest())
            self.assertEqual(result['item']['file_bytes'],size)
            self.assertEqual(len(self.store.data['media']),1)
        finally:
            server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__': unittest.main()
