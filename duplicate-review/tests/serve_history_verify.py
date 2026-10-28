import json
import os
import tempfile
from test_history_verify import fixture
import same_photo
from app import make_server

with tempfile.TemporaryDirectory() as temp:
    engine, work, keeper, target, duplicate, bad, none = fixture(temp)
    if os.environ.get('HIGH_CONFIDENCE_FIXTURE'):
        cat = work.current['source_catalog'];digest = cat[target]['sha']
        work.current['history_matches'][digest][0]['score'] = 100
        with work.db() as db:
            db.execute('INSERT INTO aliases VALUES (?,?,?,?)', (digest,cat[keeper]['sha'],same_photo.VERSION,0))
        work.persist()
    if os.environ.get('ACCEPT_ALL_FIXTURE'):
        cat = work.current['source_catalog']
        work.current['history_matches'][cat[bad]['sha']][0]['score'] = 98
        work.persist()
    server = make_server(engine)
    engine.library.request = lambda *_: (_ for _ in ()).throw(ValueError('Fixture: no companion'))
    # This UI exercise must use the existing saved job, never rebuild it.
    server.bulk.start = lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError('No inventory'))
    engine.start = lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError('No scan'))
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}'}), flush=True)
    server.serve_forever()
