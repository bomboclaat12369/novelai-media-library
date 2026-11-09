"""Read-only local media decoding/hash audit. Output contains counts, not images."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from .catalog import read_library


def snapshot(root):
    cat=read_library(root)
    paths={p for p in (Path(root)/'library.json',Path(root)/'battles.json') if p.is_file()}
    paths.update(Path(c['original']) for c in cat['cards'].values() if c.get('original'))
    hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    decoded=0;errors=[];sizes=[]
    for c in cat['cards'].values():
        if not c.get('original'):continue
        try:
            with Image.open(c['original']) as image:
                sizes.append(image.size);image.load();decoded+=1
        except Exception as exc:errors.append({'id':c['id'],'error':type(exc).__name__})
    return {'characters':len(cat['people']),'eligible_cards':len(cat['cards']),'decoded_originals':decoded,
            'missing_originals':sum(not c.get('original') for c in cat['cards'].values()),
            'errors':errors,'minimum_dimensions':[min(s[0] for s in sizes),min(s[1] for s in sizes)] if sizes else None,
            'hashes':hashes}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--library',required=True);p.add_argument('--output',required=True);p.add_argument('--compare');a=p.parse_args()
    result=snapshot(Path(a.library).resolve())
    if a.compare:
        before=json.loads(Path(a.compare).read_text(encoding='utf-8'));result['unchanged']=before['hashes']==result['hashes']
    Path(a.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='hashes'},indent=2))
