"""Local illustrated-game review with a separate career and read-only Library."""
import argparse
import json
from pathlib import Path
import sys
import urllib.request
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from game.server import build_server, serve

FOUNDERS = ['4759bed86a2645f8a1589d5ef6770918', '744a53a2ad5b4aa59696ea97e7c645f4']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', default=str(Path.home()/'Documents'/'NovelAI Media Library'))
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    folder = ROOT/'game'/'test-data'/'illustrated-preview'
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder/'preview-server.json'
    # Reopening this launcher reuses only this exact review server.
    if marker.exists():
        try:
            previous = json.loads(marker.read_text())
            with urllib.request.urlopen(previous['url']+'api/bootstrap', timeout=2) as reply:
                current = json.load(reply)
            if current['token'] == previous['token']:
                if args.open:
                    webbrowser.open_new_tab(previous['url'])
                print(previous['url'], flush=True)
                return
        except (OSError, ValueError, KeyError):
            pass
    server = build_server(args.port, folder/'career.sqlite3', args.library)
    if server.store.read()['state'] is None and all(owner in server.store.catalog['people'] for owner in FOUNDERS):
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
