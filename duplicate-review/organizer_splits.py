"""Review, combine and undo split shoot decisions in the existing Organizer transaction."""
import hashlib
import json
import time
import uuid

import tracking
from match_history import MatchHistory
from split_sets import RULE, compare_sets


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def pair_key(a,b):
    return 'split:'+digest(sorted((a,b)))


def local_draft(group):
    return bool(group and not (group.get('library_id') or group.get('applied_at') or group.get('in_purgatory')))


def destination(a,b):
    def priority(g):
        confirmed = set(g['members'])-set(g.get('auto_members',())) | set(g.get('auto_reviewed',()))
        return (not bool(g.get('library_id')),not bool(confirmed),g.get('created') or 0,g['name'].casefold(),g['id'])
    return min((a,b),key=priority)['id']


def pending(organizer, db, groups, excluded):
    from organizer_auto_sets import remaining
    rows = db.execute('SELECT id,data FROM split_fragments WHERE scope=?',(organizer.scope,)).fetchall()
    if not rows:
        return {}
    free = set(remaining(organizer,groups))-excluded
    aliases = {old:gid for gid,g in groups.items() for old in g.get('merged_sources',[])}
    result = {}
    for key,raw in rows:
        data = json.loads(raw)
        anchor = aliases.get(data['anchor'],data['anchor'])
        group = groups.get(anchor)
        if (group and not group.get('in_purgatory') and set(data['members'])<=free and
                len(set(data['anchor_members']).intersection(group['members']))>=2 and
                all(organizer.catalog[i]['sha']==h for i,h in data['hashes'].items() if i in data['members'])):
            result[key] = dict(data,anchor=anchor,id=key,name='Unassigned photos')
    return result


def hold(organizer,db,entries,anchors,groups):
    keys = []
    for entry in entries:
        anchor = anchors.get(entry['anchor'],entry['anchor'])
        members = entry['members']
        hashes = {i:organizer.catalog[i]['sha'] for i in members}
        key = 'fragment:'+digest([anchor,sorted(hashes.values())])
        proof = dict(entry['comparison'])
        for side in ('left','right'):
            proof[side] = anchor if proof[side]==entry['anchor'] else key
        row = dict(entry,anchor=anchor,comparison=proof,anchor_members=groups[anchor]['members'],hashes=hashes)
        if db.execute('INSERT OR IGNORE INTO split_fragments VALUES (?,?,?)',
                      (organizer.scope,key,json.dumps(row))).rowcount:
            keys.append(key)
    return keys


def comparison(organizer, body):
    from organizer_auto_sets import matching_inputs
    with organizer.lock, organizer.bulk.lock:
        organizer.bind()
        organizer.check_collection_idle(body)
        state = organizer.state()
        organizer.refresh_library_placement(force=True)
        with organizer.db() as db:
            groups,excluded,mixed = matching_inputs(organizer,state,db)
            fragments = pending(organizer,db,groups,excluded)
            ignored = {r[0] for r in db.execute("SELECT id FROM rejected WHERE scope=? AND context='split-set-pair'",(organizer.scope,))}
            if not body.get('left'):
                history = MatchHistory(organizer,db)
                focus = {gid for gid,g in groups.items() if local_draft(g) and
                         (g.get('auto_members') or gid in history.created or g.get('merged_sources'))}
        candidates = []
        if body.get('left'):
            left,right = str(body['left']),str(body.get('right',''))
            if left==right or left not in groups:
                raise ValueError('Choose two different Sets in this collection.')
            if right in fragments and fragments[right]['anchor']==left:
                proof = fragments[right]['comparison']
            elif right in groups and (local_draft(groups[left]) or local_draft(groups[right])):
                proof = {}
            else:
                raise ValueError('Choose an available draft or suggested fragment.')
            candidates.append((left,right,proof))
        else:
            evidence_groups = {k:dict(g,members=[i for i in g['members'] if i not in excluded])
                               for k,g in groups.items() if not g.get('in_purgatory')}
            for row in compare_sets(organizer.catalog,organizer.vector_by_id,evidence_groups,focus,mixed):
                a,b = row['left'],row['right']
                if pair_key(a,b) not in ignored and (not body.get('focus') or body['focus'] in (a,b)):
                    candidates.append((a,b,row))
            for key,g in fragments.items():
                if not body.get('focus') or body['focus']==g['anchor']:
                    candidates.append((g['anchor'],key,g['comparison']))
            candidates.sort(key=lambda x:(-x[2].get('rank',0),x[0],x[1]))
        at = max(0,min(int(body.get('offset',0)),len(candidates)-1))
        choices = sorted(({'id':k,'name':g['name'],'count':len(g['members']),'draft':local_draft(g)} for k,g in groups.items()
                          if g['members'] and not g.get('in_purgatory')),key=lambda g:(g['name'].casefold(),g['id']))
        result = {'total':len(candidates),'offset':at,'choices':choices,'revision':state.get('revision',0)}
        if not candidates:
            return result
        a,b,proof = candidates[at]
        fragment = b in fragments
        ga,gb = groups[a],fragments[b] if fragment else groups[b]
        keep = a if fragment else destination(ga,gb)
        def side(g,page):
            ids = g['members']
            page = max(0,min(int(page),max(0,len(ids)-1)))//24*24
            visible = [i for i in ids[page:page+24] if i in organizer.catalog]
            return {'id':g['id'],'name':g['name'],'count':len(ids),'offset':page,
                    'photos':[organizer.image(i) for i in visible],'can_retire':local_draft(g)}
        source = proof.get('post')
        reason = ''
        if source:
            label = organizer.posts.get(source,{}).get('label',source)
            reason = 'Both groups have photos near positions %s and %s in %s.' % (*proof['positions'],label)
        elif proof:
            reason = 'Multiple photos on both sides have similar outfits and settings.'
        return dict(result,left=side(ga,body.get('left_page',0)),right=side(gb,body.get('right_page',0)),keep=keep,
                    fragment=fragment,reason=reason,stamp=stamp(organizer.scope,ga,gb),rule=RULE)


