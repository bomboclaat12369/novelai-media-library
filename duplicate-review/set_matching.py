"""Conservative, single-pass Set matching over the organizer's saved visual analysis."""
from collections import defaultdict

import numpy as np

RULE = 'corroborated-shoot-v1'
WEIGHTS = np.array([.45, .35, .20], dtype=np.float32)
# Cosines in the outfit, whole-scene and outer-scene descriptors, respectively.
SOURCE_FLOOR = np.array([.88, .77, .78], dtype=np.float32)
CORROBORATED_FLOOR = np.array([.82, .65, .68], dtype=np.float32)
CROSS_POST_FLOOR = np.array([.90, .79, .80], dtype=np.float32)
RIVAL_GAP = .065
NEW_SET_RIVAL_CEILING = .70
MAX_POST = 24
MIN_RUN = 4


def post_ids(item):
    return {key for key, source in item.get('sources', {}).items()
            if source.get('kind') in ('instagram', 'forum')}


def evidence_vectors(items, vectors):
    # These cached vectors already contain the organizer's per-channel weights.
    valid = {}
    for ident, item in items.items():
        v = vectors.get(ident)
        if item.get('media_type', 'image') != 'image' or item.get('quarantine_only') or v is None:
            continue
        v = np.asarray(v, dtype=np.float32)
        if v.shape != (2304,) or not np.isfinite(v).all():
            continue
        channels = v.reshape(3, 768)
        if np.allclose(np.sum(channels * channels, axis=1), WEIGHTS, atol=.002, rtol=0):
            valid[ident] = v
    return valid


def channel_agreement(a, b):
    return np.sum(a.reshape(3, 768) * b.reshape(3, 768), axis=1) / WEIGHTS


def coherent(ids, vectors, floor):
    matrix = np.stack([vectors[i] for i in ids]).reshape(len(ids), 3, 768)
    minimum = np.array([np.min(matrix[:, n] @ matrix[:, n].T) / WEIGHTS[n] for n in range(3)])
    return float(minimum @ WEIGHTS) if np.all(minimum >= floor) else None


def components(edges):
    seen = set()
    for i in range(len(edges)):
        if i in seen:
            continue
        pending, group = [i], set()
        seen.add(i)
        while pending:
            current = pending.pop()
            group.add(current)
            new = set(np.flatnonzero(edges[current])) - seen
            pending.extend(new)
            seen.update(new)
        yield sorted(group)


def source_cliques(ids, vectors, floor):
    if not ids <= vectors.keys():
        return []
    order = sorted(ids)
    matrix = np.stack([vectors[i] for i in order]).reshape(len(order),3,768)
    edges = np.ones((len(order),len(order)),dtype=bool)
    for channel in range(3):
        values = matrix[:,channel] @ matrix[:,channel].T
        edges &= values >= floor[channel]*WEIGHTS[channel]
    return [{order[n] for n in part} for part in components(edges)
            if len(part)>=3 and edges[np.ix_(part,part)].all()]


def independent_photos(items, ids):
    seen = set()
    for ident in ids:
        item = items[ident]
        keys = {item.get('sha'), item.get('analysis_sha')} | {c.get('sha') for c in item.get('copies', [])}
        keys.discard(None)
        keys.discard('')
        if not keys or seen.intersection(keys):
            return False
        seen.update(keys)
    return True


def ordered_runs(sequence, vectors, eligible, floor):
    """Find consecutive, mutually compatible stills. Missing or held rows break the run."""
    def finish(run):
        if not MIN_RUN <= len(run) <= MAX_POST:
            return
        # A weak edge can be left behind. Never split a long chain into arbitrary drafts.
        for left, right in ((0,len(run)), (1,len(run)), (0,len(run)-1), (1,len(run)-1)):
            core = run[left:right]
            if len(core) >= MIN_RUN and coherent(core, vectors, floor) is not None:
                yield tuple(core)
                return

    run = []
    for ident in sequence:
        present = ident in eligible and ident in vectors
        if run and (not present or not np.all(channel_agreement(vectors[run[-1]],vectors[ident]) >= floor)):
            yield from finish(run)
            run = []
        if present:
            run.append(ident)
    yield from finish(run)


