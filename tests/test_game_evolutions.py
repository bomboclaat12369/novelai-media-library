"""Verify Set evolutions with a synthetic library or a disposable editor-written fixture."""
import argparse
from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import threading
import unittest
from urllib.parse import quote
import uuid
import zlib


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path)
    parser.add_argument('--game-root', type=Path)
    args, remaining = parser.parse_known_args()
    sys.argv[1:] = remaining
else:
    args = argparse.Namespace(library=None, game_root=None)
sys.path.insert(0, str((args.game_root or Path(__file__).resolve().parents[1]).resolve()))
from game import engine, evolution
from game.catalog import public_catalog, read_library
from game.server import build_server
from game.store import merge_catalog


def write_fixture(folder):
    folder.mkdir()
    people = [{'id': p, 'name': p.upper()} for p in ('a', 'b')]
    media, groups = [], []
    for owner, count in zip(('a', 'b'), (3, 4)):
        ids = [f'{owner}-photo-{i}' for i in range(count)]
        for i, mid in enumerate(ids):
            def chunk(kind, data):
                return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
            color = bytes([0, 40 + i * 45, 85, ord(owner)])
            png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            (folder / (mid + '.png')).write_bytes(png + chunk(b'IDAT', zlib.compress(color)) + chunk(b'IEND', b''))
            media.append({'id': mid, 'character_id': owner, 'media_type': 'image', 'stored_rel': mid + '.png',
                          'original_name': mid + '.png', 'in_all': i == 0})
        people[len(groups)]['collection'] = {'captain_schema': 2, 'captains': {owner + '-set': ids[0]},
                                             'frames': {'image:' + ids[-1]: {'x': .2, 'y': 0, 'zoom': 1.2}}}
        groups.append({'id': owner + '-set', 'name': 'Set ' + owner, 'character_id': owner,
                       'media_ids': ids, 'cover_media_id': ids[0],
                       'after_hours_evolution': {'version': 1, 'status': 'ready', 'media_ids': list(reversed(ids))}})
    data = {'_tracking_store': 'evolution-test', 'characters': people, 'media': media, 'sets': groups}
    (folder / 'library.json').write_text(json.dumps(data), encoding='utf-8')
    (folder / 'battles.json').write_text('{"boards":{}}', encoding='utf-8')
    return data


class Player:
    def __init__(self, port):
        self.port = port
        self.token = ''
        self.revision = 0
        self.get('bootstrap')

    def request(self, path, data=None):
        conn = HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            conn.request('GET' if data is None else 'POST', '/game/api/' + path,
                         None if data is None else json.dumps(data),
                         {'Content-Type': 'application/json', 'X-Game-Token': self.token})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def get(self, path, data=None):
        status, body = self.request(path, data)
        if status != 200:
            raise AssertionError(f'{path} returned {status}: {body[:250]}')
        result = json.loads(body)
        self.revision = result.get('revision', self.revision)
        self.token = result.get('token', self.token)
        return result

    def action(self, action, **body):
        return self.get('action', {'action': action, 'body': body, 'revision': self.revision, 'id': str(uuid.uuid4())})

    def restore(self, exported):
        return self.get('restore', {'export': exported, 'revision': self.revision})


