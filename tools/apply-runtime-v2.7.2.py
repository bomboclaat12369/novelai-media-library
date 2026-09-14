from pathlib import Path

p = Path('runtime-src/companion-runtime.pyw')
s = p.read_text(encoding='utf-8')
if 'API_VERSION = 9' in s:
    raise SystemExit('API version already updated')
if 'API_VERSION = 8' not in s:
    raise SystemExit('expected API_VERSION = 8')
s = s.replace('API_VERSION = 8', 'API_VERSION = 9', 1)
p.write_text(s, encoding='utf-8')
print('bumped optimized runtime API version to 9')
