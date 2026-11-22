"""Confirmed Library shoots stay independent until a one-step promotion."""
import copy
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_runtime_stability as fixtures


class ReviewSetTests(unittest.TestCase):
    setUp = fixtures.RuntimeStabilityTests.setUp
    tearDown = fixtures.RuntimeStabilityTests.tearDown
    import_image = fixtures.RuntimeStabilityTests.import_image
    post = fixtures.RuntimeStabilityTests.post

    def test_hold_reload_edit_and_promote_same_group(self):
        owner = self.character['id']
        staged = [self.import_image(i) for i in range(3)]
        ids = [image['id'] for image in staged]
        staged[0].update(in_review=True, in_all=False)
        staged[1].update(in_purgatory=True, in_all=False)
        self.store.save()
        before = copy.deepcopy(self.store.data['media'])
        battles = copy.deepcopy(self.store.battles.data)
        category = self.store.add_set_category(owner, 'Winter')
        status, held = self.post('/api/review-sets', dict(character_id=owner, name='winter shoot',
            media_ids=ids, colors=['Blue'], categories=[category['id']], notes='Original sequence',
            cover_media_id=ids[1], cover_source='manual', review_id='a' * 32))
        self.assertEqual(status, 200, held)
        ident = held['id']
        self.assertEqual(ident, 'a' * 32)
        self.assertEqual(self.store.data['media'], before)
        self.assertNotIn('review_sets', self.store.public_library())
        self.assertFalse(self.store.public_library()['sets'])
        files = self.store.duplicate_catalog(owner)['files']
        self.assertTrue(all(f['set_under_review'] and not f['sets'] for f in files))
        self.store._thumbnail_queue.join()
        reopened = fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual(reopened.review_sets(owner)['sets'], [held])
        edited = self.store.edit_review_set(ident, dict(media_ids=ids[::-1], name='final shoot', review_revision=held['review_revision']))
        route = f'/api/review-sets/{ident}/promote'
        self.assertEqual(self.post(route, dict(review_revision=held['review_revision']))[0], 400)
        self.assertFalse(self.store.public_library()['sets'])
        status, saved = self.post(route, dict(review_revision=edited['review_revision']))
        self.assertEqual(status, 200, saved)
        for key in ('id', 'name', 'media_ids', 'cover_source', 'cover_media_id', 'notes', 'colors', 'categories', 'confirmed_at', 'created_at'):
            self.assertEqual(saved[key], edited[key], key)
        self.assertEqual(self.post(route, dict(review_revision=edited['review_revision'])), (200, saved))
        self.assertEqual(self.store.review_sets(owner)['sets'], [])
        self.assertFalse(any(f['set_under_review'] for f in self.store.duplicate_catalog(owner)['files']))
        self.assertTrue(self.store.media_item(ids[0])['in_review'])
        self.assertTrue(self.store.media_item(ids[1])['in_purgatory'])
        self.assertEqual(self.store.battles.data, battles)
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            changes = [r for r in fixtures.RUNTIME['TrackingJournal'].rows(db) if r['entity'] == ident]
        self.assertTrue({'library.sets', 'library.review_sets'} <= {r['kind'] for r in changes})

    def test_hold_additions_merge_with_current_members_and_refuse_a_changed_assignment(self):
        owner = self.character['id']
        ids = [self.import_image(i)['id'] for i in range(5)]
        group = self.store.create_set(owner, 'Original', ids[:2])
        held = self.store.hold_set_additions(group['id'], ids[2:4])
        self.store.update_set(group['id'], name='Edited manually', media_ids=[ids[1], ids[4]])
        other = self.store.create_set(owner, 'Another Set', [ids[3]])
        with self.assertRaisesRegex(ValueError, 'already belongs'):
            self.store.promote_review_set(held['id'], held['review_revision'])
        held = self.store.edit_review_set(held['id'], dict(review_revision=held['review_revision'], media_ids=[ids[2]]))
        promoted = self.store.promote_review_set(held['id'], held['review_revision'])
        self.assertEqual(promoted['name'], 'Edited Manually')
        self.assertEqual(promoted['media_ids'], [ids[1], ids[4], ids[2]])
        self.assertEqual(self.store.set_item(other['id'])['media_ids'], [ids[3]])

    def test_rapid_approval_or_failed_promotion_is_atomic(self):
        owner = self.character['id']
        path = self.store.root / 'pending.png'
        path.write_bytes(b'queued')
        item = self.store._register_file(path, 'pending.png', owner, [], {}, 'image/png', pending=True)[0]
        request = dict(character_id=owner, action='new_review_set', media_ids=[item['id']], name='Queue shoot')
        disk = self.store.db_path.read_bytes()
        with patch.object(self.store, '_write_atomic', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.resolve_rapid(request)
        self.assertEqual(self.store.db_path.read_bytes(), disk)
        self.assertTrue(self.store.rapid_item(item['id']))
        held = self.store.resolve_rapid(request)['set']
        self.assertFalse(self.store.rapid_item(item['id']))
        self.assertFalse(self.store.set_item(held['id']))
        with patch.object(self.store, '_write_atomic', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.promote_review_set(held['id'], held['review_revision'])
        self.assertEqual(self.store.review_set_item(held['id']), held)
        self.assertFalse(self.store.set_item(held['id']))

    def test_manual_group_and_import_retry_preserve_placement(self):
        owner = self.character['id']
        first = self.import_image(1)
        _, held = self.post('/api/review-sets/manual-group', dict(character_id=owner, name='Search', media_ids=[first['id']]))
        ident = held['id']
        args = (b'new photo', 'new.png', owner, [], {}, 'image/png')
        item, duplicate, _ = self.store.import_bytes_profiled(*args, review_set_id=ident)
        self.assertFalse(duplicate)
        self.assertFalse(item['in_all'])
        self.assertTrue(self.store.import_bytes_profiled(*args, review_set_id=ident)[1])
        self.assertEqual(self.store.review_set_item(ident)['media_ids'], [first['id'], item['id']])
        self.assertEqual(self.post('/api/sets/manual-group', dict(character_id=owner, name='Stale', media_ids=[item['id']]))[0], 400)
        self.assertFalse(self.store.public_library()['sets'])
