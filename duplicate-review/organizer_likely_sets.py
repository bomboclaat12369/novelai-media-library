"""Review-only group sessions. All decisions use the Organizer's normal transaction."""
import uuid

import tracking
from likely_sets import RULE, proposal_key, review_queue
from organizer_auto_sets import live_memberships, matching_inputs, remaining
from organizer_splits import pair_key, pending

DISMISSED = 'likely-set-group'


def new_name(groups):
    names = {g['name'].casefold() for g in groups.values()}
    ordinal = 1
    while ('Shoot %03d' % ordinal).casefold() in names:
        ordinal += 1
    return 'Shoot %03d' % ordinal


class Review:
    def __init__(self, organizer, state, breadth):
        self.token = uuid.uuid4().hex
        self.job = organizer.bound
        self.scope = organizer.scope
        self.revision = state.get('revision', 0)
        self.items = organizer.catalog
        self.vectors = organizer.vector_by_id
        self.recipe = organizer.recipe
        self.breadth = breadth
        self.rows = []
        self.training = {}

    def current(self, organizer, state):
        return (self.job == organizer.bound and self.scope == organizer.scope
                and self.revision == state.get('revision',0) and self.items is organizer.catalog
                and self.vectors is organizer.vector_by_id and self.recipe == organizer.recipe)


def session(organizer, body, state):
    review = organizer.likely_reviews.get(body.get('session'))
    if not review or not review.current(organizer, state):
        raise ValueError('The collection changed. Refresh the likely groups before continuing.')
    return review


def load_page(organizer, body):
    with organizer.lock, organizer.bulk.lock:
        organizer.bind()
        organizer.check_collection_idle(body)
        state = organizer.state()
        if body.get('session'):
            review = session(organizer, body, state)
            if 'source_post' in body:
                return source_page(organizer, review, body, state)
            return page(organizer, review, body)
        organizer.refresh_library_placement(force=True)
        breadth = body.get('breadth','closest')
        if breadth not in ('closest','broader','partial'):
            raise ValueError('Choose a group review list.')
        review = Review(organizer, state, breadth)
        with organizer.db() as db:
            groups, excluded, mixed, available = reviewable_photos(organizer, state, db)
            dismissed = {r[0] for r in db.execute('SELECT id FROM rejected WHERE scope=? AND context=?',
                                                   (organizer.scope, DISMISSED))}
            unfinished = []
            for saved in state.get('likely_remainders', {}).values():
                members = [i for i in saved['members'] if i in available and saved['posts'].get(i) not in mixed]
                if not members:
                    continue
                excluded.update(members)
                if saved['breadth'] == breadth:
                    unfinished.append(remainder(organizer, saved, members, breadth))
    # All expensive comparisons run on a read-only snapshot outside the writer lock.
    review.rows, review.training = review_queue(review.items, review.vectors, groups, excluded, mixed,
                                               dismissed, review.breadth)
    review.rows = unfinished + review.rows
    with organizer.lock, organizer.bulk.lock:
        organizer.bind()
        if not review.current(organizer, organizer.state()):
            raise ValueError('The collection changed while finding groups. Refresh to use the current photos.')
        if len(organizer.likely_reviews) >= 4:
            del organizer.likely_reviews[next(iter(organizer.likely_reviews))]
        organizer.likely_reviews[review.token] = review
        return page(organizer, review, body)


def matching_posts(organizer, row):
    keys = list(row['posts'].values())
    keys.extend(row.get('matching_sources', ()))
    for link in row['source_links']:
        keys.extend([link['source']] if 'source' in link else link.get('sources', []))
    return [key for key in dict.fromkeys(keys) if key in organizer.posts]


