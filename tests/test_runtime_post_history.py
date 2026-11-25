"""Original posts from transferred inventory and historical, exact Library imports."""
import hashlib
import io
import json
import os
import sqlite3
import threading
import unittest
import uuid
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import test_runtime_stability as fixtures


COLLECTION = 'c' * 32
POST = 'instagram:fixture:fixtureABC'
REPOST = 'forum:smg:12345'


def event(kind, entity, payload):
    return dict(id=uuid.uuid4().hex, store='workbench-bulk-fixture', at='2026-11-25', kind=kind, entity=entity, payload=payload)


def snapshot(kind, entity, value):
    return event(kind, entity, {'change': {'before': None, 'after': value}})


def source(post, path):
    return {'key': post, 'label': 'Carousel' if post == POST else 'Repost 12345',
            'kind': post.split(':')[0], 'post_id': post.split(':')[-1], 'path': str(path)}


def add_fixture(store, owner, items, folder):
    folder.mkdir(exist_ok=True)
    rows = [snapshot('inventory.batch', 'job', {'collection_id': COLLECTION, 'config': {'character_id': owner, 'roots': [str(folder)]}})]
    for n in range(1, 32):
        item = {1: items[0], 26: items[1]}.get(n)
        path = folder / ('slide_' + str(n) + '.png')
        if item:
            raw = (store.root / item['stored_rel']).read_bytes()
        else:
            buf = io.BytesIO()
            Image.new('RGB', (70, 42), (n * 5, 70, 100)).save(buf, format='PNG')
            raw = buf.getvalue()
        path.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        origins = [source(POST, path)]
        if n == 26:
            origins.append(source(REPOST, folder / 'repost.png'))
        record = dict(id=sha, sha=sha, path=str(path), origins=origins, sources={o['key']: o for o in origins})
        rows.append(snapshot('source.catalog', COLLECTION + ':' + sha, record))
    store.tracking.ingest(rows)


