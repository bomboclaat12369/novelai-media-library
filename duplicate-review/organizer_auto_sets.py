"""Save high-confidence matches into the Organizer's normal draft/transfer workflow."""
import json
import time
import uuid

import tracking
from bulk.sources import original_sequence
from set_matching import MAX_POST, RULE, match_sets


def post_sequences(catalog, posts):
    return {p:original_sequence(catalog,p,g['ids']) for p,g in posts.items()
            if g.get('kind') in ('instagram','forum') and len(g['ids'])>MAX_POST}


def available_stills(organizer):
    return {i for i, item in organizer.catalog.items() if item.get('media_type', 'image') == 'image'
            and not item.get('quarantine_only') and i not in organizer.discarded}


def remaining(organizer, groups=None):
    groups = organizer.sets() if groups is None else groups
    members = {i for g in groups.values() for i in g['members']}
    live = (organizer.library_placement or {}).get('set_ids_by_sha') or {}
    return sorted(i for i in available_stills(organizer) - members
                  if not organizer.catalog[i].get('existing_sets') and organizer.catalog[i]['sha'] not in live)


def exclusions(organizer, groups, state, db):
    ignored = set(state.get('selection', [])) | organizer.discarded
    ignored.update(i for g in groups.values() for i in g.get('removed_members', []))
    rejected = {row[0] for row in db.execute('SELECT id FROM rejected WHERE scope=?', (organizer.scope,))}
    parked = set().union(*organizer.parked.values()) if organizer.parked else set()
    deferred = {r[0] for r in db.execute("SELECT id FROM posts WHERE scope=? AND status='deferred'", (organizer.scope,))}
    queued = {r['id'] for r in organizer.individual_imports()
              if r['options'].get('destination') in ('review', 'purgatory')}
    ignored.update(queued)
    ignored.update(rejected)
    for ident, item in organizer.catalog.items():
        hashes = organizer.hashes(ident)
        if hashes & parked or any('auto-hold:'+h in rejected for h in hashes) or deferred.intersection(item.get('sources', {})):
            ignored.add(ident)
    return ignored


@tracking.journal().action('automatic')
def apply_matches(organizer, state, db):
    groups = organizer.sets(include_discarded=True)
    excluded = exclusions(organizer, groups, state, db)
    placement = organizer.library_placement or {}
    live_sets = placement.get('set_ids_by_sha')
    local = {}
    for group in groups.values():
        for ident in group['members']:
            local.setdefault(ident, set()).add(group.get('library_id'))
    for ident, item in organizer.catalog.items():
        digest = item.get('sha')
        if digest in (placement.get('held_hashes') or set()):
            excluded.add(ident)
        if live_sets is not None:
            active = live_sets.get(digest,set())
            if active - local.get(ident,set()) or set(item.get('existing_sets',[])) - active:
                excluded.add(ident)
    mixed = {p for p in organizer.posts if organizer.is_mixed(p, state.get('post_evidence', {}))}
    plan = match_sets(organizer.catalog, organizer.vector_by_id, groups, excluded, mixed,
                      post_sequences(organizer.catalog, organizer.posts))
    before = {}
    names = {g['name'].casefold() for g in groups.values()}
    ordinal = 1
    stamp = time.time()
    event = {'rule':RULE, 'recipe':organizer.recipe, 'inventory':organizer.bound[0],
             'collection':organizer.collection_id, 'sets':[]}
    for core in plan['new']:
        while ('Shoot %03d' % ordinal).casefold() in names:
            ordinal += 1
        name = 'Shoot %03d' % ordinal
        ordinal += 1
        ident = uuid.uuid4().hex
        ids = core['members']
        group = {'id':ident,'name':name,'members':ids,'auto_members':ids,'auto_pending':ids,
                 'created':stamp,'updated':stamp,'colors':[],'categories':[],'favorite':False,'library_id':None}
        db.execute('INSERT INTO sets VALUES (?,?,?)',(organizer.scope,ident,json.dumps(group)))
        before[ident] = None
        event['sets'].append({'id':ident,'kind':'new',**core})
    for ident, matches in plan['add'].items():
        old = db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(organizer.scope,ident)).fetchone()
        before[ident] = old[0] if old else None
        group = dict(groups[ident])
        for key in ('members','auto_members','auto_pending'):
            group[key] = list(dict.fromkeys(group.get(key,[])+list(matches)))
        group['updated'] = stamp
        db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(organizer.scope,ident,json.dumps(group)))
        event['sets'].append({'id':ident,'kind':'extend','matches':matches})
    added = sum(len(matches) for matches in plan['add'].values())
    created = sum(len(g['members']) for g in plan['new'])
    if before:
        event['source_hashes'] = {i:organizer.catalog[i]['sha'] for i in {
            i for g in plan['new'] for i in g['members']} | {
            i for matches in plan['add'].values() for i in matches} | {
            a for matches in plan['add'].values() for match in matches.values() for a in match['anchors']}}
        tracking.journal().event(db,'decision.automatic_set_match',organizer.scope,event)
        state['undo'] = {'action':'auto_sets','previous':before}
    return {'created_sets':len(plan['new']), 'new_members':created, 'extended_sets':len(plan['add']),
            'added_members':added,'matched':created+added,'remaining':len(remaining(organizer,groups))-created-added}


def undo_matches(organizer, db, undo):
    for ident, previous in undo['previous'].items():
        row = db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(organizer.scope,ident)).fetchone()
        current = json.loads(row[0]) if row else {}
        old = json.loads(previous) if previous is not None else {}
        if current.get('applied_at') != old.get('applied_at'):
            raise ValueError('This batch reached the Library. Restore its import checkpoint to undo that transfer.')
    for ident, previous in undo['previous'].items():
        if previous is None:
            db.execute('DELETE FROM sets WHERE scope=? AND id=?',(organizer.scope,ident))
        else:
            db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(organizer.scope,ident,previous))
    tracking.journal().event(db,'decision.undo_automatic_set_match',organizer.scope,{'sets':list(undo['previous'])})
