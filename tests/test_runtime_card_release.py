"""The full-quality card release must work through both verified update routes."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import test_runtime_stability as fixtures

class CardRelease(unittest.TestCase):
    def test_full_quality_document_loads_and_coordinated_update_accepts_it(self):
        root=Path(__file__).resolve().parents[1]
        release=json.loads((root/'release-standalone.json').read_text())
        html=(root/f"payload/standalone-{release['version']}.html").read_bytes()
        self.assertGreater(len(html),12*1024*1024)
        UI=fixtures.RUNTIME['StandaloneUI']
        self.assertLess(len(html),UI.MAX_DOCUMENT_BYTES)
        code=b'// synthetic unchanged overlay'
        manifest={'standalone_version':release['version'],'standalone_url':UI.BASE+'standalone.html','standalone_sha256':hashlib.sha256(html).hexdigest(),'userscript_payload_version':'2.8.99','userscript_parts':[UI.BASE+'overlay.js'],'userscript_sha256':hashlib.sha256(code).hexdigest()}
        requests=[]
        def download(url,limit,*args):
            data=json.dumps(manifest).encode() if 'manifest.json' in url else code if url.endswith('overlay.js') else html
            requests.append((url,limit))
            if len(data)>limit:raise ValueError('Standalone payload is too large')
            return data
        with tempfile.TemporaryDirectory() as directory:
            ui=UI(Path(directory));ui._download=download
            self.assertEqual(ui.document(force=True),html)
            updates=fixtures.RUNTIME['UIUpdates'](ui);updates.check(force=True)
            self.assertEqual(updates.error,'')
            self.assertEqual(ui.cached,html)
            self.assertEqual(updates.html_digest,manifest['standalone_sha256'])
        html_requests=[limit for url,limit in requests if url.endswith('standalone.html')]
        self.assertEqual(html_requests,[UI.MAX_DOCUMENT_BYTES,UI.MAX_DOCUMENT_BYTES])

if __name__=='__main__':unittest.main()
