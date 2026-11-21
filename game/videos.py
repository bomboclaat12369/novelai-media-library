"""Local clip rewards. The Library supplies media and Set membership, the career supplies ownership."""
from collections import defaultdict
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3

from . import evolution


def catalog_rows(root, media, groups, cards, paths_for):
    photos = {key for key, c in cards.items() if c['source'] == 'library'}
    photos.update(f['media_id'] for c in cards.values() if c.get('available') for f in c.get('forms', []))
    matches = defaultdict(set)
    for group in groups:
        if group.get('kind', 'set') != 'set' or any(group.get(k) for k in ('in_review','in_purgatory','flagged_for_removal')):
            continue
        owner = group.get('character_id')
        members = {mid for mid in group.get('media_ids', []) if media.get(mid, {}).get('character_id') == owner}
        for vid in members:
            if media[vid].get('media_type') == 'video':
                matches[vid].update(members & photos)
    clips = {}
    for vid, item in media.items():
        if item.get('media_type') != 'video' or any(item.get(flag) for flag in ('in_review', 'in_purgatory', 'flagged_for_removal')):
            continue
        path = paths_for(root, item)['original']
        if path and item.get('character_id') and Path(path).suffix.lower() in ('.mp4', '.webm', '.m4v', '.mov', '.ogv', '.ogg'):
            clips[vid] = {'owner': item['character_id'], 'name': item.get('original_name') or item.get('filename') or vid,
                          'original': path, 'photos': sorted(matches[vid])}
    return clips


def photos_in_cards(catalog, owned=None):
    rows = {}
    for ident in (owned if owned is not None else catalog['cards']):
        card = catalog['cards'][ident]
        if owned is None and not card.get('available'): continue
        if card['source'] == 'library' and (owned is not None or card['available']):
            rows[ident] = (card['owner'], card['name'])
        if card['source'] in evolution.SET_CARDS:
            forms = card['forms'] if owned is None or card['source'] == 'duo' else evolution.earned_forms(card, owned[ident])
            for form in forms:
                if form.get('media_id'):
                    rows[form['media_id']] = (card['owner'], form.get('name') or form['media_id'])
    return rows


def unlocked(catalog, state, pairs):
    if not state or not catalog.get('videos'):
        return {}
    owned = photos_in_cards(catalog, state['owned'])
    return {vid: clip for vid, clip in catalog['videos'].items()
            if any(mid in owned and owned[mid][0] == clip['owner'] for mid in (clip['photos'] or [pairs.get(vid)]))}


def library_views(catalog, state, pairs):
    rows = defaultdict(list)
    for vid, clip in unlocked(catalog, state, pairs).items():
        rows[clip['owner']].append({'id': vid, 'name': clip['name']})
    return dict(rows)


class Pairings:
    def __init__(self, folder, source):
        key = hashlib.sha256(source.encode()).hexdigest()[:16]
        self.path = Path(folder) / ('video-pairs-' + key + '.sqlite3')

    def read(self):
        if not self.path.is_file():
            return {}
        with closing(sqlite3.connect(self.path)) as db:
            return dict(db.execute('SELECT clip,photo FROM pairs'))

    def editor(self, catalog):
        clips = {vid: {'name': c['name'], 'owner': c['owner']} for vid, c in catalog.get('videos', {}).items()
                 if not c['photos'] and c['owner'] in catalog['people']}
        owners = {c['owner'] for c in clips.values()}
        photos = {mid: {'owner': owner, 'name': name} for mid, (owner, name) in photos_in_cards(catalog).items() if owner in owners}
        return {'clips': clips, 'photos': photos, 'pairs': self.read()}

    def set(self, catalog, clip, photo, previous):
        data = self.editor(catalog)
        if clip not in data['clips'] or (photo is not None and data['photos'].get(photo, {}).get('owner') != data['clips'][clip]['owner']):
            raise ValueError('Choose a clip and a collectible photo of the same character.')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS pairs(clip TEXT PRIMARY KEY,photo TEXT NOT NULL)')
            current = db.execute('SELECT photo FROM pairs WHERE clip=?', (clip,)).fetchone()
            if (current[0] if current else None) != previous:
                raise ValueError('This pairing changed in another window. Reopen the pairing editor.')
            if photo is None:
                db.execute('DELETE FROM pairs WHERE clip=?', (clip,))
            else:
                db.execute('INSERT OR REPLACE INTO pairs VALUES (?,?)', (clip, photo))
