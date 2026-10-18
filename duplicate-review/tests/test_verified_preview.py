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

    def test_exact_families_and_visual_actions_are_separate(self):
        import shutil
        from PIL import PngImagePlugin
        image=artwork()
        image.save(self.incoming/'full.jpg',quality=96)
        shutil.copyfile(self.incoming/'full.jpg',self.incoming/'full-copy.jpg')
        small=image.resize((320,420),Image.Resampling.LANCZOS)
        small.save(self.incoming/'small.png',compress_level=0)
        info=PngImagePlugin.PngInfo();info.add_text('Comment','same pixels, different bytes')
        small.save(self.incoming/'small-metadata.png',compress_level=9,pnginfo=info)
        shutil.copyfile(self.incoming/'small.png',self.incoming/'small-copy.png')
        image.save(self.incoming/'recompressed.jpg',quality=80)
        self.scan()
        exact=self.engine.preview_exact('all',True)
        self.assertEqual(exact['count'],3)
        exact_targets={m['target'] for m in exact['moves']}
        self.engine.start_verified(self.engine.revision,preview=True);self.engine.thread.join(30)
        visual=self.engine.verified_preview()
        self.assertEqual(len(visual['moves']),1)
        self.assertEqual(Path(visual['moves'][0]['target']['path']).name,'recompressed.jpg')
        self.assertTrue(all(m['proof']=='same_photo' and m['target']['id'] not in exact_targets for m in visual['moves']))
        self.assertEqual(self.engine.view()['stats']['moved'],0)
        # Direct auto action must match the preview, with all exact families intact.
        self.engine.start_verified(self.engine.revision);self.engine.thread.join(30)
        self.assertFalse((self.incoming/'recompressed.jpg').exists())
        for filename in ('full.jpg','full-copy.jpg','small.png','small-metadata.png','small-copy.png'):
            self.assertTrue((self.incoming/filename).exists())
        exact=self.engine.preview_exact('all',True)
        self.assertEqual(exact['count'],3)
        self.engine.start_exact(exact['token']);self.engine.thread.join(30)
        # Once exact families are consolidated, the remaining small copy is visual-only.
        self.engine.start_verified(self.engine.revision,preview=True);self.engine.thread.join(30)
        plan=self.engine.verified_preview()
        self.assertEqual(len(plan['moves']),1)
        self.assertEqual(plan['moves'][0]['proof'],'same_photo')

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
