"""Build and optionally publish from a committed source tree, without tool payloads.

Defaults to a dry run in an isolated worktree. --publish uses one ordinary Git
push for payload and manifest commits; it never force-pushes or edits the source
checkout. Read tools/PUBLISHING.md before using it for an application release.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

COMPONENTS = ('standalone', 'userscript', 'runtime', 'workbench')
RAW = 'https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/'
FIELDS = {
    'standalone': ('standalone_version', 'standalone_sha256'),
    'userscript': ('userscript_payload_version', 'userscript_sha256'),
    'runtime': ('runtime_version', 'runtime_sha256'),
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Release versions must have the form 1.2.3')
    return tuple(map(int, value.split('.')))


def local_path(root, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Invalid release path')
    path = root / name
    if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Release path escapes the repository')
    return path


def url_path(root, url):
    prefix = RAW + 'main/'
    if not isinstance(url, str) or not url.startswith(prefix):
        raise ValueError('Media Library requires existing main-branch payload URLs')
    return local_path(root, url[len(prefix):])


def git(root, *args):
    p = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                       env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}, timeout=120)
    if p.returncode:
        # Never print diffs, file bodies, credentials or a giant subprocess error.
        detail = re.sub(r'https?://\S+', '<remote>', p.stderr.strip())[-600:]
        raise RuntimeError('Git operation failed: ' + args[0] + ': ' + detail)
    return p.stdout.strip()


def run(root, command, log, env, input_data=None):
    with log.open('ab') as output:
        p = subprocess.run(command, cwd=root, env=env, input=input_data,
                           stdout=output, stderr=output, timeout=300)
    if p.returncode:
        raise RuntimeError('Build/validation command failed; inspect the saved log: ' + command[0])


def options(args):
    selected = args.components or ['standalone']
    publish = args.publish
    notes = args.workbench_notes
    if args.request:
        request = read(Path(args.request))
        if set(request) - {'schema', 'id', 'components', 'publish', 'workbench_notes'}:
            raise ValueError('Unknown release request field')
        if request.get('schema') != 1 or not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', str(request.get('id', ''))):
            raise ValueError('Release request needs schema 1 and a short unique id')
        if type(request.get('publish', False)) is not bool:
            raise ValueError('publish must be a JSON boolean')
        if args.components is not None or args.publish or args.workbench_notes:
            raise ValueError('Use either --request or individual release options')
        selected = request.get('components')
        publish = request.get('publish', False)
        notes = request.get('workbench_notes', '')
    if not isinstance(selected, list) or not selected or any(x not in COMPONENTS for x in selected):
        raise ValueError('Choose one or more known release components')
    if not isinstance(notes, str) or len(notes) > 8000:
        raise ValueError('Invalid Workbench release notes')
    return sorted(set(selected)), publish, notes


def validate_inputs(root, selected):
    for component in selected:
        if component == 'workbench':
            continue
        config = read(root / f'release-{component}.json')
        version(config['version'])
        for name in config.get('parts', []):
            if not local_path(root, name).is_file():
                raise ValueError('A configured source part is missing')
        if component == 'runtime':
            local_path(root, config['source']).read_bytes()
        if component == 'standalone':
            for name in config.get('title_artwork', {}).values():
                local_path(root, name).read_bytes()
            for key in ('base_catalog', 'edition_catalog'):
                if not config.get(key):
                    continue
                catalog = read(local_path(root, config[key]))
                entries = catalog.get('frames', catalog.get('editions', {}))
                for entry in entries.values():
                    local_path(root, entry['art']).read_bytes()
                for kind in ('ranks', 'fonts'):
                    for name in catalog.get(kind, {}).values():
                        local_path(root, name).read_bytes()


def inspect_core(root, component, manifest, log, env):
    config = read(root / f'release-{component}.json')
    generated = []
    if component == 'standalone':
        path = url_path(root, manifest['standalone_url'])
        data = path.read_bytes()
        if len(data) > 32 * 1024 * 1024:
            raise ValueError('Standalone exceeds the installed updater limit of 32 MiB')
        match = re.search(rb'<script>(.*)</script>', data, re.S)
        if not match or f'data-nai-media-payload-version="{config["version"]}"'.encode() not in data:
            raise ValueError('Standalone document is incomplete or has the wrong version')
        run(root, ['node', '--check'], log, env, match[1])
        generated.append(path.relative_to(root).as_posix())
    elif component == 'userscript':
        paths = [url_path(root, u) for u in manifest['userscript_parts']]
        data = b''.join(p.read_bytes() for p in paths)
        source = b''.join(local_path(root, p).read_bytes() for p in config['parts'])
        if data != source:
            raise ValueError('Userscript parts differ from configured source')
        run(root, ['node', '--check'], log, env, data)
    else:
        paths = [url_path(root, u) for u in manifest['runtime_parts']]
        data = base64.b64decode(b''.join(p.read_bytes() for p in paths), validate=True)
        if data != local_path(root, config['source']).read_bytes():
            raise ValueError('Runtime payload differs from source')
        compile(data, config['source'], 'exec')
        generated.extend(p.relative_to(root).as_posix() for p in paths)
    ver_key, hash_key = FIELDS[component]
    if manifest[ver_key] != config['version'] or manifest[hash_key] != digest(data):
        raise ValueError('Manifest does not match the built ' + component)
    return {'version': config['version'], 'sha256': digest(data), 'bytes': len(data)}, generated


def build_workbench(root, notes, log, env):
    if not notes.strip():
        raise ValueError('Workbench releases need explicit workbench_notes')
    source = (root / 'duplicate-review/engine.py').read_text(encoding='utf-8')
    match = re.search(r"^VERSION = '([^']+)'", source, re.M)
    if not match:
        raise ValueError('Cannot find Workbench version')
    ver = match[1]
    version(ver)
    run(root, [sys.executable, 'tools/build-duplicate-review.py'], log, env)
    archive = root / 'downloads' / f'Local-Duplicate-Review-{ver}.zip'
    data = archive.read_bytes()
    part_count = (4 * ((len(data) + 2) // 3) + 59999) // 60000
    parts = [root / 'payload' / f'duplicate-review-{ver}.part{index:02d}.txt'
             for index in range(1, part_count + 1)]
    encoded = b''.join(p.read_bytes().strip() for p in parts)
    if base64.b64decode(encoded, validate=True) != data:
        raise ValueError('Workbench parts do not reproduce the ZIP')
    with zipfile.ZipFile(archive) as z:
        if z.testzip():
            raise ValueError('Workbench ZIP failed its integrity check')
        for name in z.namelist():
            if name.endswith(('.py', '.pyw')):
                compile(z.read(name), name, 'exec')
    files = [p.relative_to(root).as_posix() for p in parts]
    info = {'version': ver, 'sha256': digest(data), 'bytes': len(data)}
    manifest = {'schema': 1, 'version': ver, 'sha256': digest(data), 'notes': notes,
                'parts': [{'path': p.relative_to(root).as_posix(), 'sha256': digest(p.read_bytes())} for p in parts]}
    return info, files + [archive.relative_to(root).as_posix()], manifest


def guard_version(before, info):
    old_version, old_hash = before
    if old_version is None:
        return
    if version(info['version']) < version(old_version):
        raise ValueError('Refusing a release version downgrade')
    if info['version'] == old_version and info['sha256'] != old_hash:
        raise ValueError('Changed release bytes require a new version; refusing to overwrite an existing release')


def commit_files(root, paths, message):
    if paths:
        git(root, 'add', '--', *paths)
    if git(root, 'diff', '--cached', '--name-only'):
        git(root, 'commit', '-m', message)
    return git(root, 'rev-parse', 'HEAD')


def execute(args, report, log):
    selected, publish, notes = options(args)
    root = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel'))
    source = git(root, 'rev-parse', 'HEAD')
    report.update(source_commit=source, components=selected, publish=publish)
    if git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Commit source changes before building a release')
    if args.request:
        relative = Path(args.request).resolve().relative_to(root).as_posix()
        if git(root, 'show', 'HEAD:' + relative) != Path(args.request).read_text(encoding='utf-8').strip():
            raise ValueError('Release request must match its committed version')
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    module_path = str(root / 'tools/node_modules')
    env['NODE_PATH'] = module_path + (os.pathsep + env['NODE_PATH'] if env.get('NODE_PATH') else '')
    if publish:
        if git(root, 'ls-remote', args.remote, 'refs/heads/main').split()[0] != source:
            raise ValueError('Remote main differs from this source commit; restart from current main')
    before = read(root / 'manifest.json')
    old_workbench = read(root / 'release-duplicate-review.json') if 'workbench' in selected else None
    with tempfile.TemporaryDirectory(prefix='nai-release-') as temp:
        stage = Path(temp) / 'tree'
        git(root, 'worktree', 'add', '--detach', str(stage), source)
        try:
            validate_inputs(stage, selected)
            core = [c for c in selected if c in FIELDS]
            if core:
                run(stage, [sys.executable, 'tools/build-release.py', '--components', *core], log, env)
            manifest = read(stage / 'manifest.json')
            generated = []
            report['artifacts'] = {}
            wb_manifest = None
            for component in selected:
                if component == 'workbench':
                    info, paths, wb_manifest = build_workbench(stage, notes, log, env)
                    guard_version((old_workbench.get('version'), old_workbench.get('sha256')), info)
                else:
                    info, paths = inspect_core(stage, component, manifest, log, env)
                    vk, hk = FIELDS[component]
                    guard_version((before.get(vk), before.get(hk)), info)
                report['artifacts'][component] = info
                generated.extend(paths)
            # All objects are built and checked before any manifest reaches main.
            payload_commit = commit_files(stage, generated, 'Build release payloads from ' + source[:12])
            manifests = ['manifest.json'] if core else []
            if wb_manifest:
                if old_workbench.get('sha256') != wb_manifest['sha256'] or old_workbench.get('version') != wb_manifest['version']:
                    for part in wb_manifest['parts']:
                        part['url'] = RAW + payload_commit + '/' + part.pop('path')
                    write(stage / 'release-duplicate-review.json', wb_manifest)
                manifests.append('release-duplicate-review.json')
            final = commit_files(stage, manifests, 'Publish verified release manifests\n\nSource-Commit: ' + source)
            report.update(payload_commit=payload_commit, release_commit=final, generated_files=len(generated))
            # Save the exact expected state BEFORE attempting network writes.
            # A lost acknowledgement must not erase the information needed to
            # distinguish an unpublished release from a completed upload.
            output = Path(args.report).resolve().parent
            for name in manifests:
                (output / name).write_bytes((stage / name).read_bytes())
            if not publish:
                report['status'] = 'dry_run_passed'
            elif final == source:
                report['status'] = 'already_published'
            else:
                if git(root, 'ls-remote', args.remote, 'refs/heads/main').split()[0] != source:
                    raise ValueError('Remote main advanced while building; no release was pushed')
                # A single fast-forward publishes both commits; failure cannot
                # leave main advertising an artifact that has not been uploaded.
                report.update(status='push_started', push_attempted=True)
                write(Path(args.report).resolve(), report)
                git(stage, 'push', args.remote, final + ':refs/heads/main')
                if git(root, 'ls-remote', args.remote, 'refs/heads/main').split()[0] != final:
                    raise RuntimeError('Push result could not be confirmed; inspect main before retrying')
                report['status'] = 'pushed_verification_pending'
        finally:
            git(root, 'worktree', 'remove', '--force', str(stage))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--components', nargs='+', choices=COMPONENTS)
    parser.add_argument('--request', help='Committed JSON release request')
    parser.add_argument('--workbench-notes', default='')
    parser.add_argument('--publish', action='store_true', help='Publish to origin/main after validation')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--report', default='.release-output/report.json')
    args = parser.parse_args()
    path = Path(args.report).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    log = path.with_suffix('.log')
    log.write_bytes(b'')
    report = {'status': 'started', 'log': str(log)}
    try:
        execute(args, report, log)
    except Exception as error:
        status = 'publication_unconfirmed' if report.get('push_attempted') else 'failed'
        report.update(status=status, error=str(error)[:1000])
        write(path, report)
        print(json.dumps(report), flush=True)
        return 1
    write(path, report)
    print(json.dumps(report), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