class OtherPhotos:
    """Look for a competing explanation among photos whose Sets are still unknown."""
    def __init__(self, vectors, origins, posts):
        self.ids = sorted(vectors)
        self.at = {i:n for n,i in enumerate(self.ids)}
        self.matrix = np.stack([vectors[i] for i in self.ids]) if self.ids else np.empty((0,2304),np.float32)
        self.origins = origins
        self.sources = {p for ps in origins.values() for p in ps}
        self.posts = posts

    def corroborated(self, common):
        # Each platform has material absent from the other. Identical or nested reposts
        # alone must not turn a mixed carousel into two independent confirmations.
        return any(p.split(':',1)[0] != q.split(':',1)[0] and self.posts[p]-self.posts[q]
                   and self.posts[q]-self.posts[p] for p in common for q in common)

    def supports(self, ident, witnesses, allowed, weakest, run_context=False):
        outside_posts = self.sources - set().union(*(self.origins[i] for i in [ident]+list(witnesses)))
        if (len(outside_posts) < 2 and not run_context) or len(self.ids)-len(allowed) < (12 if run_context else 6):
            return False
        score = self.matrix @ self.matrix[self.at[ident]]
        score[[self.at[i] for i in allowed if i in self.at]] = -np.inf
        return float(np.max(score)) < weakest - .045


