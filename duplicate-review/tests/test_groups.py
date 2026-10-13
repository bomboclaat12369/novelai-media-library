from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import PngImagePlugin
from engine import Engine, pixel_digest, sha256
from test_engine import artwork

class GroupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.source=self.base/'downloads';self.source.mkdir()
        self.engine=Engine(self.base/'state')
    def tearDown(self):
        if self.engine.thread:self.engine.thread.join(20)
        self.temp.cleanup()
    def scan(self):
        self.engine.start([str(self.source)],[],'balanced');self.engine.thread.join(20)
        self.assertEqual(self.engine.status['phase'],'Scan complete')
    def files(self):
        with self.engine.db() as db:return [dict(r) for r in db.execute('SELECT * FROM files')]
    def fixture(self):
        old=self.source/'2024-02-27';new=self.source/'2025-08-03';old.mkdir();new.mkdir()
        im=artwork();info=PngImagePlugin.PngInfo();info.add_text('Comment','Different metadata')
        im.save(old/'older.png',compress_level=0)
        im.save(new/'newest.png',compress_level=9,pnginfo=info)
        shutil.copy2(new/'newest.png',old/'exact.png')
        im.resize((320,420)).save(old/'smaller.jpg',quality=70)
        different=artwork(62);different.save(new/'different.jpg')
        shutil.copy2(new/'different.jpg',old/'different-copy.jpg')
        return old,new
    def test_pixels_group_count_sort_and_newest_keeper(self):
        old,new=self.fixture();self.scan()
        groups=self.engine.groups()['groups']
        self.assertEqual([g['count'] for g in groups],[4,2])
        self.assertEqual([g['count'] for g in self.engine.groups(sort='fewest')['groups']],[2,4])
        rows=self.files();by_name={Path(r['path']).name:r for r in rows}
        a,b=by_name['older.png'],by_name['newest.png']
        self.assertNotEqual(a['sha'],b['sha']);self.assertEqual(a['pixel'],b['pixel'])
        plan=self.engine.preview_exact(include_pixels=True)
        self.assertEqual(plan['count'],3) # two PNG copies and one other exact copy
        self.assertTrue(all('/2025-08-03/' in r['keep'] for r in plan['moves']))
        selection=[{k:r[k] for k in ('target','keeper','proof')} for r in plan['moves']]
        self.engine.move_selection(selection,self.engine.revision);self.engine.thread.join(20)
        self.assertTrue((new/'newest.png').exists());self.assertTrue((old/'smaller.jpg').exists())
        self.assertFalse((old/'older.png').exists());self.assertFalse((old/'exact.png').exists())
        self.assertEqual(self.engine.view()['stats']['moved'],3)
        self.engine.undo();self.engine.thread.join(20)
        self.assertTrue((old/'older.png').exists())
    def test_dimensions_do_not_auto_select_different_pixels(self):
        im=artwork();im.save(self.source/'a.png');changed=im.copy();changed.putpixel((40,40),(0,0,0));changed.save(self.source/'b.png')
        self.scan();self.assertEqual(self.engine.preview_exact(include_pixels=True)['count'],0)
        self.assertNotEqual(pixel_digest(self.source/'a.png'),pixel_digest(self.source/'b.png'))
    def test_manual_group_moves_have_batch_undo_and_protect_last_copy(self):
        self.fixture();self.scan();g=self.engine.groups()['groups'][0]
        members=self.engine.groups(g['id'])['files'];keeper=members[0]
        selections=[dict(target=r['id'],keeper=keeper['id'],proof='manual') for r in members[1:]]
        self.engine.move_selection(selections,self.engine.revision);self.engine.thread.join(20)
        self.assertEqual(self.engine.view()['stats']['moved'],3)
        self.engine.undo();self.engine.thread.join(20)
        self.assertEqual(self.engine.view()['stats']['moved'],0)
        with self.assertRaisesRegex(ValueError,'Keep at least'):
            self.engine.move_selection([dict(target=members[0]['id'],keeper=members[1]['id']),dict(target=members[1]['id'],keeper=members[0]['id'])],self.engine.revision)
    def test_group_dismiss_persistence_and_stale_selection(self):
        self.fixture();self.scan();g=self.engine.groups()['groups'][0]
        revision=self.engine.revision
        self.engine.dismiss_group(g['id'],revision)
        self.assertEqual(len(self.engine.groups()['groups']),1)
        with self.assertRaisesRegex(ValueError,'review changed'):
            self.engine.move_selection([dict(target=1,keeper=2)],revision)
        self.scan();self.assertEqual(len(self.engine.groups()['groups']),1)
    def test_existing_exact_button_also_keeps_newest_folder(self):
        old,new=self.fixture();self.scan()
        plan=self.engine.preview_exact()
        exact=next(m for m in plan['moves'] if m['move'].endswith('exact.png'))
        self.assertEqual(exact['keep'],str(new/'newest.png'))

if __name__=='__main__':unittest.main()
