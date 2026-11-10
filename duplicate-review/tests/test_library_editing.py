import copy
import json
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch
import test_individual_imports as imports


class MetadataEditingHTTPTests(unittest.TestCase):
    tearDown = imports.IndividualHTTPTests.tearDown
    request = imports.IndividualHTTPTests.request

    def setUp(self):
        imports.IndividualHTTPTests.setUp(self)
        self.store._queue_image_thumbnail = lambda *args: None
        self.org = self.server.organizer
        self.job = self.org.summary()['job']

    def imported(self, n=3, pending=False):
        source = Path(self.org.catalog[self.ids[n]]['path'])
        if pending:
            temp = self.store.root / ('pending-' + str(n) + '.jpg')
            temp.write_bytes(source.read_bytes())
            return self.store._register_file(temp, source.name, self.owner['id'], [], {}, 'image/jpeg', pending=True)[0]
        return self.store.import_bytes(source.read_bytes(), source.name, self.owner['id'], [], {}, 'image/jpeg')[0]

    def editor(self, kind='image', ident=None):
        return self.request('edit-read', {'job': self.job, 'kind': kind, 'id': ident or self.ids[3]})

    def save(self, record, **fields):
        return self.request('edit-save', {'job': self.job, 'token': record['token'], 'fields': fields})

    def test_existing_image_categories_replace_without_changing_identity_or_other_metadata(self):
        item = self.imported()
        old = self.store.add_category(self.owner['id'], 'Old')
        new = self.store.add_category(self.owner['id'], 'New')
        self.store.set_categories(item['id'], [old['id']])
        self.store.set_favorite(item['id'], True)
        self.store.set_crop(item['id'], .1, .2)
        group = self.store.create_set(self.owner['id'], 'Keep members', [item['id']], preserve_placement=True)
        before = copy.deepcopy(item)
        original = (self.store.root / item['stored_rel']).read_bytes()
        record = self.editor()
        self.assertEqual(record['fields']['categories'], [old['id']])
        self.save(record, categories=[new['id']])
        self.assertEqual(item['categories'], [new['id']])
        for key in ('id', 'sha256', 'stored_rel', 'in_all', 'favorite', 'crop_top', 'crop_bottom'):
            self.assertEqual(item[key], before[key])
        self.assertEqual(group['media_ids'], [item['id']])
        self.assertEqual((self.store.root / item['stored_rel']).read_bytes(), original)
        self.store.undo_last(self.store.undo_history()['entries'][0]['id'])
        self.assertEqual(item['categories'], [old['id']])

    def test_rapid_review_categories_keep_queue_position_other_choices_and_originals(self):
        item = self.imported(pending=True)
        other = self.imported(4, pending=True)
        category = self.store.add_category(self.owner['id'], 'Queue category')
        self.store.rapid_state({'character_id': self.owner['id'], 'current_id': other['id'], 'selected_ids': [other['id']],
                                'scroll_top': 55, 'choices': {other['id']: {'favorite': True}, item['id']: {'crop_top': .15}}})
        before = copy.deepcopy(self.store.rapid_queue(self.owner['id']))
        record = self.editor()
        self.assertEqual(record['location'], 'rapid_review')
        self.save(record, categories=[category['id']])
        self.assertEqual(self.store.rapid_item(item['id'])['categories'], [category['id']])
        self.assertEqual(self.store.rapid_item(item['id'])['crop_top'], .15)
        self.assertIsNone(self.store.media_item(item['id']))
        after = self.store.rapid_queue(self.owner['id'])
        self.assertEqual(after['state'], before['state'])
        self.assertEqual(after['items'][1], before['items'][1])
        self.assertTrue((self.store.root / item['stored_rel']).is_file())

    def test_set_rename_and_categories_keep_members_and_pending_draft_additions(self):
        item = self.imported(0)
        group = self.store.create_set(self.owner['id'], 'Original set', [item['id']], preserve_placement=True)
        category = self.store.add_set_category(self.owner['id'], 'New set category')
        current = self.org.bulk.current
        current['library_sets'][group['id']] = copy.deepcopy(group)
        current['source_catalog'][self.ids[0]]['existing_sets'] = [group['id']]
        self.org.bulk.persist(); self.org.bound = None; self.org.bind()
        target = 'library:' + group['id']
        self.org.mutate('save', {'job': self.job, 'revision': self.org.state()['revision'], 'target': target,
                                 'ids': [self.ids[2]], 'name': group['name']})
        before_members = self.org.sets()[target]['members'][:]
        record = self.editor('set', target)
        self.save(record, name='new set name', colors=['blue'], categories=[category['id']], favorite=True, in_purgatory=True)
        self.assertEqual(group['name'], 'New Set Name')
        self.assertEqual(group['media_ids'], [item['id']])
        self.assertTrue(group['favorite']); self.assertTrue(group['in_purgatory'])
        draft = self.org.sets()[target]
        self.assertEqual(draft['members'], before_members)
        self.assertEqual(draft['name'], group['name'])
        self.assertEqual(draft['categories'], [category['id']])
        self.assertEqual(current['library_sets'][group['id']]['name'], group['name'])
        self.assertEqual(len(self.store.data['sets']), 1)
        # A later rename preserves unsent color edits in the same draft.
        self.org.mutate('set_details', {'job': self.job, 'revision': self.org.state()['revision'],
                                        'target': target, 'colors': ['Green']})
        record = self.editor('set', target)
        self.save(record, **{**record['fields'], 'name': 'Another name'})
        self.assertEqual(self.org.sets()[target]['colors'], ['Green'])
        self.assertEqual(group['colors'], ['Blue'])

    def test_changed_item_wrong_library_and_removed_categories_reject_edits(self):
        item = self.imported()
        category = self.store.add_category(self.owner['id'], 'Category')
        record = self.editor()
        self.store.set_categories(item['id'], [category['id']])
        with self.assertRaises(HTTPError) as raised:
            self.save(record, categories=[])
        self.assertIn('changed', json.load(raised.exception)['error'])
        record = self.editor()
        real = self.engine.library.request
        def wrong_instance(path, body=None, **kwargs):
            return {'instance': 'other-library'} if path == '/api/tracking/status' else real(path, body, **kwargs)
        with patch.object(self.engine.library, 'request', side_effect=wrong_instance):
            with self.assertRaises(HTTPError) as raised:
                self.save(record, categories=[])
        self.assertIn('changed', json.load(raised.exception)['error'])
        self.assertEqual(item['categories'], [category['id']])
        record = self.editor()
        with self.assertRaises(HTTPError) as raised:
            self.save(record, categories=['removed-category'])
        self.assertIn('categories changed', json.load(raised.exception)['error'])
        self.assertEqual(item['categories'], [category['id']])

    def test_unimported_image_opens_import_choices_without_creating_anything(self):
        self.assertTrue(self.editor()['not_imported'])
        self.assertFalse(self.store.data['media'])
        self.assertFalse(self.org.individual_imports())
