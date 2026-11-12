"""Persistence, compatibility and cross-workflow checks for hand-curated evolution photos."""
import copy
import gc
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_runtime_stability as fixtures


def record(ids, status='ready'):
    return {'version':1, 'status':status, 'media_ids':list(ids)}


class EvolutionTests(unittest.TestCase):
    import_image = fixtures.RuntimeStabilityTests.import_image
    post = fixtures.RuntimeStabilityTests.post

    def setUp(self):
        fixtures.RuntimeStabilityTests.setUp(self)
        self.ids = [self.import_image(i)['id'] for i in range(5)]
        self.group = self.store.create_set(self.character['id'], 'Session', self.ids, self.ids[-1], cover_source='manual')
        self.path = '/api/sets/' + self.group['id'] + '/evolution'

    def tearDown(self):
        gc.collect()
        fixtures.RuntimeStabilityTests.tearDown(self)

    def write(self, value, expected=None):
        return self.post(self.path, {'expected':expected, 'evolution':value})

    def test_stale_retry_atomic_failure_and_evidence_through_restore(self):
        candidate = record([], 'candidate')
        chosen = record(self.ids[1:4][::-1])
        self.assertEqual(self.write(candidate)[0], 200)
        self.assertEqual(self.write(chosen)[0], 400)
        self.assertEqual(self.write(chosen, candidate)[0], 200)
        self.assertEqual(self.write(chosen, candidate)[0], 200)
        self.assertEqual(self.write(None, candidate)[0], 400)
        checkpoint = self.store.create_checkpoint({})
        group_id = self.group['id']
        with patch.object(self.store, '_write_atomic', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.set_evolution(group_id, {'expected':chosen, 'evolution':None})
        self.assertEqual(self.store.set_item(group_id)['after_hours_evolution'], chosen)
        self.assertEqual(self.write(None, chosen)[0], 200)
        self.assertNotIn('after_hours_evolution', self.store.set_item(group_id))
        plan = self.store.checkpoint_preview({'id':checkpoint['id']})
        self.store.checkpoint_restore({'id':checkpoint['id'], 'token':plan['token']})
        reopened = type(self.store)(self.store.root)
        self.assertEqual(reopened.set_item(group_id)['after_hours_evolution'], chosen)
        with sqlite3.connect(reopened.tracking.path) as db:
            payloads = [json.loads(row[0]) for row in db.execute(
                "select payload from tracking_events where kind='library.sets' and entity=?", (group_id,))]
        db.close()
        self.assertTrue(any(p.get('actor') == 'manual' and p['change'].get('changes', {}).get(
            'after_hours_evolution', {}).get('after') == chosen for p in payloads))

    def test_reject_invalid_inputs_hold_flags_and_missing_original(self):
        a, b, c, d, e = self.ids
        other = self.store.add_character('Other')
        foreign = self.store.import_bytes(b'foreign', 'Other.png', other['id'], [], {}, 'image/png')[0]
        outsider = self.import_image(100)
        video = self.store.import_bytes(b'fake video', 'clip.mp4', self.character['id'], [], {}, 'video/mp4')[0]
        self.store.update_set(self.group['id'], add_media_ids=[video['id']])
        for bad in [record([a,b]), record([a,b,c,d,e]), record([a,a,b]), record([a,{},b]),
                    record([a,b,foreign['id']]), record([a,b,outsider['id']]), record([a,b,video['id']]),
                    record([a,b,c], 'automatic'), {**record([a,b,c]), 'version':True}, [], '']:
            with self.subTest(bad=bad):
                self.assertEqual(self.write(bad)[0], 400)
        for flag in ('in_review', 'in_purgatory', 'flagged_for_removal'):
            self.store.media_item(a)[flag] = True
            self.assertEqual(self.write(record([a,b,c]))[0], 400)
            self.store.media_item(a)[flag] = False
        self.store.update_set(self.group['id'], in_purgatory=True)
        self.assertEqual(self.write(record([a,b,c]))[0], 400)
        self.store.update_set(self.group['id'], in_purgatory=False)
        (self.store.root / self.store.media_item(b)['stored_rel']).unlink()
        self.assertEqual(self.write(record([a,b,c]))[0], 400)
        self.assertNotIn('after_hours_evolution', self.group)

    def test_future_data_legacy_incomplete_and_eligibility_changes(self):
        a, b, c, d, _ = self.ids
        self.group['after_hours_evolution'] = {'version':2, 'status':'ready', 'other':'preserve'}
        self.store.save()
        self.assertEqual(self.write(None, copy.deepcopy(self.group['after_hours_evolution']))[0], 400)
        self.assertEqual(self.group['after_hours_evolution']['other'], 'preserve')
        self.group['after_hours_evolution'] = record([a,b])
        self.store._write_atomic(self.store.data)
        reopened = type(self.store)(self.store.root)
        self.assertEqual(reopened.set_item(self.group['id'])['after_hours_evolution'], record([a,b], 'candidate'))
        self.store = reopened
        value = record([c,a,b,d])
        self.assertEqual(self.write(value, record([a,b], 'candidate'))[0], 200)
        self.store.set_removal_flag(b, True)
        self.assertEqual(self.store.set_item(self.group['id'])['after_hours_evolution'], record([c,a,b,d], 'candidate'))
        self.store.set_removal_flag(b, False)
        self.assertEqual(self.write(value, record([c,a,b,d], 'candidate'))[0], 200)
        self.store.update_set(self.group['id'], remove_media_ids=[a])
        self.assertEqual(self.store.set_item(self.group['id'])['after_hours_evolution'], record([c,b,d], 'candidate'))

    def test_organizer_skip_move_and_explicit_destination_removal(self):
        owner = self.character['id']
        a,b,c,d,_ = self.ids
        other_ids = [self.import_image(i)['id'] for i in range(10,14)]
        other = self.store.create_set(owner, 'Second', other_ids)
        first_order = [c,a,d,b]
        self.write(record(first_order))
        self.store.set_evolution(other['id'], {'expected':None, 'evolution':record(other_ids)})
        catalog = {}
        for mid in self.ids + other_ids:
            item = self.store.media_item(mid)
            catalog[mid] = {'id':mid, 'sha':item['sha256'], 'path':str(self.store.root/item['stored_rel'])}
        def transfer(groups, action):
            draft = {'format':'folder-organizer-2', 'scope':'test', 'config':{'roots':[str(self.store.root)]},
                     'source_catalog':catalog, 'sets':groups}
            plan = self.store.organizer_preview({'character_id':owner, 'draft':draft})
            self.assertEqual(plan['issues'], [])
            return self.store.organizer_apply({'token':plan['token'], 'conflicts':action})
        destination = {'id':'dest', 'name':'Destination', 'saved':True, 'members':[b, other_ids[1]]}
        transfer([destination], 'skip')
        self.assertEqual(self.group['after_hours_evolution'], record(first_order))
        self.assertEqual(other['after_hours_evolution'], record(other_ids))
        # First photo is removed directly from a linked organizer destination. The other
        # departs through the normal Move conflict path in _detach_set_members.
        release = {'id':'first', 'library_id':self.group['id'], 'name':'Session', 'saved':True,
                   'members':[a,c,d], 'removed_members':[b]}
        transfer([release, destination], 'move')
        self.assertEqual(self.group['after_hours_evolution'], record([c,a,d], 'candidate'))
        self.assertEqual(other['after_hours_evolution'], record([other_ids[0], *other_ids[2:]], 'candidate'))
