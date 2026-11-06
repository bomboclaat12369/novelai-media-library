import copy,hashlib,json,runpy,statistics,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'duplicate-review'))
from engine import Engine
from bulk.workbench import Workbench
for count in (1000,10000,30000):
    with tempfile.TemporaryDirectory() as folder:
        engine=Engine(Path(folder)/'state');bulk=Workbench(engine);catalog={}
        for i in range(count):
            sha=hashlib.sha256(str(i).encode()).hexdigest();path=f'/synthetic/Post {i//20}/image-{i}.jpg'
            source={'kind':'forum','key':f'post:{i//20}','path':path,'label':f'Post {i//20}','quarantine':False}
            catalog[sha]={'id':sha,'sha':sha,'path':path,'stamp':'100:200:300:400','origins':[source],'sources':{source['key']:source},'copies':[],'existing_sets':[]}
        bulk.current={'id':'benchmark','config':{'roots':['/synthetic']},'source_catalog':catalog,'proposals':[],'items':{},'running':False,'phase':'Ready','issues':[]}
        start=time.perf_counter();bulk.persist();initial=time.perf_counter()-start
        with bulk.db() as db:before=db.execute('SELECT count(*) FROM tracking_events').fetchone()[0]
        times=[]
        for _ in range(5):
            start=time.perf_counter();bulk.persist();times.append(time.perf_counter()-start)
        with bulk.db() as db:after=db.execute('SELECT count(*) FROM tracking_events').fetchone()[0]
        assert before==after
        print(json.dumps({'images':count,'first_persist_ms':round(initial*1000,2),'unchanged_persist_median_ms':round(statistics.median(times)*1000,2),'unchanged_history_growth_events':after-before,'database_bytes':bulk.path.stat().st_size}),flush=True)
