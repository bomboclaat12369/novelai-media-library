"""Body-aware crop review through the companion's collection HTTP routes."""
from contextlib import closing
import copy
import hashlib
import json
import sqlite3
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_runtime_auto_framing as fixtures

R = fixtures.R


def geometry(rect, render, padding=0, hips=2, legs=2, distal=None, fuller=None):
    result = {
        'status':'balanced-guided', 'reason':'Uses the visible subject to guide the crop.',
        'render':render, 'rect':rect, 'padding':padding,
        'evidence':{'observedGroups':{'head':11, 'hips':hips, 'legs and feet':legs},
                    'estimatedForegroundTrimPercent':.77, 'observedDistalEdge':distal},
    }
    if fuller:
        result['variants'] = {'fuller':fuller}
    return result


LIKELY = geometry([0,.15,1,.9], [0,-.2,1,4/3])
LOWER_LEGS = geometry([0,.008,1,.883], [.087,-.009,.826,1.143], .174, legs=0, distal=.88)
RECLINING = geometry([.134,0,.809,1], [-.199,.13,1.482,.741], .259, legs=8, distal=.134,
                     fuller={'rect':[.21,0,.762,1], 'render':[-.38,.045,1.817,.909], 'padding':.09})


class CropReviewTests(unittest.TestCase):
    setUp = fixtures.AutomaticFramingTests.setUp
    tearDown = fixtures.AutomaticFramingTests.tearDown
    post = fixtures.AutomaticFramingTests.post
    photo = fixtures.AutomaticFramingTests.photo
    call = fixtures.AutomaticFramingTests.call
    edit = fixtures.AutomaticFramingTests.edit

    def crop(self, action, expected=200, **body):
        code, result = self.post('/api/collection/crop-review-' + action,
                                 {'character_id':self.character['id'], **body})
        self.assertEqual(code, expected, result)
        return result

    def fill_page(self, *items, analyses=()):
        with patch.object(self.store, '_analyze_card_crop', side_effect=analyses):
            return self.crop('state', media_ids=[item['id'] for item in items])

    @staticmethod
    def decisions(page, *choices):
        return [{'media_id':item['id'], 'token':page['proposals'][item['id']]['token'], 'choice':choice}
                for item, choice in choices]

    def test_review_saves_extended_vertical_pan_using_oriented_source_dimensions(self):
        # The Photo app sees this 12:1 stored JPEG as a 1:12 portrait.
        item=self.photo(3456,288,orientation=6)
        page=self.crop('state',media_ids=[item['id']],analyze=False)
        frame={'x':0,'y':-1300,'zoom':3,'fit':'fill','reference':dict(R['CARD_FRAME_REFERENCE'])}
        review=self.decisions(page,(item,'manual'))[0]
        for rejected in [{**frame,'y':-1500},{**frame,'x':1300}]:
            self.crop('save',expected=400,revision=page['revision'],reviews=[{**review,'frame':rejected}])
        result=self.crop('save',revision=page['revision'],reviews=[{**review,'frame':frame}])
        key='image:'+item['id']
        self.assertEqual(result['collection']['frames'][key],frame)
        self.assertEqual(self.call()['collection']['frames'][key],frame)
        self.assertEqual(result['collection']['frame_meta'][key]['dimensions'],[288,3456])

    def test_queue_protects_missing_lower_leg_evidence_and_real_padding_tradeoffs(self):
        lower_legs = self.photo(505,932)
        reclining = self.photo(2048,1365)
        trivial = self.photo(750,1000)
        unwritten = self.crop('state')
        self.assertEqual(unwritten['queue']['pending'], [lower_legs['id'], reclining['id'], trivial['id']])
        self.assertEqual(unwritten['queue']['fit'], [])
        state = self.fill_page(lower_legs, reclining, trivial, analyses=[LOWER_LEGS, RECLINING])
        self.assertEqual(state['queue']['needs_look'], [lower_legs['id'], reclining['id']])
        self.assertEqual(state['proposals'][trivial['id']]['category'], 'fit')
        lower = state['proposals'][lower_legs['id']]
        self.assertIn('legs and feet', lower['reason'])
        self.assertIn('fuller', state['proposals'][reclining['id']]['options'])
        self.assertEqual(state['changed_frames'], {})
        self.assertEqual(self.call()['collection']['frames'], {})
        reviews = self.decisions(state, (lower_legs,'fit'), (reclining,'suggested'))
        saved = self.crop('save', revision=state['revision'], reviews=reviews)['collection']
        self.assertEqual(saved['frames']['image:'+lower_legs['id']], lower['options']['fit']['frame'])
        self.assertEqual(saved['frames']['image:'+reclining['id']], state['proposals'][reclining['id']]['options']['suggested']['frame'])

    def test_queue_verifies_fit_using_displayed_orientation_and_keeps_it_after_restart(self):
        actual_landscape = self.photo(750,1000,orientation=6)
        actual_fit = self.photo(1000,750,orientation=6)
        ids = [actual_landscape['id'], actual_fit['id']]
        with patch.object(self.store, '_crop_image_snapshot', side_effect=AssertionError('opened source')):
            preview = self.crop('state')
        self.assertEqual(preview['queue']['pending'], ids)
        self.assertEqual(preview['queue']['fit'], [])
        state = self.fill_page(actual_landscape, actual_fit, analyses=[RECLINING])
        self.assertEqual(state['queue']['needs_look'], [ids[0]])
        self.assertEqual(state['queue']['fit'], [ids[1]])
        self.assertEqual(state['queue']['pending'], [])
        self.store = R['LibraryStore'](self.store.root)
        self.assertEqual(self.crop('state')['queue'], state['queue'])
        with patch.object(self.store, '_analyze_card_crop', side_effect=AssertionError('repeated analysis')):
            reopened = self.crop('state', media_ids=ids)
        self.assertEqual(reopened['proposals'], state['proposals'])

    def test_replacing_source_reopens_suggested_approval_but_preserves_explicit_choices(self):
        suggested, explicit_fit, fuller = self.photo(505,932), self.photo(505,932), self.photo(2048,1365)
        state = self.fill_page(suggested, explicit_fit, fuller, analyses=[LOWER_LEGS, LOWER_LEGS, RECLINING])
        reviews = self.decisions(state, (suggested,'suggested'), (explicit_fit,'fit'), (fuller,'fuller'))
        saved = self.crop('save', revision=state['revision'], reviews=reviews)['collection']
        key = 'image:' + suggested['id']
        self.assertEqual(saved['frame_meta'][key]['mode'], 'auto')
        self.assertIn(suggested['id'], self.crop('state')['queue']['checked'])
        for item in (suggested, explicit_fit, fuller):
            path = self.store.root / item['stored_rel']
            R['Image'].new('RGB',(item['width'], item['height']),(51,112,61)).save(path)
            item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.store.save()
        self.store = R['LibraryStore'](self.store.root)
        self.assertEqual(self.crop('state')['queue']['pending'], [suggested['id']])
        self.assertEqual(self.crop('state')['queue']['checked'], [explicit_fit['id'], fuller['id']])
        live = self.call()['collection']
        self.assertNotIn(key, live['frames'])
        self.assertNotIn(key, live['frame_meta'])
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            crop_history = [row for row in R['TrackingJournal'].rows(db)
                            if row['kind'] == 'library.card_crop' and row['entity'] == suggested['id']]
        removal = crop_history[-1]['payload']['change']
        self.assertIsNone(removal['after'])
        self.assertEqual(removal['before']['frame_meta'], saved['frame_meta'][key])
        for item in (explicit_fit, fuller):
            explicit = 'image:' + item['id']
            self.assertEqual(live['frames'][explicit], saved['frames'][explicit])
            self.assertEqual(live['frame_meta'][explicit], saved['frame_meta'][explicit])
        scanned = self.fill_page(suggested, analyses=[LOWER_LEGS])
        self.assertEqual(scanned['queue']['needs_look'], [suggested['id']])
        self.crop('save', expected=400, revision=state['revision'], reviews=reviews[:1])

    def test_likely_applies_live_and_persists_analysis_without_reopening_source_in_queue(self):
        item = self.photo(750,1333)
        original = (self.store.root / item['stored_rel']).read_bytes()
        state = self.fill_page(item, analyses=[LIKELY])
        key = 'image:' + item['id']
        self.assertEqual(state['proposals'][item['id']]['category'], 'likely')
        self.assertEqual(state['changed_frames'][key], state['proposals'][item['id']]['options']['suggested']['frame'])
        live = self.call()['collection']['frame_meta'][key]
        self.assertFalse(live['checked'])
        self.store = R['LibraryStore'](self.store.root)
        with patch.object(self.store, '_analyze_card_crop', side_effect=AssertionError('repeated analysis')):
            cached = self.crop('state')
            self.assertEqual(cached['queue']['likely'], [item['id']])
            reopened = self.crop('state', media_ids=[item['id']])
        self.assertEqual(reopened['proposals'][item['id']], state['proposals'][item['id']])
        self.assertEqual(reopened['changed_frames'], {})
        saved = self.crop('save', revision=state['revision'],
                          reviews=self.decisions(state, (item,'suggested')))['collection']
        self.assertEqual(saved['frame_meta'][key]['token'], live['token'])
        self.assertTrue(saved['frame_meta'][key]['checked'])
        self.assertEqual((self.store.root / item['stored_rel']).read_bytes(), original)
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            rows = json.dumps(R['TrackingJournal'].rows(db))
        self.assertIn('body-aware-balanced-v2-safe', rows)
        self.assertIn('manual', rows)
        self.assertIn('automatic', rows)

    def test_deferred_after_restart_and_independent_battle_flag_for_legacy_frame(self):
        first, legacy = self.photo(505,932), self.photo(801,1000)
        existing = {'x':-1,'y':3,'zoom':1.15,'fit':'contain'}
        self.character['collection'] = {'frames':{'image:'+legacy['id']:existing}}
        self.store.save()
        state = self.fill_page(first, analyses=[LOWER_LEGS])
        self.crop('save', revision=state['revision'], reviews=self.decisions(state, (first,'later')))
        self.store = R['LibraryStore'](self.store.root)
        state = self.crop('state', media_ids=[legacy['id']], analyze=False)
        self.assertEqual(state['queue']['later'], [first['id']])
        self.assertEqual(state['proposals'][legacy['id']]['options']['suggested']['frame'], existing)
        self.crop('save', revision=state['revision'], reviews=self.decisions(state, (legacy,'flag')))
        flagged = self.crop('state', media_ids=[legacy['id']], analyze=False)
        self.assertEqual(flagged['queue']['flagged'], [legacy['id']])
        self.assertEqual(flagged['queue']['later'], [first['id']])
        saved = self.crop('save', revision=flagged['revision'],
                          reviews=self.decisions(flagged, (legacy,'suggested')))['collection']
        self.assertEqual(saved['frames']['image:'+legacy['id']], existing)
        self.assertNotIn('image:'+legacy['id'], saved['frame_meta'])
        self.assertNotIn(legacy['id'], saved['crop_review'])

    def test_save_and_undo_are_atomic_and_reject_changed_sources_and_frames(self):
        first, second, third = [self.photo(505,932) for _ in range(3)]
        page = self.fill_page(first, second, analyses=[LOWER_LEGS, LOWER_LEGS])
        reviews = self.decisions(page, (first,'fit'), (second,'fit'))
        stale = copy.deepcopy(reviews)
        stale[-1]['token'] = 'wrong'
        self.crop('save', expected=400, revision=page['revision'], reviews=stale)
        self.assertEqual(self.call()['collection']['frames'], {})
        saved = self.crop('save', revision=page['revision'], reviews=reviews)
        new = self.fill_page(third, analyses=[LIKELY])
        self.assertNotEqual(new['revision'], saved['collection']['revision'])
        undone = self.crop('undo', revision=saved['collection']['revision'], undo_token=saved['undo_token'])
        self.assertEqual(set(undone['collection']['frames']), {'image:'+third['id']})
        page = self.crop('state', media_ids=[first['id'], second['id']])
        saved = self.crop('save', revision=page['revision'], reviews=self.decisions(page, (first,'fit'), (second,'fit')))
        second['sha256'] = 'replacement'
        self.store.save()
        self.crop('undo', expected=400, revision=saved['collection']['revision'], undo_token=saved['undo_token'])
        self.assertEqual(self.call()['collection']['frames'], saved['collection']['frames'])
        fresh = self.crop('state', media_ids=[first['id']])
        self.edit('frame', self.call(), first, key='image:'+first['id'], frame={'x':1,'y':0,'zoom':1.1})
        self.crop('save', expected=400, revision=fresh['revision'], reviews=self.decisions(fresh, (first,'fit')))

    def test_saving_manual_review_can_restore_exact_automatic_record(self):
        item = self.photo(750,1333)
        state = self.fill_page(item, analyses=[LIKELY])
        key = 'image:' + item['id']
        original = self.call()['collection']
        reviews = self.decisions(state, (item,'manual'))
        reviews[0]['frame'] = {'x':2,'y':-3,'zoom':1.32,'fit':'contain'}
        saved = self.crop('save', revision=state['revision'], reviews=reviews)
        self.assertEqual(saved['collection']['frame_meta'][key]['mode'], 'manual')
        self.assertEqual(saved['collection']['frames'][key], reviews[0]['frame'])
        result = self.crop('undo', revision=saved['collection']['revision'], undo_token=saved['undo_token'])
        self.assertEqual(result['collection']['frame_meta'], original['frame_meta'])
        self.assertEqual(result['collection']['frames'], original['frames'])

    def test_failed_crop_save_and_undo_can_be_retried_without_partial_history(self):
        item = self.photo(750,1333)
        page = self.fill_page(item, analyses=[LIKELY])
        owner = self.character['id']

        def attempt(action, **body):
            return self.store.crop_review_edit('crop-review-' + action, {'character_id':owner, **body})

        def fail_then_retry(action, **body):
            snapshot = self.store.db_path.read_bytes()
            journal = self.store.tracking.export()
            with patch.object(self.store, '_write_atomic', side_effect=OSError('disk full')):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    attempt(action, **body)
            self.assertEqual(self.store.db_path.read_bytes(), snapshot)
            self.assertEqual(self.store.tracking.export(), journal)
            return attempt(action, **body)

        original = self.store.character(owner)['collection']
        saved = fail_then_retry('save', revision=page['revision'], reviews=self.decisions(page, (item,'suggested')))
        key = 'image:' + item['id']
        self.assertTrue(saved['collection']['frame_meta'][key]['checked'])
        restored = fail_then_retry('undo', revision=saved['collection']['revision'], undo_token=saved['undo_token'])
        self.assertEqual(restored['collection']['frames'], original['frames'])
        self.assertEqual(restored['collection']['frame_meta'], original['frame_meta'])

    def test_tracking_keeps_compact_photo_deltas_and_checkpoint_history(self):
        item = self.photo(750,1333)
        page = self.fill_page(item, analyses=[LIKELY])
        owner, mid = self.character['id'], item['id']
        key = 'image:' + mid
        collection = self.character['collection']
        for n in range(400):
            other = 'image:unrelated-' + str(n)
            collection['frames'][other] = {'x':n, 'y':0, 'zoom':1, 'fit':'contain'}
            collection['frame_meta'][other] = {'mode':'manual', 'notes':'untouched-frame-' * 80}
        collection['title_overrides'] = {'other-card':{'team_captain':'grant'}}
        self.store.save()
        before = self.call()['collection']
        initial = self.crop('state', media_ids=[mid])
        checkpoint = self.store.create_checkpoint({})
        def events():
            with closing(sqlite3.connect(self.store.tracking.path)) as db:
                return R['TrackingJournal'].rows(db)
        watermark = events()[-1]['seq']
        saved = self.crop('save', revision=initial['revision'], reviews=self.decisions(initial, (item,'suggested')))
        delta = [row for row in events() if row['seq'] > watermark]
        self.assertEqual(len(delta), 1)
        self.assertEqual((delta[0]['kind'], delta[0]['entity']), ('library.card_crop', mid))
        self.assertLess(len(json.dumps(delta)), 6000)
        self.assertNotIn('untouched-frame', json.dumps(delta))
        self.assertNotIn('other-card', json.dumps(delta))
        evidence = delta[0]['payload']
        self.assertEqual(evidence['character_id'], owner)
        self.assertEqual(evidence['actor'], 'manual')
        self.assertEqual(evidence['source']['after']['sha256'], item['sha256'])
        self.assertEqual(evidence['revision'], {'before':before['revision'], 'after':saved['collection']['revision']})
        checked = evidence['change']['changes']['frame_meta']
        self.assertFalse(checked['before']['checked'])
        self.assertTrue(checked['after']['checked'])
        self.assertNotIn('frames', evidence['change']['changes'])

        preview = self.store.checkpoint_preview({'id':checkpoint['id']})
        self.store.checkpoint_restore({'id':checkpoint['id'], 'token':preview['token']})
        existing = self.store.character(owner)['collection']
        self.assertEqual(existing['frames'], before['frames'])
        self.assertFalse(existing['frame_meta'][key]['checked'])
        history = R['TrackingJournal'].decode(self.store.tracking.export())
        per_photo = [row for row in history if row['kind'] == 'library.card_crop' and row['entity'] == mid]
        self.assertIn(delta[0], per_photo)
        self.assertFalse(per_photo[-1]['payload']['change']['changes']['frame_meta']['after']['checked'])
        other_journal = R['TrackingJournal'](self.store.root / 'transfer.sqlite3')
        other_journal.ingest(per_photo)
        other_journal.ingest(per_photo)
        exported = R['TrackingJournal'].decode(other_journal.export())
        self.assertEqual([r['payload'] for r in exported], [r['payload'] for r in per_photo])

    def test_tracking_keeps_manual_frame_and_other_collection_changes(self):
        item = self.photo(750,1333)
        initial = self.call()
        manual = {'x':2,'y':1,'zoom':1.1,'fit':'contain'}
        saved = self.edit('frame', initial, item, key='image:'+item['id'], frame=manual)
        attrs = copy.deepcopy(saved['collection']['attributes'])
        attrs[0]['value'] = 78
        self.call('save', revision=saved['collection']['revision'], attributes=attrs)
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            rows = R['TrackingJournal'].rows(db)
        photo = [row for row in rows if row['kind'] == 'library.card_crop'][-1]
        self.assertEqual(photo['payload']['change']['after']['frames'], manual)
        self.assertEqual(photo['payload']['source']['after']['sha256'], item['sha256'])
        setting = [row for row in rows if row['kind'] == 'library.characters'][-1]
        self.assertEqual(setting['payload']['change']['changes']['collection']['after']['attributes'], attrs)

    def test_analysis_does_not_hold_library_lock_or_overwrite_a_concurrent_manual_frame(self):
        item = self.photo(750,1333)
        started, release = threading.Event(), threading.Event()
        def analyze(_):
            started.set()
            self.assertTrue(release.wait(5))
            return LIKELY
        with patch.object(self.store, '_analyze_card_crop', side_effect=analyze), ThreadPoolExecutor() as executor:
            future = executor.submit(self.crop, 'state', media_ids=[item['id']])
            self.assertTrue(started.wait(5))
            try:
                key = 'image:' + item['id']
                manual = {'x':2,'y':1,'zoom':1.1,'fit':'contain'}
                saved = executor.submit(self.edit, 'frame', self.call(), item, key=key, frame=manual).result(4)
            finally:
                release.set()
            page = future.result(4)
        self.assertEqual(page['changed_frames'], {})
        self.assertEqual(page['proposals'][item['id']]['options']['suggested']['frame'], manual)
        self.assertEqual(self.call()['collection']['frames'], saved['collection']['frames'])

    def test_unavailable_provider_has_true_fit_and_explicit_retry(self):
        item = self.photo(505,932)
        result = self.fill_page(item, analyses=[{'status':'unavailable','reason':'offline'}])
        proposal = result['proposals'][item['id']]
        self.assertEqual(proposal['analysis_status'], 'unavailable')
        self.assertEqual(proposal['options']['fit']['frame'], {'x':0,'y':0,'zoom':1,'fit':'contain'})
        with patch.object(self.store, '_analyze_card_crop', return_value=LOWER_LEGS) as provider:
            retried = self.crop('state', media_ids=[item['id']], retry=True)
        provider.assert_called_once()
        self.assertEqual(retried['proposals'][item['id']]['analysis_status'], 'ready')


if __name__ == '__main__':
    unittest.main()
