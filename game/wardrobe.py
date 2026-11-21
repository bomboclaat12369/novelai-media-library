"""Permanent career cosmetics earned with a matching photo or character experience."""
import hashlib
import json
from pathlib import Path

from . import evolution

ART_DIR = Path(__file__).with_name('wardrobe-data')
OUTFITS = json.loads((ART_DIR / 'outfits.json').read_text(encoding='utf-8'))
DEFAULT = 'default'


def empty():
    return {'version': 1, 'unlocked': {}, 'equipped': {}}


def validate(state):
    book = state['wardrobe']
    if not isinstance(book, dict) or type(book.get('version')) is not int or book['version'] != 1:
        raise ValueError('Invalid wardrobe version.')
    unlocked, equipped = book['unlocked'], book['equipped']
    if not isinstance(unlocked, dict) or not isinstance(equipped, dict):
        raise ValueError('Invalid wardrobe.')
    for key, receipt in unlocked.items():
        outfit = OUTFITS.get(key)
        if not outfit or not isinstance(receipt, dict) or receipt.get('owner') != outfit['owner'] or outfit['owner'] not in state['people']:
            raise ValueError('Invalid outfit owner.')
        route = receipt.get('route')
        if route not in ('photo', 'career') or type(receipt.get('day')) is not int or not 1 <= receipt['day'] <= state['day']:
            raise ValueError('Invalid outfit unlock.')
        threshold = outfit.get(route + '_level')
        if threshold is None or type(receipt.get('level')) is not int or receipt['level'] < threshold:
            raise ValueError('Invalid outfit milestone.')
        if route == 'photo' and not isinstance(receipt.get('card_id'), str):
            raise ValueError('Missing outfit photo evidence.')
    for owner, key in equipped.items():
        if key not in unlocked or unlocked[key]['owner'] != owner:
            raise ValueError('Invalid equipped outfit.')


def matching_card(state, catalog, outfit):
    photos = outfit['photo_ids']
    if not photos:
        return None
    source = hashlib.sha256(catalog['source_id'].encode()).hexdigest()
    if source != outfit['library_sha256']:
        return None
    cards = catalog['cards']
    for photo in photos:
        if photo in state['owned'] and cards[photo].get('source') == 'library' and cards[photo]['owner'] == outfit['owner']:
            return photo
    for ident, item in state['owned'].items():
        card = cards[ident]
        if card['owner'] != outfit['owner'] or card.get('source') not in evolution.SET_CARDS:
            continue
        forms = card['forms'] if card['source'] == 'duo' else evolution.earned_forms(card, item)
        keys = {evolution.form_key(ident, photo) for photo in photos}
        if any(form['key'] in keys for form in forms):
            return ident
    return None


def reconcile(state, catalog):
    book = state.setdefault('wardrobe', empty())
    for key, outfit in OUTFITS.items():
        owner = outfit['owner']
        if key in book['unlocked'] or owner not in state['people']:
            continue
        level = 1 + state['people'][owner]['xp'] // 100
        if level < (outfit['photo_level'] or outfit['career_level']):
            continue
        receipt = {'owner': owner, 'level': level, 'day': state['day']}
        if level >= outfit['career_level']:
            receipt['route'] = 'career'
        else:
            card = matching_card(state, catalog, outfit)
            if not card:
                continue
            receipt.update(route='photo', card_id=card)
        book['unlocked'][key] = receipt
        state['journal'].append({'kind': 'outfit_unlocked', 'outfit': key, **receipt})


def wear(state, owner, key):
    from .engine import RuleError
    book = state['wardrobe']
    if owner not in state['people'] or not any(o['owner'] == owner for o in OUTFITS.values()):
        raise RuleError('Choose a recruited worker with a wardrobe.')
    if key != DEFAULT and (key not in book['unlocked'] or book['unlocked'][key]['owner'] != owner):
        raise RuleError('Earn this outfit before wearing it.')
    if book['equipped'].get(owner, DEFAULT) == key:
        return
    if key == DEFAULT:
        book['equipped'].pop(owner, None)
    else:
        book['equipped'][owner] = key
    state['journal'].append({'kind': 'outfit_equipped', 'owner': owner, 'outfit': key, 'day': state['day']})


def views(state, catalog):
    book = state['wardrobe']
    result = {}
    for key, outfit in OUTFITS.items():
        owner = outfit['owner']
        if owner not in state['people']:
            continue
        worker = result.setdefault(owner, {'level': 1 + state['people'][owner]['xp'] // 100,
                                           'equipped': book['equipped'].get(owner, DEFAULT), 'outfits': []})
        receipt = book['unlocked'].get(key)
        row = {'id': key, 'name': outfit['name'], 'unlocked': bool(receipt),
               'photo_level': outfit['photo_level'], 'career_level': outfit['career_level'],
               'has_photo': bool(matching_card(state, catalog, outfit))}
        if receipt:
            row['art'] = {'appearance_id': key, 'image': '/game/api/outfit/' + key, 'sha256': outfit['sha256']}
            for view in ('side', 'back'):
                if view in outfit:
                    row['art'][view] = {'image': row['art']['image'] + '?view=' + view, 'sha256': outfit[view + '_sha256']}
        worker['outfits'].append(row)
    return result
