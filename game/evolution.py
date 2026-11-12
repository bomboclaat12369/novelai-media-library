"""Game-owned progression for the Library's hand-picked Set sequences."""
import hashlib


MASTERY_LEVELS = {3: (0, 2, 5), 4: (0, 1, 3, 5)}


def ready_cards(groups, media, people, paths_for, specialty_for):
    for group in groups:
        if not isinstance(group, dict) or group.get('kind', 'set') != 'set' or group.get('in_purgatory'):
            continue
        owner, sid = group.get('character_id'), group.get('id')
        recipe = group.get('after_hours_evolution')
        if not isinstance(owner, str) or owner not in people or not isinstance(sid, str) or not sid or not isinstance(recipe, dict):
            continue
        if type(recipe.get('version')) is not int or recipe['version'] != 1 or recipe.get('status') != 'ready':
            continue
        ids = recipe.get('media_ids')
        if not isinstance(ids, list) or len(ids) not in MASTERY_LEVELS or not all(isinstance(i, str) and i for i in ids):
            continue
        members = group.get('media_ids')
        if not isinstance(members, list) or len(set(ids)) != len(ids) or not all(i in members for i in ids):
            continue
        chosen = [media.get(i, {}) for i in ids]
        if any(m.get('character_id') != owner or m.get('media_type', 'image') != 'image' or
               any(m.get(flag) for flag in ('in_review', 'in_purgatory', 'flagged_for_removal')) for m in chosen):
            continue
        ident = 'evolution:' + sid
        if ident in media:
            continue
        forms = []
        for mid, item in zip(ids, chosen):
            # Exports retain order across edits without listing unrevealed source IDs or filenames.
            key = hashlib.sha256((ident + '\0' + mid).encode()).hexdigest()
            forms.append({'key': key, 'media_id': mid, 'name': item.get('original_name') or item.get('filename') or mid,
                          **paths_for(item)})
        yield {'id': ident, 'owner': owner, 'name': group.get('name') or 'Evolution Set',
               'source': 'evolution', 'forms': forms, 'rarity': 2, 'rarity_schema': 2,
               'specialty': specialty_for(ident), 'categories': [], 'source_categories': [],
               'available': all(f['original'] for f in forms), 'ranked': False, 'rating': 1200,
               'image': None, 'original': None}


def form_keys(forms):
    """The only part of a saved form that can be brought into a new catalog."""
    if not isinstance(forms, list) or len(forms) not in MASTERY_LEVELS:
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
                'forms': [{'number': i, 'media_id': form.get('media_id'), 'name': form.get('name'),
                           'original_available': bool(form.get('original')), 'image_available': bool(form.get('image'))}
                          for i, form in enumerate(earned, 1)]}
    return result