def remainder(organizer, row, members, breadth, placed=()):
    sources = matching_posts(organizer, row)
    posts = {i: row['posts'].get(i) or next((p for p in sources if p in organizer.catalog[i]['sources']), None)
             for i in members}
    return {'key': 'remaining:' + proposal_key(organizer.catalog, members, None),
            'parent_group': row.get('parent_group') or row['key'], 'members': members,
            'posts': posts, 'positions': {i: row['positions'][i] for i in members if i in row['positions']},
            'matching_sources': sources, 'breadth': breadth, 'placed_sets': list(dict.fromkeys(placed or row.get('placed_sets', ()))),
            'target': None, 'alternatives': [], 'references': [], 'reference_evidence': {}, 'source_links': [],
            'rule_version': 'manual-group-remainder-v1'}


def advance(organizer, review, offer, consumed, state, unavailable_targets, keep, retained=(), placed=(), discarded=()):
    # Stage the next queue alongside the database transaction. Install it only after commit.
    pending_rows = []
    before = state.get('likely_remainders', {})
    saved = dict(before)
    current_key = None
    claimed = consumed.union(retained)
    for row in review.rows:
        original = row.get('parent_group') or row['key']
        current = row is offer
        remaining = [i for i in row['members'] if i not in (consumed if current else claimed)]
        affected = (current or len(remaining) != len(row['members']) or row['target'] in unavailable_targets
                    or bool(discarded and any(i in discarded for i in row['posts'])))
        if not affected:
            pending_rows.append(row)
            continue
        saved.pop(original, None)
        if not keep:
            continue
        if current:
            remaining = list(dict.fromkeys([*remaining, *retained]))
        if remaining:
            next_row = remainder(organizer, row, remaining, review.breadth, placed if current else ())
            pending_rows.append(next_row)
            saved[original] = next_row
            if current:
                current_key = next_row['key']
    if before != saved:
        changed = set(before) | set(saved)
        state['undo']['previous_likely_remainders'] = {k: before.get(k) for k in changed if before.get(k) != saved.get(k)}
        state['likely_remainders'] = saved
    return pending_rows, current_key


def mark_separate(organizer, db, state, other_sets, target):
    added = []
    for other in dict.fromkeys(other_sets):
        if not other or other == target:
            continue
        key = pair_key(other, target)
        if db.execute("INSERT OR IGNORE INTO rejected VALUES (?,'split-set-pair',?)", (organizer.scope, key)).rowcount:
            added.append(key)
    if added:
        state['undo']['likely_separate_pairs'] = added
        tracking.journal().event(db, 'decision.keep_likely_sets_separate', organizer.scope,
                                 {'set': target, 'other_sets': list(other_sets), 'pairs': added})


def reviewable_photos(organizer, state, db):
    groups, excluded, mixed = matching_inputs(organizer, state, db, reviewing_remainders=True)
    excluded.update(i for g in pending(organizer, db, groups, excluded).values() for i in g['members'])
    return groups, excluded, mixed, set(remaining(organizer, groups)) - excluded


def post_photos(organizer, source):
    original = organizer.ordered(organizer.posts[source]['ids'], 'original', source)
    post_ids = organizer.post_ids(source)
    visible = set(post_ids)
    photos = [i for i in original if i in visible and not organizer.catalog[i].get('quarantine_only')
              and organizer.catalog[i].get('media_type', 'image') == 'image']
    return original, post_ids, photos


def owns_photo(organizer, group, ident):
    if ident in group.get('removed_members', ()):
        return False
    sid = group.get('library_id')
    if sid:
        if sid in live_memberships(organizer, ident):
            return True
        if sid in organizer.catalog[ident].get('existing_sets', ()):
            return False
    return ident in group['members']


