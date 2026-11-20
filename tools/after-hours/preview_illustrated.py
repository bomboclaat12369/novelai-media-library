"""Local illustrated-game review with a separate career and read-only Library."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from game.server import build_server, serve
from game import engine, migrations, wardrobe
from game.store import encode

FOUNDERS = ['4759bed86a2645f8a1589d5ef6770918', '744a53a2ad5b4aa59696ea97e7c645f4']


def seed_wardrobe_review(store):
    """Create the one-booking review career exactly once in its own database."""
    key = 'patricia-red-gingham'
    outfit = wardrobe.OUTFITS[key]
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM save WHERE id=1').fetchone():
            return
        state = engine.new_game(store.catalog, FOUNDERS, seed=1)
        owner, photo = outfit['owner'], outfit['photo_id']
        state['people'][owner]['xp'] = 896
        state['owned'].setdefault(photo, {'copies': 1, 'xp': 0, 'mastery': 0, 'uses': 0, 'acquired_day': 1})
        migrations.validate(state, store.catalog)
        if wardrobe.matching_card(state, store.catalog, outfit) != photo:
            raise ValueError('This preview needs Patricia and her matching Library photo.')
        first_booking = engine.command(state, store.catalog, 'start', labels=store.label_pack)
        if key not in first_booking['wardrobe']['unlocked']:
            raise ValueError('The first booking did not reach the preview milestone.')
        engine.record(state, 'wardrobe_preview_staged', owner=owner, xp=896, card=photo)
        db.executemany('INSERT INTO events(at,body) VALUES (?,?)',
                       [(time.time(), encode(event)) for event in state['journal']])
        state['journal'] = []
        db.execute('INSERT INTO save VALUES (1,1,?)', (encode(state),))
    store.backup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', default=str(Path.home()/'Documents'/'NovelAI Media Library'))
    parser.add_argument('--port', type=int)
    parser.add_argument('--wardrobe', action='store_true', help='Open the separate one-booking outfit review')
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    port = args.port if args.port is not None else (62413 if args.wardrobe else 62412)
    folder = ROOT/'game'/'test-data'/('wardrobe-preview' if args.wardrobe else 'illustrated-preview')
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder/'preview-server.json'
    # Reopening this launcher reuses only this exact review server.
    if marker.exists():
        try:
            previous = json.loads(marker.read_text())
            if previous['url'] != f'http://127.0.0.1:{port}/game/':
                raise ValueError('Different review address')
            with urllib.request.urlopen(previous['url']+'api/bootstrap', timeout=2) as reply:
                current = json.load(reply)
            if current['token'] == previous['token']:
                if args.open:
                    webbrowser.open_new_tab(previous['url'])
                print(previous['url'], flush=True)
                return
        except (OSError, ValueError, KeyError):
            pass
    server = build_server(port, folder/'career.sqlite3', args.library)
    if args.wardrobe:
        if server.store.path == server.save_origin:
            seed_wardrobe_review(server.store)
    elif server.store.read()['state'] is None and all(owner in server.store.catalog['people'] for owner in FOUNDERS):
        def action(name, body):
            server.store.apply(name, body, uuid.uuid4().hex, server.store.read()['revision'])
        action('new', {'selected': FOUNDERS, 'seed': 117})
        action('upgrade', {'kind': 'rooms'})
        action('plan', {'owner': FOUNDERS[1], 'role': 'room'})
    url = f'http://127.0.0.1:{server.server_port}/game/'
    marker.write_text(json.dumps({'url': url, 'token': server.token}), encoding='utf-8')
    print('Illustrated After Hours review: '+url, flush=True)
    print('Separate review career. Original game saves and Library files are unchanged.', flush=True)
    if args.open:
        webbrowser.open_new_tab(url)
    return serve(server)


if __name__ == '__main__':
    sys.exit(main())