def match_sets(items, vectors, groups, excluded, mixed_posts, ordered_posts=None):
    """Return new cores and additions to existing Sets; do not mutate any input."""
    vectors = evidence_vectors(items, vectors)
    posts = defaultdict(set)
    for ident, item in items.items():
        if item.get('media_type', 'image') == 'image' and not item.get('quarantine_only'):
            for post in post_ids(item):
                posts[post].add(ident)
    usable_posts = {p: ids for p, ids in posts.items() if p not in mixed_posts and 2 <= len(ids) <= MAX_POST}
    origins = {i: post_ids(items[i]).intersection(usable_posts) for i in vectors}
    # Singleton posts supply independent comparison context, though they cannot seed a draft.
    comparison_posts = {p for p,ids in posts.items() if p not in mixed_posts and len(ids)<=MAX_POST}
    comparison_origins = {i:post_ids(items[i]).intersection(comparison_posts) for i in vectors}
    outside = OtherPhotos(vectors, comparison_origins, posts)
    owners = defaultdict(set)
    for gid, group in groups.items():
        for ident in group['members']:
            owners[ident].add(gid)
    candidates = sorted(i for i in vectors if i not in excluded and i not in owners and not items[i].get('existing_sets'))
    runs = defaultdict(dict)
    allowed_for_runs = set(candidates) | (set(owners) - excluded)
    for post, sequence in (ordered_posts or {}).items():
        if post in mixed_posts or len(sequence) <= MAX_POST:
            continue
        # A substantial number of observed alternatives is needed even for a single-post inventory.
        analysed = len(set(sequence).intersection(vectors))
        positions = {i:n for n,i in enumerate(sequence,1)}
        for run in ordered_runs(sequence,vectors,allowed_for_runs,SOURCE_FLOOR):
            if analysed-len(run) >= 12 and independent_photos(items,run):
                runs[frozenset(run)][post] = [positions[run[0]],positions[run[-1]]]
    references = sorted(i for i in owners if i in vectors)
    reference_groups = [next(iter(owners[i])) if len(owners[i]) == 1 else None for i in references]
    auto = {i for g in groups.values() for i in g.get('auto_members', [])}
    eligible_anchors = defaultdict(list)
    for j, ident in enumerate(references):
        gid = reference_groups[j]
        if gid is not None and ident not in auto and ident not in excluded:
            eligible_anchors[gid].append(j)
    occupied_posts = {p for i in owners if i in items for p in post_ids(items[i]) if p in usable_posts}
    additions = defaultdict(dict)
    nearest = {}
    if references:
        ref_matrix = np.stack([vectors[i] for i in references])
        for start in range(0, len(candidates), 64):
            batch = candidates[start:start+64]
            for ident, scores in zip(batch, np.stack([vectors[i] for i in batch]) @ ref_matrix.T):
                best_index = int(np.argmax(scores))
                gid = reference_groups[best_index]
                nearest[ident] = float(scores[best_index])
                if gid is None or groups[gid].get('in_purgatory') or scores[best_index] < float(CORROBORATED_FLOOR @ WEIGHTS):
                    continue
                # Only manual members vote positively. Every other Set still competes.
                within = eligible_anchors[gid]
                if len(within) < 2:
                    continue
                first, second = sorted(within,key=lambda j:-float(scores[j]))[:2]
                anchors = [references[first], references[second]]
                if not independent_photos(items, [ident] + anchors):
                    continue
                rival = max((float(score) for j, score in enumerate(scores) if reference_groups[j] != gid), default=-1.)
                if scores[second] < rival + RIVAL_GAP:
                    continue
                shared = origins[ident].intersection(*(origins[i] for i in anchors))
                # A whole compilation can be reposted across platforms. Two manual
                # exemplars must always clear the full appearance threshold.
                floor = SOURCE_FLOOR if shared else CROSS_POST_FLOOR
                if not all(np.all(channel_agreement(vectors[ident], vectors[i]) >= floor) for i in anchors):
                    continue
                allowed = {ident} | {references[j] for j in within}
                evidence = {'anchors': anchors, 'posts': sorted(shared), 'similarity': round(float(scores[second]), 5),
                            'rival': round(rival, 5) if rival > -1 else None}
                if outside.supports(ident,anchors,allowed,float(scores[second])):
                    additions[gid][ident] = evidence
    # Consecutive unassigned neighbors remain competitors when linking to a
    # named Set. Their proximity alone cannot corroborate a transfer into it.
    taken = {i for matches in additions.values() for i in matches}
    free = set(candidates) - taken
    # A post can contain more than one shoot. A connected but inconsistent chain
    # cannot start a draft. Corroborated cross-platform overlaps may nominate a core too.
    by_members = defaultdict(set)
    for core, spans in runs.items():
        if core <= free:
            by_members[core].update(spans)
    for p, ids in sorted(usable_posts.items()):
        if len(ids) >= 3:
            for core in source_cliques(ids, vectors, SOURCE_FLOOR):
                if core <= free:
                    by_members[frozenset(core)].add(p)
        others = {q for i in ids for q in origins.get(i,()) if q>p and q.split(':',1)[0]!=p.split(':',1)[0]}
        for q in others:
            overlap = ids & usable_posts[q]
            if len(overlap)<3 or not outside.corroborated({p,q}):
                continue
            for core in source_cliques(overlap,vectors,CORROBORATED_FLOOR):
                if core <= free:
                    by_members[frozenset(core)].update((p,q))
    cores = [(ps,ids) for ids,ps in by_members.items()]
    # Overlapping reposts share a real survivor. Vet the entire union from scratch;
    # if even the two endpoints disagree, none of the competing cores is assigned.
    by_photo = defaultdict(list)
    for n, (_, ids) in enumerate(cores):
        for i in ids:
            by_photo[i].append(n)
    visited = set()
    new = []
    for n in range(len(cores)):
        if n in visited:
            continue
        pending, members, origins_used = [n], set(), []
        visited.add(n)
        while pending:
            k = pending.pop()
            sources, ids = cores[k]
            origins_used.extend(sources)
            members.update(ids)
            for i in ids:
                for other in by_photo[i]:
                    if other not in visited:
                        visited.add(other)
                        pending.append(other)
        if len(members) > MAX_POST or not independent_photos(items, members):
            continue
        ids = sorted(members)
        common = set.intersection(*(origins[i] for i in ids))
        corroborated = outside.corroborated(common)
        weakest = coherent(ids, vectors, CORROBORATED_FLOOR if corroborated else SOURCE_FLOOR)
        if weakest is None or any(origins[i] & occupied_posts for i in ids):
            continue
        if any(nearest.get(i, -1.) >= min(weakest - RIVAL_GAP, NEW_SET_RIVAL_CEILING) for i in ids):
            continue
        run_spans = runs.get(frozenset(members),{})
        if not all(outside.supports(i,[j for j in ids if j!=i],members,weakest,bool(run_spans)) for i in ids):
            continue
        evidence = {'members':ids, 'posts':sorted(set(origins_used)), 'similarity':round(weakest,5)}
        if run_spans:evidence['original_order']=run_spans
        new.append(evidence)
    return {'new': new, 'add': dict(additions)}
