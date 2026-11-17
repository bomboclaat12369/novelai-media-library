"""Disposable browser-check server, never connected to the personal library."""
import json
from pathlib import Path
import sys
import uuid
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game import engine, stage_labels
from game.server import build_server, serve
from game.store import encode

folder = Path(sys.argv[1]).resolve()
library = folder/'library'
library.mkdir(parents=True, exist_ok=True)
owners = ['4759bed86a2645f8a1589d5ef6770918', '744a53a2ad5b4aa59696ea97e7c645f4', 'fixture-third']
names = ['Patricia', 'Alice', 'Unillustrated guest']
media = []
for index, (owner, name) in enumerate(zip(owners, names)):
    for photo in range(2):
        image = Image.new('RGB', (600, 900) if photo == 0 else (1000, 600), ['#4c5f62', '#686348', '#665363'][index])
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 30, image.width-30, image.height-30), outline='#cbb68a', width=2)
        font = ImageFont.truetype('C:/Windows/Fonts/georgia.ttf', 38)
        small = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 20)
        draw.text((image.width/2, image.height/2-45), name, fill='#ede7d7', font=font, anchor='mm')
        draw.text((image.width/2, image.height/2+10), 'PHOTO FIXTURE', fill='#ede7d7', font=small, anchor='mm')
        draw.text((image.width/2, image.height/2+42), 'No personal media in this screenshot', fill='#ede7d7', font=small, anchor='mm')
        file=f'photo-{index}-{photo}.png'
        image.save(library/file)
        media.append({'id': f'{index}-{photo}', 'character_id': owner, 'stored_rel': file, 'thumb_rel': file, 'media_type': 'image', 'in_all': True})
(library/'library.json').write_text(json.dumps({'_tracking_store':'illustrated-ui-fixture','characters':[{'id': owner, 'name': name} for owner,name in zip(owners,names)],'media':media}), encoding='utf-8')
(library/'battles.json').write_text('{"boards":{}}', encoding='utf-8')
data=folder/'data'
data.mkdir(exist_ok=True)
(data/'stage-labels.json').write_text(json.dumps({'format':'after-hours-stage-labels','version':2,'entries':[{'id':slot,'slot':slot,'when':{},'text':text} for slot,text in stage_labels.FALLBACKS.items()]}), encoding='utf-8')
server=build_server(0,data/'career.sqlite3',library)
def action(name,body):
    server.store.apply(name,body,uuid.uuid4().hex,server.store.read()['revision'])
action('new',{'selected':owners[:2],'seed':2})
action('upgrade',{'kind':'rooms'})
action('plan',{'owner':owners[1],'role':'room'})
action('start',{})
state=engine.command(server.store.read()['state'],server.store.catalog,'advance',{'seconds':22,'stop_at_decision':True},labels=server.store.label_pack)
state['night']['paused']=True
with server.store.connect() as connection:
    connection.execute('UPDATE save SET body=? WHERE id=1',(encode(state),))
print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/game/','library':str(library)}),flush=True)
serve(server)
