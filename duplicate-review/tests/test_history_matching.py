"""Compare targeted history results with the original manual-review matcher."""
import sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import ImageOps
from engine import Engine,sha256
from bulk.workbench import Workbench
from test_engine import artwork


class HistoryMatchingTests(unittest.TestCase):
    def test_original_matcher_parity_cache_and_no_review_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);images=root/'collection';images.mkdir()
            live=images/'Post 10';live.mkdir()
            source=artwork();source.save(live/'original.png')
            artwork(765).save(live/'unrelated.png')
            quarantine=images/'_Duplicate_Review_Quarantine'/'batch'/'Post 20';quarantine.mkdir(parents=True)
            crop=source.crop((60,100,600,800));crop.save(quarantine/'crop.jpg',quality=78)
            ImageOps.mirror(crop).save(quarantine/'mirror.jpg')
            # Same bytes from another post must retain both locations.
            qcopy=images/'_Duplicate_Review_Quarantine'/'other'/'Post 30'/'copy.jpg';qcopy.parent.mkdir(parents=True);qcopy.write_bytes((quarantine/'crop.jpg').read_bytes())
            # A trusted exact copy should not enter the targeted review queue.
            (quarantine/'exact.png').write_bytes((live/'original.png').read_bytes())
            missing=quarantine/'no-match.png';artwork(999).save(missing)
            engine=Engine(root/'state');engine.start([str(live)],[],'balanced');engine.thread.join(30)
            with engine.db() as db:
                before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in ('files','pairs','keeps','ignored','moves','separations')}
            work=Workbench(engine)
            baseline=Engine(root/'baseline')
            paths=sorted(live.glob('*'))+[quarantine/'crop.jpg',quarantine/'mirror.jpg',missing]
            records=baseline.read_records([(p,False,images) for p in paths],{'workers':1},None,{})
            targets={sha256(p) for p in paths if p.parent==quarantine}
            keeper=sha256(live/'original.png');unrelated=sha256(live/'unrelated.png')
            for mode in ('strict','balanced','broad'):
                with baseline.db() as db:db.execute('DELETE FROM pairs')
                baseline.match(records,mode);baseline.match_aligned(records,mode,1)
                expected={sha:set() for sha in targets}
                by_id={r['id']:r['sha'] for r in records}
                with baseline.db() as db:
                    for row in db.execute('SELECT a,b FROM pairs'):
                        a,b=by_id[row['a']],by_id[row['b']]
                        if a in targets and b not in targets:expected[a].add(b)
                        if b in targets and a not in targets:expected[b].add(a)
                with patch.object(work,'recover_visual_aliases',return_value=0):
                    work.start({'roots':[str(images)],'limit':0,'duplicate_mode':mode,'workers':1},inventory_only=True);work.thread.join(30)
                self.assertFalse(work.current['running']);self.assertNotIn('error',work.current,work.current.get('error'))
                self.assertEqual(work.current['issues'],[])
                for target in targets:
                    data=work.origin_audit(target=target)
                    self.assertTrue(data['matching_ready'])
                    self.assertEqual({r['id'] for r in data['candidates']},expected[target],mode)
                    self.assertNotIn(unrelated,{r['id'] for r in data['candidates']})
                data=work.origin_audit(target=sha256(quarantine/'crop.jpg'))
                self.assertEqual(data['copy_count'],2);self.assertEqual({o['post_id'] for o in data['origins']},{'20','30'})
                self.assertEqual(data['total_files'],4)  # 2 crop files + mirror + no match; exact excluded
                self.assertEqual({r['id'] for r in data['candidates']},{keeper})
                with engine.db() as db:
                    after={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in before}
                self.assertEqual(before,after)
            # Restart and repeat: analysis/task cache hits; no fingerprint work.
            work=Workbench(engine)
            with patch.object(work,'recover_visual_aliases',return_value=0),patch('crop_match.describe',side_effect=AssertionError('analysis cache missed')),patch('crop_match.verify',side_effect=AssertionError('comparison cache missed')):
                work.start({'roots':[str(images)],'duplicate_mode':'broad','workers':1},inventory_only=True);work.thread.join(30)
            self.assertNotIn('error',work.current);self.assertEqual(work.current['issues'],[])
            self.assertGreater(work.current['cached_tasks'],0)
            # Missing candidates are still unresolved, not discarded or padded.
            empty=work.origin_audit(target=sha256(missing));self.assertEqual(empty['candidates'],[]);self.assertEqual(empty['review_status'],'pending')
            data=work.origin_audit(target=sha256(quarantine/'crop.jpg'))
            work.confirm_origin({'job':work.current['id'],'target':data['image']['id'],'keeper':keeper})
            self.assertEqual({o['post_id'] for o in work.current['source_catalog'][keeper]['origins']},{'10','20','30'})
            self.assertTrue(qcopy.exists());work.undo_origin({'job':work.current['id']})
            self.assertEqual(work.origin_audit(target=data['digest'])['copy_count'],2)

if __name__=='__main__':unittest.main()
