import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_organizer import fixture, add_instagram
from source_navigation import focus_photo
from engine import stat_key


def browser_inventory(bulk, org, ids):
    """Two collections share the post key. The selected photo has never been imported."""
    from PIL import Image
    source = 'forum:fixture:381'
    original = bulk.current
    folder = Path(org.engine.state_dir).parent / 'history'
    folder.mkdir()
    photos = []
    for n in range(121):
        path = folder / f'{121-n:03}.jpg'
        Image.new('RGB', (160,240), (n*2,55,50+n)).save(path)
        # Store distinct valid JPEGs, including the file's identifying trailing bytes.
        with path.open('ab') as file:file.write(str(n).encode())
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        origin = dict(key=source, kind='forum', label='Original photo post', path=f'original/frame-{n+1:03}.jpg')
        item = dict(id=sha, sha=sha, path=str(path), stamp=stat_key(path), sources={source:origin},
                    origins=[origin], copies=[], existing_sets=[])
        original['source_catalog'][sha] = item
        photos.append(sha)
    bulk.persist()
    org.bind()
    org.mutate('draft',dict(job=original['id'],ids=[ids[3]],new_name='Unfinished shoot'))
    org.page('post','post:1',order='similar')
    other = copy.deepcopy(original)
    other['id'] = 'other-job'
    other['config']['roots'] = [str(folder.parent / 'other-collection')]
    other['source_catalog'] = {photos[0]: other['source_catalog'][photos[0]]}
    bulk.current = other
    bulk.persist()
    return dict(collection=original['collection_id'], other=other['collection_id'], post=source,
                focus=photos[96], before=photos[95], after=photos[97], job=original['id'])


class SourceNavigationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.engine, self.bulk, self.org, self.ids = fixture(temp.name)
        self.collection = self.bulk.current['collection_id']
        offline = patch.object(self.engine.library, 'request', side_effect=ValueError('Disconnected fixture.'))
        offline.start()
        self.addCleanup(offline.stop)

    def locate(self, collection, post='post:1', photo='', job=None):
        return self.org.open_source_post(dict(job=job or self.bulk.current['id'], collection=collection, post=post, photo=photo))

    def other_collection(self, ids=None):
        job = copy.deepcopy(self.bulk.current)
        job['id'] = 'other-job'
        job['config']['roots'] = [str(Path(self.engine.state_dir).parent / 'other')]
        if ids is not None:
            job['source_catalog'] = {i: job['source_catalog'][i] for i in ids}
        self.bulk.current = job
        self.bulk.persist()
        self.org.bind()
        return job['collection_id']

    def test_copy_focus_original_order_and_existing_review(self):
        add_instagram(self.bulk, self.ids)
        photo = 'ab' * 32
        self.bulk.current['source_catalog'][self.ids[1]]['copies'].append({'sha': photo})
        self.bulk.persist()
        self.org.bound = None
        self.org.bind()
        self.org.mutate('draft', dict(job='fixture-job', ids=[self.ids[4]], new_name='Unfinished shoot'))
        state = self.org.state()
        post = 'instagram:test_account:P2'
        located = self.locate(self.collection, post, photo.upper())
        self.assertEqual(located, {'job':'fixture-job','post':post,'focus':self.ids[1]})
        page = self.org.page('post', post, order='original', focus_id=located['focus'], expected_job=located['job'])
        self.assertEqual(page['ids'], [self.ids[2],self.ids[1],self.ids[0]])
        self.assertEqual(page['focus_id'], self.ids[1])
        self.assertEqual(self.org.state()['selection'], state['selection'])
        self.assertEqual(self.org.state()['new_name'], state['new_name'])
        self.assertEqual(self.locate(self.collection, post)['focus'], '')

    def test_exact_collection_and_old_window_guard(self):
        original = self.org.sets()
        other = self.other_collection(self.ids[:2])
        self.assertNotEqual(self.collection, other)
        for collection, post, photo in [(other,'post:1',self.ids[3]), ('missing','post:1',self.ids[0]),
                                        (self.collection,'missing',self.ids[0]), (self.collection,'post:1','c:/source.jpg')]:
            with self.assertRaises(ValueError):
                self.locate(collection, post, photo)
            self.assertEqual(self.bulk.current['id'], 'other-job')
        with self.assertRaisesRegex(ValueError, 'another window'):
            self.locate(self.collection, photo=self.ids[3], job='stale-display')
        self.engine.status['running'] = True
        with self.assertRaisesRegex(ValueError, 'pause'):
            self.locate(self.collection, photo=self.ids[3])
        self.engine.status['running'] = False
        located = self.locate(self.collection, photo=self.ids[3])
        self.assertEqual(located, dict(job='fixture-job',post='post:1',focus=self.ids[3]))
        self.assertEqual(self.org.sets(), original)
        with self.assertRaisesRegex(ValueError, 'another window'):
            self.org.page('post', 'post:1', expected_job='other-job')

    def test_hidden_photo_does_not_switch_active_collection(self):
        ident = self.ids[3]
        with self.org.db() as db:
            db.execute('INSERT INTO parked VALUES (?,?,?)',(self.org.scope,'post:1',ident))
        self.other_collection(self.ids[:1])
        with self.assertRaisesRegex(ValueError, 'no longer visible'):
            self.locate(self.collection, photo=ident)
        self.assertEqual(self.bulk.current['id'],'other-job')

    def test_older_job_with_collection_identity_only_in_the_tracking_journal(self):
        self.other_collection(self.ids[:2])
        with self.bulk.db() as db:
            db.execute("UPDATE jobs SET data=json_remove(data,'$.collection_id') WHERE id='fixture-job'")
        located = self.locate(self.collection,photo=self.ids[3])
        self.assertEqual(located,dict(job='fixture-job',post='post:1',focus=self.ids[3]))

    def test_ambiguous_copy_and_photo_from_a_different_post(self):
        sha = 'f' * 64
        self.org.catalog[self.ids[2]]['copies'].append({'sha':sha})
        self.org.catalog[self.ids[3]]['copies'].append({'sha':sha})
        with self.assertRaisesRegex(ValueError,'More than one'):
            self.locate(self.collection,photo=sha)
        with self.assertRaisesRegex(ValueError, 'no longer visible'):
            self.locate(self.collection,photo=self.ids[10])
        catalog={'unresolved':{'sha':sha,'quarantine_only':True},'keeper':{'sha':self.ids[0],'copies':[{'sha':sha}]}}
        self.assertEqual(focus_photo(catalog,list(catalog),sha),'keeper')

    def test_current_post_can_open_while_its_visual_index_is_running(self):
        with patch.dict(self.org.job,running=True):
            self.assertEqual(self.locate(self.collection,photo=self.ids[3])['focus'],self.ids[3])

    def test_legacy_source_resolves_to_its_merged_character_section(self):
        job = self.bulk.current
        job['config']['character_id'] = 'person-a'
        self.bulk.persist()
        secondary = self.other_collection([self.ids[4]])
        # Create a real character section backed by both saved folder inventories.
        def library(path):
            if path == '/api/library':return {'characters':[{'id':'person-a','name':'A'},{'id':'person-b','name':'B'}]}
            if path == '/api/tracking/status':return {'instance':'fixture-library'}
            raise ValueError('Disconnected fixture.')
        self.bulk.activate('fixture-job')
        self.org.bound = None
        with patch.object(self.engine.library, 'request', side_effect=library):
            self.org.refresh_collections({'job':'fixture-job'})
        primary_section = self.bulk.current['id']
        other_section = next(s['id'] for s in self.bulk.sections.rows() if s['character_id']=='person-b')
        self.org.switch_collection({'job':primary_section,'id':other_section})
        with self.assertRaises(ValueError):
            self.locate(secondary,photo=self.ids[3])
        self.assertEqual(self.bulk.current['id'],other_section)
        self.assertEqual(self.locate(secondary,photo=self.ids[4])['job'],primary_section)
        self.assertEqual(self.org.collection_id,self.collection)


if __name__ == '__main__':
    unittest.main()
