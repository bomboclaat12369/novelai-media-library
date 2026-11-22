"""A previewed, single-transaction merge from the matching-post browser."""
import json
import time
import uuid

import organizer_likely_sets as likely
import organizer_splits as splits
import tracking
from organizer_auto_sets import live_memberships

RULE = 'matching-post-merge-v1'


def post_memberships(organizer, groups, post_ids):
    placement = organizer.library_placement or {}
    held = placement.get('held_hashes') or set()
    protected = {i for i in post_ids if organizer.hashes(i) & held}
    protected.update(i for g in groups.values() if g.get('in_purgatory') for i in g['members'])
    linked = {g['library_id']:g for g in groups.values() if g.get('library_id')}
    live = {}
    for ident in post_ids:
        if ident in protected:
            continue
        owners = sorted(live_memberships(organizer, ident))
        if not owners:
            continue
        unknown = [sid for sid in owners if sid not in linked]
        if unknown:
            label = (placement.get('set_names') or {}).get(unknown[0], 'an existing Set')
            raise ValueError('Refresh this Workbench collection to load ' + label + ' from Media Library before merging.')
        if any(linked[sid].get('in_purgatory') or ident in linked[sid].get('removed_members', ()) for sid in owners):
            protected.add(ident)
            continue
        live[ident] = owners
    candidates = set(post_ids) - protected
    participating = {k:g for k,g in groups.items() if candidates.intersection(g['members'])}
    for owners in live.values():
        for sid in owners:
            group = linked[sid]
            participating[group['id']] = group
    return participating, protected, live


def plan(organizer, db, state, body):
    from organizer import set_name_colors, title_case_label

    review, offer, groups, mixed, available = likely.current_offer(organizer, body, state, db)
    post = body.get('source_post')
    if post not in likely.matching_posts(organizer, offer) or post in mixed:
        raise ValueError('Choose a current matching post.')
    checked = likely.checked_photos(organizer, offer, body, mixed, available)
    _, _, post_ids = likely.post_photos(organizer, post)
    visible = set(post_ids)
    placement = organizer.library_placement or {}
    held_hashes = placement.get('held_hashes') or set()
    participating, protected, live = post_memberships(organizer, groups, post_ids)
    requested = str(body.get('target') or '')
    if requested:
        if requested not in groups or groups[requested].get('in_purgatory'):
            raise ValueError('Choose an available destination Set.')
        participating[requested] = groups[requested]
    fixed = [g for g in participating.values() if not splits.local_draft(g)]
    if len(fixed) > 1:
        raise ValueError('These Sets are already in Media Library: ' + ', '.join(g['name'] for g in fixed) +
                         '. Combine their existing memberships in Media Library first.')
    if fixed and requested and requested != fixed[0]['id']:
        raise ValueError('Choose ' + fixed[0]['name'] + ' as the destination to keep its Media Library membership.')
    keep = requested or (splits.destination(*participating.values()) if participating else '')
    target = groups.get(keep, {})
    sources = [g for k,g in participating.items() if k != keep]
    retired = [g['id'] for g in sources]
    moving = {i for g in sources for i in g['members']}
    if any(i not in organizer.catalog or i in organizer.discarded or organizer.catalog[i].get('quarantine_only')
           or organizer.hashes(i) & held_hashes
           or set(live_memberships(organizer,i)) - {target.get('library_id')} for i in moving):
        raise ValueError('A Set being merged contains an unavailable photo or a separate Library membership. Review that Set first.')
    if any(moving.intersection(g['members']) for k,g in groups.items() if k not in participating):
        raise ValueError('A photo outside this post also belongs to a separate Set. Review that membership first.')

    # A name typed for a proposed new draft must never rename a discovered Set.
    details = likely.set_details(organizer, groups, keep, body if keep == requested else {})
    name = target['name'] if target.get('name') == details['name'] else title_case_label(details['name'])
    edited = dict(target, name=name,
                  colors=organizer.colors(details['colors']),
                  categories=organizer.categories(details['categories'],target.get('categories', [])),
                  favorite=organizer.favorite(details['favorite']))
    if 'in_purgatory' in details and bool(edited.get('in_purgatory')) != details['in_purgatory']:
        edited.update(in_purgatory=details['in_purgatory'], purgatory_edited=True)
    group = splits.combined_group(edited, sources, retired)
    group['colors'] = set_name_colors(group['name'], group['colors'])
    additions = list(dict.fromkeys([*(i for i in post_ids if i in available and i not in protected), *checked]))
    group['members'] = list(dict.fromkeys([*group['members'], *live, *additions]))
    members = set(group['members'])
    group['removed_members'] = [i for i in group['removed_members'] if i not in members]
    if not keep and len(members) < 2:
        raise ValueError('At least two available photos are needed for a new Set.')
    if keep and not sources and members == set(target['members']):
        raise ValueError('These photos are already together in ' + target['name'] + '.')
    keep_held = any(g.get('under_review') for g in participating.values())
    summary = {'name':group['name'], 'target':keep, 'count':len(members),
               'post':organizer.posts[post].get('label') or post,
               'from_post':len(members & visible), 'checked_elsewhere':len(set(checked) - visible),
               'other_members':len(members - visible - set(checked)), 'skipped':len(visible - members),
               'sets':[{'id':k,'name':g['name'],'count':len(g['members'])} for k,g in participating.items()],
               'under_review':keep_held}
    summary['stamp'] = splits.digest([RULE,review.scope,review.job,review.revision,offer['key'],post,checked,
                                      post_ids,additions,participating,live,group,summary,
                                      placement.get('set_ids_by_sha') is not None])
    return summary, group, participating, live, review, offer, additions