def stamp(scope,left,right):
    return digest([scope, [(g['id'],g.get('name'),g['members'],g.get('updated'),g.get('library_id'),g.get('applied_at')) for g in (left,right)]])


def apply(organizer,db,state,body,action):
    from organizer_auto_sets import matching_inputs, live_memberships
    groups,excluded,_ = matching_inputs(organizer,state,db)
    left,right = body.get('left'),body.get('right')
    fragments = pending(organizer,db,groups,excluded) if str(right).startswith('fragment:') else {}
    first = groups.get(left)
    fragment = fragments.get(right)
    second = fragment or groups.get(right)
    if (not first or not second or left==right or (fragment and fragment['anchor']!=left) or
            body.get('stamp')!=stamp(organizer.scope,first,second)):
        raise ValueError('These Sets changed. Reopen the comparison.')
    keep = body.get('keep')
    if keep not in (left,right) or (fragment and keep!=left):
        raise ValueError('Choose the Set to keep.')
    target,source = (first,second) if keep==left else (second,first)
    if target.get('in_purgatory') or not local_draft(source):
        raise ValueError('Keep the existing Library Set as the destination. Only a local draft can be retired here.')
    key = pair_key(left,right)
    if not fragment and action=='separate_split':
        if db.execute("INSERT OR IGNORE INTO rejected VALUES (?,'split-set-pair',?)",(organizer.scope,key)).rowcount!=1:
            raise ValueError('These Sets were already kept separate.')
        state['undo']={'action':'reject','context':'split-set-pair','ids':[key],'split_review':True}
    else:
        source_ids = source['members']
        present = set(source_ids)
        if len(present)!=len(source_ids) or not present:
            raise ValueError('Choose a nonempty group of distinct photos.')
        if any(i not in organizer.catalog or i in organizer.discarded or organizer.catalog[i].get('quarantine_only')
               or organizer.hashes(i).intersection((organizer.library_placement or {}).get('held_hashes',()))
               or set(live_memberships(organizer,i))-{target.get('library_id')} for i in present):
            raise ValueError('A source photo is unavailable, held, or already assigned in the Library. Refresh before combining.')
        if any(present.intersection(g['members']) for gid,g in groups.items() if gid not in (left,right)):
            raise ValueError('A source photo also belongs to another Set. Review that membership first.')
        if fragment:
            for i in source_ids:organizer.original_path(i)
        if fragment and action=='separate_split':
            from organizer_likely_sets import new_name
            gid = uuid.uuid4().hex
            group = {'id':gid,'name':new_name(groups),'members':list(source_ids),'created':time.time(),
                     'favorite':False,'colors':[],'categories':[],'library_id':None}
            raw = None
            separate_id = pair_key(keep,gid)
            db.execute("INSERT INTO rejected VALUES (?,'split-set-pair',?)",(organizer.scope,separate_id))
        else:
            gid = target['id']
            prev = db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(organizer.scope,gid)).fetchone()
            raw = prev[0] if prev else None
            group = dict(target)
            def union(field):
                return list(dict.fromkeys(target.get(field,[])+source.get(field,[])))
            group['members'] = union('members')
            for field in ('auto_members','auto_reviewed','auto_pending','categories','colors','merged_sources'):
                group[field] = union(field)
            if not fragment:
                group['merged_sources'] = list(dict.fromkeys([*group['merged_sources'],source['id']]))
            group['favorite'] = bool(target.get('favorite') or source.get('favorite'))
            included = set(group['members'])
            group['removed_members'] = [i for i in union('removed_members') if i not in included]
        undo = {'action':'set','id':gid,'previous':raw,'selection':state.get('selection',[]),'split_review':True,'moved':{}}
        if fragment:
            old = db.execute('SELECT data FROM split_fragments WHERE scope=? AND id=?',(organizer.scope,right)).fetchone()
            undo['fragment'] = [right,old[0]]
            db.execute('DELETE FROM split_fragments WHERE scope=? AND id=?',(organizer.scope,right))
            if action=='separate_split':
                undo['split_separate_id'] = separate_id
        else:
            old = db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(organizer.scope,source['id'])).fetchone()
            if not old:
                raise ValueError('The source draft is no longer available.')
            undo['moved'][source['id']] = old[0]
            db.execute('DELETE FROM sets WHERE scope=? AND id=?',(organizer.scope,source['id']))
            if state.get('target')==source['id']:
                undo['old_draft_target'] = source['id']
                state['target'] = gid
            if state.get('ui',{}).get('sidebarSet')==source['id']:
                state['ui']['sidebarSet']=gid
            for obj in (state.get('view',{}),state.get('ui',{}).get('view',{})):
                if obj.get('kind')=='set' and obj.get('id')==source['id']:
                    obj['id']=gid
        group['updated'] = time.time()
        db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(organizer.scope,gid,json.dumps(group)))
        state['undo'] = undo
    tracking.journal().event(db,'decision.'+action,organizer.scope,
        {'rule':RULE,'left':left,'right':right,'keep':keep,'result':state['undo'].get('id'),
         'was_unassigned':bool(fragment),'members':{g['id']:g['members'] for g in (first,second)},
         'hashes':{i:organizer.catalog[i]['sha'] for g in (first,second) for i in g['members'] if i in organizer.catalog},
         'collection':organizer.collection_id,'inventory':organizer.bound[0]})
