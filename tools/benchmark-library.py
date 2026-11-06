"""Synthetic metadata scaling probe; never opens a user library."""
import copy, gc, hashlib, json, runpy, statistics, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
runtime=runpy.run_path(str(ROOT/'runtime-src/companion-runtime.pyw'))
def measure(fn, repeats=3):
    values=[]; result=None
    for _ in range(repeats):
        start=time.perf_counter(); result=fn(); values.append(time.perf_counter()-start)
    return {'median_ms':round(statistics.median(values)*1000,2),'samples_ms':[round(x*1000,2) for x in values]},result
for size in (1000,10000,30000):
    with tempfile.TemporaryDirectory(prefix='nai-scale-') as folder:
        store=runtime['LibraryStore'](Path(folder));store._queue_image_thumbnail=lambda *a:None
        owner=store.add_character('Synthetic Fixture')
        seed,_=store.import_bytes(b'synthetic-only','fixture.jpg',owner['id'],[],{},'image/jpeg')
        store.data['media']=[]
        for i in range(size):
            item=copy.deepcopy(seed);item.update(id=f'fixture-{i:06d}',original_name=f'fixture-{i:06d}.jpg',sha256=hashlib.sha256(str(i).encode()).hexdigest(),file_bytes=1024*1024,width=1200,height=1600)
            store.data['media'].append(item)
        store.data['sets']=[{'id':f'set-{i}','character_id':owner['id'],'name':f'Set {i}','kind':'set','media_ids':[f'fixture-{j:06d}' for j in range(i*40,i*40+20)],'cover_media_id':f'fixture-{i*40:06d}','cover_source':'auto','favorite':False,'categories':[],'colors':[],'aliases':[],'notes':''} for i in range(size//40)]
        store.save()
        out={'media':size,'sets':len(store.data['sets']),'fixture':'metadata only; no image decoding'}
        out['favorite_change'],_=measure(lambda:store.set_favorite(f'fixture-{size-1:06d}',not store.media_item(f'fixture-{size-1:06d}')['favorite']))
        out['library_response'],public=measure(store.public_library)
        out['library_response_mib']=round(len(json.dumps(public).encode())/1024**2,2)
        out['stats'],_=measure(lambda:store.character_stats(owner['id']))
        out['duplicate_catalog'],catalog=measure(lambda:store.duplicate_catalog(owner['id']))
        assert len(catalog['files'])==size
        last=store.media_item(f'fixture-{size-1:06d}')['favorite']
        out['reload'],restored=measure(lambda:runtime['LibraryStore'](Path(folder)),1)
        assert len(restored.data['media'])==size and restored.media_item(f'fixture-{size-1:06d}')['favorite']==last
        out['reload_preserved_metadata']=True
        print(json.dumps(out),flush=True)
        del store, restored, catalog, public
    gc.collect()
