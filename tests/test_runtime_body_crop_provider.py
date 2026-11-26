"""Body-aware crop geometry, neutral preprocessing and local worker failure handling."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_runtime_stability import RUNTIME

GEOMETRY = RUNTIME['body_crop_geometry']
PROPOSAL = RUNTIME['body_crop_proposal']
GLOBALS = PROPOSAL.__globals__
Image = RUNTIME['Image']


def pose(points, mask=None):
    return {'landmarks': [{'x': points[index][0], 'y': points[index][1], 'visibility': .9, 'presence': .9}
                          if index in points else {} for index in range(33)], 'mask': mask}


def neutral_body():
    points = {0: (.49, .28), 1: (.47, .265), 2: (.46, .26), 4: (.50, .265), 5: (.51, .26),
              9: (.48, .30), 10: (.51, .30), 11: (.44, .36), 12: (.56, .37), 13: (.41, .48), 14: (.61, .48),
              15: (.40, .56), 16: (.62, .56), 23: (.47, .57), 24: (.53, .57), 25: (.45, .71), 26: (.55, .72),
              27: (.43, .88), 28: (.57, .88), 31: (.43, .90), 32: (.57, .90)}
    bins = [[row * 64 + column, 100] for row in range(12, 58) for column in range(25, 41)]
    mask = {'gridSize': 64, 'grid': bins, 'bounds': [25 / 64, 12 / 64, 41 / 64, 58 / 64],
            'foregroundPixels': len(bins) * 100, 'anchored': list(points), 'threshold': .65}
    return pose(points, mask)


class FrozenBodyCropGeometryTests(unittest.TestCase):
    def assertRender(self, result, expected):
        for actual, wanted in zip(result['render'], expected, strict=True):
            self.assertAlmostEqual(actual, wanted, places=12)

    def test_mask_supported_head_endpoints_and_variants_match_frozen_calibration(self):
        # Reference geometry came from the frozen calibration with synthetic pose and mask evidence.
        result = GEOMETRY((1000, 2000), [neutral_body()])
        self.assertEqual(result['status'], 'balanced-guided')
        self.assertRender(result, [.04545454545454549, -.24261363636363645, .9090909090909091, 1.3636363636363638])
        self.assertEqual(set(result['variants']), {'wider', 'fuller'})
        self.assertRender(result['variants']['wider'], [.07452466427336794, -.19804547267650577, .8509506714532641, 1.2764260071798963])
        self.assertRender(result['variants']['fuller'], [.034883720930232634, -.25703488372093025, .9302325581395348, 1.3953488372093024])
        self.assertIn('observedCrownGuard', result['evidence'])
        self.assertIn('observedDistalEdge', result['evidence'])
        self.assertEqual(result['evidence']['linkedEndpoints'], [15, 16, 27, 28, 31, 32])

    def test_weak_mask_shifts_small_trim_and_suppresses_unsafe_variant(self):
        weak = pose({0: (.018, .3), 11: (.10, .4), 23: (.17, .6)})
        result = GEOMETRY((810, 1000), [weak])
        self.assertEqual(result['status'], 'landmark-trim')
        self.assertRender(result, [0, 0, 1.08, 1])
        self.assertEqual(result['evidence']['protectedLandmarks'], [0, 11, 23])
        self.assertEqual(set(result['variants']), {'wider'})

        spread = pose({0: (.02, .3), 11: (.20, .45), 12: (.86, .45), 23: (.40, .6), 24: (.96, .61)})
        result = GEOMETRY((810, 1000), [spread])
        self.assertEqual(result['status'], 'default')
        self.assertRender(result, [0, .03703703703703707, 1, .9259259259259258])
        self.assertEqual(result['rect'], [0, 0, 1, 1])
        self.assertNotIn('variants', result)

    def test_multipose_and_no_pose_choose_conservative_geometry(self):
        result = GEOMETRY((1200, 1000), [neutral_body(), neutral_body()])
        self.assertEqual(result['status'], 'default')
        self.assertRender(result, [0, .1875, 1, .625])
        self.assertNotIn('variants', result)

        result = GEOMETRY((790, 1000), [])
        self.assertEqual(result['status'], 'centered-trim')
        self.assertRender(result, [-.026666666666666693, 0, 1.0533333333333335, 1])
        self.assertEqual(set(result['variants']), {'wider'})


class BodyCropProviderTests(unittest.TestCase):
    def make_photo(self, path):
        image = Image.new('RGB', (60, 80), (15, 60, 95))
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = 'private metadata fixture'
        image.save(path, format='JPEG', exif=exif)
        return path.read_bytes()

    def test_orientation_and_neutral_preview_preserve_original_input(self):
        with tempfile.TemporaryDirectory() as folder:
            photo = Path(folder) / 'original.jpg'
            original = self.make_photo(photo)
            data = RUNTIME['_body_crop_preview'](photo, (80, 60))
            with Image.open(io.BytesIO(data)) as preview:
                self.assertEqual(preview.size, (1000, 750))
                self.assertEqual(preview.mode, 'RGB')
                self.assertFalse(preview.getexif())
            self.assertEqual(photo.read_bytes(), original)
            self.assertEqual(PROPOSAL(photo, (60, 80), Path(folder) / 'cache')['status'], 'error')
            self.assertFalse((Path(folder) / 'cache').exists())

    def test_unverified_model_is_rejected_and_cached_valid_model_can_start_offline(self):
        good = b'pinned model fixture'
        digest = hashlib.sha256(good).hexdigest()
        with tempfile.TemporaryDirectory() as folder, patch.dict(GLOBALS, {
            'BODY_CROP_MODEL_SHA256': digest, '_BODY_CROP_MODEL_BYTES': len(good),
        }):
            cache = Path(folder)
            fetch = GLOBALS['urllib'].request
            with patch.object(fetch, 'urlopen', return_value=io.BytesIO(b'wrong model payload')):
                with self.assertRaisesRegex(ValueError, 'Unexpected pose model'):
                    RUNTIME['_body_crop_model'](cache)
                self.assertEqual(list((cache / 'models').iterdir()), [])
            with patch.object(fetch, 'urlopen', return_value=io.BytesIO(good)):
                model = RUNTIME['_body_crop_model'](cache)
            with patch.object(fetch, 'urlopen', side_effect=AssertionError('verified offline reuse should avoid network')):
                self.assertEqual(RUNTIME['_body_crop_model'](cache), model)
                self.assertEqual(model.read_bytes(), good)

    def test_success_and_failure_remove_preview_and_retry_with_fresh_worker(self):
        stopped = []

        class Worker:
            def __init__(self, cache):
                self.cache = cache
                self.preview_dir = cache
                self.preview_dir.mkdir(exist_ok=True)
                self.process = self

            def poll(self):
                return None

            def request(self, path):
                with Image.open(path) as preview:
                    assert preview.size == (1000, 750) and not preview.getexif()
                if not stopped:
                    raise ValueError('inference crash fixture')
                return []

            def close(self):
                stopped.append(self)

        with tempfile.TemporaryDirectory() as folder, patch.dict(GLOBALS, {
            '_BodyCropWorker': Worker, '_BODY_CROP_WORKER': None, '_BODY_CROP_START_FAILURE': None,
        }):
            photo = Path(folder) / 'original.jpg'
            self.make_photo(photo)
            cache = Path(folder) / 'cache'
            self.assertEqual(PROPOSAL(photo, (80, 60), cache)['status'], 'error')
            self.assertEqual(list(cache.iterdir()), [])
            self.assertEqual(len(stopped), 1)
            self.assertEqual(PROPOSAL(photo, (80, 60), cache)['status'], 'default')
            self.assertEqual(list(cache.iterdir()), [])
            self.assertIsNot(GLOBALS['_BODY_CROP_WORKER'], stopped[0])

    def test_setup_failure_is_retryable_and_has_no_proposal_geometry(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(GLOBALS, {
            '_BODY_CROP_WORKER': None, '_BODY_CROP_START_FAILURE': None, '_BODY_CROP_RETRY_DELAY': 0,
        }):
            photo = Path(folder) / 'original.jpg'
            self.make_photo(photo)
            cache = Path(folder) / 'cache'
            with patch.dict(GLOBALS, {'_BodyCropWorker': Mock(side_effect=OSError('offline fixture'))}):
                result = PROPOSAL(photo, (80, 60), cache)
                self.assertEqual(result['status'], 'unavailable')
                self.assertEqual(set(result), {'status', 'reason'})
                self.assertIsNone(GLOBALS['_BODY_CROP_WORKER'])
                self.assertEqual(GLOBALS['_BODY_CROP_START_FAILURE'][0], cache.resolve())
                PROPOSAL(photo, (80, 60), cache)
                self.assertEqual(GLOBALS['_BodyCropWorker'].call_count, 2)


if __name__ == '__main__':
    unittest.main()
