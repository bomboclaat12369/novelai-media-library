import json
from pathlib import Path
import sys
import tempfile
import time
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import make_server
from engine import Engine

class Encoder:
    MODEL_SHA='test-only';SCENE_RECIPE='test-only'
    def _encode(self,path):
        time.sleep(.025)
        a=np.zeros(768,np.float32);a[0 if Path(path).name.startswith('A') else 1]=1
        return a
    def _encode_scene(self,path):
        a=self._encode(path);return np.stack([a,a])

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);incoming=root/'Mikayla'
    for kind,color in [('A',(63,107,149)),('B',(162,101,68))]:
        for n in range(4):
            path=incoming/'Mikayla-Images-By-Post'/'2024-10-01 - Post 3672997'/f'{kind}{n}.png'
            path.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',(400,600),tuple(v+n*9 for v in color)).save(path)
    copy=incoming/'_Duplicate_Review_Quarantine'/'abc'/'Mikayla-Videos-And-ImagePond'/'2025-10-01 - Post 3672997'/'A0.png'
    copy.parent.mkdir(parents=True);copy.write_bytes((incoming/'Mikayla-Images-By-Post'/'2024-10-01 - Post 3672997'/'A0.png').read_bytes())
    engine=Engine(root/'state');server=make_server(engine)
    server.bulk.encoder_factory=lambda _:Encoder()
    # UI still works without a connected companion; avoid connecting to an
    # unrelated local server in the test environment.
    engine.library.request=lambda *_:(_ for _ in ()).throw(ValueError('Fixture: no companion'))
    print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}','incoming':str(incoming)}),flush=True)
    server.serve_forever()
