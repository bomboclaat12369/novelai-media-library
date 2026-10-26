import base64,hashlib,io,json,re,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from updater import Updater,MANIFEST,REPOSITORY,active_program

ROOT=Path(__file__).resolve().parents[1]
def payload(extra=None):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob('*'):
            if p.is_file() and p.suffix in ('.py','.html','.js','.txt') and 'tests' not in p.parts and '__pycache__' not in p.parts:
                data=p.read_bytes()
                if p.name=='engine.py':data=re.sub(rb"^VERSION = .*",b"VERSION = '2.0.1'",data,flags=re.M)
                z.writestr('duplicate-review/'+p.relative_to(ROOT).as_posix(),data)
        z.writestr('runtime-src/companion-runtime.pyw',(ROOT.parent/'runtime-src/companion-runtime.pyw').read_bytes())
        if extra:z.writestr(*extra)
    return out.getvalue()

class UpdaterTests(unittest.TestCase):
    def test_verified_update_is_staged_then_activated_without_touching_data(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db=root/'review.sqlite3';db.write_bytes(b'Existing scan database');raw=payload();encoded=base64.b64encode(raw);url=REPOSITORY+'a'*40+'/payload/update.txt'
            manifest={'schema':1,'version':'2.0.1','sha256':hashlib.sha256(raw).hexdigest(),'parts':[{'url':url,'sha256':hashlib.sha256(encoded).hexdigest()}]}
            fetch=lambda u,*_:json.dumps(manifest).encode() if u==MANIFEST else encoded
            updater=Updater(root,'2.0.0',ROOT,fetch)
            updater.start(True);updater.thread.join(10)
            self.assertTrue(updater.status()['ready'],updater.status());self.assertIsNone(active_program(root));self.assertEqual(db.read_bytes(),b'Existing scan database')
            updater.activate();self.assertTrue(active_program(root).is_file());self.assertEqual(db.read_bytes(),b'Existing scan database')
            previous=(root/'updates/active.json').read_bytes()
            bad=Updater(root,'2.0.0',ROOT,lambda u,*_:json.dumps(manifest).encode() if u==MANIFEST else b'corrupt')
            bad.start(True);bad.thread.join(10);self.assertFalse(bad.status()['ready']);self.assertEqual((root/'updates/active.json').read_bytes(),previous)

    def test_archive_cannot_write_outside_version_directory(self):
        for name in ('../review.sqlite3','duplicate-review/../../review.sqlite3','duplicate-review/C:/evil.py','duplicate-review/..\\evil.py'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as t:
                updater=Updater(Path(t),'2.0.0',ROOT)
                with self.assertRaises(ValueError):updater.stage(payload((name,b'bad')),'2.0.1')
                self.assertIsNone(active_program(Path(t)))

if __name__=='__main__':unittest.main()