def preview(organizer, body):
    with organizer.lock, organizer.bulk.lock:
        organizer.bind()
        organizer.check_collection_idle(body)
        organizer.refresh_library_placement(force=True)
        with organizer.db() as db:
            return plan(organizer, db, organizer.state(db), body)[0]


def apply(organizer, db, state, body):
    summary, group, participating, live, review, offer, additions = plan(organizer, db, state, body)
    if summary['stamp'] != body.get('stamp'):
        raise ValueError('The merge changed. Open the preview again before merging.')
    for i in additions:
        organizer.original_path(i)
    hold = organizer.favorite(body.get('hold_for_review',False)) or summary['under_review']
    gid = summary['target'] or uuid.uuid4().hex
    group.update(id=gid, updated=time.time())
    if not summary['target']:
        group.update(created=group['updated'], library_id=None)
    def snapshot(sid):
        row = db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(organizer.scope,sid)).fetchone()
        return row[0] if row else None
    moved = {sid:snapshot(sid) for sid in participating if sid != gid}
    if any(raw is None for raw in moved.values()):
        raise ValueError('A source draft changed. Open the merge preview again.')
    undo = {'action':'set','id':gid,'previous':snapshot(gid),'moved':moved,
            'selection':state.get('selection',[]),'split_review':True,'likely_review':offer['key']}
    if hold:
        organizer.set_review_status(db,group,True,'merge_matching_post')
        undo['set_review'] = True
    splits.redirect_retired(state, moved, gid, undo)
    db.executemany('DELETE FROM sets WHERE scope=? AND id=?',((organizer.scope,sid) for sid in moved))
    db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(organizer.scope,gid,json.dumps(group)))
    state['undo'] = undo
    likely.record(organizer, db, review, offer, 'approved_likely', additions, gid)
    tracking.journal().event(db,'decision.merge_matching_post',organizer.scope,{
        'rule':RULE,'inventory':review.job[0],'collection':organizer.collection_id,'group':offer['key'],
        'post':body['source_post'],'checked':body.get('ids',[]),'preview':summary,'destination':gid,
        'sets_before':participating,'library_memberships':live,'members':group['members'],'under_review':bool(group.get('under_review')),
        'hashes':{i:organizer.catalog[i]['sha'] for i in group['members'] if i in organizer.catalog}})
    unavailable_targets = set(moved)
    if hold or group.get('in_purgatory'):
        unavailable_targets.add(gid)
    return review, offer, additions, unavailable_targets
