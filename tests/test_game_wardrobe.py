"""Career wardrobe milestones, retained Set evidence and recovery on disposable data."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game import catalog, engine, evolution, wardrobe
from game.server import build_server, serve
from game.store import GameStore

KEY = 'patricia-red-gingham'
OUTFIT = wardrobe.OUTFITS[KEY]
OWNER, PHOTO = OUTFIT['owner'], OUTFIT['photo_id']
ALICE = '744a53a2ad5b4aa59696ea97e7c645f4'
SOURCE = 'outfit-test-library'
ITEM = {'copies': 1, 'mastery': 0, 'xp': 0, 'uses': 0, 'acquired_day': 1}


def fixture(root):
    ids = [(OWNER, '0-starter'), (OWNER, PHOTO), (ALICE, '1-starter')]
    data = {'_tracking_store': SOURCE, 'characters': [{'id': OWNER, 'name': 'Patricia'}, {'id': ALICE, 'name': 'Alice'}],
            'media': [{'id': photo, 'character_id': owner, 'media_type': 'image'} for owner, photo in ids]}
    (root / 'library.json').write_text(json.dumps(data), encoding='utf-8')
    return patch.dict(wardrobe.OUTFITS, {KEY: {**OUTFIT, 'library_sha256': hashlib.sha256(SOURCE.encode()).hexdigest()}})


class WardrobeTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(fixture(self.folder))
        self.catalog = catalog.read_library(self.folder)
        self.state = engine.new_game(self.catalog, [OWNER, ALICE])

    def test_thresholds_and_either_order(self):
        s, cat = self.state, self.catalog
        s['people'][OWNER]['xp'] = 899
        s['owned'][PHOTO] = ITEM.copy()
        wardrobe.reconcile(s, cat)
        self.assertNotIn('art', wardrobe.views(s, cat)[OWNER]['outfits'][0])
        with self.assertRaises(engine.RuleError):
            engine.command(s, cat, 'wear_outfit', {'owner': OWNER, 'outfit': KEY})
        del s['owned'][PHOTO]
        s['people'][OWNER]['xp'] = 1899
        wardrobe.reconcile(s, cat)
        self.assertFalse(s['wardrobe']['unlocked'])
        guaranteed = copy.deepcopy(s)
        guaranteed['people'][OWNER]['xp'] = 1900
        wardrobe.reconcile(guaranteed, cat)
        self.assertEqual(guaranteed['wardrobe']['unlocked'][KEY]['route'], 'career')
        s['owned'][PHOTO] = ITEM.copy()
        s['people'][OWNER]['xp'] = 900
        wardrobe.reconcile(s, {**cat, 'source_id': 'unrelated-library'})
        self.assertFalse(s['wardrobe']['unlocked'])
        wardrobe.reconcile(s, cat)
        self.assertEqual(s['wardrobe']['unlocked'][KEY]['card_id'], PHOTO)
        worn = engine.command(s, cat, 'wear_outfit', {'owner': OWNER, 'outfit': KEY})
        self.assertEqual({k:v for k,v in s.items() if k not in ('wardrobe','journal')},
                         {k:v for k,v in worn.items() if k not in ('wardrobe','journal')})
        with self.assertRaises(engine.RuleError):
            engine.command(worn, cat, 'wear_outfit', {'owner': ALICE, 'outfit': KEY})

    def test_set_photo_must_be_earned(self):
        for kind, photos in [('evolution',['first', PHOTO, 'last']), ('duo',[PHOTO,'back'])]:
            with self.subTest(kind=kind):
                s, cat = copy.deepcopy(self.state), copy.deepcopy(self.catalog)
                ident = kind + ':fixture'
                cat['cards'][ident] = {'owner': OWNER, 'source': kind,
                                       'forms': [{'key': evolution.form_key(ident, photo)} for photo in photos]}
                s['owned'][ident] = {**ITEM, **({'duo_side':'back'} if kind == 'duo' else {})}
                s['people'][OWNER]['xp'] = 900
                if kind == 'evolution':
                    wardrobe.reconcile(s, cat)
                    self.assertFalse(s['wardrobe']['unlocked'])
                    s['owned'][ident]['mastery'] = 2
                wardrobe.reconcile(s, cat)
                self.assertEqual(s['wardrobe']['unlocked'][KEY]['card_id'], ident)

    def test_previous_career_reconciles_and_restores_once(self):
        store = GameStore(self.folder/'career.sqlite3', self.catalog)
        store.apply('new', {'selected':[OWNER,ALICE]}, 'start-test', 0)
        payload = store.export()
        old = payload['save']['state']
        del old['wardrobe']
        old['people'][OWNER]['xp'] = 900
        old['owned'][PHOTO] = ITEM.copy()
        restored = store.restore(payload=payload)
        restored.apply('wear_outfit', {'owner':OWNER,'outfit':KEY}, 'wear-test', 1)
        withdrawn = copy.deepcopy(self.catalog)
        del withdrawn['cards'][PHOTO]
        restored.refresh_catalog(withdrawn, 2)
        reopened = GameStore(restored.path, withdrawn)
        again = reopened.restore(payload=reopened.export())
        self.assertEqual(again.read()['state']['wardrobe']['equipped'][OWNER], KEY)
        self.assertEqual(sum(e['kind']=='outfit_unlocked' for e in again.export()['history']), 1)
        self.assertFalse(store.read()['state']['wardrobe']['unlocked'])


if __name__ == '__main__' and sys.argv[1:2] == ['--serve']:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        with fixture(folder):
            server = build_server(0, folder/'browser.sqlite3', folder)
            seed = runpy.run_path(str(ROOT/'tools'/'after-hours'/'preview_illustrated.py'))['seed_wardrobe_review']
            seed(server.store)
            print(f'http://127.0.0.1:{server.server_port}/game/', flush=True)
            serve(server)
elif __name__ == '__main__':
    unittest.main()