class PostHistoryTests(unittest.TestCase):
    setUp = fixtures.RuntimeStabilityTests.setUp
    tearDown = fixtures.RuntimeStabilityTests.tearDown
    import_image = fixtures.RuntimeStabilityTests.import_image

    def test_pages_scope_corrections_preview_and_reload(self):
        first, focus = self.import_image(1), self.import_image(2)
        folder = self.store.root / 'origin'
        add_fixture(self.store, self.character['id'], [first, focus], folder)
        other = self.store.add_character('Other character')
        foreign, _ = self.store.import_bytes(b'fixture-2', 'foreign.png', other['id'], [], {}, 'image/png')
        view = self.store.original_posts.view
        self.assertEqual(view(foreign['id'])['posts'], [])
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            events = db.execute('SELECT count(*) FROM tracking_events').fetchone()
        result = view(focus['id'])
        self.assertEqual([p['key'] for p in result['posts']], [POST, REPOST])
        page = result['page']
        self.assertEqual((page['offset'], page['focus'], page['total']), (24, 25, 31))
        self.assertEqual([r['name'] for r in page['items']], ['slide_%d.png' % i for i in range(25, 32)])
        self.assertTrue(page['items'][1]['current'])
        self.assertEqual(page['workbench'], {'collection': COLLECTION, 'photo': focus['sha256']})
        previous = view(focus['id'], POST, 0)['page']
        self.assertEqual(previous['items'][0]['media_id'], first['id'])
        second = previous['items'][1]
        self.assertIsNone(second['media_id'])
        jpg = self.store.original_posts.preview(second['preview'], True)
        with Image.open(io.BytesIO(jpg)) as image:
            self.assertEqual((image.format, image.size), ('JPEG', (70, 42)))
        (folder / 'slide_2.png').write_bytes((folder / 'slide_3.png').read_bytes())
        self.assertIsNone(self.store.original_posts.preview(second['preview'], False))
        self.assertEqual(view(focus['id'], REPOST)['page']['total'], 1)
        with self.assertRaises(ValueError):
            view(focus['id'], 'forum:smg:unrelated')
        with closing(sqlite3.connect(self.store.tracking.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tracking_events').fetchone(), events)
        # A newer Workbench catalog removed a mistaken post connection.
        self.store.tracking.ingest([event('source.catalog', COLLECTION + ':' + focus['sha256'], {'change': {'changes': {
            'origins': {'after': [source(POST, folder / 'slide_26.png')]},
            'sources': {'after': {POST: source(POST, folder / 'slide_26.png')}}}}})])
        fresh = fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual([p['key'] for p in fresh.original_posts.view(focus['id'])['posts']], [POST])

    def test_exact_reimports_explicit_keeper_legacy_and_unknown_links(self):
        owner = self.character['id']
        first = self.import_image(1)
        other = self.import_image(2)
        add_fixture(self.store, owner, [first, other], self.store.root / 'origin')
        focus, _ = self.store.import_bytes(b'kept', 'kept.png', owner, [], {'kind':'url','url':'https://example.test/download.png'}, 'image/png')
        self.store.import_bytes(b'kept', 'renamed.png', owner, [], {'kind':'url','url':'https://example.test/repost.png'}, 'image/png')
        self.assertEqual(self.store.original_posts.view(focus['id'])['posts'], [])
        catalog = {'sha': other['sha256'], 'origins': [source(POST, 'slide_26.png')]}
        self.store._source_observation(self.store.media_item(focus['id']), {'kind':'organizer'}, record=catalog)
        self.store.save()
        result = self.store.original_posts.view(focus['id'])
        self.assertEqual({p['key'] for p in result['posts']}, {POST, REPOST})
        self.assertEqual({s['url'] for s in result['sources'] if s['url']},
                         {'https://example.test/download.png','https://example.test/repost.png'})
        self.assertTrue(any(r['current'] for r in result['page']['items']))
        # Switching the file at the same stable ID must not claim the old file's posts.
        media = self.store.media_item(focus['id'])
        media.update(sha256='f' * 64, source={'kind':'local'})
        self.store.save()
        self.assertEqual(self.store.original_posts.view(focus['id'])['posts'], [])
        blank = self.import_image(7)
        self.assertEqual(self.store.original_posts.view(blank['id'])['sources'][0]['name'], 'fixture-7.png')
        # Initial observed Library records (pre-journal imports) supply sibling memberships on upgrade.
        a, _ = self.store.import_bytes(b'older-a', 'a.png', owner, [], {'origins': [source(REPOST, 'a.png')]}, 'image/png')
        b, _ = self.store.import_bytes(b'older-b', 'b.png', owner, [], {'origins': [source(REPOST, 'b.png')]}, 'image/png')
        self.store.tracking.path.unlink()
        data = json.loads(self.store.db_path.read_bytes())
        data.pop('_tracking_store', None)
        data.pop('_tracking_pending', None)
        self.store.db_path.write_text(json.dumps(data), encoding='utf-8')
        fresh = fixtures.RUNTIME['LibraryStore'](self.store.root)
        self.assertEqual({r['media_id'] for r in fresh.original_posts.view(a['id'])['page']['items']}, {a['id'], b['id']})

    def test_previews_are_scoped_to_actual_roots_and_exact_bytes(self):
        h = self.store.original_posts
        root = self.store.root / 'collection'
        root.mkdir()
        sha = 'a' * 64
        for path in [str(self.store.root / 'outside.jpg'), str(root / '..' / 'outside.jpg'),
                     r'\\server\share\image.jpg', '/dev/../etc/passwd']:
            self.assertIsNone(h.offer_preview(dict(sha=sha, path=path), [str(root)]))
        self.assertIsNone(h.preview('f' * 32, False))

    def test_workbench_probe_validates_address_and_never_follows_redirects(self):
        class Handler(BaseHTTPRequestHandler):
            redirect = False
            def do_GET(self):
                self.server.seen.append(self.path)
                self.send_response(302 if self.redirect else 200)
                if self.redirect:
                    self.send_header('Location', '/other')
                self.end_headers()
                self.wfile.write(b'{"post_navigation":1}')
            def log_message(self, *args):
                pass
        app = self.store.root / 'LocalDuplicateReview'
        app.mkdir()
        address = app / 'running-url.txt'
        probe = fixtures.RUNTIME['running_post_organizer']
        with HTTPServer(('127.0.0.1', 0), Handler) as server, patch.dict(os.environ, {'LOCALAPPDATA': str(self.store.root)}):
            server.seen = []
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = 'http://127.0.0.1:%d/organizer' % server.server_port
                for invalid in [base + '?token=x', 'https://example.test/organizer', base.replace('127.0.0.1', 'localhost')]:
                    address.write_text(invalid)
                    self.assertIsNone(probe())
                self.assertEqual(server.seen, [])
                address.write_text(base)
                self.assertEqual(probe(), base)
                Handler.redirect = True
                self.assertIsNone(probe())
                self.assertEqual(server.seen, ['/api/workbench/post-navigation'] * 2)
            finally:
                server.shutdown()
                worker.join()
