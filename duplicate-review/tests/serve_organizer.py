import copy,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_organizer import fixture,add_instagram
from app import make_server
with tempfile.TemporaryDirectory() as temp:
    engine,bulk,org,ids=fixture(temp)
    add_instagram(bulk,ids)
    if "--large" in sys.argv or "--focus" in sys.argv:
        from test_organizer_evidence import add_large_post
        add_large_post(bulk,ids)
        if "--focus" in sys.argv:
            catalog=bulk.current['source_catalog'];item=catalog.pop('dump-image-0900')
            item['id']='a-dump-anchor'
            source=dict(item['sources']['post:dump'],path='original/zzzz.jpg')
            item['sources']={'post:dump':source};item['origins']=[source]
            catalog[item['id']]=item;bulk.persist()
    if "--collections" in sys.argv:
        bulk.current['config']['roots']=[r'C:\SMG\Mikayla'];bulk.persist();org.bound=None;org.bind()
        org.mutate('save',{'job':bulk.current['id'],'revision':0,'name':'Mikayla Shoot','ids':[ids[2]]})
        mikayla=copy.deepcopy(bulk.current)
        bulk.current=copy.deepcopy(mikayla);bulk.current['id']='alice-job';bulk.current['config']['roots']=[r'C:\SMG\Alice'];bulk.persist()
        org.bound=None;org.bind()
        org.mutate('save',{'job':'alice-job','revision':0,'name':'Alice Shoot','ids':[ids[3]]})
        bulk.activate('fixture-job')
    server=make_server(engine)
    print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/organizer','ids':ids}),flush=True)
    server.serve_forever()