@contextmanager
def playing(library, save):
    server = build_server(0, library=library, save=save)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Player(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def pack_seed(catalog, card):
    pool = engine.pool_for(catalog, 'spotlight', card['owner'])
    for seed in range(20000):
        rng = random.Random(engine.stable((seed, 'pack', 1)))
        if sum(engine.draw(pool, rng)['id'] == card['id'] for _ in range(5)) >= 2:
            return seed
    raise AssertionError('Use a small disposable fixture with repeatable Spotlight pulls.')


class Evolutions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.temp = Path(tmp.name)
        self.library = self.temp / 'library'
        self.data = write_fixture(self.library)

    def test_invalid_or_withdrawn_selections_and_existing_careers(self):
        catalog = read_library(self.library)
        group = self.data['sets'][0]
        ident = 'evolution:' + group['id']
        original = group['after_hours_evolution']
        invalid = [None, {}, {**original, 'version': 2}, {**original, 'version': True},
                   {**original, 'status': 'candidate'}, {**original, 'media_ids': ['a-photo-0'] * 3},
                   {**original, 'media_ids': ['a-photo-0', 'a-photo-1', 'b-photo-0']}]
        for recipe in invalid:
            with self.subTest(recipe=recipe):
                group['after_hours_evolution'] = recipe
                (self.library / 'library.json').write_text(json.dumps(self.data))
                self.assertNotIn(ident, read_library(self.library)['cards'])
        group['after_hours_evolution'] = original
        media = self.data['media'][1]
        for key, value in [('in_review', True), ('in_purgatory', True), ('flagged_for_removal', True), ('media_type', 'video')]:
            before = media.copy()
            media[key] = value
            (self.library / 'library.json').write_text(json.dumps(self.data))
            self.assertNotIn(ident, read_library(self.library)['cards'])
            media.clear()
            media.update(before)
        keys = evolution.form_keys(catalog['cards'][ident]['forms'])
        original['media_ids'].reverse()
        (self.library / 'library.json').write_text(json.dumps(self.data))
        reordered = read_library(self.library)
        self.assertEqual(evolution.form_keys(merge_catalog(catalog, reordered, {})['cards'][ident]['forms']), keys[::-1])
        owned = {ident: {'mastery': 2}}
        self.assertEqual(evolution.form_keys(merge_catalog(catalog, reordered, owned)['cards'][ident]['forms']), keys)
        exported = json.loads(json.dumps(catalog))
        exported['cards'][ident]['forms'][0].update(original='untrusted', image='untrusted')
        verified = merge_catalog(exported, reordered, owned)['cards'][ident]['forms']
        self.assertEqual(verified[0]['original'], catalog['cards'][ident]['forms'][0]['original'])
        group['media_ids'].remove(media['id'])  # An older organizer moved a photo without updating its recipe.
        (self.library / 'library.json').write_text(json.dumps(self.data))
        withdrawn = merge_catalog(catalog, read_library(self.library), owned)
        self.assertFalse(withdrawn['cards'][ident]['available'])
        self.assertNotIn(ident, [c['id'] for c in engine.pool_for(withdrawn, 'standard')])
        self.assertEqual([f.get('original') for f in withdrawn['cards'][ident]['forms']], [None] * 3)
        self.assertEqual(len(evolution.progress(withdrawn, owned)[ident]['forms']), 2)

    def check_art(self, player, card, expected, earned):
        ident = quote(card['id'], safe='')
        line = player.get('state')['derived']['evolutions'].get(card['id'])
        self.assertEqual([f['media_id'] for f in line['forms']] if line else [], expected[:earned])
        for index, form in enumerate(card['forms'], 1):
            status, data = player.request(f'image/{ident}?form={index}&original=1')
            self.assertEqual(status, 200 if index <= earned else 403)
            if index <= earned:
                self.assertEqual(data, Path(form['original']).read_bytes())
        if earned:
            self.assertEqual(player.request(f'image/{ident}?original=1')[1], Path(card['forms'][earned-1]['original']).read_bytes())
            self.assertEqual(player.request(f'image/{ident}?form=1&form={len(expected)}')[0], 403)

    def check_line(self, library, catalog, group):
        ident = 'evolution:' + group['id']
        card = catalog['cards'][ident]
        expected = group['after_hours_evolution']['media_ids']
        self.assertEqual([f['media_id'] for f in card['forms']], expected)
        self.assertEqual(card['rarity'], 2)
        for mid in expected:
            member = next(m for m in self.raw_media if m['id'] == mid)
            self.assertEqual(mid in catalog['cards'], bool(member.get('in_all', True)))
        starters = list(dict.fromkeys(c['owner'] for c in catalog['cards'].values() if c['source'] != 'evolution'))
        owner = card['owner']
        founders = ([owner] if owner in starters else []) + [p for p in starters if p != owner]
        save = self.temp / (uuid.uuid4().hex + '.sqlite3')
        with playing(library, save) as player:
            first = player.action('new', selected=founders[:2], seed=pack_seed(catalog, card))
            self.assertNotIn(ident, first['state']['owned'])
            if library == self.library:
                self.assertIn(expected[-1], first['state']['owned'])
                self.assertTrue(catalog['cards'][expected[-1]]['presentation']['captain_sets'])
            self.check_art(player, card, expected, 0)
            purchased = player.action('pack', pack='spotlight', target=owner)
            self.assertTrue(any(r['id'] == ident and r['new'] for r in purchased['state']['pending_pack']['results']))
            player.action('reveal_done')
            self.check_art(player, card, expected, 1)
            if owner not in founders[:2]:
                player.action('hire', owner=owner)
                player.action('plan', owner=founders[1], role='rest')
                player.action('plan', owner=owner, role='lounge')
            player.action('equip', owner=owner, card=ident)
            duplicates = player.action('mastery', card=ident)['state']['owned'][ident]
            self.assertEqual(duplicates['xp'], 30)
            self.assertEqual(duplicates['copies'], purchased['state']['owned'][ident]['copies'] - 1)
            player.action('start')
            state = player.action('finish')['state']
            self.assertGreater(state['owned'][ident]['uses'], 0)
            for mid in expected:
                if mid not in catalog['cards']:
                    self.assertEqual(player.request('image/' + quote(mid, safe=''))[0], 403)
            snapshot = player.get('export')
            self.assertEqual(evolution.form_keys(snapshot['catalog']['cards'][ident]['forms']), evolution.form_keys(card['forms']))
            self.assertTrue(all(set(f) == {'key'} for f in snapshot['catalog']['cards'][ident]['forms']))
            seen = 1
            # Advance real shifts in memory to skip wall-clock waits and redundant disk backups.
            for _ in range(120):
                if state['cash'] < engine.recurring_cost(state):
                    state = engine.command(state, catalog, 'recovery')
                state = engine.command(state, catalog, 'start')
                state = engine.command(state, catalog, 'finish')
                earned = len(evolution.earned_forms(card, state['owned'][ident]))
                if earned > seen:
                    self.assertEqual(earned, seen + 1)
                    self.assertEqual(state['owned'][ident]['mastery'], evolution.MASTERY_LEVELS[len(expected)][earned - 1])
                    snapshot['save']['state'] = state
                    player.restore(snapshot)
                    self.check_art(player, card, expected, earned)
                    seen = earned
                if seen == len(expected):
                    break
            self.assertEqual(seen, len(expected))
        with playing(library, save) as reopened:
            self.assertEqual(reopened.get('state')['state']['owned'][ident], state['owned'][ident])
            self.check_art(reopened, card, expected, len(expected))

    def test_packs_mastery_protected_art_and_reopen(self):
        library = args.library.resolve() if args.library else self.library
        def hashes():
            return {p.relative_to(library): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in library.rglob('*') if p.is_file()}
        before = hashes()
        data = json.loads((library / 'library.json').read_text(encoding='utf-8'))
        self.raw_media = data['media']
        catalog = read_library(library)
        ready = {len(g['after_hours_evolution']['media_ids']): g for g in data['sets']
                 if catalog['cards'].get('evolution:' + g['id'], {}).get('available')}
        self.assertEqual(set(ready), {3, 4}, 'Provide one ready three-form and one ready four-form Set.')
        for count, group in ready.items():
            with self.subTest(length=count):
                self.assertNotIn('forms', public_catalog(catalog)['cards']['evolution:' + group['id']])
                self.check_line(library, catalog, group)
        self.assertEqual(hashes(), before, 'The game changed its source library')


if __name__ == '__main__':
    unittest.main()
