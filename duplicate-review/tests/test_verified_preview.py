"""Focused approval-boundary regression tests for same-photo previews."""
import unittest
from pathlib import Path
from unittest.mock import patch
import test_verified_copies
from test_engine import artwork
from PIL import Image

class VerifiedPreview(unittest.TestCase):
    setUp = test_verified_copies.VerifiedCopies.setUp
    tearDown = test_verified_copies.VerifiedCopies.tearDown
    scan = test_verified_copies.VerifiedCopies.scan

    def prepare_preview(self):
        image = artwork()
        image.save(self.incoming/'full.jpg', quality=96)
        image.resize((320,420), Image.Resampling.LANCZOS).save(self.incoming/'small.jpg', quality=85)
        image.save(self.incoming/'copy.jpg', quality=80)
        self.scan()
        files = self.engine.groups(self.engine.groups()['groups'][0]['id'])['files']
        expected = self.engine._verified_group(files,set(),set(),'all')
        self.engine.start_verified(self.engine.revision, preview=True)
        self.engine.thread.join(30)
        self.assertFalse(self.engine.status['running'])
        plan = self.engine.verified_preview()
        self.assertEqual(len(plan['moves']),2)
        self.assertEqual({(m['target']['id'],m['keeper']['id'],m['proof']) for m in expected},
                         {(m['target']['id'],m['keeper']['id'],m['proof']) for m in plan['moves']})
        self.assertEqual(self.engine.view()['stats']['moved'],0)
        self.assertTrue(all(Path(m[r]['path']).is_file() for m in plan['moves'] for r in ('target','keeper')))
        self.assertEqual(self.engine.view()['verified_preview']['token'],plan['token'])
        return plan

    def test_preview_subset_apply_and_undo(self):
        plan=self.prepare_preview();chosen,excluded=plan['moves']
        for targets in ([],[999999],[str(chosen['target']['id'])]):
            with self.assertRaises(ValueError):self.engine.apply_verified_preview(plan['token'],targets)
        with self.assertRaises(ValueError):self.engine.apply_verified_preview('stale',[chosen['target']['id']])
        self.engine.apply_verified_preview(plan['token'],[chosen['target']['id']]);self.engine.thread.join(30)
        self.assertFalse(Path(chosen['target']['path']).exists())
        self.assertTrue(Path(excluded['target']['path']).exists())
        self.assertTrue(Path(chosen['keeper']['path']).exists())
        self.assertEqual(self.engine.view()['stats']['moved'],1)
        self.assertIsNone(self.engine.view()['verified_preview'])
        with self.assertRaises(ValueError):self.engine.apply_verified_preview(plan['token'],[excluded['target']['id']])
        self.engine.undo();self.engine.thread.join(30)
        self.assertTrue(Path(chosen['target']['path']).exists())

    def test_changed_review_or_file_cannot_apply_old_approval(self):
        plan=self.prepare_preview();self.engine.invalidate_groups()
        with self.assertRaises(ValueError):self.engine.apply_verified_preview(plan['token'],[plan['moves'][0]['target']['id']])
        self.engine.start_verified(self.engine.revision,preview=True);self.engine.thread.join(30)
        plan=self.engine.verified_preview();move=plan['moves'][0]
        Path(move['target']['path']).write_bytes(b'changed after preview')
        self.engine.apply_verified_preview(plan['token'],[move['target']['id']]);self.engine.thread.join(30)
        self.assertEqual(self.engine.view()['stats']['moved'],0)
        self.assertTrue(Path(move['target']['path']).exists())
        self.assertIn('skipped',self.engine.status['phase'])

    def test_cancelled_verification_has_no_plan_or_moves(self):
        self.prepare_preview()
        def cancel(*args):
            self.engine.cancel.set()
            return []
        with patch.object(self.engine,'_verified_group',side_effect=cancel):
            self.engine.start_verified(self.engine.revision,preview=True);self.engine.thread.join(30)
        self.assertIsNone(self.engine.view()['verified_preview'])
        self.assertEqual(self.engine.view()['stats']['moved'],0)
        with self.assertRaises(ValueError):self.engine.verified_preview()

if __name__=='__main__':unittest.main()
