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
API = 'https://api.github.com/repos/bomboclaat12369/novelai-media-library/contents/manifest.json'


def download(url, limit=32 * 1024 * 1024, api=False):
    if not (url.startswith(RAW) or (api and url.startswith(API + '?'))):
        raise ValueError('Untrusted release URL')
    headers = {'User-Agent': 'NovelAI-Release-Verification', 'Cache-Control': 'no-cache, no-store'}
    if api:
        headers['Accept'] = 'application/vnd.github.raw+json'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Release file exceeds size limit')
    return data


def verify(components):
    expected = json.loads(Path('manifest.json').read_text())
    fields = {
        'runtime': ('runtime_version', 'runtime_sha256', 'runtime_parts', 'runtime_encoding'),
        'standalone': ('standalone_version', 'standalone_sha256', 'standalone_url'),
        'userscript': ('userscript_payload_version', 'userscript_sha256', 'userscript_parts'),
    }
    for url, api in [(API + '?ref=main&_=' + str(time.time_ns()), True),
                     (RAW + 'main/manifest.json?_=' + str(time.time_ns()), False)]:
        actual = json.loads(download(url, 256 * 1024, api=api))
        for component in components:
            for key in fields[component]:
                if actual.get(key) != expected.get(key):
                    raise ValueError(f'{component}: published {key} is not ready on {"API" if api else "raw"} route')
    with ThreadPoolExecutor(max_workers=6) as pool:
        for component in components:
            if component == 'standalone':
                data = download(expected['standalone_url'])
            else:
                data = b''.join(pool.map(download, expected[component + '_parts']))
                if component == 'runtime':
                    data = base64.b64decode(data, validate=True)
            if hashlib.sha256(data).hexdigest() != expected[component + '_sha256']:
                raise ValueError(f'{component}: published payload verification failed')
            print(f'Verified {component}: {expected[fields[component][0]]} ({len(data):,} bytes)', flush=True)
    print('Published manifests and downloads match. Update is ready.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--components', nargs='+', choices=['runtime', 'standalone', 'userscript'],
                        default=['runtime', 'standalone', 'userscript'])
    verify(parser.parse_args().components)
