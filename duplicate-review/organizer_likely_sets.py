"""Review-only group sessions. All decisions use the Organizer's normal transaction."""
import uuid

import tracking
from likely_sets import RULE, review_queue
from organizer_auto_sets import matching_inputs, remaining
from organizer_splits import pending

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
            groups, excluded, mixed = matching_inputs(organizer, state, db)
            excluded.update(i for g in pending(organizer,db,groups,excluded).values() for i in g['members'])
            dismissed = {r[0] for r in db.execute('SELECT id FROM rejected WHERE scope=? AND context=?',
                                                   (organizer.scope, DISMISSED))}
    # All expensive comparisons run on a read-only snapshot outside the writer lock.
    review.rows, review.training = review_queue(review.items, review.vectors, groups, excluded, mixed,
                                               dismissed, review.breadth)
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
    for link in row['source_links']:
        keys.extend([link['source']] if 'source' in link else link.get('sources', []))
    return [key for key in dict.fromkeys(keys) if key in organizer.posts]


def reviewable_photos(organizer, state, db):
    groups, excluded, mixed = matching_inputs(organizer, state, db)
    excluded.update(i for g in pending(organizer, db, groups, excluded).values() for i in g['members'])
    return groups, excluded, mixed, set(remaining(organizer, groups)) - excluded


def source_page(organizer, review, body, state):
    row = next((r for r in review.rows if r['key'] == body.get('key')), None)
    source = body['source_post']
    if row is None or source not in matching_posts(organizer, row):
        raise ValueError('Choose a matching post for this group.')
    with organizer.db() as db:
        groups, _, mixed, available = reviewable_photos(organizer, state, db)
    if source in mixed:
        raise ValueError('This post changed. Refresh the likely groups.')
    assigned = {i: g['name'] for g in groups.values() for i in g['members']}
    post = organizer.posts[source]
    visible = set(organizer.post_ids(source)) - set(row['members'])
    ordered = organizer.ordered(post['ids'], 'original', source)
    others = [(n, i) for n, i in enumerate(ordered, 1) if i in visible
              and not organizer.catalog[i].get('quarantine_only') and organizer.catalog[i].get('media_type', 'image') == 'image']
    limit = 24
    offset = min(max(0, int(body.get('post_offset', 0)) // limit) * limit, (max(0, len(others) - 1) // limit) * limit)
    photos = []
    for pos, ident in others[offset:offset + limit]:
        reason = '' if ident in available else ('In ' + assigned[ident] if ident in assigned else 'Unavailable for this group')
        photos.append(dict(organizer.image(ident), source_position=pos, unavailable_reason=reason,
                           display_name=organizer.original_name(ident, source)))
    return {'photos': photos, 'offset': offset, 'total': len(others), 'limit': limit}


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
    if chosen and (chosen not in groups or groups[chosen].get('in_purgatory')):
        raise ValueError('That destination Set is no longer available.')
    def photo(ident):
        item = organizer.image(ident)
        key = row['posts'].get(ident)
        return dict(item, source_key=key, source_label=organizer.posts.get(key,{}).get('label',key),
                    source_position=row['positions'].get(ident))
    refs = row['references'] if chosen == row['target'] else groups.get(chosen,{}).get('members',())[:4]
    reason = ''
    if row.get('partial_post'):
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
                  alternatives=row['alternatives'], source_reason=reason,
                  source_posts=[{'id': key, 'label': organizer.posts[key].get('label') or key}
                                for key in matching_posts(organizer, row)],
                  photos=[photo(i) for i in row['members']], references=[photo(i) for i in refs])
    return answer


def validate(organizer, action, body, state, db):
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
    if action == 'dismiss_likely':
        return review, row, {}
    ids = organizer.valid_ids(body.get('ids',[]))
    target = str(body.get('target') or '')
    extras = set(ids) - set(row['members'])
    if not ids:
        raise ValueError('Select photos from this group.')
    if extras:
        visible = {i for post in matching_posts(organizer, row) if post not in mixed for i in organizer.post_ids(post)}
        if not extras <= visible & available:
            raise ValueError('Select available photos from this group or its matching posts.')
    if target and (target not in groups or groups[target].get('in_purgatory')):
        raise ValueError('Choose an available destination Set.')
    if not target and len(ids) < 2:
        raise ValueError('Select at least two photos for a new Set, or choose an existing Set.')
    for i in ids + row['references']:
        organizer.original_path(i)
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
    choices = {'ids': ids, 'target': target, 'name': name, 'colors': details.get('colors', previous.get('colors', [])),
               'categories': details.get('categories', previous.get('categories', [])),
               'favorite': details.get('favorite', previous.get('favorite', False))}
    if target and 'in_purgatory' in details:
        choices['in_purgatory'] = organizer.favorite(details['in_purgatory'])
    return review, row, choices


def record(organizer, db, review, row, action, selected, target=None):
    identities = set(row['posts']) | {w['id'] for values in row['reference_evidence'].values() for w in values}
    additions = {i: [p for p in matching_posts(organizer, row) if p in organizer.catalog[i].get('sources', {})]
                 for i in selected if i not in row['members']}
    identities.update(additions)
    evidence = {**row, 'manual_post_additions': additions, 'rule': row.get('rule_version', RULE), 'breadth':review.breadth, 'analysis_recipe': review.recipe, 'ranking': review.training,
                'inventory': organizer.bound[0], 'collection': organizer.collection_id,
                'source_hashes': {i: organizer.catalog[i]['sha'] for i in identities},
                'selected': list(selected), 'destination': target}
    tracking.journal().event(db, 'decision.'+action+'_group', organizer.scope, evidence)
