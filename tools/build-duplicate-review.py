"""Build the standalone ZIP and immutable update parts (no databases or caches).

Run once to create the payload commit, then again with --commit <payload SHA> to
write release-duplicate-review.json. Publish the manifest after its payload.
"""
import argparse,base64,hashlib,json,re,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--commit');args=p.parse_args()
version=re.search(r"^VERSION = '([^']+)'",(root/'duplicate-review/engine.py').read_text(),re.M)[1]
archive=root/'downloads'/('Local-Duplicate-Review-'+version+'.zip');archive.parent.mkdir(exist_ok=True)
paths=[f for f in (root/'duplicate-review').rglob('*') if f.is_file() and not any(v in f.parts for v in ('tests','__pycache__','.venv')) and f.suffix in ('.py','.js','.html','.txt','.bat','.json')]
paths.append(root/'runtime-src/companion-runtime.pyw')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for f in sorted(paths):
        info=zipfile.ZipInfo(f.relative_to(root).as_posix(),(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,f.read_bytes())
payload=archive.read_bytes();encoded=base64.b64encode(payload).decode();parts=[]
for at,start in enumerate(range(0,len(encoded),60000),1):
    path=root/'payload'/f'duplicate-review-{version}.part{at:02d}.txt';content=(encoded[start:start+60000]+'\n').encode();path.write_bytes(content)
    parts.append({'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(content).hexdigest()})
if args.commit:
    if not re.fullmatch('[0-9a-f]{40}',args.commit):raise ValueError('Use the full payload commit SHA.')
    manifest={'schema':1,'version':version,'sha256':hashlib.sha256(payload).hexdigest(),'notes':'Instagram post browsing and original filename order, displaying your selected duplicate-review keepers. Existing scans and review decisions are preserved; no rescan or reimport.',
              'parts':[{'url':'https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/'+args.commit+'/'+r['path'],'sha256':r['sha256']} for r in parts]}
    (root/'release-duplicate-review.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'version':version,'archive':str(archive),'bytes':len(payload),'parts':len(parts)}))
