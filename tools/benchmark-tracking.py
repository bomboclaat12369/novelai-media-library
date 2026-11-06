"""Disposable old/new metadata benchmark; no user files, scans, or downloads."""
import argparse,copy,gc,hashlib,json,runpy,statistics,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--size',type=int,default=30000);parser.add_argument('--baseline',default='0559380bfe330d31db3ad2498b682b15f0a5be57');args=parser.parse_args()

def probe(runtime,size):
    with tempfile.TemporaryDirectory(prefix='tracking-scale-') as folder:
        store=runtime['LibraryStore'](Path(folder));store._queue_image_thumbnail=lambda *a:None
        owner=store.add_character('Synthetic');seed,_=store.import_bytes(b'fixture','fixture.png',owner['id'],[],{'kind':'local'},'image/png')
        store.data['media']=[]
        for i in range(size):
            item=copy.deepcopy(seed);item.update(id=f'fixture-{i}',sha256=hashlib.sha256(str(i).encode()).hexdigest(),original_name=f'image-{i}.png',width=1200,height=1600)
            store.data['media'].append(item)
        store.data['sets']=[{'id':f'set-{i}','character_id':owner['id'],'name':f'Set {i}','kind':'set','media_ids':[f'fixture-{j}' for j in range(i*40,i*40+20)],'cover_source':'auto','cover_media_id':f'fixture-{i*40}'} for i in range(size//40)]
        start=time.perf_counter();store.save();initial=time.perf_counter()-start
        # Clear the large initial-import outbox before measuring steady state.
        store.set_favorite(f'fixture-{size-1}',True)
        start_bytes=store.tracking.path.stat().st_size if hasattr(store,'tracking') else 0
        durations=[]
        for i in range(20):
            start=time.perf_counter();store.set_favorite(f'fixture-{size-1}',i%2==0);durations.append(time.perf_counter()-start)
        end_bytes=store.tracking.path.stat().st_size if hasattr(store,'tracking') else 0
        start=time.perf_counter();reopened=runtime['LibraryStore'](Path(folder));restart=time.perf_counter()-start
        assert len(reopened.data['media'])==size and reopened.media_item(f'fixture-{size-1}')['favorite']==False
        return {'media':size,'sets':size//40,'initial_save_ms':round(initial*1000,2),'favorite_median_ms':round(statistics.median(durations)*1000,2),
                'favorite_p95_ms':round(sorted(durations)[18]*1000,2),'restart_ms':round(restart*1000,2),
                'journal_bytes':end_bytes,'journal_growth_20_edits_bytes':end_bytes-start_bytes,'metadata_preserved':True}

with tempfile.TemporaryDirectory() as folder:
    old=Path(folder)/'baseline.pyw';old.write_bytes(subprocess.check_output(['git','show',args.baseline+':runtime-src/companion-runtime.pyw'],cwd=ROOT))
    result={'fixture':'synthetic metadata; no user media or model execution','baseline_commit':args.baseline}
    result['before']=probe(runpy.run_path(str(old)),args.size);gc.collect()
    result['after']=probe(runpy.run_path(str(ROOT/'runtime-src/companion-runtime.pyw')),args.size)
    print(json.dumps(result,indent=2))
