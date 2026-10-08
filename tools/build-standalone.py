"""Build the standalone page from the same versioned payload as the NovelAI UI."""
import hashlib
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else 'release-userscript.json').read_text())
version = config['version']
payload = ''.join(Path(p).read_text() for p in config['parts'])
bootstrap = Path('standalone-src/bootstrap.js').read_text()
script = (bootstrap + '\n' + payload).replace('</script', '<\\/script')
html = f'''<!doctype html>
<html lang="en" data-nai-standalone="1" data-nai-media-payload-version="{version}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NovelAI Media Library</title><style>html,body{{margin:0;background:#0b0d1d;color:#eee;overflow:hidden}}</style></head>
<body><noscript>Enable JavaScript to use the media library.</noscript><script>{script}</script></body></html>
'''
path = Path(f'payload/standalone-{version}.html')
path.write_text(html, encoding='utf-8')
print(json.dumps({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))
