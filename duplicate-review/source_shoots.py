"""Recognize a whole shoot across camera angles using a real source and local scene details."""
from collections import defaultdict

import numpy as np

from bulk.sources import original_sequence
from set_matching import WEIGHTS, channel_agreement, independent_photos, post_ids
from shoot_context import complete_shoot, numbered_series
from shoot_scene import RECIPE

MAX_GROUP = 32
MIN_GROUP = 3


def source_orders(items,mixed):
    posts=defaultdict(list)
    for i,item in items.items():
        for p in post_ids(item)-mixed:
            posts[p].append(i)
    return {p:original_sequence(items,p,ids) for p,ids in posts.items() if len(ids)>=MIN_GROUP
            and all(items[i].get('path') for i in ids)}


def source_spans(items,vectors,mixed,orders=None):
    for post,order in sorted((orders if orders is not None else source_orders(items,mixed)).items()):
        if len(order)<=24:
            yield post,order,True
        # Missing rows, videos and a visual cut interrupt an ordered run.
        run=[]
        for ident in order:
            valid=ident in vectors and not items[ident].get('quarantine_only') and items[ident].get('media_type','image')=='image'
            if run and (not valid or not np.all(channel_agreement(vectors[run[-1]],vectors[ident])>=[.74,.53,.62])):
                if MIN_GROUP<=len(run)<=MAX_GROUP and len(run)!=len(order):
                    yield post,run,False
                run=[]
            if valid:run.append(ident)
        if MIN_GROUP<=len(run)<=MAX_GROUP and len(run)!=len(order):
            yield post,run,False


def repeated_blocks(ids,post,items,positions):
    blocks={}
    sources=set.intersection(*(post_ids(items[i]) for i in ids))-{post}
    for q in sources.intersection(positions):
        if positions[q].keys()==positions[post].keys():continue
        loc=[positions[q][i] for i in ids]
        if max(loc)-min(loc)+1==len(ids):
            blocks[q]=[min(loc)+1,max(loc)+1]
    return blocks


def verify_span(ids,vectors,scene,whole,corroborated=False,numbered=False):
    n=len(ids)
    mat=np.stack([vectors[i] for i in ids]).reshape(n,3,768)
    values=np.stack([mat[:,k]@mat[:,k].T/WEIGHTS[k] for k in range(3)],axis=-1)
    values[np.arange(n),np.arange(n)]=np.nan
    proof = verify_visible_scene(ids, values, scene, whole, corroborated)
    if proof is None and whole:
        return complete_shoot(ids, values, scene, numbered, corroborated)
    return proof


