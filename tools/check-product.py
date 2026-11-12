#!/usr/bin/env python3
"""Build local test inputs and run current product suites without publishing."""
import os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(*args):
    print('+ '+' '.join(args),flush=True)
    subprocess.run(args,cwd=ROOT,check=True)

def main():
    # Product checks need the newly assembled page, but publication builds from
    # a clean committed worktree. Never leave a test-generated manifest staged.
    manifest=ROOT/'manifest.json';before=manifest.read_bytes()
    try:
        run(sys.executable,'tools/sync-ui-sources.py','--check')
        run(sys.executable,'tools/build-release.py','--components','standalone','userscript','runtime')
        run(sys.executable,'-m','unittest','discover','-s','tests','-p','test_runtime_*.py')
        run(sys.executable,'-m','unittest','discover','-s','duplicate-review/tests','-p','test_*.py')
        run('node','--test','tests/test-ui-stability.cjs','tests/test-review-dom.cjs','tests/test-workflow-dom.cjs','tests/test-organizer-dom.cjs','tests/test-missing-files-dom.cjs','tests/test-card-auto-frame-dom.cjs')
        run(sys.executable,'tests/evolution_editor_fixture.py')
        run('node','tests/test-final-card-renderer.cjs')
    finally:
        manifest.write_bytes(before)
if __name__=='__main__':main()