def source_page(organizer, review, body, state):
    row = next((r for r in review.rows if r['key'] == body.get('key')), None)
    source = body['source_post']
    if row is None or source not in matching_posts(organizer, row):
        raise ValueError('Choose a matching post for this group.')
    with organizer.db() as db:
        groups, _, mixed, available = reviewable_photos(organizer, state, db)
    if source in mixed:
        raise ValueError('This post changed. Refresh the likely groups.')
    assigned = {}
    linked = {g['library_id']: g for g in groups.values() if g.get('library_id')}
    placement = organizer.library_placement or {}
    library_names = dict(placement.get('set_names', {}))
    for group in groups.values():
        if group.get('library_id'):
            library_names[group['library_id']] = group['name']
        for ident in group['members']:
            assigned.setdefault(ident, []).append(group)
    order = body.get('post_order', 'original')
    if order not in ('original', 'similar'):
        raise ValueError('Choose original post order or visual grouping.')
    original, post_ids, visible_photos = post_photos(organizer, source)
    positions = {ident: pos for pos, ident in enumerate(original, 1)}
    context = body.get('post_context') is True
    suggested = set(row['members'])
    included = set(visible_photos)
    if not context:
        included.difference_update(suggested)
    ordered = original if order == 'original' else organizer.ordered(post_ids, 'similar', source)
    page_ids = [i for i in ordered if i in included]
    focus = None
    if context and 'post_offset' not in body:
        requested = body.get('focus_id')
        if requested in suggested and requested in included:
            focus = requested
        else:
            candidates = [i for i in row['members'] if row['posts'].get(i) == source]
            focus = next((i for i in [*candidates, *row['members'], *row['references']] if i in included), None)
            if focus is None:
                witnesses = {link['survivor_sha'] for link in row['source_links']
                             if source in link.get('sources', ()) and link.get('survivor_sha')}
                focus = next((i for i in page_ids if organizer.catalog[i]['sha'] in witnesses), None)
    limit = 24
    at = page_ids.index(focus) if focus is not None else int(body.get('post_offset', 0))
    offset = max(0, min(at, len(page_ids) - 1)) // limit * limit
    photos = []
    for ident in page_ids[offset:offset + limit]:
        memberships = [g for g in assigned.get(ident, ()) if owns_photo(organizer, g, ident)]
        for sid in sorted(live_memberships(organizer, ident)):
            group = linked.get(sid)
            if group and ident in group.get('removed_members', ()):
                continue
            memberships.append(group or {'id': 'library:' + sid, 'name': library_names.get(sid, 'a Library Set')})
        names = [g['name'] for g in memberships]
        targets = {g['id']: g['name'] for g in memberships if not g.get('in_purgatory')}
        if not names and organizer.catalog[ident]['sha'] in placement.get('held_set_hashes', ()):
            names.append('a Set under review')
        names = list(dict.fromkeys(names))
        reason = '' if ident in available else ('In ' + ', '.join(names) if names else 'Unavailable for this group')
        photos.append(dict(organizer.image(ident), source_position=positions[ident], suggested=ident in suggested,
                           set_names=names, destination_sets=targets, unavailable_reason=reason,
                           display_name=organizer.original_name(ident, source)))
    result = {'photos': photos, 'offset': offset, 'total': len(page_ids), 'limit': limit, 'focus_id': focus}
    if body.get('include_selectable'):
        result['selectable_ids'] = [i for i in visible_photos if i in available]
    return result


def destination_group(organizer, groups, target):
    if not target:
        return {}
    group = groups.get(target)
    # A matching-post badge can refer to a Library Set created after the last inventory.
    if group is None and target.startswith('library:'):
        sid = target[len('library:'):]
        placement = organizer.library_placement or {}
        by_hash = placement.get('set_ids_by_sha') or {}
        if sid in placement.get('set_names', {}) and any(sid in owners for owners in by_hash.values()):
            owner = organizer.bulk.current.get('config', {}).get('character_id') or organizer.category_catalog().get('character_id')
            library = organizer.engine.library.request('/api/library')
            record = next((g for g in library.get('sets', []) if g['id'] == sid and owner and
                           g.get('character_id') == owner and g.get('kind', 'set') == 'set'), None)
            if record:
                group = {k: record.get(k) for k in ('name', 'favorite', 'colors', 'categories', 'in_purgatory')}
                group.update(id=target, library_id=sid, saved=False,
                             members=[i for i,r in organizer.catalog.items() if sid in by_hash.get(r['sha'], ())
                                      and not r.get('quarantine_only') and i not in organizer.discarded])
                group['colors'] = group['colors'] or []
                group['categories'] = group['categories'] or []
                group['favorite'] = bool(group['favorite'])
    if not group or group.get('in_purgatory'):
        raise ValueError('That destination Set is no longer available.')
    return group


