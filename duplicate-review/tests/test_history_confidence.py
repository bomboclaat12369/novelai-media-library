import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageCms, ImageDraw
import same_photo
from bulk import history_confidence as high
from bulk.workbench import Workbench
from test_history_verify import fixture
from test_engine import artwork


class ConfidenceTests(unittest.TestCase):
    def test_profile_and_resize_variants_but_not_changed_pose_or_other_photo(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original=artwork()
            profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
            original.save(root/'large.jpg',quality=96,icc_profile=profile)
            original.resize((320,420)).save(root/'small.jpg',quality=85)
            changed=original.copy();ImageDraw.Draw(changed).ellipse((290,300,315,315),fill=(100,80,70))
            changed.save(root/'pose.jpg',quality=96)
            artwork(999).save(root/'different.png')
            self.assertFalse(same_photo.verify(same_photo.prepare(root/'small.jpg'),same_photo.prepare(root/'large.jpg')))
            keeper=high.prepare(root/'large.jpg')
            self.assertTrue(high.verify(high.prepare(root/'small.jpg'),keeper))
            self.assertFalse(high.verify(high.prepare(root/'pose.jpg'),keeper))
            self.assertFalse(high.verify(high.prepare(root/'different.png'),keeper))

    def test_ambiguity_low_scores_invalid_scores_and_separations(self):
        catalog={'a':{'sha':'a'},'b':{'sha':'b'},'same-a':{'sha':'a'},'q':{'sha':'q','quarantine_only':True}}
        a={'id':'a','score':100};b={'id':'b','score':99.9}
        self.assertEqual(high.candidates([a],catalog,'target',set()),[a])
        self.assertEqual(high.candidates([a,b],catalog,'target',set()),[])
        self.assertEqual(high.candidates([a,{'id':'same-a','score':100}],catalog,'target',set()),[a])
        for score in (98.9,float('nan'),101):
            self.assertEqual(high.candidates([{'id':'a','score':score}],catalog,'target',set()),[])
        self.assertEqual(high.candidates([a],catalog,'target',{('a','target')}),[])
        self.assertEqual(high.candidates([{'id':'q','score':100}],catalog,'target',set()),[])

    def test_opt_in_cache_isolation_saved_inventory_and_undo_after_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,work,keeper,target,duplicate,bad,none=fixture(temp)
            cat=work.current['source_catalog'];digest=cat[target]['sha']
            work.current['history_matches'][digest][0]['score']=100
            with work.db() as db:
                db.execute('INSERT INTO aliases VALUES (?,?,?,?)',(digest,cat[keeper]['sha'],same_photo.VERSION,0))
            before=copy.deepcopy(cat);work.persist()
            with patch.object(work,'inventory',side_effect=AssertionError('No inventory')):
                work.verify_history({'job':work.current['id'],'policy':'high_confidence'});work.thread.join(30)
            self.assertEqual(work.current['phase'],'High-confidence recovery complete')
            self.assertNotIn(target,cat);self.assertIn(bad,cat)
            self.assertEqual(cat[keeper]['copies'][0]['proof'],'high-confidence history connection')
            with work.db() as db:
                self.assertEqual(db.execute('SELECT accepted FROM aliases WHERE recipe=?',(same_photo.VERSION,)).fetchone()[0],0)
                self.assertEqual(db.execute('SELECT accepted FROM aliases WHERE recipe=?',(high.VERSION,)).fetchone()[0],1)
            reopened=Workbench(engine);self.assertEqual(reopened.origin_audit()['auto_policy'],'high_confidence')
            reopened.undo_origin({'job':reopened.current['id']})
            self.assertEqual(reopened.current['source_catalog'],before)
            with work.db() as db:
                self.assertEqual(db.execute('SELECT accepted FROM aliases WHERE recipe=?',(same_photo.VERSION,)).fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM aliases WHERE recipe=?',(high.VERSION,)).fetchone()[0],0)
            # Omitting policy always invokes strict verification, even after high confidence was used.
            with patch('bulk.history_confidence.verify',side_effect=AssertionError('Must stay opt-in')):
                reopened.verify_history({'job':reopened.current['id']});reopened.thread.join(30)
            self.assertEqual(reopened.current['history_verification']['policy'],'strict')
            self.assertIn(target,reopened.current['source_catalog'])

    def test_high_confidence_undo_preserves_earlier_strict_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,work,keeper,target,duplicate,bad,none=fixture(temp)
            cat=work.current['source_catalog'];digest=cat[target]['sha']
            original=copy.deepcopy(cat)
            work.current['history_matches'][digest]=[]
            # Exercise successive batch journals independently of image thresholds.
            with patch('same_photo.verify',return_value=True):
                work.verify_history({'job':work.current['id']});work.thread.join(30)
            strict_catalog=copy.deepcopy(cat);strict_undo=copy.deepcopy(work.current['origin_undo'])
            work.current['history_matches'][digest]=[{'id':keeper,'score':100}]
            work.verify_history({'job':work.current['id'],'policy':'high_confidence'});work.thread.join(30)
            self.assertNotIn(target,cat)
            work.undo_origin({'job':work.current['id']})
            self.assertEqual(work.current['source_catalog'],strict_catalog)
            self.assertEqual(work.current['origin_undo'],strict_undo)
            work.undo_origin({'job':work.current['id']})
            self.assertEqual(work.current['source_catalog'],original)

    def test_high_score_alone_cannot_link_and_ambiguous_pairs_are_not_decoded(self):
        with tempfile.TemporaryDirectory() as temp:
            engine,work,keeper,target,duplicate,bad,none=fixture(temp)
            cat=work.current['source_catalog']
            work.current['history_matches'][cat[target]['sha']]=[{'id':keeper,'score':100},{'id':'other','score':99.9}]
            cat['other']=dict(cat[keeper],id='other',sha='different-content')
            work.current['history_matches'][cat[bad]['sha']][0]['score']=100
            with patch('bulk.history_confidence.verify',wraps=high.verify) as verify:
                work.verify_history({'job':work.current['id'],'policy':'high_confidence'});work.thread.join(30)
                self.assertEqual(verify.call_count,1)
            self.assertEqual(work.current['inventory']['unlinked_quarantine'],4)

if __name__=='__main__':unittest.main()
