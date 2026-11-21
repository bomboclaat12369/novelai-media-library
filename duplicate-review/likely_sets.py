"""Read-only shoot proposals for explicit human review."""
from collections import Counter, defaultdict
import hashlib
import json

import numpy as np

from bulk.sources import original_sequence
from set_matching import WEIGHTS, evidence_vectors, independent_photos, post_ids
from source_shoots import source_orders

RULE = 'cross-post-review-v1'
MAX_PHOTOS = 12


def identities(item):
    values = {item.get('sha'), item.get('analysis_sha')}
    values.update(copy.get('sha') for copy in item.get('copies', ()))
    return values - {None, ''}


def source_layout(items, mixed):
    sources = {i: post_ids(item) - mixed for i, item in items.items()}
    counts = Counter(p for posts in sources.values() for p in posts)
    # Prefer the most specific known post over a large repost or compilation.
    home = {i: min(posts, key=lambda p: (counts[p], p)) for i, posts in sources.items() if posts}
    by_post = defaultdict(list)
    for ident, posts in sources.items():
        for post in posts:
            by_post[post].append(ident)
    positions = {}
    neighbors = defaultdict(set)
    for post, members in by_post.items():
        if not all(items[i].get('path') for i in members):
            continue
        order = original_sequence(items, post, members)
        for n, ident in enumerate(order):
            if home[ident] == post:
                positions[ident] = n + 1
                neighbors[ident].update(j for j in order[max(0,n-2):n+3] if j != ident and home[j] == post)
    return home, positions, neighbors


def corroborated_neighbors(items, mixed, homes, usable):
    """Actual neighbors in a post, or two post windows joined by the same surviving photo."""
    posts = defaultdict(list)
    for ident, item in items.items():
        for post in post_ids(item) - mixed:
            posts[post].append(ident)
    links, windows = defaultdict(dict), defaultdict(list)
    def connect(i, j, proof):
        if i != j and homes[i] != homes[j] and j not in links[i]:
            links[i][j] = proof
            links[j][i] = proof
    for post, rows in sorted(posts.items(), key=lambda pair:(len(pair[1]),pair[0])):
        if not all(items[i].get('path') for i in rows):
            continue
        order = original_sequence(items,post,rows)
        for pos, ident in enumerate(order):
            if ident in usable:
                for j in range(pos+1,min(len(order),pos+4)):
                    if order[j] in usable:
                        connect(ident,order[j],{'source':post,'positions':[pos+1,j+1]})
            item = items[ident]
            if (len(post_ids(item)-mixed) < 2 or not item.get('sha') or item.get('quarantine_only')
                    or item.get('media_type','image') != 'image' or len(windows[ident]) >= 8):
                continue
            near = [order[j] for j in range(max(0,pos-2),min(len(order),pos+3)) if j!=pos and order[j] in usable]
            if near:
                windows[ident].append((post,pos+1,near))
    for witness, bounded in windows.items():
        for n,(a,pa,left) in enumerate(bounded):
            for b,pb,right in bounded[n+1:]:
                proof = {'survivor_sha':items[witness]['sha'],'sources':[a,b],'survivor_positions':[pa,pb]}
                for i in left:
                    for j in right:
                        if homes[i] != homes[j] and independent_photos(items,[i,j,witness]):
                            connect(i,j,proof)
    return links


