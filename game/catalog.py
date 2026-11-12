"""Read-only media adapter and deterministic, non-photographic demo catalog."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from . import evolution
from .library_snapshot import rows as snapshot_rows

RARITIES = ('Common', 'Uncommon', 'Rare', 'Epic', 'Legendary')
SPECIALTIES = ('tips', 'service', 'efficiency', 'loyalty')


def stable(value):
    return int(hashlib.sha256(str(value).encode()).hexdigest()[:12], 16)


def demo_catalog():
    names = ['Nikki', 'Mikayla', 'Alice', 'Genesis'] + [f'Guest {i:02}' for i in range(1, 17)]
    people, cards = {}, {}
    for index, name in enumerate(names):
        owner = f'demo-{index}'
        people[owner] = {'id': owner, 'name': name, 'color': index % 8}
        count = 120 if index < 4 else 6
        for n in range(count):
            ident = f'{owner}-{n}'
            percentile = (n + 1) / count
            rarity = 4 if percentile <= .02 else 3 if percentile <= .08 else 2 if percentile <= .2 else 1 if percentile <= .45 else 0
            cards[ident] = {'id': ident, 'owner': owner, 'name': f'{name} · {n+1:03}',
                            'rarity': rarity, 'specialty': SPECIALTIES[stable(ident) % 4],
                            'categories': ['Evening', 'Studio', 'Summer'][n % 3:n % 3 + 1],
                            'available': True, 'ranked': True, 'rating': 1800 - n * 3,
                            'image': None, 'original': None, 'source': 'demo'}
    return {'source_id': 'demo-v1', 'demo': True, 'people': people, 'cards': cards}


def media_paths(root, media):
    paths = {}
    for field, key in [('image', 'thumb_rel'), ('original', 'stored_rel')]:
        relative = media.get(key) or media.get('stored_rel')
        path = None
        if isinstance(relative, str) and relative and not Path(relative).anchor and '..' not in Path(relative).parts:
            try:
                resolved = (root / relative).resolve()
                if root in resolved.parents and resolved.is_file():
                    path = str(resolved)
            except (OSError, ValueError, RuntimeError):
                pass
        paths[field] = path
    paths['image'] = paths['image'] or paths['original']
    return paths


def read_library(root):
    root = Path(root).resolve()
    data = json.loads((root / 'library.json').read_text(encoding='utf-8'))
    battle_file = root / 'battles.json'
    battles = json.loads(battle_file.read_text(encoding='utf-8')) if battle_file.exists() else {'boards': {}}
    if not isinstance(data.get('media'), list) or not isinstance(data.get('characters'), list):
        raise ValueError('Select a media-library folder containing library.json.')
    presentation=snapshot_rows(data,battles)
    people = {str(p['id']): {'id': str(p['id']), 'name': p['name'], 'color': i % 8,
                            'collection': {'finish':p.get('collection',{}).get('finish','obsidian'),
                                           'frames':p.get('collection',{}).get('frames',{})}}
              for i, p in enumerate(data['characters'])}
    category_names = {str(p['id']): {str(c['id']): c.get('name', str(c['id']))
                      for c in p.get('categories', [])} for p in data['characters']}
    eligible = [m for m in data['media'] if m.get('character_id') in people
                and m.get('media_type') != 'video' and m.get('in_all', True)
                and not any(m.get(k) for k in ('in_review', 'in_purgatory', 'flagged_for_removal'))]
    cards = {}
    for owner in people:
        images = [m for m in eligible if m['character_id'] == owner]
        scores = battles.get('boards', {}).get(owner + ':images', {}).get('ratings', {})
        placed = sorted([m for m in images if not presentation[m['id']]['provisional']],
                        key=lambda m: -float(scores[m['id']].get('rating', 1200)))
        ranks = {}
        for i, item in enumerate(placed, 1):
            rating = round(float(scores[item['id']].get('rating', 1200)), 8)
            ranks.setdefault(rating, i)
        for m in images:
            ident = str(m['id'])
            score = scores.get(ident, {})
            ranked = not presentation[ident]['provisional']
            rating = round(float(score.get('rating', 1200)), 8)
            rarity = 0
            if ranked and len(placed) >= 5 and len(ranks) > 1:
                rarity = next((tier for fraction, tier in ((.02,4),(.08,3),(.20,2),(.45,1))
                               if ranks[rating] <= max(1, math.ceil(len(placed)*fraction))), 0)
            cards[ident] = {'id': ident, 'owner': owner,
                            'name': m.get('original_name') or m.get('filename') or ident,
                            'rarity': rarity, 'specialty': SPECIALTIES[stable(ident) % 4],
                            'categories': [category_names[owner].get(str(c), str(c)) for c in m.get('categories', [])],
                            'source_categories': list(m.get('categories', [])), 'rarity_schema': 2, 'available': True,
                            'presentation':presentation[ident], 'media_sha256':m.get('sha256'),
                            'ranked': ranked, 'rating': rating, 'source': 'library', **media_paths(root, m)}
    if len({c['owner'] for c in cards.values()}) < 2:
        raise ValueError('The game needs eligible image cards for at least two girls.')
    media = {m['id']: m for m in data['media']}
    for card in evolution.ready_cards(data.get('sets', []), media, people, lambda m: media_paths(root, m),
                                      lambda ident: SPECIALTIES[stable(ident) % len(SPECIALTIES)]):
        cards[card['id']] = card
    owners = {c['owner'] for c in cards.values()}
    people = {p: v for p, v in people.items() if p in owners}
    return {'source_id': str(data.get('_tracking_store') or hashlib.sha256(str(root).encode()).hexdigest()),
            'demo': False, 'people': people, 'cards': cards}


def public_catalog(catalog):
    cards = {}
    for key, card in catalog['cards'].items():
        public = {k: v for k, v in card.items() if k not in ('image', 'original', 'forms')}
        public['image'] = '/api/image/' + key if card.get('image') or card.get('forms') else None
        public['original_available'] = bool(card.get('original') or card.get('forms'))
        cards[key] = public
    return {**catalog, 'cards': cards}
