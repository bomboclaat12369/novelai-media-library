"""Losslessly encode native frame PNGs for the self-contained release document."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
from PIL import Image

catalog_path=Path('assets/cards/editions/catalog.json')
catalog=json.loads(catalog_path.read_text())
def encode(item):
    key,edition=item
    source=Path(edition['art']).with_suffix('.png')
    target=source.with_suffix('.webp')
    original=Image.open(source).convert('RGBA')
    original.save(target,'WEBP',lossless=True,exact=True,method=6)
    decoded=Image.open(target).convert('RGBA')
    assert original.size==decoded.size and original.tobytes()==decoded.tobytes(),key
    return key,target.as_posix(),hashlib.sha256(target.read_bytes()).hexdigest()
with ThreadPoolExecutor(max_workers=4) as pool:
    for key,path,digest in pool.map(encode,catalog['editions'].items()):
        catalog['editions'][key]['art']=path
        catalog['sha256'][path]=digest
        print(key,Path(path).stat().st_size,flush=True)
catalog_path.write_text(json.dumps(catalog,indent=2)+'\n')
print('All 13 WebP frames are pixel-identical to the full-resolution PNG renders.')
