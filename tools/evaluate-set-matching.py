"""Replay hidden human Set memberships using saved analysis. Report aggregate counts only."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'duplicate-review'))


def snapshot(path):
    # Skip an active write log rather than opening a writable SQLite connection.
    wal = Path(str(path) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError(f'Use a consistent snapshot of {path.name} with its WAL checkpointed.')
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA query_only=ON')
    return closing(db)


def inventories(workbench, library, label_source='library'):
    from organizer import runtime_helpers
    cls = runtime_helpers()['OutfitMatcher']
    recipe = cls.MODEL_SHA + ':' + cls.SCENE_RECIPE
    with snapshot(workbench / 'organizer.sqlite3') as org:
        discarded = {r[0] for r in org.execute('SELECT hash FROM discarded')}
        draft_labels = defaultdict(lambda: defaultdict(set))
        if label_source == 'workbench':
            for scope, gid, raw in org.execute('SELECT scope,id,data FROM sets'):
                group = json.loads(raw)
                for item in set(group['members']) - set(group.get('auto_members', [])) - set(group.get('removed_members', [])):
                    draft_labels[scope][item].add(group.get('library_id') or gid)
    labels = defaultdict(dict)
    records = json.loads(library.read_text(encoding='utf-8-sig'))
    media = {r['id']: r for r in records['media']}
    for group in records['sets']:
        for ident in group['media_ids']:
            sha = media.get(ident, {}).get('sha256')
            if sha:
                labels[group['character_id']].setdefault(sha, set()).add(group['id'])
    with snapshot(workbench / 'bulk-preparation.sqlite3') as db:
        jobs = db.execute("SELECT id,json_extract(data,'$.config.character_id') FROM jobs "
                          "WHERE json_type(data,'$.source_catalog')='object' ORDER BY updated DESC").fetchall()
        latest = {}
        for ident, owner in jobs:
            if owner in labels:
                latest.setdefault(owner, ident)
        for position, owner in enumerate(sorted(latest, key=lambda x: hashlib.sha256(x.encode()).digest())):
            raw = db.execute('SELECT data FROM jobs WHERE id=?', (latest[owner],)).fetchone()[0]
            job = json.loads(raw)
            from organizer_auto_sets import post_sequences
            posts = {}
            for ident,item in job['source_catalog'].items():
                for post,source in item.get('sources',{}).items():
                    posts.setdefault(post,{'kind':source.get('kind'),'ids':[]})['ids'].append(ident)
            sequences = post_sequences(job['source_catalog'],posts)
            alias = 'section:'+job['section_id'] if job.get('section_id') else hashlib.sha256(
                json.dumps(job.get('config',{}).get('roots',[]),sort_keys=True).encode()).hexdigest()
            scope = job.get('organizer_scope') or alias
            items, truth, digests = {}, {}, {}
            for ident, entry in job['source_catalog'].items():
                sha = entry.get('sha')
                aliases = {c.get('sha') for c in entry.get('copies', [])} | {sha}
                if not sha or aliases & discarded or entry.get('quarantine_only') or entry.get('media_type','image') != 'image':
                    continue
                # Hide Library membership, Library paths, and any previous proposals from the matcher.
                items[ident] = {k:entry[k] for k in ('sha','analysis_sha','sources','origins','path','copies') if k in entry}
                digests[ident] = entry.get('analysis_sha', sha)
                known = labels[owner].get(sha, set()) if label_source=='library' else draft_labels[scope].get(ident,set())
                if len(known) == 1:
                    truth[ident] = next(iter(known))
            cache = {}
            required = set(digests.values())
            for sha, blob in db.execute('SELECT sha,data FROM vectors WHERE recipe=?', (recipe,)):
                if sha in required and len(blob) == 9216:
                    v = np.frombuffer(blob, dtype=np.float32).reshape(3, 768)
                    if np.isfinite(v).all() and np.all(np.linalg.norm(v,axis=1)>0.001):
                        cache[sha] = ((v / np.linalg.norm(v,axis=1)[:,None]) * np.sqrt(np.array([.45,.35,.20],np.float32))[:,None]).ravel()
            vectors = {ident:cache[d] for ident,d in digests.items() if d in cache}
            yield position, items, vectors, truth, sequences


def seeded_sets(truth):
    sets = defaultdict(list)
    for ident, gid in truth.items():
        sets[gid].append(ident)
    result = {}
    for gid, ids in sorted(sets.items()):
        if len(ids) >= 2 and hashlib.sha256(('seed-set:'+gid).encode()).digest()[0] < 160:
            chosen = sorted(ids,key=lambda x: hashlib.sha256(('seed-photo:'+x).encode()).digest())[:2]
            result[gid] = {'id':gid, 'members':chosen}
    return result


def score(plan,truth,groups):
    out = Counter()
    known = {}
    for gid, group in groups.items():
        for ident in group['members']:
            known[ident] = gid
    out['eligible_labelled_photos'] = len(truth.keys() - known.keys())
    for cluster in plan['new']:
        labels = [truth.get(i) for i in cluster['members']]
        distinct = set(labels) - {None}
        out['new_drafts'] += 1
        out['new_photos'] += len(labels)
        if cluster.get('original_order'):
            out['drafts_from_consecutive_photos'] += 1
            out['photos_from_consecutive_runs'] += len(labels)
        if len(distinct) > 1:
            out['known_mixed_drafts'] += 1
        elif None in labels:
            out['partly_or_entirely_unlabelled_drafts'] += 1
        else:
            out['fully_labelled_pure_drafts'] += 1
            out['photos_in_fully_labelled_pure_drafts'] += len(labels)
        if distinct & groups.keys():
            out['new_drafts_overlapping_a_seeded_set'] += 1
    for gid, matches in plan['add'].items():
        for ident in matches:
            out['additions'] += 1
            out['unlabelled_additions' if ident not in truth else 'correct_additions' if truth[ident]==gid else 'wrong_additions'] += 1
    return dict(out)


def lookalikes(items, vectors, truth):
    """Construct a small, deceptively coherent post from two distinctly labelled shoots."""
    from set_matching import match_sets
    ids = sorted(set(truth) & vectors.keys())
    if len(ids) < 3:
        return {}
    x = np.stack([vectors[i] for i in ids])
    by_set = defaultdict(list)
    for n, ident in enumerate(ids):
        by_set[truth[ident]].append(n)
    counts = Counter()
    for group, rows in by_set.items():
        if len(rows) < 2 or len(rows) == len(ids):
            continue
        # A credible same-shoot pair and its closest known outsider to BOTH photos.
        first = rows[0]
        second = max(rows[1:],key=lambda n:float(x[n] @ x[first]))
        score = np.minimum(x @ x[first], x @ x[second])
        score[rows] = -np.inf
        third = int(np.argmax(score))
        selected = [ids[n] for n in (first,second,third)]
        fixtures = {i:{'sha':items[i]['sha'],'sources':{'forum:test':{'kind':'forum'}}} for i in selected}
        # Include the closest other photos as live, unlabelled competitors and several
        # unrelated posts. This also exercises the matcher when there is no rival named Set.
        nearby = np.maximum.reduce([x@x[n] for n in (first,second,third)])
        for j in np.argsort(-nearby,kind='stable')[:32]:
            ident = ids[j]
            if ident not in fixtures:
                fixtures[ident] = {'sha':items[ident]['sha'],'sources':{f'instagram:context:{j}':{'kind':'instagram'}}}
        descriptors = {i:vectors[i] for i in fixtures}
        counts['mixed_posts'] += 1
        counts['false_new_drafts'] += len(match_sets(fixtures,descriptors,{},set(),set())['new'])
        anchors = {group:{'id':group,'members':selected[:2]}}
        matches = match_sets(fixtures,descriptors,anchors,set(),set())['add'].get(group,{})
        counts['false_additions'] += sum(truth[i]!=group for i in matches)
        extra = [i for i in fixtures if i not in selected]
        if len(extra)>=2:
            for i in selected+[extra[0]]:
                fixtures[i]['sources']['instagram:repost']={'kind':'instagram'}
            fixtures[extra[1]]['sources']['forum:test']={'kind':'forum'}
            counts['mixed_reposts'] += 1
            p = match_sets(fixtures,descriptors,{},set(),set())
            counts['false_repost_drafts'] += sum(len({truth[i] for i in g['members']})>1 for g in p['new'])
            p = match_sets(fixtures,descriptors,anchors,set(),set())
            counts['false_repost_additions'] += sum(truth[i]!=group for i in p['add'].get(group,{}))
        if len(fixtures)>24:
            # Put the nearest different-Set photo directly beside its two apparent
            # matches and another credible neighbor in a single large ordered post.
            fourth = next((i for i in extra if truth[i]==group),extra[0])
            center = selected+[fourth]
            rest = sorted(set(fixtures)-set(center),key=lambda i:hashlib.sha256(i.encode()).digest())
            order = rest[:len(rest)//2]+center+rest[len(rest)//2:]
            one_post = {i:{'sha':items[i]['sha'],'sources':{'forum:large':{'kind':'forum'}}} for i in order}
            sequence = {'forum:large':order}
            counts['ordered_mixed_boundaries'] += 1
            p = match_sets(one_post,descriptors,{},set(),set(),sequence)
            counts['false_ordered_drafts'] += sum(len({truth[i] for i in g['members']})>1 for g in p['new'])
            p = match_sets(one_post,descriptors,anchors,set(),set(),sequence)
            counts['false_ordered_additions'] += sum(truth[i]!=group for i in p['add'].get(group,{}))
            # A fresh download may omit the nearest alternatives. Test a second
            # collection whose context is drawn independently of visual distances.
            sample = np.random.default_rng(int.from_bytes(hashlib.sha256(group.encode()).digest()[:8],'big'))
            pool = [i for i in ids if i not in center]
            context = [pool[j] for j in sample.choice(len(pool),min(40,len(pool)),replace=False)]
            order = context[:len(context)//2]+center+context[len(context)//2:]
            sparse = {i:{'sha':items[i]['sha'],'sources':{'forum:small' if i in center else 'instagram:'+i:
                      {'kind':'forum' if i in center else 'instagram'}}} for i in order}
            desc = {i:vectors[i] for i in order}
            counts['sparse_mixed_posts'] += 1
            p = match_sets(sparse,desc,{},set(),set())
            counts['false_sparse_drafts'] += sum(len({truth[i] for i in g['members']})>1 for g in p['new'])
            p = match_sets(sparse,desc,anchors,set(),set())
            counts['false_sparse_additions'] += sum(truth[i]!=group for i in p['add'].get(group,{}))
            sparse = {i:{'sha':items[i]['sha'],'sources':{'forum:large':{'kind':'forum'}}} for i in order}
            p = match_sets(sparse,desc,{},set(),set(),{'forum:large':order})
            counts['false_sparse_ordered_drafts'] += sum(len({truth[i] for i in g['members']})>1 for g in p['new'])
            p = match_sets(sparse,desc,anchors,set(),set(),{'forum:large':order})
            counts['false_sparse_ordered_additions'] += sum(truth[i]!=group for i in p['add'].get(group,{}))
            if truth[fourth] == group:
                counts['three_anchor_boundaries'] += 1
                three = {group:{'id':group,'members':selected[:2]+[fourth]}}
                p = match_sets(sparse,desc,three,set(),set(),{'forum:large':order})
                counts['false_three_anchor_additions'] += sum(truth[i]!=group for i in p['add'].get(group,{}))
                # Independent repost evidence for the first anchor alone still
                # cannot establish the boundary of the candidate's own shoot.
                sparse[selected[0]]['sources']['instagram:anchor']={'kind':'instagram'}
                p = match_sets(sparse,desc,three,set(),set(),{'forum:large':order})
                counts['false_partial_repost_additions'] += sum(truth[i]!=group for i in p['add'].get(group,{}))
    return dict(counts)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workbench',required=True,type=Path)
    p.add_argument('--library',required=True,type=Path,help='library.json to read')
    p.add_argument('--split',choices=('inventory','development','validation'),required=True)
    p.add_argument('--lookalikes',action='store_true')
    p.add_argument('--labels',choices=('library','workbench'),default='library')
    args=p.parse_args()
    for pos, items, vectors, truth, sequences in inventories(args.workbench,args.library,args.labels):
        if args.split=='inventory':
            print(json.dumps({'profile':pos,'photos':len(items),'analysed':len(vectors),'labelled':len(truth),'sets':len(set(truth.values()))}),flush=True)
            continue
        if (pos%2 == 0) != (args.split=='development'):
            continue
        if args.lookalikes:
            print(json.dumps({'profile':pos,'lookalikes':lookalikes(items,vectors,truth)}),flush=True)
            continue
        from set_matching import match_sets
        for mode,groups in [('new',{}),('new_and_started',seeded_sets(truth))]:
            plan=match_sets(items,vectors,groups,set(),{'forum:smg:603571'},sequences)
            print(json.dumps({'profile':pos,'mode':mode,**score(plan,truth,groups)}),flush=True)

if __name__=='__main__':
    main()
