from pathlib import Path
import runpy

runtime = Path('runtime-src/companion-runtime.pyw').read_text(encoding='utf-8')

# Compatibility trigger: this path is watched by the existing runtime-apply workflow.
# v2.6.2 is already applied in current installations; new changes live in the immutable
# v2.6.3 patch script. Keep this shim idempotent so future workflow re-runs are harmless.
if 'API_VERSION = 7' in runtime:
    runpy.run_path('tools/apply-runtime-v2.6.3.py', run_name='__main__')
elif 'API_VERSION = 8' in runtime:
    print('runtime v2.6.3 already applied')
else:
    raise SystemExit('expected runtime API_VERSION 7 or 8')
