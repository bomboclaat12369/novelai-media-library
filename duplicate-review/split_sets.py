"""Compare whole shoots before treating independently found fragments as different Sets."""
from collections import defaultdict

import numpy as np

from bulk.sources import original_sequence
from set_matching import WEIGHTS, evidence_vectors, independent_photos, post_ids

RULE = 'split-shoot-review-v1'
SAMPLE = 20


def compare_sets(items, vectors, groups, focus, mixed):
    """Return review candidates only. Neither visual resemblance nor adjacency authorizes a merge."""
    valid = evidence_vectors(items, vectors)
    photos, representatives = {}, {}
    for gid, group in groups.items():
        if group.get('in_purgatory'):
            continue
        ids = [i for i in dict.fromkeys(group['members']) if i in valid]
        if len(ids) < 2:
            continue
        photos[gid] = ids
        sample = [ids[int(n)] for n in np.linspace(0,len(ids)-1,min(SAMPLE,len(ids)))]
        representatives[gid] = sample
    keys = sorted(photos)
    focus = set(focus).intersection(keys)
    if not focus or len(keys)<2:
        return []
    sources = defaultdict(lambda:defaultdict(set))
    for gid, ids in photos.items():
        for i in ids:
            for p in post_ids(items[i])-mixed:
                sources[p][gid].add(i)
    # Rank whole-Set views first. Shared original-post boundaries also nominate pairs,
    # including a wardrobe or angle change that makes the centroids less alike.
    centers = np.stack([np.mean([valid[i] for i in representatives[k]],axis=0) for k in keys])
    centers /= np.maximum(np.linalg.norm(centers,axis=1,keepdims=True),1e-8)
    candidates = set()
    for n, gid in enumerate(keys):
        if gid not in focus:
            continue
        scores = centers @ centers[n]
        for j in np.argsort(-scores,kind='stable')[:9]:
            if n!=j and scores[j]>=.76:
                candidates.add(tuple(sorted((gid,keys[j]))))
    shared = defaultdict(list)
    posts = {p for p, owners in sources.items() if len(owners)>1 and focus.intersection(owners)}
    by_post = defaultdict(list)
    for i, item in items.items():
        for p in post_ids(item).intersection(posts):
            by_post[p].append(i)
    for p, ids in by_post.items():
        if not all(items[i].get('path') for i in ids):
            continue
        order = original_sequence(items,p,ids)
        owners = defaultdict(set)
        for gid, members in sources[p].items():
            if len(members)>=2:
                for i in members:
                    owners[i].add(gid)
        for n, i in enumerate(order):
            for offset, other in enumerate(order[n+1:n+4],1):
                for left in owners.get(i,()):
                    for right in owners.get(other,()):
                        if left==right or not (left in focus or right in focus):
                            continue
                        pair = tuple(sorted((left,right)))
                        candidates.add(pair)
                        positions = [n+1,n+1+offset] if left==pair[0] else [n+1+offset,n+1]
                        shared[pair].append((offset,len(order),p,positions))
    rows = []
    for a,b in sorted(candidates):
        left,right = representatives[a],representatives[b]
        if not independent_photos(items,left+right):
            continue
        source = min(shared[(a,b)],default=None)
        x = np.stack([valid[i] for i in left]).reshape(-1,3,768)
        y = np.stack([valid[i] for i in right]).reshape(-1,3,768)
        channels = np.einsum('ick,jck->ijc',x,y) / WEIGHTS
        floor = [.61,.68,.70] if source else [.79,.75,.76]
        scores = channels @ WEIGHTS
        links = (channels >= floor).all(axis=2) & (scores >= (.71 if source else .82))
        # A repeated angle or one lookalike cannot stand in for either group.
        hits_a, hits_b = int(links.any(axis=1).sum()), int(links.any(axis=0).sum())
        coverage = min(hits_a/len(left),hits_b/len(right))
        if min(hits_a,hits_b)<2 or coverage < (.5 if source else .7):
            continue
        best = np.concatenate((scores.max(axis=0),scores.max(axis=1)))
        typical = float(np.median(best))
        if typical < (.73 if source else .84):
            continue
        row = {'left':a,'right':b,'witnesses':[hits_a,hits_b],'coverage':round(coverage,3),
               'similarity':round(typical,4),'rule':RULE}
        if source:
            _,length,post,positions = source
            row.update(post=post,positions=positions,post_size=length)
        row['rank'] = round(typical+.06*coverage+(.09 if source else 0),5)
        rows.append(row)
    return sorted(rows,key=lambda r:(-r['rank'],r['left'],r['right']))


def reconcile_plan(plan, items, vectors, groups, mixed):
    """Keep a credible anchor. Hold a possible second fragment for an explicit decision."""
    cores = {'new:'+str(n):core for n,core in enumerate(plan['new'])}
    if not cores:
        return plan
    rows = compare_sets(items,vectors,{**groups,**cores},cores,mixed)
    by_core = defaultdict(list)
    for row in rows:
        for a,b in ((row['left'],row['right']),(row['right'],row['left'])):
            if a in cores:
                by_core[a].append((b,row))
    # Existing Sets take precedence, then the largest independently verified draft.
    active = set(groups)
    held = []
    for key,core in sorted(cores.items(),key=lambda kv:(-len(kv[1]['members']),int(kv[0][4:]))):
        choices = [(other,row) for other,row in by_core[key] if other in active
                   and not groups.get(other,{}).get('in_purgatory')]
        if choices:
            target,row = choices[0]
            held.append({'anchor':target,'members':core['members'],'comparison':row,'original_proof':core})
        else:
            active.add(key)
    return {**plan,'new':[dict(core,plan_key=k) for k,core in cores.items() if k in active],
            'held_fragments':held}
