"""Incremental coverage, legacy checkpoints, preparation and invalidation checks."""
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import crop_match
from engine import Engine, preferred, stat_key
from test_engine import artwork


class FakeIndexes:
    def __init__(self, *args): pass
    def acquire(self): return nullcontext(self)
    def close(self): pass


def unpack(identity):
    return dict(identity=int(identity), desc=np.zeros((6,128), np.float32),
                mirror_desc=np.zeros((6,128), np.float32))


def records(n, start=0, folder='2026-10-01'):
    return [dict(id=i+1, path=f'/fixture/{folder}/{i:04}.png', sha=str(i),
                 pixel=str(i), reference=False, features=str(i)) for i in range(start,start+n)]


class IncrementalTests(unittest.TestCase):
    def test_additions_removals_renames_and_modes_preserve_pair_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            e=Engine(d); old=records(270); seen=set()
            def verify(a,b,*args):
                seen.add(tuple(sorted((a['identity'], b['identity']))))
            with patch('engine.SearchIndexes', FakeIndexes), patch('crop_match.unpack', side_effect=unpack), patch('crop_match.candidates', side_effect=lambda q,i,o:np.unique(o)), patch('crop_match.verify', side_effect=verify):
                e.match_aligned(old,'broad',4)
                self.assertEqual(len(seen),270*269//2)
                new=records(3,270,'2026-10-21'); seen.clear()
                e=Engine(d)  # Layout survives a process restart.
                e.match_aligned(new+list(reversed(old)),'broad',4)
                self.assertEqual(e.status['cached_tasks'],269)  # Original full block.
                expected={(i,j) for j in range(270,273) for i in range(j)}
                self.assertTrue(expected.issubset(seen))  # All new/old and new/new pairs.
                self.assertNotIn((1,2),seen)  # Old/full-block work was NOT repeated.
                renamed=[dict(r,path='/renamed/'+Path(r['path']).name,reference=True) for r in old+new]
                seen.clear(); e.match_aligned(renamed,'broad',4)
                self.assertFalse(seen); self.assertEqual(e.status['cached_tasks'],e.status['total'])
                # A removed first-block image leaves a hole; other blocks stay reusable.
                seen.clear(); e.match_aligned(renamed[1:],'broad',4)
                self.assertEqual(e.status['cached_tasks'],16)
                self.assertFalse(any(0 in pair for pair in seen))
                # Restore it: the original signature/checkpoint remains available.
                seen.clear(); e.match_aligned(renamed,'broad',4)
                self.assertFalse(seen)
                seen.clear(); e.match_aligned(renamed,'strict',4)
                self.assertEqual(e.status['cached_tasks'],0)
                self.assertEqual(len(seen),273*272//2)
                with patch.object(crop_match,'FEATURE_VERSION',crop_match.FEATURE_VERSION+1):
                    seen.clear(); e.match_aligned(renamed,'strict',4)
                    self.assertEqual(e.status['cached_tasks'],0)
                    self.assertEqual(len(seen),273*272//2)

    def test_upgrade_seeds_old_layout_before_new_folder_reorders_it(self):
        with tempfile.TemporaryDirectory() as d:
            e=Engine(Path(d)/'state'); old=records(258)
            # Model a 1.7.4 database: previous scan rows and original v2 keys,
            # but no persistent layout. This also checks the legacy key format.
            with e.db() as db:
                for r in old:
                    db.execute('INSERT INTO files(id,path,stamp,sha,pixel,reference) VALUES (?,?,\'stamp\',?,?,0)',(r['id'],r['path'],r['sha'],r['pixel']))
                    db.execute('INSERT INTO features VALUES (?,\'stamp\',?,?)',(r['path'],crop_match.FEATURE_VERSION,r['features']))
                ordered=preferred(old)
                for start in range(0,len(ordered),256):
                    signature=hashlib.sha256(json.dumps([r['sha'] for r in ordered[start:start+256]]).encode()).hexdigest()
                    for j in range(start+1,len(ordered)):
                        key=hashlib.sha256(json.dumps(['aligned-v2',crop_match.FEATURE_VERSION,'broad',signature,ordered[j]['sha'],min(j-start,256)]).encode()).hexdigest()
                        db.execute('INSERT INTO aligned_tasks VALUES (?,\'[]\')',(key,))
            # start() must migrate before deleting the previous files table.
            with patch.object(e,'scan'):
                e.start([d],[],'broad');e.thread.join()
            with patch('engine.SearchIndexes',FakeIndexes), patch('crop_match.unpack',side_effect=unpack), patch('crop_match.candidates',return_value=[]):
                e.match_aligned(records(3,258,'2026-10-21')+old,'broad',4)
            self.assertEqual(e.status['cached_tasks'],257)

    def test_preparation_reuse_changed_file_and_bounded_parallelism(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); inc=root/'incoming';inc.mkdir()
            for i in range(4): artwork(i).save(inc/f'{i}.png')
            e=Engine(root/'state'); barrier=threading.Barrier(2)
            real=e.prepare_image; active=peak=0; lock=threading.Lock()
            def prepare(*args):
                nonlocal active,peak
                with lock: active+=1; peak=max(peak,active)
                try:
                    barrier.wait(timeout=10)
                    return real(*args)
                finally:
                    with lock: active-=1
            def scan():
                e.start([str(inc)],[],'broad',workers=2);e.thread.join(30)
                self.assertFalse(e.status['running']);self.assertEqual(e.status['phase'],'Scan complete',e.status)
            with patch.object(e,'prepare_image',side_effect=prepare): scan()
            self.assertEqual(peak,2);self.assertEqual(e.status['read_prepared'],4)
            # All preparation operations, including decoding and hashing, are bypassed.
            with patch.object(e,'prepare_image',side_effect=AssertionError('unchanged image reprocessed')): scan()
            self.assertEqual(e.status['read_cached'],4);self.assertEqual(e.status['read_prepared'],0)
            artwork(80).save(inc/'1.png'); scan()
            self.assertEqual(e.status['read_cached'],3);self.assertEqual(e.status['read_prepared'],1)
            self.assertEqual(e.view()['coverage']['read_cached'],3)
            # Cache hits must not rewrite large cached feature/fingerprint records.
            with e.db() as db:
                for table in ('cache','features'):
                    db.execute(f"CREATE TRIGGER no_write_{table} BEFORE INSERT ON {table} BEGIN SELECT RAISE(FAIL,'unexpected cache write'); END")
            scan(); self.assertEqual(e.status['read_cached'],4)

    def test_preparation_detects_changes_and_stop_preserves_collected_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inc=root/'incoming';inc.mkdir()
            for i in range(4): artwork(i).save(inc/f'{i}.png')
            e=Engine(root/'state'); original=crop_match.describe
            def changed(image):
                result=original(image); artwork(99).save(inc/'0.png');return result
            with patch('crop_match.describe',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'Changed during scan'):
                    e.prepare_image(inc/'0.png',stat_key(inc/'0.png'),None,None)
            status=e.set_status
            def stop_after_first(**kwargs):
                status(**kwargs)
                if kwargs.get('read_prepared',0)>0:e.cancel.set()
            with patch.object(e,'set_status',side_effect=stop_after_first):
                e.start([str(inc)],[],'broad',workers=1);e.thread.join(30)
            self.assertIn('Cancelled',e.status['phase'])
            with e.db() as db: count=db.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
            self.assertGreater(count,0)
            e.start([str(inc)],[],'broad',workers=2);e.thread.join(30)
            self.assertEqual(e.status['phase'],'Scan complete',e.status)
            self.assertGreaterEqual(e.status['read_cached'],count)

if __name__=='__main__':unittest.main()
