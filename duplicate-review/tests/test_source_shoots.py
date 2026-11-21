import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import sha256, stat_key
from set_matching import WEIGHTS
from shoot_scene import SceneEvidence, describe, geometric_support
from source_shoots import combine, source_matches, verify_span


def vector(axis=0):
    values = np.zeros((3, 768), dtype=np.float32)
    values[:, axis] = np.sqrt(WEIGHTS)
    return values.ravel()


class ControlledScene:
    def __init__(self, views, bridges=()):
        self.views = views
        self.bridges = {frozenset(pair) for pair in bridges}

    def feature(self, ident):
        return None, None, None, np.array([1., 0.])

    def pair(self, a, b):
        if self.views.get(a, a) == self.views.get(b, b):
            return {'inliers': 48, 'area': .31}
        if frozenset((a, b)) in self.bridges:
            return {'inliers': 12, 'area': .031}
        return None

    def check_group(self, ids, options, compute):
        return compute()


class SourceShootTests(unittest.TestCase):
    def setUp(self):
        self.small = 'forum:small'
        self.large = 'forum:compilation'
        self.ids = [f'photo{n:02d}' for n in range(10)]
        order = ['before', *self.ids, 'after']
        self.items = {}
        for n, ident in enumerate(order):
            sources = {self.large: {'kind': 'forum'}}
            if ident in self.ids:
                sources[self.small] = {'kind': 'forum'}
            self.items[ident] = {'sha': ident, 'path': f'{n:04d}.jpg', 'sources': sources}
        self.vectors = {i: vector(0 if i in self.ids else 1) for i in order}
        self.scene = ControlledScene({i: int(n >= 3) for n, i in enumerate(self.ids)})
        self.groups = {'first': {'members': self.ids[2:3] + self.ids[6:7] + self.ids[8:9]}}
        self.groups['first']['auto_members'] = list(self.groups['first']['members'])

    def find(self, excluded=(), mixed=()):
        return source_matches(self.items, self.vectors, self.groups, set(excluded), set(mixed), self.scene)

    def test_ten_across_two_camera_angles_fill_existing_three_and_retry_is_empty(self):
        hits = self.find()
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit['scene']['camera_groups'], 2)
        self.assertEqual(hit['scene']['repeated_positions'], {self.large: [2, 11]})
        old = {'new': [], 'add': {}}
        plan = combine(old, hits, self.items, self.vectors, self.groups)
        self.assertEqual(plan['new'], [])
        additions = plan['add']['first']
        self.assertEqual(set(additions), set(self.ids) - set(self.groups['first']['members']))
        self.assertEqual(len(additions), 7)
        self.assertEqual(set(next(iter(additions.values()))['anchors']), set(self.groups['first']['members']))
        self.groups['first']['members'].extend(additions)
        self.assertEqual(self.find(), [])

    def test_multi_angle_needs_a_real_second_block_and_respects_existing_decisions(self):
        self.assertFalse(self.find(excluded=[self.ids[0]]))
        self.assertFalse(self.find(mixed=[self.large]))
        self.groups['other'] = {'members': [self.ids[5]]}
        self.assertFalse(self.find())
        del self.groups['other']
        self.items['after']['path'] = '0005a.jpg'  # Separates the saved original positions.
        self.assertFalse(any(set(hit['members']) == set(self.ids) for hit in self.find()))
        self.items.pop('before')
        self.items.pop('after')  # An identical repost is not independent confirmation.
        self.assertFalse(self.find())

    def test_new_draft_replaces_subset_and_held_anchors_are_never_exported(self):
        self.groups.clear()
        hit = self.find()[0]
        old = {'new': [{'members': self.ids[:3]}], 'add': {}}
        plan = combine(old, [hit], self.items, self.vectors, self.groups)
        self.assertEqual([set(g['members']) for g in plan['new']], [set(self.ids)])
        self.groups['first'] = {'members': self.ids[:3]}
        hit = self.find(excluded=[self.ids[0]])[0]
        self.assertEqual(set(hit['anchors']), set(self.ids[1:3]))
        self.assertFalse(self.find(excluded=self.ids[:2]))

    def test_weak_links_cannot_bridge_two_shoots_even_when_reposted(self):
        scene = ControlledScene(self.scene.views, [(self.ids[0], self.ids[3])])
        for repeated in (False, True):
            self.assertIsNone(verify_span(self.ids, self.vectors, scene, True, repeated))
        same_angle = ControlledScene(dict.fromkeys(self.ids[:5], 'same'))
        self.assertIsNotNone(verify_span(self.ids[:5], self.vectors, same_angle, True))


class PhotographicEvidenceTests(unittest.TestCase):
    def test_real_features_handle_reframing_and_ignore_watermarks(self):
        rng = np.random.default_rng(81)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = Image.new('RGB', (520, 400), '#091245')
            draw = ImageDraw.Draw(source)
            for _ in range(700):
                x, y, width = rng.integers([0, 0, 2], [520, 400, 16])
                color = tuple(int(v) for v in rng.integers(35, 235, size=3))
                draw.rectangle((int(x), int(y), int(x+width), int(y+width)), fill=color)
            a, b, c = [folder / (s+'.png') for s in 'abc']
            source.save(a)
            source.crop((38, 32, 472, 365)).resize(source.size).save(b)
            blank = Image.new('RGB', source.size, '#888080')
            blank.paste(source.crop((0, 366, 520, 400)), (0, 366))
            blank.save(c)
            self.assertIsNotNone(geometric_support(describe(a), describe(b)))
            self.assertIsNone(geometric_support(describe(a), describe(c)))
            items = {i: {'path': str(p), 'stamp': stat_key(p), 'sha': sha256(p)} for i, p in zip('ab', (a,b))}
            cache = folder / 'evidence.sqlite3'
            scene = SceneEvidence(items, cache_path=cache)
            result = scene.check_group(['a', 'b'], (True, False), lambda: {'ok': True})
            scene.close()
            scene = SceneEvidence(items, cache_path=cache)
            try:
                self.assertEqual(scene.check_group(['a', 'b'], (True, False), lambda: self.fail('cache missed')), result)
                blank.save(b)
                self.assertIsNone(scene.check_group(['a', 'b'], (True, False), lambda: self.fail('stale input admitted')))
            finally:
                scene.close()
