"""Synthetic server benchmark; does not measure browser rendering or photo decoding."""
import json
from pathlib import Path
import statistics
import tempfile
import time
from .catalog import demo_catalog,public_catalog
from .store import GameStore


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
    report={'scope':'Synthetic Python/SQLite server timings on this Linux workspace; small owned inventory, no photos or browser timing.',
            'cases':results}
    Path('game/performance-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':run()