def page(organizer, review, body):
    rows = review.rows
    offset = max(0, min(int(body.get('offset',0)), len(rows)-1))
    answer = {'session': review.token, 'total': len(rows), 'offset': offset,
              'photos_left': sum(len(r['members']) for r in rows), 'training': review.training}
    if not rows:
        return answer
    row = rows[offset]
    groups = organizer.sets()
    chosen = body.get('destination', row['target']) or ''
    destination = destination_group(organizer, groups, chosen)
    separate_name = ''
    if destination:
        from organizer import runtime_helpers
        used = {g['name'].casefold() for g in groups.values()}
        used.update(name.casefold() for name in (organizer.library_placement or {}).get('set_names', {}).values() if name)
        separate_name = runtime_helpers()['LibraryStore']._numbered_set_name(destination['name'], used)
    def photo(ident):
        item = organizer.image(ident)
        key = row['posts'].get(ident)
        return dict(item, source_key=key, source_label=organizer.posts.get(key,{}).get('label',key),
                    source_position=row['positions'].get(ident))
    refs = row['references'] if chosen == row['target'] else destination.get('members', ())[:4]
    reason = ''
    if row.get('partial_post') and chosen == row['target']:
        post = row['partial_post']
        label = organizer.posts.get(post, {}).get('label', post)
        name = groups[row['target']]['name']
        reason = f'Each suggested photo resembles at least two photos from {label} already in {name}.'
    if row['source_links']:
        link = next((p for p in row['source_links'] if 'source' in p),row['source_links'][0])
        if 'source' in link:
            label = organizer.posts.get(link['source'],{}).get('label',link['source'])
            a,b = link['positions']
            reason = f'Two of these photos appear at positions {a} and {b} in {label}.'
        else:
            labels = [organizer.posts.get(p,{}).get('label',p) for p in link['sources']]
            reason = f'The same surviving photo links nearby images in {labels[0]} and {labels[1]}.'
    answer.update(key=row['key'], proposed_target=row['target'], destination=chosen, new_name=new_name(groups),
                  remaining_group=bool(row.get('parent_group')), separate_name=separate_name,
                  destination_set=destination if chosen and chosen not in groups else None,
                  alternatives=row['alternatives'], source_reason=reason,
                  source_posts=[{'id': key, 'label': organizer.posts[key].get('label') or key}
                                for key in matching_posts(organizer, row)],
                  photos=[photo(i) for i in row['members']], references=[photo(i) for i in refs])
    return answer


def current_offer(organizer, body, state, db):
    review = session(organizer, body, state)
    row = next((r for r in review.rows if r['key'] == body.get('key')), None)
    if row is None:
        raise ValueError('This suggestion is no longer pending.')
    groups, excluded, mixed, available = reviewable_photos(organizer, state, db)
    if not set(row['members']) <= available or mixed.intersection(row['posts'].values()):
        raise ValueError('A photo or source changed. Refresh the likely groups.')
    old_target = row['target']
    witnesses = {w['id'] for matches in row['reference_evidence'].values() for w in matches}
    if old_target and (old_target not in groups or groups[old_target].get('in_purgatory') or
            not witnesses <= set(groups[old_target]['members'])-excluded):
        raise ValueError('The suggested Set changed. Refresh the likely groups.')
    if db.execute('SELECT 1 FROM rejected WHERE scope=? AND context=? AND id=?',
                  (organizer.scope, DISMISSED, row['key'])).fetchone():
        raise ValueError('This group was already dismissed.')
    return review, row, groups, mixed, available


def checked_photos(organizer, row, body, mixed, available):
    ids = organizer.valid_ids(body.get('ids',[]))
    extras = set(ids) - set(row['members'])
    if extras:
        visible = {i for post in matching_posts(organizer, row) if post not in mixed for i in organizer.post_ids(post)}
        if not extras <= visible & available:
            raise ValueError('Select available photos from this group or its matching posts.')
    return ids


