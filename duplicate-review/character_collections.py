"""Persistent per-character organizer sections; never guesses owners from names.

Inventories remain independent recovery records. A section combines their saved
metadata without scanning images, and retains the first inventory's scope so
existing drafts, transfer IDs and resume state remain valid.
"""
import copy
import hashlib
import json
import time
import uuid

import tracking


def scope(job):
    return job.get('organizer_scope') or hashlib.sha256(json.dumps(job.get('config',{}).get('roots',[]),sort_keys=True).encode()).hexdigest()


def union(a,b):
    result=copy.deepcopy(a);seen={json.dumps(v,sort_keys=True) for v in result}
    for v in b:
        key=json.dumps(v,sort_keys=True)
        if key not in seen:result.append(copy.deepcopy(v));seen.add(key)
    return result


def merge_catalog(target,source):
    for ident,item in source.items():
        old=target.get(ident)
        if old is None:target[ident]=copy.deepcopy(item);continue
        merged=copy.deepcopy(item)
        for key in ('origins','copies'):
            merged[key]=union(old.get(key,[]),item.get(key,[]))
        merged['existing_sets']=copy.deepcopy(item.get('existing_sets',[])) if item.get('reference') else union(old.get('existing_sets',[]),item.get('existing_sets',[]))
        merged['sources']={**old.get('sources',{}),**item.get('sources',{})}
        target[ident]=merged


class Sections:
    def __init__(self,bulk):
        self.bulk=bulk
        with bulk.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS character_sections(id TEXT PRIMARY KEY,data TEXT)')
            tracking.journal().install(db,{'character_sections':(['id'],['id','data'],'organizer.character_section')})

    def rows(self):
        with self.bulk.db() as db:return [json.loads(r[0]) for r in db.execute('SELECT data FROM character_sections')]

    def save(self,db,row):
        db.execute('INSERT OR REPLACE INTO character_sections VALUES (?,?)',(row['id'],json.dumps(row)))

    def sync(self):
        # Only explicit UI initialization/refresh makes companion requests.
        library=self.bulk.engine.library.request('/api/library')
        instance=self.bulk.engine.library.request('/api/tracking/status')['instance']
        if not isinstance(instance,str) or not instance:raise ValueError('Library identity unavailable. Update the companion.')
        with self.bulk.db() as db:
            existing={r['id']:r for r in self.rows()}
            jobs=[{'id':i,'config':json.loads(c or '{}')} for i,c in db.execute("SELECT id,json_extract(data,'$.config') FROM jobs")]
            claimed={i for r in existing.values() for i in r.get('legacy_job_ids',[])}
            for person in library.get('characters',[]):
                if not person.get('id'):continue
                ident='girl:'+hashlib.sha256((instance+':'+person['id']).encode()).hexdigest()[:32]
                row=existing.get(ident,{'id':ident,'character_id':person['id'],'library_instance':instance,'created':time.time()})
                row.setdefault('legacy_job_ids',[])
                for job in jobs:
                    config=job.get('config',{})
                    if job['id'] not in claimed and config.get('character_id')==person['id'] and not config.get('library_instance'):
                        row['legacy_job_ids'].append(job['id']);claimed.add(job['id'])
                row['name']=person['name'];row['categories']=person.get('set_categories',[])
                self.save(db,row)
        self.bulk._collections_cache=None
        return {'connected':True}

    def belongs(self,job,row):
        config=job.get('config',{})
        return config.get('character_id')==row['character_id'] and (config.get('library_instance')==row['library_instance'] or job.get('id') in row.get('legacy_job_ids',[]))

    def entries(self,legacy):
        rows=self.rows()
        if not rows:return legacy
        with self.bulk.db() as db:
            jobs={ident:{'id':ident,'config':json.loads(raw or '{}')} for ident,raw in db.execute("SELECT id,json_extract(data,'$.config') FROM jobs")}
        claimed=set();result=[]
        for row in rows:
            associated=[j for j in jobs.values() if self.belongs(j,row)]
            claimed.update(j['id'] for j in associated)
            roots=[]
            for job in associated:roots=union(roots,job.get('config',{}).get('roots',[]))
            result.append({'id':row['id'],'name':row['name'],'roots':roots,'character_id':row['character_id'],'library_instance':row['library_instance']})
        result.extend(c for c in legacy if c['id'] not in claimed)
        return sorted(result,key=lambda r:r['name'].casefold())

    def activate(self,ident):
        row=next((r for r in self.rows() if r['id']==ident),None)
        if not row:raise ValueError('Choose an available girl.')
        with self.bulk.db() as db:
            jobs=[json.loads(r[0]) for r in db.execute("SELECT data FROM jobs WHERE json_extract(data,'$.config.character_id')=? ORDER BY updated",(row['character_id'],))]
        latest={}
        for job in jobs:
            if self.belongs(job,row):
                # The stable aggregate is a recovery base even if a newer folder
                # refresh crashed before its final merge/commit.
                key=(scope(job),job['id']==row['id'])
                latest.pop(key,None);latest[key]=job
        jobs=list(latest.values())
        current=self.bulk.current or {}
        # Preserve the active legacy scope on first adoption. Subsequent additions
        # never change this scope, even when the girl's folder list changes.
        if not row.get('scope'):
            primary=current if current in jobs else next((j for j in reversed(jobs) if j.get('source_catalog')),None)
            row['scope']=scope(primary) if primary else uuid.uuid4().hex
            row['collection_id']=(primary or {}).get('collection_id') or uuid.uuid4().hex
        result={'id':ident,'section_id':ident,'organizer_scope':row['scope'],'config':{'roots':[],'character_id':row['character_id'],
            'library_instance':row['library_instance'],'person':row['name'],'forum':'smg','limit':0},'running':False,
            'phase':'Saved inventory ready','source_catalog':{},'library_sets':{},'items':{},'proposals':[],'issues':[],
            'inventory_complete':False,'inventory_only':True,'created':row['created'],'source_scopes':[]}
        for job in jobs:
            result['config']['roots']=union(result['config']['roots'],job.get('config',{}).get('roots',[]))
            merge_catalog(result['source_catalog'],job.get('source_catalog',{}))
            result['library_sets'].update(copy.deepcopy(job.get('library_sets',{})))
            result['source_scopes']=union(result['source_scopes'],[scope(job)])
            if job.get('model_root'):result['model_root']=job['model_root']
            result['inventory_complete']|=bool(job.get('inventory_complete') or job.get('complete'))
        result['collection_id']=row['collection_id'];result['collection_roots']=result['config']['roots'][:]
        with self.bulk.db() as db:self.save(db,row)
        self.bulk.current=result;self.bulk.persist()
        return result
