"""Focused safeguards for opt-in same-photo quarantine, not broad recall tests."""
import sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1])]
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from test_engine import artwork
from engine import Engine
import same_photo


class VerifiedCopies(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.incoming = self.base/'incoming'; self.incoming.mkdir()
        self.reference = self.base/'reference'; self.reference.mkdir()
        self.engine = Engine(self.base/'state')

    def tearDown(self):
        if self.engine.thread:
            self.engine.cancel.set(); self.engine.thread.join(30)
        self.temp.cleanup()

    def scan(self, reference=False):
        self.engine.start([str(self.incoming)], [str(self.reference)] if reference else [], 'broad', workers=2)
        self.engine.thread.join(30)
        self.assertFalse(self.engine.status['running'])
        self.assertEqual(self.engine.status['phase'], 'Scan complete')

    def run_auto(self, scope='all'):
        self.engine.start_verified(self.engine.revision, scope)
        self.engine.thread.join(30)
        self.assertFalse(self.engine.status['running'])
        self.assertNotIn('failed', self.engine.status['phase'])

    def test_resizes_recompression_crop_and_local_pose_difference(self):
        image = artwork()
        image.save(self.incoming/'full.jpg', quality=96)
        image.resize((320, 420), Image.Resampling.LANCZOS).save(self.incoming/'small.jpg', quality=85)
        image.save(self.incoming/'recompressed.jpg', quality=80)
        image.crop((60, 80, 580, 780)).save(self.incoming/'crop.jpg', quality=92)
        changed = image.copy()
        ImageDraw.Draw(changed).ellipse((290, 300, 315, 315), fill=(100, 80, 70))
        changed.save(self.incoming/'pose.jpg', quality=96)
        full = same_photo.prepare(self.incoming/'full.jpg')
        for name in ('small', 'recompressed', 'crop'):
            self.assertTrue(same_photo.verify(same_photo.prepare(self.incoming/(name+'.jpg')), full), name)
        self.assertFalse(same_photo.verify(same_photo.prepare(self.incoming/'pose.jpg'), full))
        self.assertFalse(same_photo.verify(full, same_photo.prepare(self.incoming/'crop.jpg')))
        # Two overlapping crops each contain unique content: retain both.
        image.crop((0, 0, 550, 840)).save(self.incoming/'left.png')
        image.crop((90, 0, 640, 840)).save(self.incoming/'right.png')
        self.assertFalse(same_photo.verify(same_photo.prepare(self.incoming/'left.png'), same_photo.prepare(self.incoming/'right.png')))

    def test_mixed_group_highest_mp_tie_order_direct_keeper_undo_restart(self):
        image = artwork()
        image.save(self.incoming/'a-full.jpg', quality=96)
        shutil.copyfile(self.incoming/'a-full.jpg', self.incoming/'z-tie.jpg')
        image.resize((320, 420), Image.Resampling.LANCZOS).save(self.incoming/'small.jpg', quality=85)
        changed = image.copy(); ImageDraw.Draw(changed).rectangle((290, 300, 315, 320), fill='black')
        changed.save(self.incoming/'b-pose.jpg', quality=96)
        changed.resize((320, 420), Image.Resampling.LANCZOS).save(self.incoming/'pose-small.jpg', quality=85)
        self.scan()
        # Deliberately force a mixed connected group, regardless of scan thresholds.
        with self.engine.db() as db:
            files = [dict(r) for r in db.execute('SELECT * FROM files')]
            for r in files[1:]: self.engine.add_pair(db, files[0], r, 'Visual match', 99, set())
        self.engine.invalidate_groups()
        self.run_auto()
        self.assertEqual({p.name for p in self.incoming.iterdir() if p.is_file()}, {'a-full.jpg', 'b-pose.jpg'})
        self.assertEqual(self.engine.view()['stats']['moved'], 3)
        self.assertEqual(len({h['batch'] for h in self.engine.history()}), 1)
        self.engine = Engine(self.base/'state'); self.engine.undo(); self.engine.thread.join(30)
        self.assertEqual(self.engine.view()['stats']['moved'], 0)
        self.assertTrue(all(Path(r['path']).is_file() for r in files))
        # Successful visual verifications are cached by contents and verifier version.
        with patch('same_photo.verify', side_effect=AssertionError('Unexpected repeated verification')):
            self.run_auto()
        self.assertEqual(self.engine.view()['stats']['moved'], 3)

    def test_protected_reference_upgrade_manual_keep_and_folder_scope(self):
        image = artwork()
        image.save(self.reference/'library.jpg', quality=96)
        image.resize((320, 420), Image.Resampling.LANCZOS).save(self.incoming/'small.jpg', quality=85)
        image.resize((1280, 1680), Image.Resampling.LANCZOS).save(self.incoming/'upgrade.jpg', quality=96)
        self.scan(True)
        self.run_auto('folder')
        # Same incoming folder may consolidate against the incoming upgrade;
        # a smaller protected copy can never discard the higher-MP incoming image.
        self.assertTrue((self.incoming/'upgrade.jpg').exists())
        self.assertTrue((self.reference/'library.jpg').exists())
        if not (self.incoming/'small.jpg').exists():
            self.engine.undo(); self.engine.thread.join(30)
        g = self.engine.groups()['groups'][0]
        small = next(r for r in self.engine.groups(g['id'])['files'] if Path(r['path']).name=='small.jpg')
        self.engine.mark_keep(g['id'], small['id'], True, self.engine.revision)
        self.run_auto()
        self.assertTrue((self.incoming/'small.jpg').exists())
        self.assertTrue((self.incoming/'upgrade.jpg').exists())

    def test_library_keeper_and_scope_use_live_validation(self):
        image = artwork(); image.save(self.reference/'library.jpg', quality=96)
        image.resize((320, 420), Image.Resampling.LANCZOS).save(self.incoming/'copy.jpg', quality=85)
        self.scan(True)
        self.run_auto('folder')
        self.assertEqual(self.engine.view()['stats']['moved'], 0)
        with self.engine.db() as db:
            record = dict(db.execute('SELECT * FROM files WHERE reference=1').fetchone())
            db.execute('UPDATE files SET library=? WHERE id=?',
                       (json.dumps({'id':'imported', 'library_id':'library', 'sets':[]}), record['id']))
        self.engine.invalidate_groups()
        with patch.object(self.engine.library, 'item', return_value={'sha':record['sha'], 'path':record['path']}) as live:
            self.run_auto()
            self.assertTrue(live.called)
        self.assertEqual(self.engine.view()['stats']['moved'], 1)
        self.assertTrue(Path(record['path']).exists())
        self.engine.undo(); self.engine.thread.join(30)
        with patch.object(self.engine.library, 'item', return_value={'sha':'changed', 'path':record['path']}):
            self.run_auto()
        self.assertEqual(self.engine.view()['stats']['moved'], 0)
        self.assertTrue((self.incoming/'copy.jpg').exists())

    def test_split_decisions_changed_files_stop_and_library_mode(self):
        image = artwork(); image.save(self.incoming/'a.jpg', quality=96)
        image.resize((320, 420), Image.Resampling.LANCZOS).save(self.incoming/'b.jpg', quality=85)
        self.scan()
        g = self.engine.groups()['groups'][0]
        self.engine.dismiss_group(g['id'], self.engine.revision)
        self.run_auto(); self.assertEqual(self.engine.view()['stats']['moved'], 0)
        self.engine.reset_dismissed()
        # A separation must also win if an indirect edge reconnects a group.
        with self.engine.db() as db:
            files = [dict(r) for r in db.execute('SELECT * FROM files')]
            db.execute('INSERT INTO separations VALUES (?,?)', tuple(sorted(r['sha'] for r in files)))
        self.run_auto(); self.assertEqual(self.engine.view()['stats']['moved'], 0)
        with self.engine.db() as db: db.execute('DELETE FROM separations')
        self.engine.cancel.set()
        self.engine._run_verified([files], set(), set(), 'all', 1)
        self.assertEqual(self.engine.view()['stats']['moved'], 0)
        self.assertIn('stopped', self.engine.status['phase'])
        (self.incoming/'b.jpg').write_bytes(b'changed since scan')
        self.run_auto(); self.assertEqual(self.engine.view()['stats']['moved'], 0)
        self.assertTrue(self.engine.view()['errors'])
        with self.engine.db() as db:
            config = self.engine.config(); config['scan_kind'] = 'library'
            db.execute("UPDATE settings SET value=? WHERE key='config'", (json.dumps(config),))
        with self.assertRaisesRegex(ValueError, 'Library-only'):
            self.engine.start_verified(self.engine.revision)

if __name__ == '__main__': unittest.main()
