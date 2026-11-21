"""Resolve real automatic decisions by durable Set identity and original content hash."""
from collections import defaultdict
import json


class MatchHistory:
    def __init__(self, organizer, db):
        self.created = defaultdict(set)
        self.placements = defaultdict(set)
        self.inventory_placements = defaultdict(set)
        self.suggested = set()
        self.suggested_sets = set()
        self.scopes = [r[0] for r in db.execute(
            'WITH RECURSIVE lineage(scope) AS (SELECT ? UNION SELECT source FROM scope_merges '
            'JOIN lineage ON target=lineage.scope) SELECT scope FROM lineage',(organizer.scope,))]
        for scope in self.scopes:
            for event,kind,raw in db.execute(
                "SELECT id,kind,payload FROM tracking_events WHERE entity=? AND kind IN "
                "('decision.automatic_set_match','decision.approved_likely_group',"
                "'decision.combine_split','decision.separate_split') ORDER BY seq",(scope,)):
                data = json.loads(raw)
                if kind in ('decision.combine_split','decision.separate_split'):
                    if data.get('was_unassigned'):
                        self.suggested_sets.add(data['result'])
                        self.suggested.update(data['hashes'][i] for i in data['members'][data['right']] if i in data['hashes'])
                    continue
                hashes = data.get('source_hashes',{})
                if kind=='decision.approved_likely_group':
                    self.suggested_sets.add(data.get('destination'))
                    self.suggested.update(hashes[i] for i in data.get('selected',()) if hashes.get(i))
                    continue
                for group in data.get('sets',()):
                    gid = group['id']
                    if group['kind']=='new':
                        self.created[gid].add(event)
                    for i in group.get('members',group.get('matches',{})):
                        self.inventory_placements[i].add((event,gid))
                        if hashes.get(i):
                            self.placements[hashes[i]].add((event,gid))

    def matching(self, organizer, groups, kind, choice):
        if choice not in ('automatic','contains','approved') or (kind=='images' and choice=='contains'):
            raise ValueError('Choose an available match history filter.')
        digests = self.suggested if choice=='approved' else self.placements
        photos = {i for i in organizer.catalog if organizer.hashes(i).intersection(digests)}
        if choice!='approved':
            photos.update(self.inventory_placements.keys() & organizer.catalog.keys())
            # Older local Set records may still prove placement without a recoverable batch ID.
            photos.update(i for g in groups.values() for i in g.get('auto_members',()) if i in organizer.catalog)
        if kind=='images':
            return photos
        if choice=='contains':
            return {gid for gid,g in groups.items() if photos.intersection(g['members'])}
        origins = self.suggested_sets if choice=='approved' else self.created
        return {gid for gid,g in groups.items()
                if {gid,*g.get('merged_sources',())}.intersection(origins)
                or (gid.startswith('recovered:') and gid.rsplit(':',1)[-1] in origins)}

    def export(self):
        return {'version':1,'auto_created_sets':{k:sorted(v) for k,v in self.created.items()},
                'auto_placed_inventory_ids':{i:sorted(v) for i,v in self.inventory_placements.items()},
                'auto_placed_photos':{h:[{'batch':b,'set':g} for b,g in sorted(v)] for h,v in self.placements.items()}}
