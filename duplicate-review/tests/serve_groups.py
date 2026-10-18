import json
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import make_server
from engine import Engine
from test_engine import artwork
from PIL import PngImagePlugin
base=Path(tempfile.mkdtemp(prefix='duplicate-groups-ui-'))
source=base/'downloads';source.mkdir()
old=source/'2024-02-27';new=source/'2025-08-03';old.mkdir();new.mkdir()
im=artwork();info=PngImagePlugin.PngInfo();info.add_text('Comment','Different metadata')
im.save(old/'older.png',compress_level=0);im.save(new/'newest.png',compress_level=9,pnginfo=info)
shutil.copy2(new/'newest.png',old/'exact.png');im.resize((320,420)).save(old/'smaller.jpg',quality=98 if '--visual' in sys.argv else 70)
im=artwork(62);im.save(new/'different.jpg');shutil.copy2(new/'different.jpg',old/'different-copy.jpg')
engine=Engine(base/'state');server=make_server(engine)
print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/','base':str(base),'incoming':str(source),'old':str(old),'new':str(new)}),flush=True)
server.serve_forever()
