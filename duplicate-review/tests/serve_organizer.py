import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_organizer import fixture,add_instagram
from app import make_server
with tempfile.TemporaryDirectory() as temp:
    engine,bulk,org,ids=fixture(temp)
    add_instagram(bulk,ids)
    if "--large" in sys.argv:
        from test_organizer_evidence import add_large_post
        add_large_post(bulk,ids)
    server=make_server(engine)
    print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/organizer','ids':ids}),flush=True)
    server.serve_forever()
