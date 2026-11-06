"""Shared durable metadata journal, bundled with the companion runtime."""
from functools import lru_cache
from pathlib import Path,PureWindowsPath
import copy,hashlib,json,runpy

@lru_cache(maxsize=1)
def journal():
    return runpy.run_path(str(Path(__file__).resolve().parents[1]/'runtime-src'/'companion-runtime.pyw'))['TrackingJournal']

def configure(db):
    journal().configure(db)

ENGINE = {
    'settings': (['key'], ['key','value'], 'analysis.configuration'),
    'files': (['path'], ['path','stamp','sha','w','h','size','reference','root','pixel','library'], 'inventory.file'),
    'cache': (['path'], ['path','stamp','algorithm','sha','w','h','size','pixel'], 'analysis.image'),
    'features': (['path'], ['path','stamp','version'], 'analysis.features'),
    'errors': (['path'], ['path','message'], 'analysis.failure'),
    'pairs': (['key'], ['key','kind','score','decision'], 'relationship.review'),
    'ignored': (['key'], ['key'], 'decision.ignored_pair'),
    'moves': (['id'], ['id','src','dst','sha','state','created','batch','keeper_sha','keeper_path'], 'file.move'),
    'verified_copies': (['key'], ['key','accepted'], 'relationship.verified_copy'),
    'separations': (['a','b'], ['a','b'], 'decision.separation'),
    'group_links': (['a','b'], ['a','b'], 'relationship.group_link'),
    'keeps': (['path','sha'], ['path','sha'], 'decision.keeper'),
    'library_cleanups': (['operation'], ['operation','payload','state','created'], 'library.cleanup'),
    'replacements': (['operation'], ['operation','payload','state','created'], 'relationship.replacement'),
}
BULK = {
    'hashes': (['path'], ['path','stamp','sha','pixel'], 'inventory.hash'),
    'vectors': (['sha','recipe'], ['sha','recipe'], 'analysis.embedding'),
    'origin_review': (['sha'], ['sha','status','updated'], 'decision.origin_review'),
    'confirmed_origins': (['target'], ['target','keeper','created'], 'relationship.confirmed_origin'),
    'aliases': (['target','keeper','recipe'], ['target','keeper','recipe','accepted'], 'relationship.same_photo'),
}
ORGANIZER = {
    'sets': (['scope','id'], ['scope','id','data'], 'organizer.set'),
    'state': (['scope'], ['scope','data'], 'organizer.evidence'),
    'posts': (['scope','id'], ['scope','id','status'], 'decision.post'),
    'rejected': (['scope','context','id'], ['scope','context','id'], 'decision.rejected'),
    'discarded': (['hash'], ['hash','batch','data'], 'decision.discarded'),
    'parked': (['scope','post','hash'], ['scope','post','hash'], 'decision.deferred'),
    'video_references': (['scope','sha'], ['scope','sha','data'], 'analysis.video_frame'),
    'category_catalog': (['scope'], ['scope','data'], 'organizer.categories'),
}

def inventory(db, job, legacy=False, previous=None):
    """Only saved source facts and proposal evidence, never embeddings/bytes.

    Called at inventory persistence boundaries, not each thumbnail or UI render.
    Existing heads deduplicate unchanged records across runs and restarts.
    """
    log=journal();config=job.get('config',{});roots=config.get('roots',[])
    cache=dict(previous or {}) if (previous or {}).get('_job')==job['id'] else {}
    cache['_job']=job['id']
    def observe(kind,entity,value):
        key=(kind,entity)
        if key in cache and cache[key]==value:return
        log.observe(db,kind,entity,value,legacy)
        cache[key]=copy.deepcopy(value)
    def folder(path):
        if ('folder',path) not in cache:
            log.identity(db,'folder',path);cache[('folder',path)]=True
    alias=hashlib.sha256(json.dumps(roots,sort_keys=True).encode()).hexdigest()
    collection=log.identity(db,'collection',alias,job.get('collection_id') if job.get('collection_roots')==roots else None)
    job['collection_id']=collection;job['collection_roots']=list(roots)
    observe('inventory.batch',job['id'],{'collection_id':collection,'config':config,
        'recipe':job.get('recipe'),'model_root':job.get('model_root'),'complete':bool(job.get('complete')),'interrupted':bool(job.get('interrupted')),'error':job.get('error'),'issues':job.get('issues',[]),'sampled':job.get('sampled'),'outside_evaluation':job.get('outside_evaluation'),'analyzed_ids':sorted(job.get('items',{}))})
    for root in roots:folder(str(root))
    for ident,item in job.get('source_catalog',{}).items():
        key=('source.catalog',collection+':'+ident)
        if key in cache and cache[key]==item:continue
        observe('source.catalog',collection+':'+ident,item)
        for sid,source in item.get('sources',{}).items():
            observe('source.post',collection+':'+sid+':'+hashlib.sha256(log.encode(source).encode()).hexdigest(),source)
        paths=[item.get('path')]+[o.get(k) for o in item.get('origins',[]) for k in ('path','original_path','quarantine_path')]
        for path in set(p for p in paths if p):
            parent=str((PureWindowsPath(path) if '\\' in path else Path(path)).parent)
            folder(parent)
    for group in job.get('proposals',[]):
        observe('relationship.proposed_set',collection+':'+str(group.get('id')),group)
    return cache


def transfer(engine, bulk, organizer):
    """Bounded, resumable, idempotent pages; no growing history in UI responses."""
    destination=engine.library.request('/api/tracking/status')['instance']
    for owner in (engine,bulk,organizer):
        with owner.db() as db:
            log=journal();cursor_key='transfer:'+destination
            cursor=db.execute('SELECT value FROM tracking_meta WHERE key=?',(cursor_key,)).fetchone()
            after=int(cursor[0]) if cursor else 0
            through=db.execute('SELECT COALESCE(max(seq),0) FROM tracking_events').fetchone()[0]
            while after<through:
                rows=[r for r in log.rows(db,after,100) if r['seq']<=through]
                if not rows:break
                page=[];size=0
                for row in rows:
                    raw=log.encode(row);length=len(raw.encode())
                    if page and size+length>512*1024:
                        engine.library.request('/api/tracking/import',{'events':page});page=[];size=0
                    if length>512*1024:
                        digest=hashlib.sha256(raw.encode()).hexdigest()
                        chunks=[raw[i:i+64000] for i in range(0,len(raw),64000)]
                        for index,chunk in enumerate(chunks):
                            engine.library.request('/api/tracking/import',{'fragment':{'digest':digest,'index':index,'total':len(chunks),'text':chunk}})
                    else:
                        page.append(row);size+=length
                if page:engine.library.request('/api/tracking/import',{'events':page})
                after=rows[-1]['seq']
                db.execute('INSERT OR REPLACE INTO tracking_meta VALUES (?,?)',(cursor_key,str(after)))
                db.commit()


def export_history(*owners):
    records=[]
    for owner in owners:
        with owner.db() as db:records.extend(journal().rows(db))
    return {'schema':1,'events':records}
