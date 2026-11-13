"""Build the independently versioned standalone page (including Battles)."""
import base64
import hashlib
import json
import mimetypes
import subprocess
import sys
import runpy
from pathlib import Path

config_path=sys.argv[1] if len(sys.argv)>1 else 'release-standalone.json'
runpy.run_path('tools/sync-ui-sources.py')['sync'](config_path)
config = json.loads(Path(config_path).read_text())
version = config['version']
payload = ''.join(Path(p).read_text() for p in config['parts'])
bootstrap = Path('standalone-src/bootstrap.js').read_text()
artwork={key:'data:image/webp;base64,'+base64.b64encode(Path(path).read_bytes()).decode('ascii') for key,path in config.get('title_artwork',{}).items()}
asset_code='const naiCardTitleAssets=Object.freeze('+json.dumps(artwork,separators=(',',':'))+');\n'
if config.get('base_catalog'):
    bases=json.loads(Path(config['base_catalog']).read_text())
    for frame in bases['frames'].values():
        path=frame['art']
        mime=mimetypes.guess_type(path)[0] or 'application/octet-stream'
        frame['art']='data:'+mime+';base64,'+base64.b64encode(Path(path).read_bytes()).decode('ascii')
    asset_code+='const naiCardBaseAssets=Object.freeze('+json.dumps(bases,separators=(',',':'))+');\n'
if config.get('edition_catalog'):
    catalog=json.loads(Path(config['edition_catalog']).read_text())
    def embedded(path, mime=None):
        mime=mime or mimetypes.guess_type(path)[0] or 'application/octet-stream'
        return 'data:'+mime+';base64,'+base64.b64encode(Path(path).read_bytes()).decode('ascii')
    for edition in catalog['editions'].values():edition['art']=embedded(edition['art'])
    if 'duo' in catalog:
        for field in ('art', 'backArt'):
            if field in catalog['duo']:
                catalog['duo'][field] = embedded(catalog['duo'][field], 'image/webp')
    for kind in ('ranks','fonts'):
        catalog[kind]={key:embedded(path) for key,path in catalog[kind].items()}
    asset_code+='const naiCardEditionAssets=Object.freeze('+json.dumps(catalog,separators=(',',':'))+');\n'
script = (asset_code + bootstrap + '\n' + payload).replace('</script', '<\\/script')
if config.get('minify_javascript'):
    script = subprocess.run(['node', 'tools/minify-standalone.cjs'], input=script,
                            text=True, capture_output=True, check=True).stdout
html = f'''<!doctype html>
<html lang="en" data-nai-standalone="1" data-nai-media-payload-version="{version}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NovelAI Media Library</title><style>html,body{{margin:0;background:#0b0d1d;color:#eee;overflow:hidden}}</style></head>
<body><noscript>Enable JavaScript to use the media library.</noscript><script>{script}</script></body></html>
'''
path = Path(f'payload/standalone-{version}.html')
path.write_text(html, encoding='utf-8')
print(json.dumps({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))