def ranking_weights(channels, ids, homes, manual):
    """Choose a review-only outfit/scene blend with a separate check on unseen Sets."""
    base = tuple(float(v) for v in WEIGHTS)
    choices = np.array([base, (.60,.22,.18), (.55,.18,.27), (.32,.40,.28), (.29,.25,.46)], np.float32)
    by_set = defaultdict(list)
    for n, ident in enumerate(ids):
        if ident in manual:
            by_set[manual[ident]].append(n)
    def digest(value):
        return hashlib.sha256(value.encode()).digest()
    ordered = sorted(by_set, key=lambda gid: (digest(gid), gid))[:160]

    def evaluate(gids):
        rows, labels = [], []
        for gid in gids:
            by_post = defaultdict(list)
            for n in sorted(by_set[gid], key=lambda n: digest(ids[n])):
                by_post[homes[n]].append(n)
            # Sample different posts first. Large Sets cannot dominate the score.
            picked = []
            for depth in range(12):
                picked.extend(photo[depth] for photo in by_post.values() if len(photo) > depth)
                if len(picked) >= 12:
                    break
            rows.extend(picked[:12])
            labels.extend([gid] * min(12, len(picked)))
        if len(rows) < 2:
            return None
        labels = np.asarray(labels)
        posts = np.asarray([homes[n] for n in rows])
        eligible = posts[:,None] != posts[None,:]
        probes = np.flatnonzero((eligible & (labels[:,None] == labels[None,:])).any(axis=1))
        tested_sets = np.unique(labels[probes])
        if len(tested_sets) < 6 or len(probes) < 24:
            return None
        views = channels[:,rows,:]
        similarity = views @ views.transpose(0,2,1)
        scores = []
        for weight in choices:
            rank = np.tensordot(weight, similarity[:,probes,:], axes=1)
            rank[~eligible[probes]] = -np.inf
            correct = labels[rank.argmax(axis=1)] == labels[probes]
            scores.append(float(np.mean([correct[labels[probes] == gid].mean() for gid in tested_sets])))
        return scores, len(tested_sets), len(probes)

    fit = evaluate(ordered[1::3] + ordered[2::3])
    check = evaluate(ordered[::3]) if fit else None
    info = {'adapted': False, 'weights': [round(v,3) for v in base]}
    if not fit or not check:
        return WEIGHTS, info
    best = int(np.argmax(fit[0]))
    info.update(fit_sets=fit[1], held_out_sets=check[1], held_out_queries=check[2],
                baseline=round(check[0][0],4), candidate=round(check[0][best],4))
    if fit[0][best] >= fit[0][0] + .02 and check[0][best] >= check[0][0] + .015:
        info.update(adapted=True, weights=[round(float(v),3) for v in choices[best]])
        return choices[best], info
    return WEIGHTS, info


def best_indices(row, limit):
    present = np.flatnonzero(np.isfinite(row))
    if len(present) > limit:
        boundary = np.partition(row[present], -limit)[-limit]
        present = present[row[present] >= boundary]
    return sorted(present.tolist(), key=lambda n: (-row[n], n))[:limit]


def proposal_key(items, members, target):
    identities = sorted(items[i]['sha'] for i in members)
    payload = json.dumps([target, identities], separators=(',', ':'))
    return 'likely:' + hashlib.sha256(payload.encode()).hexdigest()


def partial_posts(items, valid, owners, free, refs, mixed, dismissed):
    """Offer unassigned companions to one known Set in a compact source post."""
    available, references = set(free), set(refs)
    offers = []
    orders = source_orders(items, mixed)
    for post, order in sorted(orders.items(), key=lambda row: (len(row[1]), row[0])):
        if len(order) > 24 or not available.intersection(order):
            continue
        targets = {gid for i in order for gid in owners.get(i, ())}
        anchors = [i for i in order if i in references]
        if len(targets) != 1 or len(anchors) < 2 or not independent_photos(items, anchors):
            continue
        target = next(iter(targets))
        matrix = np.stack([valid[i] for i in anchors]).reshape(-1, 3, 768)
        evidence = {}
        for i in order:
            if i not in available or not independent_photos(items, [i, *anchors]):
                continue
            channels = np.einsum('jkd,kd->jk', matrix, valid[i].reshape(3,768)) / WEIGHTS
            scores = channels @ WEIGHTS
            witnesses = np.flatnonzero((channels[:,0] >= .65) & (scores >= .57))
            if len(witnesses) >= 2:
                top = sorted(witnesses, key=lambda k: -scores[k])[:3]
                evidence[i] = [{'id':anchors[k], 'post':post, 'score':round(float(scores[k]),4)} for k in top]
        members = list(evidence)
        if not members:
            continue
        key = proposal_key(items, members, target)
        if key in dismissed:
            continue
        used = {w['id'] for ws in evidence.values() for w in ws}
        shown = sorted(used, key=lambda a:(-sum(w['id']==a for ws in evidence.values() for w in ws), order.index(a)))[:4]
        involved = used | set(members)
        offers.append({'key':key, 'members':members, 'target':target, 'references':shown,
                       'posts':dict.fromkeys(involved, post), 'positions':{i:n for n,i in enumerate(order,1) if i in involved},
                       'reference_evidence':evidence, 'alternatives':[], 'source_links':[],
                       'partial_post':post, 'rule_version':'partial-post-review-v1',
                       'strength':min(ws[1]['score'] for ws in evidence.values())})
        available.difference_update(members)
    return sorted(offers, key=lambda row:(-row['strength'], -len(row['members']), row['key']))


