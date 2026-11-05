"""Build selected release artifacts on disk; print metadata, never payload bytes.

Run from the repository root. The default still builds all three Media Library
components. Source publishing uses --components to preserve unrelated releases.
"""
import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

COMPONENTS = ('standalone', 'userscript', 'runtime')
RAW = 'https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def build(components):
    import runpy
    sync=runpy.run_path('tools/sync-ui-sources.py')['sync']
    for component in components:
        if component in ('userscript','standalone'):sync('release-'+component+'.json')
    manifest = read('manifest.json')
    artifacts = []
    if 'userscript' in components:
        release = read('release-userscript.json')
        data = b''.join(Path(p).read_bytes() for p in release['parts'])
        manifest.update(userscript_payload_version=release['version'],
                        userscript_parts=[RAW + p for p in release['parts']],
                        userscript_sha256=hashlib.sha256(data).hexdigest())
    if 'standalone' in components:
        release = read('release-standalone.json')
        subprocess.run([sys.executable, 'tools/build-standalone.py'], check=True)
        path = Path(f"payload/standalone-{release['version']}.html")
        # Match the installed companion's document limit, not a connector limit.
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Standalone exceeds the installed updater limit of 32 MiB')
        manifest.update(standalone_version=release['version'],
                        standalone_url=RAW + path.as_posix(),
                        standalone_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        artifacts.append(path.as_posix())
    if 'runtime' in components:
        release = read('release-runtime.json')
        payload = Path(release['source']).read_bytes()
        encoded = base64.b64encode(payload).decode('ascii')
        parts = []
        for index in range(0, len(encoded), 10000):
            path = Path(f"payload/runtime-{release['version']}.part{index // 10000 + 1:02d}.b64")
            path.write_text(encoded[index:index + 10000], encoding='ascii')
            parts.append(path.as_posix())
        if base64.b64decode(''.join(Path(p).read_text() for p in parts), validate=True) != payload:
            raise ValueError('Runtime parts do not reproduce their source')
        manifest.update(runtime_version=release['version'], runtime_encoding='base64',
                        runtime_parts=[RAW + p for p in parts],
                        runtime_sha256=hashlib.sha256(payload).hexdigest())
        artifacts.extend(parts)
    Path('manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return artifacts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--components', nargs='+', choices=COMPONENTS, default=list(COMPONENTS))
    args = parser.parse_args()
    artifacts = build(args.components)
    print(json.dumps({'components': args.components, 'generated_files': len(artifacts)}))
