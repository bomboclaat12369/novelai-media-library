from pathlib import Path
import shutil
import tempfile
import unittest
from test_engine import artwork
from engine import Engine

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.source=self.base/'incoming';self.source.mkdir();self.engine=Engine(self.base/'state')
    def tearDown(self):
        if self.engine.thread:self.engine.thread.join(20)
        self.temp.cleanup()
    def scan(self):
        self.engine.start([str(self.source)],[],'balanced');self.engine.thread.join(20)
        self.assertEqual(self.engine.status['phase'],'Scan complete')
    def fixture(self):
        a=artwork();a.save(self.source/'a.png');shutil.copyfile(self.source/'a.png',self.source/'a-copy.png')
        b=a.copy();b.putpixel((310,100),(255,255,255));b.save(self.source/'b.png');shutil.copyfile(self.source/'b.png',self.source/'b-copy.png')
        self.scan();g=self.engine.groups()['groups'][0];return g,self.engine.groups(g['id'])['files']
    def test_different_image_splits_entire_family_and_survives_restart_rescan(self):
        g,files=self.fixture();self.assertEqual(len(files),4)
        selected=[r['id'] for r in files if Path(r['path']).name.startswith('b')]
        self.engine.split_group(g['id'],selected,self.engine.revision)
        self.assertEqual([g['count'] for g in self.engine.groups()['groups']],[2,2])
        self.engine=Engine(self.base/'state');self.scan()
        self.assertEqual([g['count'] for g in self.engine.groups()['groups']],[2,2])
        # A freshly downloaded exact alias joins its own family, not the other pose.
        shutil.copyfile(self.source/'b.png',self.source/'b-third.png');self.scan()
        self.assertEqual([g['count'] for g in self.engine.groups()['groups']],[3,2])
    def test_cannot_split_verified_copies_apart(self):
        g,files=self.fixture()
        with self.assertRaisesRegex(ValueError,'every verified identical'):
            self.engine.split_group(g['id'],[files[0]['id']],self.engine.revision)
        self.assertEqual(len(self.engine.groups()['groups']),1)
    def test_multiple_keep_finish_batch_undo(self):
        g,files=self.fixture();keepers=[r for r in files if Path(r['path']).name in ('a.png','b.png')]
        for r in keepers:self.engine.mark_keep(g['id'],r['id'],True,self.engine.revision)
        self.engine=Engine(self.base/'state')
        self.engine.finish_group(g['id'],self.engine.revision);self.engine.thread.join(20)
        self.assertTrue(all(Path(r['path']).exists() for r in keepers));self.assertEqual(self.engine.view()['stats']['moved'],2)
        self.assertEqual(self.engine.groups()['groups'],[])
        self.engine.undo();self.engine.thread.join(20)
        self.assertEqual(self.engine.view()['stats']['moved'],0);self.assertTrue(all(Path(r['path']).exists() for r in files))
    def test_automatic_selection_respects_manual_keep(self):
        g,files=self.fixture();chosen=next(r for r in files if Path(r['path']).name=='a-copy.png')
        self.engine.mark_keep(g['id'],chosen['id'],True,self.engine.revision)
        self.assertNotIn(chosen['id'],[m['target'] for m in self.engine.preview_exact(include_pixels=True)['moves']])

if __name__=='__main__':unittest.main()
