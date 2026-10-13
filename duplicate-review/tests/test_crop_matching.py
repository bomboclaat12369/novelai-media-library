import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import ImageOps, ImageEnhance
from engine import Engine
from test_engine import artwork

class CropTests(unittest.TestCase):
    def test_crops_mirrors_rotation_brightness_and_negative(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); inc=root/'incoming';ref=root/'reference';inc.mkdir();ref.mkdir()
            image=artwork();image.save(ref/'original.png')
            cropped=image.crop((60,100,600,800))
            cropped.save(inc/'crop.jpg',quality=78)
            ImageOps.mirror(cropped).save(inc/'mirror.jpg')
            cropped.rotate(90,expand=True).save(inc/'rotate.jpg')
            ImageEnhance.Brightness(cropped).enhance(1.15).save(inc/'bright.jpg')
            artwork(765).save(inc/'different.jpg')
            e=Engine(root/'state');e.start([str(inc)],[str(ref)],'broad');e.thread.join(30)
            self.assertEqual(e.status['phase'],'Scan complete',e.status)
            groups=e.groups()['groups'];self.assertEqual(len(groups),1)
            files=e.groups(groups[0]['id'])['files']
            self.assertEqual({Path(r['path']).name for r in files},{'original.png','crop.jpg','mirror.jpg','rotate.jpg','bright.jpg'})
            self.assertEqual(e.preview_exact(include_pixels=True)['count'],0)
            with patch('crop_match.describe',side_effect=AssertionError('cache missed')):
                e.start([str(inc)],[str(ref)],'broad');e.thread.join(30)
            self.assertEqual(e.status['errors'],0)
    def test_decode_failure_is_visible_incomplete_scan(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inc=root/'incoming';inc.mkdir();(inc/'bad.jpg').write_bytes(b'broken')
            e=Engine(root/'state');e.start([str(inc)],[],'broad');e.thread.join(10)
            self.assertIn('incomplete',e.status['phase'])
            self.assertEqual(e.view()['coverage']['discovered'],1)
            self.assertEqual(e.view()['coverage']['scanned'],0)
    def test_feature_failure_does_not_remove_exact_matching(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inc=root/'incoming';inc.mkdir();artwork().save(inc/'a.png');(inc/'b.png').write_bytes((inc/'a.png').read_bytes())
            e=Engine(root/'state')
            with patch('crop_match.describe',side_effect=RuntimeError('feature failure')):
                e.start([str(inc)],[],'broad');e.thread.join(10)
            self.assertIn('incomplete',e.status['phase'])
            self.assertEqual(e.view()['stats']['total'],2)
            self.assertEqual(e.preview_exact(include_pixels=True)['count'],1)

if __name__=='__main__':unittest.main()