def validate(organizer, action, body, state, db):
    review, row, groups, mixed, available = current_offer(organizer, body, state, db)
    if action == 'dismiss_likely':
        return review, row, {}
    if action == 'discard_likely':
        ids = organizer.valid_ids(body.get('ids', []))
        visible = set(row['members'])
        for post in matching_posts(organizer, row):
            if post not in mixed:
                visible.update(i for i in organizer.post_ids(post) if organizer.catalog[i].get('media_type', 'image') == 'image')
        if not ids or not set(ids) <= visible:
            raise ValueError('Choose photos to discard from this group or its matching posts.')
        retained = checked_photos(organizer, row, {'ids': body.get('retain_ids', [])}, mixed, available)
        return review, row, {'ids': ids, 'retained': retained}
    ids = checked_photos(organizer, row, body, mixed, available)
    target = str(body.get('target') or '')
    if not ids:
        raise ValueError('Select photos from this group.')
    destination = destination_group(organizer, groups, target)
    if destination:
        groups[target] = destination
    anchor = body.get('destination_anchor')
    if anchor:
        if (anchor not in organizer.catalog or anchor in organizer.discarded or not destination or
                not any(anchor in organizer.posts[p]['ids'] for p in matching_posts(organizer, row)) or
                not owns_photo(organizer, destination, anchor)):
            raise ValueError('That photo’s Set changed. Choose the destination again.')
    if not target and len(ids) < 2:
        raise ValueError('Select at least two photos for a new Set, or choose an existing Set.')
    for i in ids:
        try:
            organizer.original_path(i)
        except (ValueError, OSError) as error:
            name = organizer.original_name(i, row['posts'].get(i)) if row['posts'].get(i) else organizer.catalog[i]['path']
            raise ValueError(f'Check the original for {name} or uncheck that photo. {error}') from error
    return review, row, dict(ids=ids, target=target, destination_set=destination,
                             **set_details(organizer, groups, target, body))


def set_details(organizer, groups, target, body):
    previous = groups.get(target,{})
    details = body.get('set_details', {})
    if not isinstance(details, dict):
        raise ValueError('Choose valid Set details.')
    name = str(details.get('name', previous.get('name') or body.get('name') or new_name(groups))).strip()
    if not name or len(name) > 250:
        raise ValueError('Give the Set a name (up to 250 characters).')
    if name.casefold() != str(previous.get('name', '')).casefold() and any(
            g['name'].casefold() == name.casefold() for g in groups.values() if g['id'] != target):
        raise ValueError('That Set name is in use. Choose it as the destination or use another name.')
    choices = {'name': name, 'colors': details.get('colors', previous.get('colors', [])),
               'categories': details.get('categories', previous.get('categories', [])),
               'favorite': details.get('favorite', previous.get('favorite', False))}
    if target and 'in_purgatory' in details:
        choices['in_purgatory'] = organizer.favorite(details['in_purgatory'])
    return choices


def record(organizer, db, review, row, action, selected, target=None):
    identities = set(row['posts']) | {w['id'] for values in row['reference_evidence'].values() for w in values}
    additions = {i: [p for p in matching_posts(organizer, row) if p in organizer.catalog[i].get('sources', {})]
                 for i in selected if i not in row['members']}
    identities.update(additions)
    post_choices = 'manual_post_discards' if action == 'discarded_likely' else 'manual_post_additions'
    evidence = {**row, post_choices: additions, 'rule': row.get('rule_version', RULE), 'breadth':review.breadth, 'analysis_recipe': review.recipe, 'ranking': review.training,
                'inventory': organizer.bound[0], 'collection': organizer.collection_id,
                'source_hashes': {i: organizer.catalog[i]['sha'] for i in identities},
                'selected': list(selected), 'destination': target}
    tracking.journal().event(db, 'decision.'+action+'_group', organizer.scope, evidence)
