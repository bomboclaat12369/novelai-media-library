"""Build verified release artifacts without coupling standalone and NovelAI versions.

Run from the repository root after editing the relevant release-*.json files.
Generated runtime parts and HTML are committed together with the final manifest.
"""
import base64
import hashlib
import json
import runpy
from pathlib import Path

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

raw = 'https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/'
manifest = read('manifest.json')
overlay = read('release-userscript.json')
standalone = read('release-standalone.json')
runtime = read('release-runtime.json')
code = b''.join(Path(p).read_bytes() for p in overlay['parts'])
manifest.update(userscript_payload_version=overlay['version'],
                userscript_parts=[raw+p for p in overlay['parts']],
                userscript_sha256=hashlib.sha256(code).hexdigest())
runpy.run_path('tools/build-standalone.py')
html = Path(f"payload/standalone-{standalone['version']}.html")
manifest.update(standalone_version=standalone['version'],standalone_url=raw+html.as_posix(),
                standalone_sha256=hashlib.sha256(html.read_bytes()).hexdigest())
payload = Path(runtime['source']).read_bytes()
encoded = base64.b64encode(payload).decode('ascii')
parts = []
for index in range(0,len(encoded),10000):
    path = Path(f"payload/runtime-{runtime['version']}.part{index//10000+1:02d}.b64")
    path.write_text(encoded[index:index+10000],encoding='ascii')
    parts.append(path.as_posix())
manifest.update(runtime_version=runtime['version'],runtime_encoding='base64',
                runtime_parts=[raw+p for p in parts],runtime_sha256=hashlib.sha256(payload).hexdigest())
Path('manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'standalone':standalone['version'],'novelai':overlay['version'],'runtime':runtime['version'],'runtime_parts':len(parts)}))
