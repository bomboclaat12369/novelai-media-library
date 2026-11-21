"""Save high-confidence matches into the Organizer's normal draft/transfer workflow."""
import hashlib
import json
import threading
import time
import uuid

import tracking
from bulk.sources import original_sequence
from set_matching import MAX_POST, RULE, evidence_vectors, match_sets
from shoot_scene import RECIPE as SCENE_RECIPE, SceneEvidence
from source_shoots import combine, source_matches


def post_sequences(catalog, posts):
    return {p:original_sequence(catalog,p,g['ids']) for p,g in posts.items()
            if g.get('kind') in ('instagram','forum') and len(g['ids'])>MAX_POST}


def available_stills(organizer):
    return {i for i, item in organizer.catalog.items() if item.get('media_type', 'image') == 'image'
            and not item.get('quarantine_only') and i not in organizer.discarded}


def remaining(organizer, groups=None):
    groups = organizer.sets() if groups is None else groups
    members = {i for g in groups.values() for i in g['members']}
    live = (organizer.library_placement or {}).get('set_ids_by_sha') or {}
    return sorted(i for i in available_stills(organizer) - members
                  if not organizer.catalog[i].get('existing_sets') and organizer.catalog[i]['sha'] not in live)


def exclusions(organizer, groups, state, db):
    ignored = set(state.get('selection', [])) | organizer.discarded
    ignored.update(i for g in groups.values() for i in g.get('removed_members', []))
    rejected = {row[0] for row in db.execute('SELECT id FROM rejected WHERE scope=?', (organizer.scope,))}
    parked = set().union(*organizer.parked.values()) if organizer.parked else set()
    deferred = {r[0] for r in db.execute("SELECT id FROM posts WHERE scope=? AND status='deferred'", (organizer.scope,))}
    queued = {r['id'] for r in organizer.individual_imports()
              if r['options'].get('destination') in ('review', 'purgatory')}
    ignored.update(queued)
    ignored.update(rejected)
    for ident, item in organizer.catalog.items():
        hashes = organizer.hashes(ident)
        if hashes & parked or any('auto-hold:'+h in rejected for h in hashes) or deferred.intersection(item.get('sources', {})):
            ignored.add(ident)
    return ignored


def matching_inputs(organizer, state, db):
    groups = organizer.sets(include_discarded=True)
    excluded = exclusions(organizer, groups, state, db)
    placement = organizer.library_placement or {}
    live_sets = placement.get('set_ids_by_sha')
    local = {}
    for group in groups.values():
        for ident in group['members']:
            local.setdefault(ident, set()).add(group.get('library_id'))
    for ident, item in organizer.catalog.items():
        digest = item.get('sha')
        if digest in (placement.get('held_hashes') or set()):
            excluded.add(ident)
        if live_sets is not None:
            active = live_sets.get(digest,set())
            if active - local.get(ident,set()) or set(item.get('existing_sets',[])) - active:
                excluded.add(ident)
    mixed = {p for p in organizer.posts if organizer.is_mixed(p, state.get('post_evidence', {}))}
    return groups, excluded, mixed


class MatchPreparation:
    """Compute image evidence without a writer lock. Only the explicit commit edits drafts."""
    def __init__(self,organizer,state,db):
        self.job=organizer.bound
        self.revision=state.get('revision',0)
        self.items=organizer.catalog
        self.vectors=organizer.vector_by_id
        self.groups,self.excluded,self.mixed=matching_inputs(organizer,state,db)
        self.sequences=post_sequences(self.items,organizer.posts)
        self.scene = SceneEvidence(self.items, organizer.engine.recovered_original,
                                   organizer.engine.state_dir/'set-scene-cache.sqlite3', organizer.recipe)
        self.token=uuid.uuid4().hex
        self.cancel=threading.Event()
        self.status={'running':True,'phase':'Comparing saved analysis','done':0,'total':0}
        self.plan=None
        self.thread=None

    def collect(self):
        try:
            plan=match_sets(self.items,self.vectors,self.groups,self.excluded,self.mixed,self.sequences)
            valid=evidence_vectors(self.items,self.vectors)
            def progress(done,total):
                if self.cancel.is_set():raise InterruptedError('Matching stopped.')
                self.status={'running':True,'phase':'Checking outfits and scene details','done':done,'total':total}
            hits=source_matches(self.items,valid,self.groups,self.excluded,self.mixed,self.scene,progress)
            self.plan=combine(plan,hits,self.items,valid,self.groups)
            self.status={'running':False,'phase':'Matches prepared'}
        except Exception as error:
            self.status={'running':False,'phase':'Matching stopped','error':str(error)}
        finally:
            self.scene.close()

    def compatible(self,organizer,state,db):
        if (self.job != organizer.bound or self.revision != state.get('revision',0)
                or self.items is not organizer.catalog or self.vectors is not organizer.vector_by_id
                or self.scene.analysis_recipe != organizer.recipe):
            return False
        groups,excluded,mixed=matching_inputs(organizer,state,db)
        return (self.groups==groups and self.excluded==excluded and self.mixed==mixed
                and all(self.scene.stamp(i)==stamp for i,stamp in list(self.scene.verified_stamps.items())))


