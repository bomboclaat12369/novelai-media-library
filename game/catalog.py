"""Read-only media adapter and deterministic, non-photographic demo catalog."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path

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


def read_library(root):
    root = Path(root).resolve()
    data = json.loads((root / 'library.json').read_text(encoding='utf-8'))
    battle_file = root / 'battles.json'
    battles = json.loads(battle_file.read_text(encoding='utf-8')) if battle_file.exists() else {'boards': {}}
    if not isinstance(data.get('media'), list) or not isinstance(data.get('characters'), list):
        raise ValueError('Select a media-library folder containing library.json.')
    people = {str(p['id']): {'id': str(p['id']), 'name': p['name'], 'color': i % 8}
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
        placed = sorted([m for m in images if scores.get(m['id'], {}).get('played', 0) > 0],
                        key=lambda m: -float(scores[m['id']].get('rating', 1200)))
        ranks = {}
        for i, item in enumerate(placed, 1):
            rating = round(float(scores[item['id']].get('rating', 1200)), 8)
            ranks.setdefault(rating, i)
        for m in images:
            ident = str(m['id'])
            score = scores.get(ident, {})
            ranked = score.get('played', 0) > 0
            rating = round(float(score.get('rating', 1200)), 8)
            rarity = 0
            if ranked and len(placed) >= 5 and len(ranks) > 1:
                rarity = next((tier for fraction, tier in ((.02,4),(.08,3),(.20,2),(.45,1))
                               if ranks[rating] <= max(1, math.ceil(len(placed)*fraction))), 0)
            paths = {}
            for field, key in [('image', 'thumb_rel'), ('original', 'stored_rel')]:
                relative = m.get(key) or m.get('stored_rel')
                path = (root / relative).resolve() if isinstance(relative, str) else None
                if path and root in path.parents and path.is_file():
                    paths[field] = str(path)
                else:
                    paths[field] = None
            if not paths['image']:
                paths['image'] = paths['original']
            cards[ident] = {'id': ident, 'owner': owner,
                            'name': m.get('original_name') or m.get('filename') or ident,
                            'rarity': rarity, 'specialty': SPECIALTIES[stable(ident) % 4],
                            'categories': [category_names[owner].get(str(c), str(c)) for c in m.get('categories', [])],
                            'source_categories': list(m.get('categories', [])), 'rarity_schema': 1, 'available': True,
                            'ranked': ranked, 'rating': rating, 'source': 'library', **paths}
    people = {p: v for p, v in people.items() if any(c['owner'] == p for c in cards.values())}
    if len(people) < 2:
        raise ValueError('The game needs eligible image cards for at least two girls.')
    return {'source_id': str(data.get('_tracking_store') or hashlib.sha256(str(root).encode()).hexdigest()),
            'demo': False, 'people': people, 'cards': cards}


def public_catalog(catalog):
    return {**catalog, 'cards': {key: {**{k:v for k,v in card.items() if k not in ('image','original')},
                                      'image': '/api/image/' + key if card.get('image') else None}
                                for key, card in catalog['cards'].items()}}
