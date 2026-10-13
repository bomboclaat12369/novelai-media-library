import json
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import make_server
from engine import Engine
from test_engine import artwork
from PIL import ImageDraw

base=Path(tempfile.mkdtemp(prefix='duplicate-review-ui-'))
incoming=base/'Nikki Downloads'
reference=base/'Reference Collection'
incoming.mkdir();reference.mkdir()
image=artwork()
image.save(reference/'Original portrait.jpg',quality=96)
shutil.copy2(reference/'Original portrait.jpg',incoming/'Forum copy.jpg')
image.resize((320,420)).save(incoming/'Smaller download.jpg',quality=68)
mark=image.copy()
ImageDraw.Draw(mark).rectangle((490,755,635,835),fill='white')
ImageDraw.Draw(mark).text((500,780),'WATERMARK',fill='black')
mark.save(incoming/'Watermarked copy.jpg',quality=85)
artwork(65).save(incoming/'Different image.jpg')
engine=Engine(base/'state')
server=make_server(engine)
print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/','base':str(base),'incoming':str(incoming),'reference':str(reference)}),flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
    shutil.rmtree(base)