@tracking.journal().action('automatic')
def apply_matches(organizer, state, db, prepared):
    groups=prepared.groups
    plan=prepared.plan
    before = {}
    names = {g['name'].casefold() for g in groups.values()}
    ordinal = 1
    stamp = time.time()
    event = {'rule':RULE+'+'+SCENE_RECIPE, 'recipe':organizer.recipe, 'inventory':organizer.bound[0],
             'collection':organizer.collection_id, 'sets':[],'scene_proofs':{}}
    def record(match):
        if 'scene' not in match:return match
        proof=match['scene']
        key=hashlib.sha256(json.dumps(proof,sort_keys=True).encode()).hexdigest()
        event['scene_proofs'][key]=proof
        return {k:v for k,v in match.items() if k!='scene'}|{'scene_proof':key}
    for core in plan['new']:
        while ('Shoot %03d' % ordinal).casefold() in names:
            ordinal += 1
        name = 'Shoot %03d' % ordinal
        ordinal += 1
        ident = uuid.uuid4().hex
        ids = core['members']
        group = {'id':ident,'name':name,'members':ids,'auto_members':ids,'auto_pending':ids,
                 'created':stamp,'updated':stamp,'colors':[],'categories':[],'favorite':False,'library_id':None}
        db.execute('INSERT INTO sets VALUES (?,?,?)',(organizer.scope,ident,json.dumps(group)))
        before[ident] = None
        event['sets'].append({'id':ident,'kind':'new',**record(core)})
    for ident, matches in plan['add'].items():
        old = db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(organizer.scope,ident)).fetchone()
        before[ident] = old[0] if old else None
        group = dict(groups[ident])
        for key in ('members','auto_members','auto_pending'):
            group[key] = list(dict.fromkeys(group.get(key,[])+list(matches)))
        group['updated'] = stamp
        db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(organizer.scope,ident,json.dumps(group)))
        event['sets'].append({'id':ident,'kind':'extend','matches':{i:record(m) for i,m in matches.items()}})
    added = sum(len(matches) for matches in plan['add'].values())
    created = sum(len(g['members']) for g in plan['new'])
    if before:
        event['source_hashes'] = {i:organizer.catalog[i]['sha'] for i in {
            i for g in plan['new'] for i in g['members']} | {
            i for matches in plan['add'].values() for i in matches} | {
            a for matches in plan['add'].values() for match in matches.values() for a in match['anchors']}}
        tracking.journal().event(db,'decision.automatic_set_match',organizer.scope,event)
        state['undo'] = {'action':'auto_sets','previous':before}
    return {'created_sets':len(plan['new']), 'new_members':created, 'extended_sets':len(plan['add']),
            'added_members':added,'matched':created+added,'remaining':len(remaining(organizer,groups))-created-added}


def undo_matches(organizer, db, undo):
    for ident, previous in undo['previous'].items():
        row = db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(organizer.scope,ident)).fetchone()
        current = json.loads(row[0]) if row else {}
        old = json.loads(previous) if previous is not None else {}
        if current.get('applied_at') != old.get('applied_at'):
            raise ValueError('This batch reached the Library. Restore its import checkpoint to undo that transfer.')
    for ident, previous in undo['previous'].items():
        if previous is None:
            db.execute('DELETE FROM sets WHERE scope=? AND id=?',(organizer.scope,ident))
        else:
            db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(organizer.scope,ident,previous))
    tracking.journal().event(db,'decision.undo_automatic_set_match',organizer.scope,{'sets':list(undo['previous'])})


def live_memberships(organizer,ident):
    memberships=(organizer.library_placement or {}).get('set_ids_by_sha')
    item=organizer.catalog[ident]
    return item.get('existing_sets',[]) if memberships is None else memberships.get(item['sha'],())


def review_page(organizer, body):
    groups=organizer.sets()
    only=None
    if body.get('period')=='latest':
        with organizer.db() as db:
            row=db.execute("SELECT payload FROM tracking_events WHERE kind='decision.automatic_set_match' AND entity=? ORDER BY seq DESC LIMIT 1",
                           (organizer.scope,)).fetchone()
        only={}
        for hit in json.loads(row[0])['sets'] if row else ():
            only[hit['id']]=set(hit.get('members',hit.get('matches',{})))
    entries=[]
    photos={}
    for gid,g in groups.items():
        members=set(g['members'])
        ids=[i for i in g.get('auto_members',[]) if i in members and (only is None or i in only.get(gid,()))]
        if not ids:continue
        reviewed=set(g.get('auto_reviewed',[]))
        photos[gid]=ids
        entries.append({'id':gid,'name':g['name'],'count':len(ids),'reviewed':len(reviewed.intersection(ids))})
    entries.sort(key=lambda e:(e['reviewed']==e['count'],e['name'].casefold(),e['id']))
    target=body.get('target')
    if target not in photos:target=entries[0]['id'] if entries else None
    total=sum(e['count'] for e in entries)
    if not target:return {'sets':[],'target':None,'photos':[],'total':0,'offset':0}
    ids=photos[target];group=groups[target];reviewed=set(group.get('auto_reviewed',[]))
    pending=set(group.get('auto_pending',[]));automatic=set(group.get('auto_members',[]))
    offset=max(0,min(int(body.get('offset',0)),len(ids)-1))//24*24
    examples=[i for i in group['members'] if i not in automatic][:4]
    return {'sets':entries,'target':target,'total':total,'offset':offset,'count':len(ids),
            'examples':[organizer.image(i) for i in examples],
            'photos':[dict(organizer.image(i),reviewed=i in reviewed,
                           removable=i in pending and group.get('library_id') not in live_memberships(organizer,i),
                           other_membership=bool(live_memberships(organizer,i)))
                      for i in ids[offset:offset+24]]}
