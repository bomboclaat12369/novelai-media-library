"""Read hand-picked Set artwork and expose the sides or forms a career can view."""
import hashlib


MASTERY_LEVELS = {3: (0, 2, 5), 4: (0, 1, 3, 5)}
DUO_SIDES = ('front', 'back')
SET_CARDS = ('evolution', 'duo')


def selected_ids(group, kind, media):
    recipe = group.get('after_hours_' + kind)
    if not isinstance(recipe, dict) or type(recipe.get('version')) is not int or recipe['version'] != 1:
        return []
    if kind == 'evolution' and recipe.get('status') != 'ready':
        return []
    ids = recipe.get('media_ids')
    lengths = (2,) if kind == 'duo' else MASTERY_LEVELS
    if not isinstance(ids, list) or len(ids) not in lengths or not all(isinstance(i, str) and i for i in ids):
        return []
    members = group.get('media_ids')
    if not isinstance(members, list) or len(set(ids)) != len(ids) or not all(i in members for i in ids):
        return []
    for mid in ids:
        item = media.get(mid, {})
        if item.get('character_id') != group['character_id'] or item.get('media_type', 'image') != 'image':
            return []
        if any(item.get(flag) for flag in ('in_review', 'in_purgatory', 'flagged_for_removal')):
            return []
    return ids


def selected_forms(group, kind, ident, media, paths_for):
    forms = []
    for mid in selected_ids(group, kind, media):
        item = media[mid]
        paths = paths_for(item)
        if kind == 'duo' and not paths['original']:
            return []
        # Exports keep acquisition order without disclosing source filenames or trusting imported paths.
        key = hashlib.sha256((ident + '\0' + mid).encode()).hexdigest()
        forms.append({'key': key, 'media_id': mid, 'name': item.get('original_name') or item.get('filename') or mid,
                      **paths})
    return forms


def duo_rarity(forms, cards):
    photos = (cards.get(f.get('media_id')) for f in forms)
    return max((p['rarity'] for p in photos if p and p.get('source') == 'library' and p.get('available')), default=0)


def ready_cards(groups, media, people, paths_for, specialty_for, ordinary_cards):
    for group in groups:
        if not isinstance(group, dict) or group.get('kind', 'set') != 'set' or group.get('in_purgatory'):
            continue
        owner, sid = group.get('character_id'), group.get('id')
        if not isinstance(owner, str) or owner not in people or not isinstance(sid, str) or not sid:
            continue
        for kind in SET_CARDS:
            ident = kind + ':' + sid
            if ident in media:
                continue
            forms = selected_forms(group, kind, ident, media, paths_for)
            if forms:
                yield {'id': ident, 'owner': owner, 'name': group.get('name') or ('Duo' if kind == 'duo' else 'Evolution Set'),
                       'source': kind, 'forms': forms, 'rarity': duo_rarity(forms, ordinary_cards) if kind == 'duo' else 2,
                       'rarity_schema': 2, 'specialty': specialty_for(ident), 'categories': [], 'source_categories': [],
                       'available': all(f['original'] for f in forms), 'ranked': False, 'rating': 1200,
                       'image': None, 'original': None}


def form_keys(forms, kind='evolution'):
    """The only part of a saved form that can be brought into a new catalog."""
    if not isinstance(forms, list) or len(forms) not in ((2,) if kind == 'duo' else MASTERY_LEVELS):
        return []
    keys = [f.get('key') if isinstance(f, dict) else None for f in forms]
    if not all(isinstance(k, str) and len(k) == 64 and all(c in '0123456789abcdef' for c in k) for k in keys):
        return []
    return keys if len(set(keys)) == len(keys) else []


def earned_forms(card, owned):
    forms = card.get('forms', [])
    if not owned or len(forms) not in MASTERY_LEVELS:
        return []
    return forms[:sum(level <= owned['mastery'] for level in MASTERY_LEVELS[len(forms)])]


def public_art(form):
    return {'media_id': form.get('media_id'), 'name': form.get('name'),
            'original_available': bool(form.get('original')), 'image_available': bool(form.get('image'))}


def duo_views(catalog, owned):
    result = {}
    for ident in owned:
        card = catalog['cards'][ident]
        if card.get('source') == 'duo':
            result[ident] = {side: {'side': side, **public_art(form)}
                             for side, form in zip(DUO_SIDES, card['forms'])}
    return result


def progress(catalog, owned):
    result = {}
    for ident, item in owned.items():
        card = catalog['cards'][ident]
        earned = earned_forms(card, item)
        if earned:
            count = len(card['forms'])
            result[ident] = {
                'total': count,
                'next_mastery': MASTERY_LEVELS[count][len(earned)] if len(earned) < count else None,
                'forms': [{'number': i, **public_art(form)}
                          for i, form in enumerate(earned, 1)]}
    return result
