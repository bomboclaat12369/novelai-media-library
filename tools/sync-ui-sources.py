"""Materialize immutable release parts from stable UI source modules on disk."""
import json,sys
from pathlib import Path

def sync(config_path,check=False):
    config=json.loads(Path(config_path).read_text())
    for part,source in config.get('module_sources',{}).items():
        if part not in config['parts']:raise ValueError('Source mapping is not selected by the release')
        content=Path(source).read_bytes();destination=Path(part)
        if check:
            if not destination.is_file() or destination.read_bytes()!=content:raise ValueError('Release part differs from '+source)
        else:destination.write_bytes(content)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('configs',nargs='*')
    args=parser.parse_args()
    for config in args.configs or ['release-standalone.json','release-userscript.json']:sync(config,args.check)
