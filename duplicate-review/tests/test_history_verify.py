import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Engine, sha256, stat_key
from bulk.workbench import Workbench
from bulk.history_matching import RECIPE
from test_engine import artwork


def fixture(temp):
    root = Path(temp)
    engine = Engine(root/'state')
    work = Workbench(engine)
    catalog = {}
    def add(name, im, quarantined=False):
        path = root/name
        im.save(path, quality=96 if not quarantined else 92)
        digest = sha256(path)
        ident = ('q:'+name if quarantined else digest)
        source = {'key': 'post:'+name, 'kind': 'forum', 'label': name, 'path': str(path), 'quarantine': quarantined}
        catalog[ident] = {'id': ident, 'path': str(path), 'sha': digest, 'stamp': stat_key(path),
                         'sources': {source['key']: source}, 'origins': [source], 'copies': [], 'quarantine_only': quarantined}
        return ident
    original = artwork()
    keeper = add('keeper.jpg', original)
    target = add('crop.jpg', original.crop((60,80,580,780)), True)
    duplicate = add('crop-copy.jpg', original.crop((60,80,580,780)), True)
    bad = add('different.png', artwork(999), True)
    none = add('missing.png', artwork(765), True)
    work.current = {'id': 'saved-alice', 'config': {'roots': [str(root)], 'duplicate_mode': 'broad'},
                    'running': False, 'source_catalog': catalog, 'items': {}, 'proposals': [],
                    'inventory': {'unlinked_quarantine': 4}, 'inventory_complete': True,
                    'history_match_recipe': RECIPE,
                    'history_matches': {catalog[target]['sha']: [{'id': keeper, 'score': 0.1, 'kind': 'crop'}],
                                        catalog[bad]['sha']: [{'id': keeper, 'score': 99999, 'kind': 'visual'}]}, 'issues': []}
    work.persist()
    return engine, work, keeper, target, duplicate, bad, none