def verify_visible_scene(ids, values, scene, whole, corroborated):
    n = len(ids)
    if (np.any(np.nanmin(values,axis=(0,1)) < [.57,.33,.57])
            or np.any(np.nanmedian(values,axis=1).min(axis=0)<[.68,.53,.68])):
        return None
    features=[scene.feature(i) for i in ids]
    if any(f is None for f in features):
        return None
    # Compare a limited number of distinct witnesses per photo. A close viewing
    # angle helps recover actual shared objects and textures across reframing.
    ranking=np.argsort(-np.nan_to_num(values@WEIGHTS,nan=-2),axis=1,kind='stable')
    edges=[set() for _ in ids]
    links=[]
    pairs=set()
    for j in range(n):
        for k in ranking[j,:min(n-1,7)]:
            k=int(k)
            if not np.all(values[j,k]>=[.67,.48,.60]):continue
            key=tuple(sorted((j,k)))
            if key in pairs:continue
            pairs.add(key)
            link=scene.pair(ids[j],ids[k])
            if link:
                edges[j].add(k); edges[k].add(j)
                links.append([ids[j],ids[k],link['inliers'],link['area']])
    if min(map(len,edges))<min(n-1,2):
        return None
    # A mixed post can contain two internally convincing groups. Separate
    # camera angles need independent outfit, scene and palette agreement.
    unseen=set(range(n));parts=[]
    while unseen:
        stack=[unseen.pop()];part=set(stack)
        while stack:
            found=edges[stack.pop()]&unseen
            part.update(found);stack.extend(found);unseen-=found
        parts.append(part)
    if any(f[3] is None for f in features):
        return None
    palettes = np.stack([f[3] for f in features])
    colors = palettes @ palettes.T
    if len(parts) == 1:
        # A reused background can give two different shoots a few geometric
        # links, even when someone has reposted the same compilation.
        strong = [set() for _ in ids]
        index = {ident: j for j, ident in enumerate(ids)}
        for a, b, count, area in links:
            if count >= 24 and area >= .055:
                strong[index[a]].add(index[b])
                strong[index[b]].add(index[a])
        if min(map(len, strong)) < max(2, n // 2):
            return None
        for j, peers in enumerate(strong):
            two_steps = {j} | peers | set().union(*(strong[k] for k in peers))
            if len(two_steps) != n:
                return None
        if np.min(colors) < .91 or np.any(np.nanmedian(values, axis=1).min(axis=0) < [.73,.57,.70]):
            return None
    else:
        if not corroborated or not whole or n < 6 or len(parts) > 3:
            return None
        if np.min(colors)<.93 or np.min(values[:,:,2],where=np.isfinite(values[:,:,2]),initial=1)<.68:
            return None
        for part in parts:
            rivals=set(range(n))-part
            bridges=[(j,k) for j in part for k in rivals if colors[j,k]>=.95 and
                     np.all(values[j,k]>=[.74,.58,.76])]
            if min(len({j for j,k in bridges}),len({k for j,k in bridges}))<2:
                return None
    return {'recipe':RECIPE,'geometric_pairs':len(links),'minimum_witnesses':min(map(len,edges)),
            'minimum_inliers':min(p[2] for p in links),'camera_groups':len(parts),'links':links}


def source_matches(items,vectors,groups,excluded,mixed,scene,progress=None):
    """Nominate from scratch, independently of earlier automatic memberships."""
    owner=defaultdict(set)
    for gid,group in groups.items():
        for ident in group['members']:owner[ident].add(gid)
    orders=source_orders(items,mixed)
    positions={p:{i:n for n,i in enumerate(order)} for p,order in orders.items()}
    pool=[]
    for post,ids,whole in source_spans(items,vectors,mixed,orders):
        free=[i for i in ids if i not in owner]
        if (not free or set(free)&excluded or any(i not in vectors or items[i].get('quarantine_only') or
                items[i].get('media_type','image')!='image' or (i not in owner and items[i].get('existing_sets')) for i in ids)
                or not independent_photos(items,ids)):
            continue
        targets={g for i in ids for g in owner.get(i,())}
        if len(targets)>1:continue
        target=next(iter(targets),None)
        if target is not None and (groups[target].get('in_purgatory') or len(set(ids)-set(free)-excluded)<2):
            continue
        pool.append((post,ids,whole,target))
    hits={}
    for n,(post,ids,whole,target) in enumerate(pool):
        if progress:progress(n,len(pool))
        key=frozenset(ids)
        if key in hits:
            hits[key]['posts'].add(post)
            continue
        blocks=repeated_blocks(ids,post,items,positions)
        numbered = whole and numbered_series(items, ids, post)
        options = (whole, bool(blocks), numbered)
        evidence = scene.check_group(ids, options, lambda: verify_span(ids, vectors, scene, *options))
        if evidence:
            window = [positions[post][ids[0]] + 1, positions[post][ids[-1]] + 1]
            hits[key] = {'members': list(ids), 'posts': {post, *blocks}, 'target': target,
                         'anchors': [i for i in ids if i in owner and i not in excluded],
                         'scene': dict(evidence, source_post=post, source_positions=window,
                                       whole_post=whole, repeated_positions=blocks)}
    if progress:progress(len(pool),len(pool))
    return list(hits.values())


def combine(original,hits,items,vectors,groups):
    # A verified larger shoot replaces an automatic subset. A partial overlap,
    # competing destination or a plausible existing shoot requires manual review.
    ref_owner=defaultdict(set)
    for gid,g in groups.items():
        for i in g['members']:
            if i in vectors:ref_owner[i].add(gid)
    refs=list(ref_owner)
    matrix=np.stack([vectors[i] for i in refs]) if refs else None
    accepted=[]
    for hit in sorted(hits,key=lambda h:(-len(h['members']),sorted(h['posts']))):
        ids=set(hit['members']); target=hit['target']
        if any(ids < set(other['members']) for other in hits):continue
        if any(ids & set(other['members']) and not set(other['members'])<=ids for other in hits if other is not hit):continue
        if any(ids & set(core['members']) and not set(core['members'])<=ids for core in original['new']):continue
        if any(ids & matches.keys() and gid!=target for gid,matches in original['add'].items()):continue
        if refs:
            scores=np.stack([vectors[i] for i in hit['members']])@matrix.T
            plausible=defaultdict(set)
            for n,row in enumerate(scores):
                for j in np.flatnonzero(row>=.84):
                    for gid in ref_owner[refs[j]]:
                        if gid!=target:
                            plausible[gid].add((n,j))
            crops = hit['scene'].get('crop_witnesses', {})
            if any(any(sum(hit['members'][n] == crop for n, j in pairs) >= 2 for crop in crops)
                   for pairs in plausible.values()):
                continue
            if any(len({n for n,j in pairs})>=2 and len({j for n,j in pairs})>=2 for pairs in plausible.values()):
                continue
        accepted.append(hit)
    covered={i for h in accepted for i in h['members']}
    new=[core for core in original['new'] if not set(core['members'])&covered]
    adds={gid:dict(matches) for gid,matches in original['add'].items()}
    for hit in accepted:
        ids=hit['members'];gid=hit['target']
        proof={'posts':sorted(hit['posts']),'scene':hit['scene']}
        if gid is None:
            new.append({'members':ids,**proof})
        else:
            members=set(groups[gid]['members'])
            anchors=hit['anchors']
            for i in ids:
                if i not in members:
                    adds.setdefault(gid,{})[i]={'anchors':anchors,**proof}
    return {'new':new,'add':adds}
