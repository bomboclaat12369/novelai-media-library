"""Synthetic server benchmark; does not measure browser rendering or photo decoding."""
import json
import platform
from pathlib import Path
import statistics
import tempfile
import time
from .catalog import demo_catalog,public_catalog
from .store import GameStore,encode


def run():
    results=[]
    for size in (10000,50000):
        cat=demo_catalog();base=list(cat['cards'].values())
        cat['cards']={f'bench-{i}':{**base[i%len(base)],'id':f'bench-{i}'} for i in range(size)}
        with tempfile.TemporaryDirectory() as tmp:
            start=time.perf_counter();store=GameStore(Path(tmp)/'save.sqlite3',cat)
            setup=(time.perf_counter()-start)*1000
            start=time.perf_counter();payload=json.dumps(public_catalog(store.catalog)).encode()
            catalog_ms=(time.perf_counter()-start)*1000
            r=store.apply('new',{'selected':['demo-0','demo-1'],'seed':71},'benchmark-new',0)
            timings=[]
            for i in range(3):
                start=time.perf_counter();r=store.apply('pack',{'pack':'standard'},f'benchmark-pack-{i}',r['revision'])
                timings.append((time.perf_counter()-start)*1000)
                r=store.apply('reveal_done',{},f'benchmark-ack-{i}',r['revision'])
            results.append({'cards':size,'catalog_open_ms':round(setup,2),
                            'catalog_serialize_ms':round(catalog_ms,2),'catalog_json_bytes':len(payload),
                            'pack_transaction_mean_ms':round(statistics.mean(timings),2)})
    cat=demo_catalog();base=list(cat['cards'].values())
    cat['cards']={f'long-{i}':{**base[i%len(base)],'id':f'long-{i}'} for i in range(12000)}
    with tempfile.TemporaryDirectory() as tmp:
        store=GameStore(Path(tmp)/'long.sqlite3',cat)
        r=store.apply('new',{'selected':['demo-0','demo-1'],'seed':71},'long-save-new',0)
        state=r['state'];state['cash']=100000
        state['owned']={i:{'copies':3,'mastery':2,'xp':60,'uses':10,'acquired_day':1} for i in list(cat['cards'])[:10000]}
        for w in state['people'].values():state['owned'].setdefault(w['card'],{'copies':1,'mastery':0,'xp':0,'uses':0,'acquired_day':1})
        with store.connect() as db:
            db.execute('UPDATE save SET body=?',(encode(state),))
            db.executemany('INSERT INTO events(at,body) VALUES (?,?)',[(float(i),encode({'kind':'benchmark_history','day':i,'cost':100})) for i in range(20000)])
        start=time.perf_counter();export=store.export();export_ms=(time.perf_counter()-start)*1000
        start=time.perf_counter();r=store.apply('pack',{'pack':'standard'},'large-owned-pack',r['revision']);pack_ms=(time.perf_counter()-start)*1000
        start=time.perf_counter();restored=store.restore(export);restore_ms=(time.perf_counter()-start)*1000
        start=time.perf_counter();reloaded=GameStore(restored.path,cat);reload_ms=(time.perf_counter()-start)*1000
        assert reloaded.read()['state']['owned']==export['save']['state']['owned']
        large={'catalog_cards':12000,'owned_cards':len(state['owned']),'history_events':20001,'export_ms':round(export_ms,2),
               'pack_transaction_ms':round(pack_ms,2),'restore_ms':round(restore_ms,2),'reload_ms':round(reload_ms,2),
               'export_bytes':len(encode(export).encode()),'restored_owned_equal':True}
    report={'scope':'Synthetic Python/SQLite timings on '+platform.system()+'; no browser or photo decoding timings.',
            'cases':results,'growing_save':large}
    Path('game/performance-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':run()
