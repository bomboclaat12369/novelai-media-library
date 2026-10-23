"""Sparse candidate retrieval + supported grouping, for local evaluation.

Thresholds are engineering hypotheses, never confidence percentages. Original
outfit similarity is used unblended. Context can admit additional connections.
A source connection alone cannot admit an edge or merge two groups.
"""
from collections import defaultdict
import numpy as np

RECIPE = 'bulk-evaluation-1'


def propose(items, outfit, scene, update=lambda **kw: None, check=lambda: None):
    n = len(items)
    if n < 2:
        return [], list(range(n)), []
    by_source = defaultdict(list)
    for i, item in enumerate(items):
        for key, source in item['sources'].items():
            if source['kind'] in ('forum', 'instagram'):
                by_source[key].append(i)
    candidates = set()
    capped = [key for key, ids in by_source.items() if len(ids) > 200]
    # Bound temporary memory: never allocate the full N x N score matrix.
    for start in range(0, n, 128):
        check()
        stop = min(n, start+128)
        for matrix, right, k in ((outfit[start:stop], outfit, 32), (scene[start:stop, 0], scene[:, 0], 24), (scene[start:stop, 1], scene[:, 1], 24)):
            scores = matrix @ right.T
            width = min(k+1, n)
            neighbors = np.argpartition(scores, n-width, axis=1)[:, -width:]
            for offset, ids in enumerate(neighbors):
                i = start+offset
                for j in ids:
                    if i != j:
                        candidates.add((min(i, int(j)), max(i, int(j))))
        update(phase='Finding outfit and setting candidates', done=stop, total=n)
    for ids in by_source.values():
        # Extremely large compilation posts are candidates through visual search;
        # do not create quadratic edges merely because they share a post ID.
        if len(ids) <= 200:
            for at, i in enumerate(ids):
                for j in ids[at+1:]:
                    candidates.add((min(i,j), max(i,j)))
    cache = {}

    def evidence(i, j):
        key = (min(i,j), max(i,j))
        if key in cache:
            return cache[key]
        o = float(outfit[i] @ outfit[j])
        full = float(scene[i, 0] @ scene[j, 0])
        outer = float(scene[i, 1] @ scene[j, 1])
        shared = items[i]['sources'].keys() & items[j]['sources'].keys()
        ig = any(items[i]['sources'][s]['kind']=='instagram' for s in shared)
        forum = any(items[i]['sources'][s]['kind']=='forum' for s in shared)
        # Do not force classification of an image as clothed or unclothed.
        # Outfit matches remain eligible regardless of the context score.
        context = (full >= .81 and outer >= .81) if ig else ((full >= .86 and outer >= .84) if forum else (full >= .91 and outer >= .89))
        accepted = o >= .86 or context
        strength = max(o, min(full,outer) + (.025 if ig else .01 if forum else 0))
        value = (accepted, strength, o, full, outer, 'outfit' if o >= .86 else 'setting + post' if ig or forum else 'setting')
        # Candidate cache only. Cross-group checks are short-lived and bounded.
        if key in candidates:
            cache[key] = value
        return value

    links = []
    for step, (i,j) in enumerate(sorted(candidates)):
        if step % 2000 == 0:
            check(); update(phase='Checking visual support between candidates', done=step, total=len(candidates))
        e = evidence(i,j)
        if e[0]:
            links.append((e[1],i,j))
    links.sort(reverse=True)
    groups = {i:{i} for i in range(n)}
    membership = list(range(n))
    # Known library sets anchor suggestions; they are never combined automatically.
    labels = {i:set(items[i].get('existing_sets', [])) for i in range(n)}
    for step, (_,i,j) in enumerate(links):
        if step % 1000 == 0:
            check(); update(phase='Building supported set proposals', done=step, total=len(links))
        a,b = membership[i],membership[j]
        if a == b:
            continue
        ga,gb = groups[a],groups[b]
        if len(ga)+len(gb)>120:
            continue
        if labels[a] and labels[b] and labels[a] != labels[b]:
            continue
        # A single bridge cannot join two internally unrelated groups. Every
        # member must have direct support on the other side; larger merges need
        # several supporting relationships, not just one high-scoring pair.
        compatible = True
        for left,right in ((ga,gb),(gb,ga)):
            required = min(2,len(right))
            for member in left:
                supporting = sum(evidence(member,other)[0] for other in right)
                if supporting < required or supporting/len(right) < .4:
                    compatible = False; break
            if not compatible:
                break
        if not compatible:
            continue
        groups[a] |= groups.pop(b);labels[a] |= labels.pop(b)
        for member in gb:
            membership[member] = a
    adjacency = defaultdict(list)
    for strength,i,j in links:
        adjacency[i].append((strength,j));adjacency[j].append((strength,i))
    result, singles = [], []
    for ids in groups.values():
        check()
        if not any(not items[i].get('reference') for i in ids):
            continue
        if len(ids)<2:
            singles.extend(ids);continue
        rows=[]
        for i in sorted(ids):
            inside=sorted((evidence(i,j) for j in ids if j!=i),key=lambda e:-e[1])
            rivals=sorted(((v,j) for v,j in adjacency[i] if j not in ids),reverse=True)
            best=inside[0];margin=best[1]-(rivals[0][0] if rivals else 0)
            support=sum(e[0] for e in inside)
            rows.append({'index':i,'support':support,'method':best[5], 'score':round(best[1],4),
                         'ambiguous':margin<.025,'alternatives':[j for _,j in rivals[:3]]})
        # This is a queue priority, not an accuracy claim.
        ambiguous = any(r['ambiguous'] for r in rows)
        result.append({'members':rows,'priority':'inspect' if ambiguous else 'review',
                       'existing_sets':sorted(set().union(*(set(items[i].get('existing_sets',[])) for i in ids)))})
    result.sort(key=lambda g:(g['priority']=='inspect',-len(g['members'])))
    return result,singles,capped
