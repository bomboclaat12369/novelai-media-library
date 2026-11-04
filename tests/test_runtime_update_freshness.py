"""Exercise stale release discovery without touching a real library or GitHub."""
import hashlib
import io
import json
import runpy
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
StandaloneUI = runpy.run_path(str(ROOT / 'runtime-src/companion-runtime.pyw'))['StandaloneUI']


class UpdateFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ui = StandaloneUI(Path(self.temp.name))
        self.version = '2.9.22'
        self.calls = []
        self.api_error = None
        self.corrupt = False
        self.offline = False
        self.patcher = patch('urllib.request.urlopen', side_effect=self.download)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def html(self, version):
        return f'<html data-nai-media-payload-version="{version}">'.encode()

    def download(self, request, **kwargs):
        url = request.full_url
        self.calls.append(url)
        if self.offline:
            raise urllib.error.URLError('offline')
        if url.startswith(self.ui.MANIFEST_API):
            if self.api_error:
                raise self.api_error
            self.assertEqual(request.get_header('Accept'), 'application/vnd.github.raw+json')
            version = self.version
        elif '/manifest.json?' in url:
            version = '2.9.22'  # Simulate a stale raw-GitHub branch cache.
        else:
            self.assertTrue(url.startswith(self.ui.BASE + 'payload/'))
            return io.BytesIO(b'corrupt' if self.corrupt else self.html(url.rsplit('/', 1)[1]))
        return io.BytesIO(json.dumps({'standalone_url': self.ui.BASE + 'payload/' + version,
                                    'standalone_sha256': hashlib.sha256(self.html(version)).hexdigest()}).encode())

    def test_manual_check_sees_new_release_despite_stale_raw_and_local_caches(self):
        self.assertEqual(self.ui.document(), self.html('2.9.22'))
        self.version = '2.9.23'
        count = len(self.calls)
        self.assertEqual(self.ui.document(), self.html('2.9.22'))
        self.assertEqual(len(self.calls), count, 'normal loads retain the local cooldown')
        self.assertEqual(self.ui.document(force=True), self.html('2.9.23'))
        manifests = [u for u in self.calls if '/manifest.json?' in u]
        self.assertEqual(len(manifests), 2)
        self.assertNotEqual(*manifests, 'each check uses a unique manifest URL')
        self.assertTrue(all(u.startswith(self.ui.MANIFEST_API) for u in manifests))
        self.assertTrue(all('?' not in u for u in self.calls if '/payload/' in u))
        self.assertEqual(StandaloneUI(Path(self.temp.name)).document(), self.html('2.9.23'))

    def test_api_quota_or_outage_falls_back_to_cache_busted_raw(self):
        for error in [urllib.error.HTTPError(self.ui.MANIFEST_API, 403, 'quota', {}, None), TimeoutError()]:
            self.api_error = error
            self.assertEqual(self.ui.document(force=True), self.html('2.9.22'))
            self.assertTrue(any(u.startswith(self.ui.BASE + 'manifest.json?_=') for u in self.calls))

    def test_corrupt_release_cannot_replace_verified_offline_copy(self):
        self.ui.document()
        path = self.ui.directory / 'standalone.json'
        before = path.read_bytes()
        self.version = '2.9.23'
        self.corrupt = True
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            self.ui.document(force=True)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.ui.cached, self.html('2.9.22'))
        self.offline = True
        with self.assertRaises(urllib.error.URLError):
            self.ui.document(force=True)  # Never report a failed manual check as up to date.
        self.ui.checked_at = 0
        self.assertEqual(self.ui.document(), self.html('2.9.22'))

    def test_manifest_size_and_download_origin_stay_restricted(self):
        with patch('urllib.request.urlopen', return_value=io.BytesIO(b'x' * 11)):
            with self.assertRaisesRegex(ValueError, 'manifest is too large'):
                self.ui._download(self.ui.BASE + 'manifest.json?_=test', 10)
        with self.assertRaisesRegex(ValueError, 'Untrusted'):
            self.ui._download('https://example.com/payload', 100)


if __name__ == '__main__':
    unittest.main()
