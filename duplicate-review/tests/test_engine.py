import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
import numpy as np
from engine import Engine, QUARANTINE, sha256


def artwork(seed=1):
    rng = np.random.default_rng(seed)
    im = Image.new('RGB', (640, 840), (28, 45, 70))
    draw = ImageDraw.Draw(im)
    for _ in range(75):
        x, y = rng.integers(-60, 580), rng.integers(-60, 780)
        w, h = rng.integers(30, 250), rng.integers(30, 250)
        color = tuple(int(v) for v in rng.integers(20, 240, 3))
        draw.ellipse((int(x), int(y), int(x+w), int(y+h)), fill=color)
    draw.polygon([(0, 800), (320, 90), (640, 800)], fill=(60, 125, 180))
    draw.ellipse((210, 220, 430, 440), fill=(250, 195, 95))
    return im


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.incoming = self.base/'incoming'
        self.incoming.mkdir()
        self.reference = self.base/'reference'
        self.reference.mkdir()
        self.engine = Engine(self.base/'state')

    def tearDown(self):
        if self.engine.thread:
            self.engine.cancel.set()
            self.engine.thread.join(10)
        self.temp.cleanup()

    def scan(self, references=False, mode='balanced'):
        self.engine.start([str(self.incoming)], [str(self.reference)] if references else [], mode)
        self.engine.thread.join(20)
        self.assertFalse(self.engine.status['running'])
        self.assertEqual(self.engine.status['phase'], 'Scan complete', self.engine.status)
        return self.engine.view()

    def test_exact_resized_recompressed_watermark_and_unrelated(self):
        image = artwork()
        image.save(self.incoming/'original.jpg', quality=96)
        shutil.copy2(self.incoming/'original.jpg', self.incoming/'exact.jpg')
        image.resize((320, 420)).save(self.incoming/'small.jpg', quality=68)
        mark = image.copy()
        ImageDraw.Draw(mark).rectangle((490, 755, 635, 835), fill='white')
        ImageDraw.Draw(mark).text((500, 780), 'WATERMARK', fill='black')
        mark.save(self.incoming/'watermarked.jpg', quality=85)
        artwork(65).save(self.incoming/'different.jpg')
        view = self.scan()
        pairs = view['pairs']
        self.assertTrue(any(p['kind'] == 'Exact bytes' for p in pairs))
        found = {Path(p[s]['path']).name for p in pairs for s in ('left','right')}
        self.assertTrue({'small.jpg', 'watermarked.jpg'}.issubset(found), found)
        self.assertNotIn('different.jpg', found)
        self.assertTrue(any('corner' in p['kind'] for p in pairs), [p['kind'] for p in pairs])
        self.assertEqual(view['stats']['total'], 5)
        # Unchanged second scan must reuse all cached fingerprints.
        import unittest.mock as mock
        with mock.patch('engine.fingerprint', side_effect=AssertionError('Cache miss')):
            second = self.scan()
        self.assertEqual(second['count'], view['count'])
        self.assertEqual(second['errors'], [])

    def test_reference_protection_keep_both_and_persistence(self):
        artwork().save(self.reference/'known.jpg')
        shutil.copy2(self.reference/'known.jpg', self.incoming/'download.jpg')
        pair = self.scan(True)['pairs'][0]
        self.assertTrue(pair['left']['reference'])
        with self.assertRaisesRegex(ValueError, 'protected'):
            self.engine.review(pair['id'], 'left')
        self.engine.review(pair['id'], 'keep')
        self.assertEqual(self.scan(True)['count'], 0)
        self.engine = Engine(self.base/'state')
        self.assertEqual(self.engine.view()['count'], 0)
        self.engine.reset_dismissed()
        self.assertEqual(self.scan(True)['count'], 1)
        self.assertTrue((self.reference/'known.jpg').exists())

    def test_move_exact_anchor_still_finds_remaining_duplicates_and_undo(self):
        image = artwork()
        image.save(self.incoming/'a.jpg')
        shutil.copy2(self.incoming/'a.jpg', self.incoming/'b.jpg')
        shutil.copy2(self.incoming/'a.jpg', self.incoming/'c.jpg')
        image.resize((320, 420)).save(self.incoming/'small.jpg')
        view = self.scan()
        pair = next(p for p in view['pairs'] if p['kind'] == 'Exact bytes')
        target = Path(pair['left']['path'])
        original_hash = sha256(target)
        self.engine.review(pair['id'], 'left')
        self.assertFalse(target.exists())
        remains = self.engine.view()['pairs']
        self.assertTrue(any(p['kind'] == 'Exact bytes' for p in remains))
        self.assertTrue(any(p['kind'] != 'Exact bytes' for p in remains))
        history = self.engine.history()
        self.assertEqual(sha256(Path(history[0]['dst'])), original_hash)
        self.engine = Engine(self.base/'state')
        self.engine.undo()
        self.assertEqual(sha256(target), original_hash)
        self.assertGreater(self.engine.view()['count'], 0)

    def test_changed_files_and_occupied_restore_are_blocked(self):
        artwork().save(self.incoming/'a.jpg')
        shutil.copy2(self.incoming/'a.jpg', self.incoming/'b.jpg')
        pair = self.scan()['pairs'][0]
        path = Path(pair['right']['path'])
        artwork(3).save(path)
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.engine.review(pair['id'], 'right')
        shutil.copy2(self.incoming/'a.jpg', path)
        pair = self.scan()['pairs'][0]
        self.engine.review(pair['id'], 'right')
        artwork(6).save(path)
        occupant_hash = sha256(path)
        with self.assertRaisesRegex(ValueError, 'occupied'):
            self.engine.undo()
        self.assertEqual(sha256(path), occupant_hash)
        self.assertEqual(self.engine.history()[0]['state'], 'moved')

    def test_skips_corrupt_animated_symlink_and_quarantine(self):
        artwork().save(self.incoming/'valid.jpg')
        (self.incoming/'broken.jpg').write_bytes(b'not an image')
        Image.new('RGB',(30,30),'red').save(self.incoming/'motion.gif', save_all=True,
            append_images=[Image.new('RGB',(30,30),'blue')], duration=200, loop=0)
        q=self.incoming/QUARANTINE
        q.mkdir()
        artwork().save(q/'ignored.jpg')
        if os.name != 'nt':
            (self.incoming/'link.jpg').symlink_to(self.incoming/'valid.jpg')
        view=self.scan()
        self.assertEqual(view['stats']['total'],1)
        self.assertEqual(len(view['errors']),2)

    def test_crash_journal_recovers_pending_move(self):
        artwork().save(self.incoming/'a.jpg')
        shutil.copy2(self.incoming/'a.jpg',self.incoming/'b.jpg')
        pair=self.scan()['pairs'][0]
        path=Path(pair['right']['path'])
        dest=self.incoming/QUARANTINE/'simulated-crash'/'b.jpg'
        dest.parent.mkdir(parents=True)
        with self.engine.db() as db:
            db.execute('INSERT INTO moves(id,src,dst,sha,state,created) VALUES (?,?,?,?,?,?)', ('crash',str(path),str(dest),sha256(path),'pending',123))
        path.rename(dest)
        self.engine=Engine(self.base/'state')
        self.assertEqual(self.engine.history()[0]['state'],'moved')
        self.assertEqual(self.engine.view()['count'],0)
        self.engine.undo()
        self.assertTrue(path.exists())

    def test_reference_nested_in_incoming_and_overlap(self):
        nested=self.incoming/'protected'
        nested.mkdir()
        artwork().save(nested/'known.jpg')
        shutil.copy2(nested/'known.jpg',self.incoming/'new.jpg')
        self.engine.start([str(self.incoming)],[str(nested)],'balanced')
        self.engine.thread.join(20)
        pair=self.engine.view()['pairs'][0]
        self.assertTrue(pair['left']['reference'])
        with self.assertRaisesRegex(ValueError, 'inside a reference'):
            self.engine.start([str(nested)],[str(self.incoming)],'balanced')

    def test_bulk_exact_preserves_reference_and_visual_then_undo_entire_batch(self):
        image=artwork()
        image.save(self.reference/'known.jpg')
        for name in ['copy-a.jpg','copy-b.jpg','copy-c.jpg']:
            shutil.copy2(self.reference/'known.jpg', self.incoming/name)
        image.resize((320,420)).save(self.incoming/'similar.jpg')
        self.scan(True)
        preview=self.engine.preview_exact()
        self.assertEqual(preview['count'],3)
        self.assertTrue(all(p['keep']==str(self.reference/'known.jpg') for p in preview['moves']))
        self.engine.start_exact(preview['token'])
        self.engine.thread.join(20)
        self.assertEqual(self.engine.view()['stats']['moved'],3)
        self.assertTrue((self.incoming/'similar.jpg').exists())
        self.assertTrue((self.reference/'known.jpg').exists())
        self.assertTrue(all(p['kind']!='Exact bytes' for p in self.engine.view()['pairs']))
        self.engine=Engine(self.base/'state')
        self.engine.undo()
        self.engine.thread.join(20)
        self.assertEqual(self.engine.view()['stats']['moved'],0)
        self.assertTrue(all((self.incoming/name).exists() for name in ['copy-a.jpg','copy-b.jpg','copy-c.jpg']))

    def test_bulk_folder_priority_scope_and_keep_both(self):
        preferred=self.base/'preferred'
        preferred.mkdir()
        artwork().save(preferred/'z.jpg')
        shutil.copy2(preferred/'z.jpg',self.incoming/'a.jpg')
        shutil.copy2(preferred/'z.jpg',self.incoming/'b.jpg')
        self.engine.start([str(preferred),str(self.incoming)],[],'balanced')
        self.engine.thread.join(20)
        plan=self.engine.preview_exact()
        self.assertEqual(plan['count'],2)
        self.assertTrue(all(m['keep']==str(preferred/'z.jpg') for m in plan['moves']))
        local=self.engine.preview_exact('folder')
        self.assertEqual(local['count'],1)
        self.assertEqual(local['moves'][0]['keep'],str(self.incoming/'a.jpg'))
        pair=self.engine.view()['pairs'][0]
        self.engine.review(pair['id'],'keep')
        with self.assertRaisesRegex(ValueError,'Preview|preview'):
            self.engine.start_exact(local['token'])
        self.assertEqual(self.engine.preview_exact()['count'],0)
        self.assertEqual(self.engine.preview_exact()['skipped_groups'],1)

    def test_bulk_rehashes_and_skips_changed_keeper(self):
        artwork().save(self.reference/'known.jpg')
        shutil.copy2(self.reference/'known.jpg',self.incoming/'a.jpg')
        self.scan(True)
        plan=self.engine.preview_exact()
        artwork(77).save(self.reference/'known.jpg')
        self.engine.start_exact(plan['token'])
        self.engine.thread.join(20)
        self.assertTrue((self.incoming/'a.jpg').exists())
        self.assertEqual(self.engine.view()['stats']['moved'],0)
        self.assertIn('1 skipped',self.engine.status['phase'])

    def test_bulk_undo_leaves_occupied_file_intact_and_restores_other_copies(self):
        artwork().save(self.reference/'known.jpg')
        for name in ['a.jpg','b.jpg']:
            shutil.copy2(self.reference/'known.jpg',self.incoming/name)
        self.scan(True)
        self.engine.start_exact(self.engine.preview_exact()['token'])
        self.engine.thread.join(20)
        artwork(90).save(self.incoming/'a.jpg')
        digest=sha256(self.incoming/'a.jpg')
        self.engine.undo()
        self.engine.thread.join(20)
        self.assertEqual(sha256(self.incoming/'a.jpg'),digest)
        self.assertTrue((self.incoming/'b.jpg').exists())
        self.assertEqual(self.engine.view()['stats']['moved'],1)
        self.assertIn('1 could not be restored',self.engine.status['phase'])


if __name__ == '__main__':
    unittest.main()
