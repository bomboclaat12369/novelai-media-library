import sys, tempfile, unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from search_index import SearchIndexes
from engine import Engine
import crop_match
from test_engine import artwork


class ParallelSearchTests(unittest.TestCase):
    def test_clones_return_identical_neighbors_under_concurrent_search(self):
        rng = np.random.default_rng(61)
        data = rng.uniform(0, 255, (4000, 128)).astype(np.float32)
        queries = [np.ascontiguousarray(data[i:i+100]+rng.normal(0, 2, (100,128)), dtype=np.float32) for i in range(0, 800, 100)]
        indexes = SearchIndexes(data, 4)
        try:
            self.assertEqual(len(indexes.indexes), 4)
            expected = [indexes.indexes[0].knnSearch(q, 12, params={'checks':96}) for q in queries]
            def search(q):
                with indexes.acquire() as index:
                    return index.knnSearch(q, 12, params={'checks':96})
            with ThreadPoolExecutor(max_workers=4) as pool:
                actual = list(pool.map(search, queries))
            for (ei, ed), (ai, ad) in zip(expected, actual):
                np.testing.assert_array_equal(ai, ei)
                np.testing.assert_array_equal(ad, ed)
        finally:
            indexes.close()

    def test_stop_commits_completed_tasks_before_half_second_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            e = Engine(Path(d)); feature = crop_match.describe(artwork())
            records = [dict(id=i+1, path=f'/fixture/{i:04}.png', sha=str(i), pixel=str(i), reference=False, features=feature) for i in range(12)]
            original = e.set_status
            def progress(**kwargs):
                original(**kwargs)
                if e.status['phase'] == 'Comparing crops, rotations and mirrors' and kwargs.get('done', 0) > 0:
                    e.cancel.set()
            with patch.object(e, 'set_status', side_effect=progress), patch('crop_match.candidates', return_value=[]):
                with self.assertRaises(InterruptedError): e.match_aligned(records, 'broad', workers=4)
            with e.db() as db: saved = db.execute('SELECT COUNT(*) FROM aligned_tasks').fetchone()[0]
            self.assertGreater(saved, 0)
            e.cancel.clear()
            with patch('crop_match.candidates', return_value=[]): e.match_aligned(records, 'broad', workers=24)
            self.assertGreaterEqual(e.status['cached_tasks'], saved)
            self.assertEqual(e.status['done'], 11)
            self.assertLessEqual(e.status['workers'], 24)

if __name__ == '__main__': unittest.main()
