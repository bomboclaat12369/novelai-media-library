"""Workbench metadata editing through the companion's existing save/Undo APIs."""
import copy
import json
import sqlite3
import time
import uuid
from urllib.parse import urlencode


class LibraryEditor:
    SET_FIELDS = ('name', 'colors', 'categories', 'favorite', 'in_purgatory')

    def __init__(self, organizer):
        self.org = organizer
        self.plans = {}

    def context(self, body):
        org = self.org
        org.bind()
        org.check_collection_idle(body)
        client = org.engine.library
        instance = client.request('/api/tracking/status')['instance']
        config = (org.bulk.current or {}).get('config', {})
        if config.get('library_instance') and config['library_instance'] != instance:
            raise ValueError('The connected library changed. Reconnect the original library before editing.')
        library = client.request('/api/library')
        owner = config.get('character_id') or org.category_catalog().get('character_id')
        if not owner and len(library.get('characters', [])) == 1:
            owner = library['characters'][0]['id']
        character = next((c for c in library.get('characters', []) if c['id'] == owner), None)
        if not character:
            raise ValueError('Assign this collection to a girl in the connected library before editing.')
        return client, instance, library, character

    @staticmethod
    def fingerprint(kind, item):
        keys = ('id', 'character_id', 'name', 'colors', 'categories', 'favorite', 'in_purgatory', 'media_ids') if kind == 'set' else (
            'id', 'character_id', 'sha256', 'media_type', 'categories', 'in_all', 'in_videos', 'in_review', 'in_purgatory')
        return json.dumps({k: item.get(k) for k in keys}, sort_keys=True)

    @staticmethod
    def category_choices(kind, character, item):
        if kind == 'set':
            return character.get('set_categories', [])
        return [c for c in character.get('categories', []) if c.get('media_type', 'image') == item.get('media_type', 'image')]

    def read(self, body):
        org = self.org
        with org.lock, org.bulk.lock:
            client, instance, library, character = self.context(body)
            kind, ident = body.get('kind'), body.get('id')
            location = 'library'
            if kind == 'set':
                group = org.sets().get(ident)
                if not group or not group.get('library_id'):
                    raise ValueError('Choose an existing library set. New sets can be edited as drafts.')
                item = next((g for g in library.get('sets', []) if g['id'] == group['library_id']), None)
            elif kind == 'image':
                org.valid_ids([ident])
                digest = org.catalog[ident]['sha']
                matches = [m for m in library.get('media', []) if m['character_id'] == character['id'] and m.get('sha256') == digest]
                if not matches:
                    queue = client.request('/api/rapid-review?' + urlencode({'character_id': character['id']}))
                    matches = [m for m in queue['items'] if m.get('sha256') == digest]
                    location = 'rapid_review'
                if not matches:
                    return {'not_imported': True, 'character_id': character['id']}
                if len(matches) != 1:
                    raise ValueError('Several library records match this image. Choose the exact record in Media Library.')
                item = matches[0]
            else:
                raise ValueError('Choose a set or image to edit.')
            if not item or item.get('character_id') != character['id']:
                raise ValueError('This item is no longer in the selected girl’s library.')
            token = uuid.uuid4().hex
            while len(self.plans) >= 32:
                self.plans.pop(next(iter(self.plans)))
            self.plans[token] = dict(kind=kind, id=ident, target=item['id'], sha=item.get('sha256'),
                                     owner=character['id'], instance=instance, scope=org.scope, job=body['job'],
                                     location=location, expected=self.fingerprint(kind, item), at=time.monotonic())
            fields = {key: copy.deepcopy(item.get(key)) for key in (self.SET_FIELDS if kind == 'set' else ('categories',))}
            fields['categories'] = fields.get('categories') or []
            if kind == 'set':
                fields.update(colors=fields.get('colors') or [], favorite=bool(fields.get('favorite')),
                              in_purgatory=bool(fields.get('in_purgatory')))
            return {'token': token, 'kind': kind, 'location': location, 'fields': fields,
                    'name': item.get('name') if kind == 'set' else item.get('original_name', 'Image'),
                    'categories': self.category_choices(kind, character, item),
                    'in_review': bool(item.get('in_review')), 'in_purgatory': bool(item.get('in_purgatory'))}

    def save(self, body):
        org = self.org
        with org.lock, org.bulk.lock:
            plan = self.plans.get(body.get('token'))
            if not plan or time.monotonic() - plan['at'] > 1800:
                raise ValueError('This editor expired. Reopen it to load the latest details.')
            client, instance, library, character = self.context(body)
            if (instance, character['id'], org.scope, body['job']) != (plan['instance'], plan['owner'], plan['scope'], plan['job']):
                raise ValueError('The collection or library changed. Reopen the editor.')
            kind = plan['kind']
            queue = None
            if plan['location'] == 'rapid_review':
                queue = client.request('/api/rapid-review?' + urlencode({'character_id': plan['owner']}))
                records = queue['items']
            else:
                records = library.get('sets' if kind == 'set' else 'media', [])
            item = next((row for row in records if row['id'] == plan['target']), None)
            if not item or self.fingerprint(kind, item) != plan['expected']:
                raise ValueError('This item changed in the library. Reopen the editor before saving.')
            values = body.get('fields')
            allowed = set(self.SET_FIELDS if kind == 'set' else ('categories',))
            if not isinstance(values, dict) or set(values) - allowed:
                raise ValueError('Invalid metadata fields.')
            categories = values.get('categories', item.get('categories', []))
            valid = {c['id'] for c in self.category_choices(kind, character, item)}
            if not isinstance(categories, list) or any(not isinstance(c, str) or c not in valid for c in categories):
                raise ValueError('The available categories changed. Reopen the editor.')
            changes = {'categories': list(dict.fromkeys(categories))}
            if kind == 'set':
                name = values.get('name', item['name'])
                if not isinstance(name, str) or not name.strip() or len(name.strip()) > 250:
                    raise ValueError('Enter a set name (up to 250 characters).')
                changes.update(name=name.strip(), colors=org.colors(values.get('colors', item.get('colors', []))),
                               favorite=org.favorite(values.get('favorite', bool(item.get('favorite')))),
                               in_purgatory=org.favorite(values.get('in_purgatory', bool(item.get('in_purgatory')))))
                changed = {key: value for key, value in changes.items() if (
                    set(value) != set(item.get(key, [])) if key == 'categories' else
                    value != bool(item.get(key)) if key in ('favorite', 'in_purgatory') else
                    value != item.get(key, [] if key == 'colors' else ''))}
                saved = client.request('/api/sets/' + item['id'], changed) if changed else item
                try:
                    self.remember_set(saved, character, set(changed))
                except (OSError, ValueError, sqlite3.Error) as error:
                    raise ValueError('The library set was saved, but Workbench could not refresh its cached details. Reload the collection before editing again.') from error
            elif queue is not None:
                # Preserve the library's review selection, cursor, scroll and other
                # images' choices. Saving categories never promotes a queued image.
                client.request('/api/rapid-review/state', {**queue.get('state', {}), 'character_id': plan['owner'],
                               'choices': {item['id']: {**changes, 'rapid_edited': True}}})
            else:
                client.request('/api/media/' + item['id'] + '/categories', changes)
            self.plans.pop(body['token'], None)
            org.library_placement = None
            return {'ok': True, 'location': plan['location'], 'kind': kind}

    def remember_set(self, saved, character, changed):
        org = self.org
        fields = {key: copy.deepcopy(saved.get(key)) for key in self.SET_FIELDS}
        # Refresh metadata without replacing pending member additions or removals.
        org.bulk.current.setdefault('library_sets', {}).setdefault(saved['id'], {'id': saved['id']}).update(fields)
        with org.db() as db:
            for ident, raw in db.execute('SELECT id,data FROM sets WHERE scope=?', (org.scope,)).fetchall():
                group = json.loads(raw)
                if group.get('library_id') != saved['id']:
                    continue
                # Editing one library field must not erase unrelated draft edits.
                group.update({key: copy.deepcopy(fields[key]) for key in changed})
                if 'in_purgatory' in changed:group['purgatory_edited'] = False
                if changed:group['updated'] = time.time()
                db.execute('UPDATE sets SET data=? WHERE scope=? AND id=?', (json.dumps(group), org.scope, ident))
            catalog = org.category_catalog()
            categories = {c['id']: c for c in catalog['categories']}
            categories.update({c['id']: {**c, 'local': False} for c in character.get('set_categories', [])})
            catalog.update(character_id=character['id'], categories=list(categories.values()))
            db.execute('INSERT OR REPLACE INTO category_catalog VALUES (?,?)', (org.scope, json.dumps(catalog)))
        org.bulk.persist()
