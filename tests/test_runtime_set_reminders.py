"""Visual Set reminders survive edits without preparing collectible cards."""
import concurrent.futures
import copy
import json
import os
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_runtime_stability as fixtures


class SetReminderTests(unittest.TestCase):
    setUp = fixtures.RuntimeStabilityTests.setUp
    tearDown = fixtures.RuntimeStabilityTests.tearDown
    import_image = fixtures.RuntimeStabilityTests.import_image
    post = fixtures.RuntimeStabilityTests.post

    def test_flags_are_independent_and_leave_photos_and_cards_alone(self):
        ids = [self.import_image(i)['id'] for i in range(3)]
        group = self.store.create_set(self.character['id'], 'Session', ids)
        recipes = {
            'after_hours_duo': {'version': 1, 'media_ids': ids[:2]},
            'after_hours_evolution': {'version': 1, 'status': 'ready', 'media_ids': ids},
        }
        group.update(copy.deepcopy(recipes))
        self.store.save()
        before = copy.deepcopy(self.store.data['media'])
        battles = copy.deepcopy(self.store.battles.data)
        for field in ('possible_duo', 'possible_evolution'):
            status, saved = self.post('/api/sets/' + group['id'], {field: True})
            self.assertEqual(status, 200)
            self.assertIs(saved[field], True)
        self.store.update_set(group['id'], name='Renamed', possible_duo=False)
        saved = self.store.set_item(group['id'])
        self.assertIs(saved['possible_duo'], False)
        self.assertIs(saved['possible_evolution'], True)
        self.assertEqual({key: saved[key] for key in recipes}, recipes)
        self.assertEqual(self.store.data['media'], before)
        self.assertEqual(self.store.battles.data, battles)
        disk = json.loads(self.store.db_path.read_bytes())
        self.assertTrue(disk['sets'][0]['possible_evolution'])

    def test_empty_set_can_be_marked_and_history_survives_clear(self):
        group = self.store.create_set(self.character['id'], 'Review this later', [])
        status, saved = self.post('/api/sets/' + group['id'], {'possible_evolution': True})
        self.assertEqual(status, 200)
        self.assertNotIn('after_hours_evolution', saved)
        self.assertNotIn('after_hours_duo', saved)
        self.store.update_set(group['id'], possible_evolution=False)
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            records = fixtures.RUNTIME['TrackingJournal'].rows(db)
        changes = [row for row in records if row['kind'] == 'library.sets' and row['entity'] == group['id']]
        self.assertIn('possible_evolution', json.dumps(changes))
        self.assertGreaterEqual(len(changes), 3)

    def test_validation_and_failed_save_restore_previous_state(self):
        group = self.store.create_set(self.character['id'], 'Session', [])
        before = self.store.db_path.read_bytes()
        for value in (1, 0, 'false', [], {}):
            status, _ = self.post('/api/sets/' + group['id'], {'possible_duo': value})
            self.assertEqual(status, 400)
            self.assertEqual(self.store.db_path.read_bytes(), before)
        with patch.object(os, 'replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.store.update_set(group['id'], possible_duo=True)
        self.assertEqual(self.store.db_path.read_bytes(), before)
        self.assertNotIn('possible_duo', self.store.set_item(group['id']))

    def test_concurrent_markers_keep_both_values_and_legacy_sets_are_unmarked(self):
        group = self.store.create_set(self.character['id'], 'Session', [])
        self.assertNotIn('possible_duo', group)
        self.assertNotIn('possible_evolution', group)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(self.store.update_set, group['id'], **{key: True})
                    for key in ('possible_duo', 'possible_evolution')]
            for job in jobs:
                job.result()
        saved = self.store.public_library()['sets'][0]
        self.assertTrue(saved['possible_duo'])
        self.assertTrue(saved['possible_evolution'])
