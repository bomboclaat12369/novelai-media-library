import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import Engine
from test_engine import artwork
import crop_match
import numpy as np

class SpeedTests(unittest.TestCase):
    def test_vote_vectorization_preserves_candidate_set(self):
        rng=np.random.default_rng(77)
        owners=rng.integers(0,17,120)
        ids=rng.integers(0,120,(45,12));dist=rng.integers(0,90000,(45,12))
        class Index:
            def knnSearch(self,*args,**kwargs):return ids,dist
        votes={}
        for row,ds in zip(ids,dist):
            for owner in set(int(owners[i]) for i,d in zip(row,ds) if i>=0 and d<260**2):
                votes[owner]=votes.get(owner,0)+1
        self.assertEqual(set(crop_match.candidates(np.ones((45,128)),Index(),owners)),{i for i,n in votes.items() if n>=6})
    def test_persistent_cache_reapplies_current_review_decisions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inc=root/'incoming';inc.mkdir()
            im=artwork();im.save(inc/'a.png');im.crop((40,70,610,800)).save(inc/'b.png')
            e=Engine(root/'state')
            def scan():
                e.start([str(inc)],[],'broad',workers=4);e.thread.join(15)
                self.assertFalse(e.status['running']);self.assertEqual(e.status['phase'],'Scan complete')
                self.assertEqual(e.status['done'],e.status['total'])
            scan();self.assertEqual(e.view()['count'],1)
            pair=e.view()['pairs'][0];e.review(pair['id'],'keep')
            e=Engine(root/'state')
            with patch('crop_match.verify',side_effect=AssertionError('cached verification repeated')):
                scan();self.assertEqual(e.view()['count'],0);self.assertEqual(e.status['cached_tasks'],1)
                e.reset_dismissed();scan();self.assertEqual(e.view()['count'],1)
            artwork(99).save(inc/'b.png');scan();self.assertEqual(e.status['cached_tasks'],0)

    def test_multiple_blocks_count_and_reuse_completed_tasks(self):
        with tempfile.TemporaryDirectory() as d:
            e=Engine(Path(d));feature=crop_match.describe(artwork())
            records=[dict(id=i+1,path=f'/fixture/{i:04}.png',sha=str(i),pixel=str(i),reference=False,features=feature) for i in range(258)]
            with patch('crop_match.candidates',side_effect=lambda query,index,owners:[int(owners[0])]), patch('crop_match.verify',return_value=None):
                e.match_aligned(records,'broad',workers=4)
            self.assertEqual(e.status['done'],258);self.assertEqual(e.status['total'],258)
            with patch('crop_match.candidates',side_effect=AssertionError('completed search repeated')):
                e.match_aligned(records,'broad',workers=4)
            self.assertEqual(e.status['cached_tasks'],258)

if __name__=='__main__':unittest.main()