def propose(items, vectors, sets, excluded, mixed, broader=False, partial=False, dismissed=()):
    valid = evidence_vectors(items, vectors)
    home, positions, near = source_layout(items, mixed)
    owners = defaultdict(set)
    manual = {}
    for gid, group in sets.items():
        unreviewed = set(group.get('auto_members', ())) - set(group.get('auto_reviewed', ()))
        for i in group['members']:
            owners[i].add(gid)
            if i not in unreviewed:
                manual[i] = gid
    represented = set()
    for i in items:
        if i in owners or i in excluded or items[i].get('existing_sets'):
            represented.update(identities(items[i]))
    free = []
    for i in sorted(valid):
        aliases = identities(items[i])
        if i in home and items[i].get('sha') and not represented.intersection(aliases):
            free.append(i)
            represented.update(aliases)
    refs = sorted(i for i in owners if i in valid and i in home and items[i].get('sha') and i not in excluded
                  and len(owners[i]) == 1 and not sets[next(iter(owners[i]))].get('in_purgatory'))
    ids = free + refs
    default = {'adapted': False, 'weights': [.45,.35,.20]}
    if partial:
        return partial_posts(items, valid, owners, free, refs, mixed, dismissed), default
    if not free or len({home[i] for i in ids}) < 2:
        return [], default
    nfree = len(free)
    at = {ident: n for n, ident in enumerate(ids)}
    homes = [home[i] for i in ids]
    post_index = np.unique(homes, return_inverse=True)[1]
    channels = np.ascontiguousarray(np.stack([valid[i] for i in ids]).reshape(-1,3,768).transpose(1,0,2))
    channels /= np.sqrt(WEIGHTS)[:,None,None]
    blend, training = ranking_weights(channels, ids, homes, manual)
    ref_owner = {at[i]: next(iter(owners[i])) for i in refs}
    source_links = corroborated_neighbors(items,mixed,home,set(ids)) if broader else {}
    edges, destinations = {}, defaultdict(dict)
    closest_cross = np.zeros(nfree, dtype=np.float32)
    channel_floor = (.59,.38,.49) if broader else (.73,.54,.62)
    seed_floor, neighbor_floor = (.595,.665) if broader else (.735,.695)
    group_floor, group_mean, witness_floor = (.56,.665,.62) if broader else (.665,.755,.705)
    max_size = 8 if broader else MAX_PHOTOS

    for start in range(0, nfree, 80):
        stop = min(start+80, nfree)
        similarities = channels[:,start:stop,:] @ channels.transpose(0,2,1)
        base = np.tensordot(WEIGHTS, similarities, axes=1)
        rank = np.tensordot(blend, similarities, axes=1)
        valid_pairs = ((similarities[0]>=channel_floor[0]) & (similarities[1]>=channel_floor[1])
                       & (similarities[2]>=channel_floor[2]) & (base>=seed_floor))
        for k, n in enumerate(range(start, stop)):
            cross = (post_index != post_index[n]) & valid_pairs[k]
            if broader:
                eligible = np.zeros(len(ids), dtype=bool)
                for other, proof in source_links.get(ids[n],{}).items():
                    j = at[other]
                    eligible[j] = 'source' in proof or base[k,j]>=.64
                cross &= eligible
            cross_rank = np.where(cross, rank[k], -np.inf)
            closest_cross[n] = max(0., float(cross_rank[:nfree].max()))
            for j in best_indices(cross_rank[:nfree], 10):
                pair = tuple(sorted((n,j)))
                edges[pair] = float(rank[k,j])
            for other in near[ids[n]]:
                j = at.get(other)
                if j is not None and j < nfree and base[k,j] >= neighbor_floor and np.all(similarities[:,k,j] >= [.64,.47,.55]):
                    edges[tuple(sorted((n,j)))] = float(rank[k,j]) + .018
            for index in best_indices(cross_rank[nfree:], 24):
                j = index + nfree
                if not independent_photos(items, [ids[n],ids[j]]):
                    continue
                gid = ref_owner[j]
                witnesses = destinations[n].setdefault(gid, [])
                if len(witnesses) < 3:
                    witnesses.append((float(rank[k,j]), j))

    # Require evidence across both fragments before joining them. A chain of
    # individually plausible pairs must not turn a mixed post into one group.
    groups = {i: [i] for i in range(nfree)}
    group_of = list(range(nfree))
    for (a,b), strength in sorted(edges.items(), key=lambda pair: (-pair[1], pair[0])):
        left, right = group_of[a], group_of[b]
        if left == right or len(groups[left]) + len(groups[right]) > max_size:
            continue
        if homes[a] != homes[b] and strength < max(closest_cross[a],closest_cross[b]) - (.08 if broader else .055):
            continue
        first, second = groups[left], groups[right]
        combined = first + second
        if not independent_photos(items, [ids[n] for n in combined]):
            continue
        sims = channels[:,first,:] @ channels[:,second,:].transpose(0,2,1)
        score = np.tensordot(WEIGHTS, sims, axes=1)
        floor = min(seed_floor,neighbor_floor) if len(combined)==2 else group_mean
        weakest_witness = min(score.max(axis=0).min(),score.max(axis=1).min())
        if (score.min() < group_floor or min(score.max(axis=0).mean(), score.max(axis=1).mean()) < floor
                or (weakest_witness < witness_floor and len(combined)>2)):
            continue
        groups[left].extend(groups.pop(right))
        for n in second:
            group_of[n] = left

    by_target, suggestions = defaultdict(list), []
    def package(rows, target, refs_by_strength, alternatives=()):
        members = [ids[n] for n in sorted(rows, key=lambda n:(homes[n],positions.get(ids[n],0),ids[n]))]
        refs_used = [ids[j] for j in sorted(refs_by_strength, key=lambda j:(-refs_by_strength[j],j))[:4]]
        # Different aliases of one physical photo are never cross-post witnesses.
        if not independent_photos(items, members + refs_used):
            return
        posts = {i:home[i] for i in members + refs_used}
        if len(set(posts.values())) < 2:
            return
        if target:
            strength = float(np.mean([destinations[n][target][0][0] for n in rows if target in destinations[n]]))
            reference_evidence = {ids[n]: [{'id':ids[j], 'post':homes[j], 'score':round(value,4)}
                                          for value,j in destinations[n].get(target,())] for n in rows}
        else:
            reference_evidence = {}
            block = channels[:,rows,:]
            scores = np.tensordot(blend, block @ block.transpose(0,2,1), axes=1)
            different = post_index[rows,None] != post_index[np.array(rows)[None,:]]
            support = np.where(different, scores, -np.inf).max(axis=1)
            strength = float(.6*np.mean(support) + .4*np.min(support))
        evidence = []
        if broader:
            for idx, i in enumerate(posts):
                for j in list(posts)[idx+1:]:
                    proof = source_links.get(i,{}).get(j)
                    if proof:
                        evidence.append({'photos':[i,j], **proof})
            if not evidence:
                return
        suggestions.append({'key': proposal_key(items,members,target), 'members': members, 'target': target,
                            'references': refs_used, 'posts': posts, 'positions': {i:positions[i] for i in posts if i in positions},
                            'reference_evidence':reference_evidence, 'alternatives':list(alternatives),
                            'source_links': evidence, 'strength': round(strength,4)})

    for rows in groups.values():
        candidates = defaultdict(list)
        for n in rows:
            for gid, witnesses in destinations[n].items():
                first = witnesses[0][0]
                supported = first >= .845 or (len(witnesses)>1 and first>=.785 and witnesses[1][0]>=.745)
                if broader:
                    supported = first>=.705 or (len(witnesses)>1 and first>=.665 and witnesses[1][0]>=.64)
                if first >= closest_cross[n]-.045 and supported:
                    candidates[gid].append(first)
        ranked = sorted(((sum(scores)/len(rows),gid) for gid,scores in candidates.items()
                         if len(scores)==len(rows)), reverse=True)
        best, gid = ranked[0] if ranked else (0,None)
        rival = ranked[1][0] if len(ranked)>1 else 0
        target_floor = (.705 if broader else .815) if len(rows)==1 else (.68 if broader else .79)
        if gid and best >= target_floor and best-rival >= .04:
            by_target[gid].append(rows)
        elif len({homes[n] for n in rows}) >= 2:
            package(rows,None,{},[candidate for value,candidate in ranked[:2] if value>=.72])

    for gid, fragments in by_target.items():
        pending, refs_used = [], {}
        for rows in sorted(fragments, key=lambda r:(-len(r),r[0])):
            compatible = not pending or (len(pending)+len(rows) <= max_size and
                np.min(np.tensordot(WEIGHTS,channels[:,pending,:] @ channels[:,rows,:].transpose(0,2,1),axes=1)) >= .665)
            if not compatible:
                package(pending,gid,refs_used)
                pending, refs_used = [], {}
            pending.extend(rows)
            for n in rows:
                for score,j in destinations[n].get(gid,()):
                    refs_used[j] = max(refs_used.get(j,0),score)
        if pending:
            package(pending,gid,refs_used)
    suggestions.sort(key=lambda r:(-(r['strength']+.008*min(len(r['members'])-1,5)),r['key']))
    return suggestions, training


def review_queue(items, vectors, sets, excluded, mixed, dismissed=(), breadth='closest'):
    if breadth == 'partial':
        return propose(items, vectors, sets, excluded, mixed, partial=True, dismissed=dismissed)
    rows, training = propose(items, vectors, sets, excluded, mixed)
    rows = [r for r in rows if r['key'] not in dismissed]
    if breadth == 'broader':
        reserved = {i for r in rows for i in r['members']}
        rows, training = propose(items, vectors, sets, excluded | reserved, mixed, broader=True)
        rows = [r for r in rows if r['key'] not in dismissed]
    return rows, training
