import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from test_auto_sets import descriptor
from engine import sha256, stat_key
from shoot_context import numbered_series, shared_highlights
from shoot_scene import SceneEvidence
from source_shoots import combine, source_matches, verify_span


def texture(seed):
    rng = np.random.default_rng(seed)
    image = Image.new('RGB', (440, 360), (95, 150, 224))
    draw = ImageDraw.Draw(image)
    for _ in range(2000):
        x, y = rng.integers([0, 0], image.size)
        width, height = rng.integers(2, 18, size=2)
        v = int(rng.integers(-68, 68))
        draw.rectangle((int(x), int(y), int(x + width), int(y + height)), fill=(95+v, 150+v, min(255,224+v)))
    return image


class ShootContextTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.post = 'forum:session'
        self.ids = list('abcdefgh')
        self.items, self.vectors = {}, {}
        original = texture(17)
        for n, ident in enumerate(self.ids):
            wide = n % 3 != 1
            picture = original.crop((2*n, n, 420 + n, 345 + n)).resize(original.size) if wide else texture(40+n)
            path = Path(folder.name) / f'IMG_{750+n:04d}_attachment.jpg'
            picture.save(path, quality=92)
            self.items[ident] = {'sha': sha256(path), 'stamp': stat_key(path), 'path': str(path),
                                 'sources': {self.post: {'kind':'forum'}}}
            self.vectors[ident] = descriptor(0, 1 if wide else 2+n, 1 if wide else 2+n)
        self.scene = SceneEvidence(self.items)
        self.addCleanup(self.scene.close)

    def test_real_texture_crops_fill_an_existing_partial_set_or_one_new_draft(self):
        self.assertTrue(numbered_series(self.items, self.ids, self.post))
        partial = dict.fromkeys('acd')
        for groups in ({}, {'older': {'members': list(partial), 'auto_members': list(partial)}}):
            hits = source_matches(self.items, self.vectors, groups, set(), set(), self.scene)
            whole = next(h for h in hits if h['members'] == self.ids)
            proof = whole['scene']
            self.assertEqual(set(proof['scene_core']), set('acdfg'))
            self.assertEqual(set(proof['crop_witnesses']), set('beh'))
            self.assertTrue(all(len(set(peers) & set(proof['scene_core'])) >= 2
                                for peers in proof['crop_witnesses'].values()))
            plan = combine({'new': [], 'add': {}}, hits, self.items, self.vectors, groups)
            if groups:
                self.assertEqual(set(plan['add']['older']), set(self.ids) - partial.keys())
                self.assertEqual(plan['new'], [])
            else:
                self.assertEqual([h['members'] for h in plan['new']], [self.ids])
        for excluded, mixed in [({'b'}, set()), (set(), {self.post})]:
            hits = source_matches(self.items, self.vectors, {}, excluded, mixed, self.scene)
            self.assertFalse(any(h['members'] == self.ids for h in hits))

    def test_numbering_and_same_coloring_do_not_identify_a_shoot(self):
        # Two subjects can share export settings, styling, filenames and a post.
        path = Path(self.items['e']['path'])
        with Image.open(self.items['b']['path']) as other:
            other.crop((5, 7, 425, 349)).resize(other.size).save(path, quality=92)
        self.items['e'].update(stamp=stat_key(path), sha=sha256(path))
        self.assertIsNone(verify_span(self.ids, self.vectors, self.scene, True, numbered=True))

    def test_direct_scene_witnesses_can_work_without_numbered_filenames(self):
        wide = list('acdfg')
        self.vectors['a'] = descriptor(0, 76, 83)
        self.assertFalse(numbered_series(self.items, wide, self.post))
        proof = verify_span(wide, self.vectors, self.scene, True)
        self.assertEqual(proof['method'], 'multiple-direct-scene-witnesses')
        self.assertEqual(proof['scene_core'], wide)
        self.assertEqual(proof['crop_witnesses'], {})

    def test_similar_midtones_with_a_different_light_source_do_not_complete_a_post(self):
        def style(rgb):
            return None, None, None, np.array(rgb, dtype=float)
        core = {0, 1, 2, 3, 4}
        references = [style((80+n, 180+n, 251+n%3)) for n in core]
        self.assertTrue(shared_highlights(references + [style((90, 178, 250))], core, {5}))
        self.assertFalse(shared_highlights(references + [style((205, 218, 250))], core, {5}))
        self.assertFalse(shared_highlights(references + [style((75, 160, 216))], core, {5}))
        self.assertFalse(shared_highlights([style((250, 248, 252))]*6, core, {5}))

    def test_source_gaps_missing_context_and_visually_unrelated_frame_abstain(self):
        self.assertIsNone(verify_span(self.ids, self.vectors, self.scene, True))
        self.items['a']['origins'] = [{'key': self.post, 'original_path': r'C:\source\DSC_0190.jpg'}]
        self.assertFalse(numbered_series(self.items, self.ids, self.post))
        self.items['a']['origins'] = [{'key': self.post, 'original_path': r'C:\restored\IMG_0750_archived.jpg'}]
        self.assertTrue(numbered_series(self.items, self.ids, self.post))
        self.vectors['h'] = descriptor(201)
        self.assertIsNone(verify_span(self.ids, self.vectors, self.scene, True, numbered=True))

    def test_small_scene_core_and_a_single_crop_with_a_rival_destination_abstain(self):
        self.assertIsNone(verify_span(self.ids[:6], self.vectors, self.scene, True, numbered=True))
        self.vectors.update(other1=self.vectors['b'], other2=self.vectors['b'])
        groups = {'rival': {'members': ['other1', 'other2']}}
        hits = source_matches(self.items, self.vectors, groups, set(), set(), self.scene)
        self.assertTrue(any(h['members'] == self.ids for h in hits))
        plan = combine({'new': [], 'add': {}}, hits, self.items, self.vectors, groups)
        self.assertFalse(any(h['members'] == self.ids for h in plan['new']))
