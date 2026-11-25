"""Resolve the organizer's sourceCollection, sourcePost and optional sourcePhoto link.

The collection is the durable ID in transferred source.catalog records. Only
saved post keys and recorded original/copy fingerprints can select photos.
"""
import json
import re

from tracking import collection_alias


def photo_hashes(item):
    return {h for h in [item.get('sha'), *(c.get('sha') for c in item.get('copies', ()))] if h}


def focus_photo(catalog, members, photo):
    if not members:
        raise ValueError('This original post has no visible photos in the saved Workbench collection.')
    if not photo:
        return ''
    matches = []
    for ident in members:
        item = catalog[ident]
        if photo in photo_hashes(item):
            matches.append(((bool(item.get('quarantine_only')), item.get('sha') != photo), ident))
    if not matches:
        raise ValueError('The linked photo is no longer visible in this original post.')
    best = min(priority for priority, ident in matches)
    ids = [ident for priority, ident in matches if priority == best]
    if len(ids) != 1:
        raise ValueError('More than one photo matches this source. Open the post without a focused photo.')
    return ids[0]


def post_members(catalog, post):
    return [i for i, item in catalog.items()
            if post in item.get('sources', {}) and item['sources'][post].get('kind') != 'library']


def saved_destination(bulk, collection, post, photo):
    # A legacy folder inventory may now belong to a named character section.
    # Resolve that association by stored identity, including the Library instance.
    choices = {entry['id'] for entry in bulk.collections()}
    sections = bulk.sections.rows()
    targets = set()
    witnessed = False
    with bulk.db() as db:
        aliases = {row[0] for row in db.execute("SELECT alias FROM tracking_identities WHERE kind='collection' AND identity=?",
                                                (collection,))}
        rows = db.execute("""SELECT id,json_extract(data,'$.config'),json_extract(data,'$.section_id'),
                                    json_extract(data,'$.collection_id') FROM jobs
                             WHERE json_extract(data,'$.collection_id')=? OR json_extract(data,'$.collection_id') IS NULL
                             ORDER BY updated DESC""", (collection,))
        for ident, config, section_id, stored in rows:
            job = {'id': ident, 'config': json.loads(config or '{}'), 'section_id': section_id}
            if stored is None and collection_alias(job) not in aliases:
                continue
            owners = [s['id'] for s in sections if bulk.sections.belongs(job, s)]
            available = choices.intersection(owners or [ident])
            if not available:
                continue
            targets.update(available)
            if not witnessed:
                raw = db.execute("SELECT json_extract(data,'$.source_catalog') FROM jobs WHERE id=?", (ident,)).fetchone()[0]
                catalog = json.loads(raw or '{}')
                witnessed = any(not photo or photo in photo_hashes(catalog[i]) for i in post_members(catalog, post))
    if len(targets) != 1 or not witnessed:
        raise ValueError('This source is unavailable in its saved Workbench collection.')
    return targets.pop()


def validate_snapshot(organizer, job, post, photo):
    # Check the prospective inventory before switching the active collection.
    # First adoption also brings in the dispositions from any unmerged scopes.
    with organizer.db() as db:
        alias = collection_alias(job)
        identity = db.execute("SELECT identity FROM tracking_identities WHERE kind='collection' AND alias=?",(alias,)).fetchone()
        stored = db.execute("SELECT identity FROM tracking_identities WHERE kind='organizer_scope' AND alias=?",
                            (identity[0] if identity else job.get('collection_id'),)).fetchone()
        target_scope = stored[0] if stored else job.get('organizer_scope') or alias
        scopes = {target_scope}
        merged = {r[0] for r in db.execute('SELECT source FROM scope_merges WHERE target=?', (target_scope,))}
        scopes.update(set(job.get('source_scopes', ())) - merged)
        hidden = {r[0] for r in db.execute('SELECT hash FROM discarded')}
        hidden.update(h for s, h in db.execute('SELECT scope,hash FROM parked WHERE post=?', (post,)) if s in scopes)
    catalog = job.get('source_catalog', {})
    visible = [i for i in post_members(catalog, post) if not photo_hashes(catalog[i]).intersection(hidden)]
    focus_photo(catalog, visible, photo)


def locate(organizer, body):
    collection, post, photo = (body.get(k, '') for k in ('collection', 'post', 'photo'))
    if not isinstance(collection, str) or not collection or not isinstance(post, str) or not post:
        raise ValueError('This link needs the original Workbench collection and post.')
    if not isinstance(photo, str) or (photo and not re.fullmatch('[a-fA-F0-9]{64}', photo)):
        raise ValueError('This link has an invalid source photo fingerprint.')
    photo = photo.lower()
    current = organizer.bulk.current or {}
    if collection not in (organizer.collection_id, current.get('collection_id')):
        target = saved_destination(organizer.bulk, collection, post, photo)
        if target != current.get('id'):
            organizer.check_collection_idle(body)
            organizer.activate_collection(target, lambda job: validate_snapshot(organizer, job, post, photo))
            organizer.bind()
    members = organizer.post_ids(post) if post in organizer.posts else []
    return {'job': organizer.bound[0], 'post': post, 'focus': focus_photo(organizer.catalog, members, photo)}
