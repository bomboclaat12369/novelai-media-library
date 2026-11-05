"""Exercise real Git transfers against disposable local remotes, never GitHub."""
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
PUBLISHER = REPO / 'tools/publish-source-release.py'
RAW = 'https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/'


def git(root, *args, data=None):
    return subprocess.run(['git', '-C', str(root), *args], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


class SourceReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.remote = Path(self.temp.name) / 'remote.git'
        self.root.mkdir()
        git(self.root, 'init', '-q', '-b', 'main')
        git(self.root, 'config', 'user.name', 'Release Test')
        git(self.root, 'config', 'user.email', 'release-test@example.invalid')
        for name in ('build-release.py', 'build-standalone.py', 'build-duplicate-review.py', 'sync-ui-sources.py'):
            self.put('tools/' + name, (REPO / 'tools' / name).read_bytes())
        self.put('.gitignore', '.release-output/\n__pycache__/\n')
        self.put('payload/source.js', 'globalThis.example = 1;\n')
        self.put('standalone-src/bootstrap.js', '// bootstrap\n')
        self.put('runtime-src/companion-runtime.pyw', "VERSION = '1.0.0'\n")
        self.put('duplicate-review/engine.py', "VERSION = '1.0.0'\n")
        self.put('release-userscript.json', {'version': '1.0.0', 'parts': ['payload/source.js']})
        self.put('release-standalone.json', {'version': '1.0.0', 'parts': ['payload/source.js']})
        self.put('release-runtime.json', {'version': '1.0.0', 'source': 'runtime-src/companion-runtime.pyw'})
        self.put('release-duplicate-review.json', {'schema': 1, 'version': '0.9.0', 'sha256': '0' * 64, 'parts': []})
        self.put('manifest.json', {
            'schema': 2, 'unrelated': {'keep': True},
            'standalone_version': '0.9.0', 'standalone_sha256': '0' * 64,
            'runtime_version': '0.9.0', 'runtime_sha256': '0' * 64,
            'userscript_payload_version': '0.9.0', 'userscript_sha256': '0' * 64,
        })
        self.commit()
        git(self.root, 'clone', '-q', '--bare', str(self.root), str(self.remote))
        git(self.root, 'remote', 'add', 'origin', str(self.remote))

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, dict):
            value = json.dumps(value, indent=2) + '\n'
        path.write_bytes(value if isinstance(value, bytes) else value.encode())

    def commit(self, push=False):
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'Source fixture')
        if push:
            git(self.root, 'push', '-q', 'origin', 'main')

    def head(self):
        return git(self.remote, 'rev-parse', 'main').decode().strip()

    def remote_json(self, name):
        return json.loads(git(self.remote, 'show', 'main:' + name))

    def run_release(self, *args, fail=False):
        result = subprocess.run([sys.executable, str(PUBLISHER), *args], cwd=self.root,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        report = json.loads((self.root / '.release-output/report.json').read_text())
        self.assertEqual(result.returncode != 0, fail, report)
        self.assertLess(len(result.stdout) + len(result.stderr), 5000, 'Payload leaked into command output')
        return report

    def test_dry_run_large_document_has_small_output_and_no_remote_or_checkout_changes(self):
        self.put('payload/source.js', '// ' + 'X' * (17 * 1024 * 1024) + '\n')
        self.commit(push=True)
        head = self.head()
        report = self.run_release('--components', 'standalone')
        self.assertEqual(report['status'], 'dry_run_passed')
        self.assertGreater(report['artifacts']['standalone']['bytes'], 16 * 1024 * 1024)
        self.assertEqual(head, self.head())
        self.assertEqual(git(self.root, 'status', '--porcelain'), b'')

    def test_large_document_and_manifest_arrive_in_one_push(self):
        self.put('payload/source.js', '// ' + 'Y' * (17 * 1024 * 1024) + '\n')
        self.commit(push=True)
        report = self.run_release('--components', 'standalone', '--publish')
        manifest = self.remote_json('manifest.json')
        data = git(self.remote, 'show', 'main:payload/standalone-1.0.0.html')
        self.assertEqual(hashlib.sha256(data).hexdigest(), manifest['standalone_sha256'])
        self.assertEqual(report['release_commit'], self.head())
        self.assertEqual(manifest['unrelated'], {'keep': True})
        self.assertEqual(manifest['runtime_version'], '0.9.0')

    def test_retry_after_rejected_push_preserves_old_manifest_then_completes(self):
        before = self.head()
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\necho "Simulated transfer rejection" >&2\nexit 1\n')
        hook.chmod(0o755)
        report = self.run_release('--components', 'standalone', '--publish', fail=True)
        self.assertIn('push', report['error'])
        self.assertEqual(report['status'], 'publication_unconfirmed')
        saved = json.loads((self.root / '.release-output/manifest.json').read_text())
        self.assertEqual(saved['standalone_version'], '1.0.0')
        self.assertIn('release_commit', report)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.remote_json('manifest.json')['standalone_version'], '0.9.0')
        hook.unlink()
        self.run_release('--components', 'standalone', '--publish')
        self.assertEqual(self.remote_json('manifest.json')['standalone_version'], '1.0.0')

    def test_repeat_from_current_main_is_a_noop(self):
        self.run_release('--components', 'standalone', '--publish')
        git(self.root, 'pull', '--ff-only', 'origin', 'main')
        before = self.head()
        report = self.run_release('--components', 'standalone', '--publish')
        self.assertEqual(report['status'], 'already_published')
        self.assertEqual(self.head(), before)

    def test_same_version_cannot_replace_released_bytes(self):
        self.run_release('--components', 'standalone', '--publish')
        git(self.root, 'pull', '--ff-only', 'origin', 'main')
        self.put('standalone-src/bootstrap.js', '// changed artwork or source\n')
        self.commit(push=True)
        before = self.head()
        report = self.run_release('--components', 'standalone', '--publish', fail=True)
        self.assertIn('new version', report['error'])
        self.assertEqual(before, self.head())

    def test_missing_part_cannot_advance_manifest(self):
        self.put('release-standalone.json', {'version': '1.0.0', 'parts': ['payload/missing.txt']})
        self.commit(push=True)
        before = self.head()
        self.run_release('--components', 'standalone', '--publish', fail=True)
        self.assertEqual(before, self.head())

    def test_document_over_installed_limit_is_rejected(self):
        self.put('payload/source.js', '// ' + 'Z' * (32 * 1024 * 1024) + '\n')
        self.commit(push=True)
        before = self.head()
        self.run_release('--components', 'standalone', '--publish', fail=True)
        self.assertEqual(before, self.head())

    def test_uncommitted_source_is_rejected(self):
        self.put('payload/source.js', 'globalThis.example = 2;\n')
        report = self.run_release('--components', 'standalone', fail=True)
        self.assertIn('Commit source changes', report['error'])

    def test_stale_checkout_cannot_overwrite_new_main(self):
        old = self.head()
        self.put('new-source.txt', 'Concurrent source change\n')
        self.commit(push=True)
        git(self.root, 'checkout', '--detach', old)
        before = self.head()
        report = self.run_release('--components', 'standalone', '--publish', fail=True)
        self.assertIn('Remote main differs', report['error'])
        self.assertEqual(before, self.head())

    def test_all_components_and_immutable_workbench_parts(self):
        report = self.run_release('--components', 'standalone', 'runtime', 'userscript', 'workbench',
                                  '--workbench-notes', 'Fixture release', '--publish')
        manifest = self.remote_json('manifest.json')
        runtime = base64.b64decode(b''.join(git(self.remote, 'show', 'main:' + u[len(RAW):])
                                          for u in manifest['runtime_parts']), validate=True)
        self.assertEqual(runtime, (self.root / 'runtime-src/companion-runtime.pyw').read_bytes())
        workbench = self.remote_json('release-duplicate-review.json')
        parts = []
        for part in workbench['parts']:
            ref_path = part['url'].split('/novelai-media-library/', 1)[1]
            ref, name = ref_path.split('/', 1)
            self.assertEqual(ref, report['payload_commit'])
            data = git(self.remote, 'show', ref + ':' + name)
            self.assertEqual(hashlib.sha256(data).hexdigest(), part['sha256'])
            parts.append(data.strip())
        archive = base64.b64decode(b''.join(parts), validate=True)
        self.assertEqual(hashlib.sha256(archive).hexdigest(), workbench['sha256'])
        self.assertEqual(workbench['notes'], 'Fixture release')

    def test_request_defaults_to_dry_run_and_requires_boolean_publish(self):
        request = {'schema': 1, 'id': 'fixture', 'components': ['standalone']}
        self.put('.github/release-request.json', request)
        self.commit(push=True)
        before = self.head()
        self.assertEqual(self.run_release('--request', '.github/release-request.json')['status'], 'dry_run_passed')
        self.assertEqual(before, self.head())
        request['publish'] = 'false'
        self.put('.github/release-request.json', request)
        self.commit(push=True)
        self.run_release('--request', '.github/release-request.json', fail=True)


class PublishedVerificationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('published_verifier', REPO / 'tools/verify-published-release.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'<html>verified</html>'
        self.manifest = {'standalone_version': '1.0.0', 'standalone_url': RAW + 'payload/example.html',
                         'standalone_sha256': hashlib.sha256(self.payload).hexdigest()}
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_corrupt_download_is_not_reported_ready(self):
        def download(url, *args, **kwargs):
            return json.dumps(self.manifest).encode() if 'manifest.json' in url else b'corrupt'
        with patch.object(self.module, 'download', side_effect=download), self.assertRaisesRegex(ValueError, 'payload verification failed'):
            self.module.verify(['standalone'], self.root)

    def test_stale_raw_manifest_is_not_reported_ready(self):
        def download(url, *args, **kwargs):
            data = dict(self.manifest)
            if url.startswith(RAW) and 'manifest.json' in url:
                data['standalone_version'] = '0.9.0'
            return json.dumps(data).encode()
        with patch.object(self.module, 'download', side_effect=download), self.assertRaisesRegex(ValueError, 'raw'):
            self.module.verify(['standalone'], self.root)


if __name__ == '__main__':
    unittest.main()
