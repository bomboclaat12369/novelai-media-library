"""Duo selection, invalidation and evidence across the Library and Workbench."""
import copy
import gc
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_runtime_stability as fixtures


def duo(front, back):
    return {'version': 1, 'media_ids': [front, back]}


class DuoTests(unittest.TestCase):
    import_image = fixtures.RuntimeStabilityTests.import_image
    post = fixtures.RuntimeStabilityTests.post

    def setUp(self):
        fixtures.RuntimeStabilityTests.setUp(self)
        self.store._queue_image_thumbnail = lambda *args: None
        self.ids = [self.import_image(index)['id'] for index in range(4)]
        self.group = self.store.create_set(self.character['id'], 'Session', self.ids)
        self.path = '/api/sets/' + self.group['id'] + '/duo'

    def tearDown(self):
        gc.collect()
        fixtures.RuntimeStabilityTests.tearDown(self)

    def write(self, value, expected=None):
        return self.post(self.path, {'expected': expected, 'duo': value})[0]

    def test_two_distinct_set_photos_and_version_compatibility(self):
        a, b, *_ = self.ids
        other = self.store.add_character('Other')['id']
        foreign = self.store.import_bytes(b'foreign', 'x.png', other, [], {}, 'image/png')[0]['id']
        outside = self.import_image(50)['id']
        video = self.store.import_bytes(b'video', 'x.mp4', self.character['id'], [], {}, 'video/mp4')[0]['id']
        self.store.update_set(self.group['id'], add_media_ids=[video])
        for value in (duo(a,a), duo(a,foreign), duo(a,outside), duo(a,video), duo(a,{}),
                      {'version':1,'media_ids':[a]}, {'version':1,'media_ids':self.ids},
                      {**duo(a,b),'version':True}, {**duo(a,b),'extra':1}):
            with self.subTest(value=value):
                self.assertEqual(self.write(value), 400)
        for flag in ('in_review', 'in_purgatory', 'flagged_for_removal'):
            self.store.media_item(a)[flag] = True
            self.assertEqual(self.write(duo(a,b)), 400)
            self.store.media_item(a)[flag] = False
        self.store.update_set(self.group['id'], in_purgatory=True)
        self.assertEqual(self.write(duo(a,b)), 400)
        self.store.update_set(self.group['id'], in_purgatory=False)
        (self.store.root / self.store.media_item(b)['stored_rel']).unlink()
        self.assertEqual(self.write(duo(a,b)), 400)
        future = {'version':2,'sides':{'custom':True}}
        self.group['after_hours_duo'] = copy.deepcopy(future)
        self.store.save()
        self.assertEqual(self.write(None, future), 400)
        self.assertEqual(type(self.store)(self.store.root).set_item(self.group['id'])['after_hours_duo'], future)

    def test_stale_writes_rollback_checkpoints_and_manual_decision_history(self):
        a, b, c, _ = self.ids
        first, swapped = duo(a,b), duo(b,a)
        self.assertEqual(self.write(first), 200)
        self.assertEqual(self.write(swapped, first), 200)
        self.assertEqual(self.write(swapped, first), 200)
        self.assertEqual(self.write(duo(b,c), first), 400)
        checkpoint = self.store.create_checkpoint({})
        with patch.object(self.store, '_write_atomic', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.set_duo(self.group['id'], {'expected':swapped, 'duo':None})
        self.assertEqual(self.store.set_item(self.group['id'])['after_hours_duo'], swapped)
        self.assertEqual(self.write(None, swapped), 200)
        self.assertNotIn('after_hours_duo', self.store.set_item(self.group['id']))
        plan = self.store.checkpoint_preview({'id':checkpoint['id']})
        self.store.checkpoint_restore({'id':checkpoint['id'], 'token':plan['token']})
        reopened = type(self.store)(self.store.root)
        self.assertEqual(reopened.set_item(self.group['id'])['after_hours_duo'], swapped)
        db = sqlite3.connect(reopened.tracking.path)
        try:
            rows = db.execute("select payload from tracking_events where kind='library.sets' and entity=?",
                              (self.group['id'],))
            swaps = []
            for (raw,) in rows:
                payload = json.loads(raw)
                change = payload['change'].get('changes', {}).get('after_hours_duo', {})
                if change.get('before') == first and change.get('after') == swapped:
                    swaps.append(payload['actor'])
            self.assertEqual(swaps, ['manual'])
        finally:
            db.close()

    def test_workbench_move_and_library_undo_keep_the_original_side_identities(self):
        a, b, c, d = self.ids
        chosen = duo(b, a)
        self.assertEqual(self.write(chosen), 200)
        self.store.delete_media(b)
        self.assertEqual(self.store.set_item(self.group['id'])['after_hours_duo'], chosen)
        self.store.undo_last(self.store.data['undo_history'][-1]['id'])
        self.assertEqual(self.write(chosen, chosen), 200)
        store = self.store
        catalog = {mid:{'id':mid, 'sha':store.media_item(mid)['sha256'],
                        'path':str(store.root / store.media_item(mid)['stored_rel'])} for mid in self.ids}
        draft = {'format':'folder-organizer-2', 'scope':'test', 'config':{'roots':[str(store.root)]},
                 'source_catalog':catalog, 'sets':[{'id':'dest', 'name':'Moved photos', 'saved':True, 'members':[b,d]}]}
        plan = store.organizer_preview({'character_id':self.character['id'], 'draft':draft})
        self.assertEqual(plan['issues'], [])
        store.organizer_apply({'token':plan['token'], 'conflicts':'move'})
        group = store.set_item(self.group['id'])
        self.assertNotIn(b, group['media_ids'])
        self.assertEqual(group['after_hours_duo'], chosen)
        self.assertEqual(self.write(chosen, chosen), 400)
        self.assertEqual(self.write(duo(c,a), chosen), 200)
        self.assertEqual(group['after_hours_duo'], duo(c,a))
