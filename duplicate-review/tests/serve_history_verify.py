import json
import tempfile
from test_history_verify import fixture
from app import make_server

with tempfile.TemporaryDirectory() as temp:
    engine, work, keeper, target, duplicate, bad, none = fixture(temp)
    server = make_server(engine)
    engine.library.request = lambda *_: (_ for _ in ()).throw(ValueError('Fixture: no companion'))
    # This UI exercise must use the existing saved job, never rebuild it.
    server.bulk.start = lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError('No inventory'))
    engine.start = lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError('No scan'))
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}'}), flush=True)
    server.serve_forever()
