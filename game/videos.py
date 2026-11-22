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
            rows[ident] = (card['owner'], card['name'], ident)
        if card['source'] in evolution.SET_CARDS:
            forms = card['forms'] if owned is None or card['source'] == 'duo' else evolution.earned_forms(card, owned[ident])
            for form in forms:
                if form.get('media_id'):
                    rows[form['media_id']] = (card['owner'], form.get('name') or form['media_id'], ident)
    return rows


def new_awards(catalog, state, pairs):
    """A qualifying photo is evidence of the first unlock in this career."""
    if not state or not catalog.get('videos'):
        return
    receipts = state.get('earned_videos', {})
    owned = photos_in_cards(catalog, state['owned'])
    for vid, clip in catalog['videos'].items():
        owner = clip['owner']
        if vid in receipts.get(owner, {}):
            continue
        for mid in clip['photos'] or [pairs.get(vid)]:
            if mid in owned and owned[mid][0] == owner:
                yield owner, vid, {'photo': mid, 'card': owned[mid][2], 'via': 'set' if clip['photos'] else 'pair'}
                break


def reconcile(catalog, state, pairs):
    for owner, vid, proof in new_awards(catalog, state, pairs):
        state.setdefault('earned_videos', {}).setdefault(owner, {})[vid] = proof
        state.setdefault('journal', []).append({'kind':'video_earned', 'day':state['day'], 'owner':owner, 'clip':vid, **proof})


def validate_receipts(state, catalog):
    receipts = state.get('earned_videos', {})
    if not isinstance(receipts, dict):
        raise ValueError('Invalid earned video history.')
    for owner, clips in receipts.items():
        if owner not in catalog['people'] or not isinstance(clips, dict):
            raise ValueError('Invalid video owner.')
        for vid, proof in clips.items():
            if (not isinstance(vid, str) or not vid or not isinstance(proof, dict) or set(proof) != {'photo','card','via'}
                    or not isinstance(proof['photo'], str) or not proof['photo'] or proof['via'] not in ('set','pair')):
                raise ValueError('Invalid video receipt.')
            ident, photo = proof['card'], proof['photo']
            card = catalog['cards'].get(ident)
            if ident not in state['owned'] or not card or card['owner'] != owner:
                raise ValueError('Missing earned card for this video.')
            if card['source'] in evolution.SET_CARDS:
                forms = card['forms'] if card['source']=='duo' else evolution.earned_forms(card, state['owned'][ident])
                if not any(f['key']==evolution.form_key(ident,photo) or f.get('media_id')==photo for f in forms):
                    raise ValueError('Missing earned form for this video.')
            elif card['source'] != 'library' or photo != ident:
                raise ValueError('Invalid matching photo for this video.')


def unlocked(catalog, state):
    receipts = (state or {}).get('earned_videos', {})
    return {vid: clip for vid, clip in catalog.get('videos', {}).items()
            if vid in receipts.get(clip['owner'], {})}


def library_views(catalog, state):
    rows = defaultdict(list)
    for vid, clip in unlocked(catalog, state).items():
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
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pairs'").fetchone():
                return {}
            return dict(db.execute('SELECT clip,photo FROM pairs'))

    def editor(self, catalog):
        clips = {vid: {'name': c['name'], 'owner': c['owner']} for vid, c in catalog.get('videos', {}).items()
                 if not c['photos'] and c['owner'] in catalog['people']}
        owners = {c['owner'] for c in clips.values()}
        photos = {mid: {'owner': owner, 'name': name} for mid, (owner, name, _) in photos_in_cards(catalog).items() if owner in owners}
        return {'clips': clips, 'photos': photos, 'pairs': self.read()}

    @staticmethod
    def validate_link(catalog, clip, photo):
        candidate = catalog.get('videos', {}).get(clip)
        if (not candidate or candidate['photos'] or candidate['owner'] not in catalog['people']
                or photo is not None and photos_in_cards(catalog).get(photo, (None,))[0] != candidate['owner']):
            raise ValueError('Choose a clip and a collectible photo of the same character.')

    def set(self, catalog, clip, photo, previous):
        self.validate_link(catalog,clip,photo)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self.write(db, 'main', clip, photo, previous)

    @staticmethod
    def write(db, schema, clip, photo, previous):
        # Only these two internal database aliases are used, including when the
        # pairing edit and the active career's receipt share one transaction.
        table = {'main':'main.pairs', 'links':'links.pairs'}[schema]
        db.execute(f'CREATE TABLE IF NOT EXISTS {table}(clip TEXT PRIMARY KEY,photo TEXT NOT NULL)')
        current = db.execute(f'SELECT photo FROM {table} WHERE clip=?', (clip,)).fetchone()
        if (current[0] if current else None) != previous:
            raise ValueError('This pairing changed in another window. Reopen the pairing editor.')
        if photo is None:
            db.execute(f'DELETE FROM {table} WHERE clip=?', (clip,))
        else:
            db.execute(f'INSERT OR REPLACE INTO {table} VALUES (?,?)', (clip, photo))