class SavedHistoryVerificationTests(unittest.TestCase):
    def run_saved(self, work):
        with patch.object(work, 'inventory', side_effect=AssertionError('No inventory')), \
             patch('bulk.history_matching.HistoryMatcher.run', side_effect=AssertionError('No matcher pass')), \
             patch.object(Engine, 'start', side_effect=AssertionError('No scan')):
            work.verify_history({'job': work.current['id']})
            work.thread.join(30)
        self.assertFalse(work.current['running'])
        self.assertEqual(work.current['phase'], 'Saved-match verification complete')

    def test_real_verifier_preserves_origins_rejects_high_score_and_batch_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, work, keeper, target, duplicate, bad, none = fixture(temp)
            before = copy.deepcopy(work.current)
            bytes_before = {r['path']: Path(r['path']).read_bytes() for r in before['source_catalog'].values()}
            with engine.db() as db:
                regular = {t: [tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in ('files','pairs','moves','keeps','ignored','separations')}
            self.run_saved(work)
            cat = work.current['source_catalog']
            self.assertNotIn(target, cat);self.assertNotIn(duplicate, cat)
            self.assertIn(bad, cat);self.assertIn(none, cat)
            self.assertEqual(len(cat[keeper]['origins']), 3)
            self.assertEqual(work.current['inventory']['unlinked_quarantine'], 2)
            self.assertEqual(work.current['history_verification']['linked_files'], 2)
            self.assertEqual(work.origin_audit(review_filter='uncertain')['total'], 2)
            self.assertEqual(work.origin_audit(review_filter='no_matches')['total'], 1)
            reopened = Workbench(engine)
            self.assertTrue(reopened.origin_audit()['auto_undo'])
            reopened.undo_origin({'job': 'saved-alice'})
            self.assertEqual(reopened.current['source_catalog'], before['source_catalog'])
            self.assertEqual(reopened.current['inventory'], before['inventory'])
            self.assertEqual(bytes_before, {p: Path(p).read_bytes() for p in bytes_before})
            with engine.db() as db:
                self.assertEqual(regular, {t: [tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in regular})

    def test_skips_deferred_discarded_and_different_image_choices(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, work, keeper, target, duplicate, bad, none = fixture(temp)
            cat = work.current['source_catalog'];before = copy.deepcopy(cat)
            with work.db() as db:
                db.execute('INSERT INTO origin_review VALUES (?,?,?)', (cat[target]['sha'], 'deferred', 1))
                db.execute('INSERT INTO origin_review VALUES (?,?,?)', (cat[none]['sha'], 'discarded', 1))
            with engine.db() as db:
                db.execute('INSERT INTO separations VALUES (?,?)', tuple(sorted((cat[bad]['sha'], cat[keeper]['sha']))))
            with patch('same_photo.verify', side_effect=AssertionError('Must not verify these entries')):
                self.run_saved(work)
            self.assertEqual(cat, before)
            self.assertEqual(work.origin_audit(review_filter='deferred')['total'], 1)
            self.assertEqual(work.origin_audit(review_filter='discarded')['total'], 1)
            self.assertEqual(work.origin_audit(review_filter='uncertain')['total'], 1)

    def test_partial_batch_resume_undo_restores_all_origins_and_previous_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, work, keeper, target, duplicate, bad, none = fixture(temp)
            work.current['origin_undo'] = {'prior_manual_marker': True}
            before = copy.deepcopy(work.current)
            persist = work.persist
            def stop_after_first_link():
                persist()
                if work.current.get('origin_undo', {}).get('kind') == 'auto':
                    work.cancel.set()
            with patch('same_photo.verify', return_value=True), patch.object(work, 'persist', side_effect=stop_after_first_link):
                work.verify_history({'job': 'saved-alice'});work.thread.join(30)
            self.assertIn('paused', work.current['phase'])
            reopened = Workbench(engine)
            with patch('same_photo.verify', return_value=True):
                self.run_saved(reopened)
            self.assertEqual(reopened.current['inventory']['unlinked_quarantine'], 1)
            self.assertEqual(len(reopened.current['source_catalog'][keeper]['origins']), 4)
            reopened.undo_origin({'job': 'saved-alice'})
            self.assertEqual(reopened.current['source_catalog'], before['source_catalog'])
            self.assertEqual(reopened.current['origin_undo'], before['origin_undo'])
            self.assertEqual(reopened.current['inventory'], before['inventory'])

    def test_changed_files_are_never_linked_even_with_accepted_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, work, keeper, target, duplicate, bad, none = fixture(temp)
            import same_photo
            cat = work.current['source_catalog']
            with work.db() as db:
                db.execute('INSERT INTO aliases VALUES (?,?,?,?)', (cat[target]['sha'], cat[keeper]['sha'], same_photo.VERSION, 1))
            Path(cat[keeper]['path']).write_bytes(b'changed')
            self.run_saved(work)
            self.assertEqual(work.current['inventory']['unlinked_quarantine'], 4)
            self.assertTrue(work.current['issues'])

    def test_pause_resume_and_restart_reuse_pair_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            engine, work, keeper, target, duplicate, bad, none = fixture(temp)
            import same_photo
            real = same_photo.verify
            def pause_after_check(a,b):
                result = real(a,b)
                work.cancel.set()
                return result
            with patch('same_photo.verify', side_effect=pause_after_check):
                work.verify_history({'job': 'saved-alice'});work.thread.join(30)
            self.assertIn('paused', work.current['phase'])
            with work.db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM aliases').fetchone()[0], 1)
            # Simulate a restart while verification was active: preserve the inventory.
            work.current.update(running=True, history_verifying=True);work.persist()
            reopened = Workbench(engine)
            self.assertFalse(reopened.current['running']);self.assertFalse(reopened.current['interrupted'])
            with patch('same_photo.verify', wraps=real) as verify:
                self.run_saved(reopened)
                self.assertEqual(verify.call_count, 1)
            self.assertEqual(reopened.current['inventory']['unlinked_quarantine'], 2)
            # A later ordinary scan cannot replace this saved history job.
            engine.start([temp], [], 'balanced');engine.thread.join(30)
            self.assertEqual(Workbench(engine).current['id'], 'saved-alice')
            self.assertEqual(Workbench(engine).current['inventory']['unlinked_quarantine'], 2)

if __name__ == '__main__':unittest.main()
