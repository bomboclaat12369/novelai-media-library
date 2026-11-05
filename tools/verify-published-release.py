"""Run after publishing, before announcing that Check updates can find a release.

Verify both manifest routes against the local release, then download and verify
its artifacts. A pushed source/config commit alone does not pass this check.
"""
import argparse
import base64
import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAW = 'https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/'
API_ROOT = 'https://api.github.com/repos/bomboclaat12369/novelai-media-library/contents/'
API = API_ROOT + 'manifest.json'


def download(url, limit=32 * 1024 * 1024, api=False):
    api_urls = tuple(API_ROOT + name + '?' for name in ('manifest.json', 'release-duplicate-review.json'))
    if not (url.startswith(RAW) or (api and url.startswith(api_urls))):
        raise ValueError('Untrusted release URL')
    headers = {'User-Agent': 'NovelAI-Release-Verification', 'Cache-Control': 'no-cache, no-store'}
    if api:
        headers['Accept'] = 'application/vnd.github.raw+json'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Release file exceeds size limit')
    return data


def verify(components, expected_dir=Path('.')):
    core = [c for c in components if c != 'workbench']
    expected = json.loads((expected_dir / 'manifest.json').read_text()) if core else {}
    fields = {
        'runtime': ('runtime_version', 'runtime_sha256', 'runtime_parts', 'runtime_encoding'),
        'standalone': ('standalone_version', 'standalone_sha256', 'standalone_url'),
        'userscript': ('userscript_payload_version', 'userscript_sha256', 'userscript_parts'),
    }
    if core:
        for url, api in [(API + '?ref=main&_=' + str(time.time_ns()), True),
                         (RAW + 'main/manifest.json?_=' + str(time.time_ns()), False)]:
            actual = json.loads(download(url, 256 * 1024, api=api))
            for component in core:
                for key in fields[component]:
                    if actual.get(key) != expected.get(key):
                        raise ValueError(f'{component}: published {key} is not ready on {"API" if api else "raw"} route')
    with ThreadPoolExecutor(max_workers=6) as pool:
        for component in core:
            if component == 'standalone':
                data = download(expected['standalone_url'])
            else:
                data = b''.join(pool.map(download, expected[component + '_parts']))
                if component == 'runtime':
                    data = base64.b64decode(data, validate=True)
            if hashlib.sha256(data).hexdigest() != expected[component + '_sha256']:
                raise ValueError(f'{component}: published payload verification failed')
            print(f'Verified {component}: {expected[fields[component][0]]} ({len(data):,} bytes)', flush=True)
        if 'workbench' in components:
            workbench = json.loads((expected_dir / 'release-duplicate-review.json').read_text())
            for url, api in [(API_ROOT + 'release-duplicate-review.json?ref=main&_=' + str(time.time_ns()), True),
                             (RAW + 'main/release-duplicate-review.json?_=' + str(time.time_ns()), False)]:
                if json.loads(download(url, 256 * 1024, api=api)) != workbench:
                    raise ValueError('Workbench manifest is not ready on both routes')
            parts = list(pool.map(download, (p['url'] for p in workbench['parts'])))
            for content, part in zip(parts, workbench['parts']):
                if hashlib.sha256(content).hexdigest() != part['sha256']:
                    raise ValueError('Workbench part checksum mismatch')
            data = base64.b64decode(b''.join(p.strip() for p in parts), validate=True)
            if hashlib.sha256(data).hexdigest() != workbench['sha256']:
                raise ValueError('Workbench ZIP checksum mismatch')
            print(f'Verified workbench: {workbench["version"]} ({len(data):,} bytes)', flush=True)
    print('Published manifests and downloads match. Update is ready.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--components', nargs='+', choices=['runtime', 'standalone', 'userscript', 'workbench'],
                        default=['runtime', 'standalone', 'userscript'])
    parser.add_argument('--expected-dir', type=Path, default=Path('.'))
    parser.add_argument('--attempts', type=int, choices=range(1, 41), default=1)
    parser.add_argument('--interval', type=int, choices=range(0, 61), default=15)
    parser.add_argument('--report', type=Path, help='Update the source publisher receipt after network verification')
    args = parser.parse_args()
    for attempt in range(args.attempts):
        try:
            verify(args.components, args.expected_dir)
            if args.report:
                report = json.loads(args.report.read_text())
                report['status'] = 'published_verified'
                args.report.write_text(json.dumps(report, indent=2) + '\n')
            break
        except (OSError, ValueError, KeyError) as error:
            print(f'Verification attempt {attempt + 1}/{args.attempts}: {error}', flush=True)
            if attempt + 1 == args.attempts:
                if args.report:
                    report = json.loads(args.report.read_text())
                    report.update(status='published_verification_failed', verification_error=str(error)[:1000])
                    args.report.write_text(json.dumps(report, indent=2) + '\n')
                raise SystemExit('Published release is not yet verified; rerun verification before announcing it ready.')
            time.sleep(args.interval)
