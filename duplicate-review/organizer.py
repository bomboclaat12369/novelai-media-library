"""Folder-first review over a saved inventory. No automatic scans or file moves."""
from __future__ import annotations
import copy, hashlib, io, json, re, runpy, sqlite3, threading, time, uuid
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import tracking
from engine import load_image, sha256, stat_key, linked


@lru_cache(maxsize=1)
def runtime_helpers():
    # The same runtime ships with both apps; share the actual saved-label rules.
    return runpy.run_path(str(Path(__file__).resolve().parents[1]/'runtime-src'/'companion-runtime.pyw'))


def title_case_label(value):
    return runtime_helpers()['title_case_label'](value)


def set_name_colors(name, colors=None):
    return runtime_helpers()['set_name_colors'](name,colors)


def natural(value):
    return tuple((1,int(x)) if x.isdigit() else (0,x.casefold()) for x in re.split(r'(\d+)',str(value)))


class Organizer:
    def __init__(self, engine, bulk):
        self.engine=engine;self.bulk=bulk;self.path=engine.state_dir/'organizer.sqlite3'
        self.lock=threading.RLock();self.cancel=threading.Event();self.thread=None
        self.job={'running':False,'phase':'Saved inventory ready','done':0,'total':0,'eta_seconds':None}
        self.library_placement=None
        self.bound=None;self.catalog={};self.posts={};self.order_cache={};self.vector_by_id={};self.quick={}
        self.encoder_type=None;self.recipe=None;self.scope='';self.revision=0;self.discarded=set();self.parked={}
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS scope_merges(target TEXT,source TEXT,PRIMARY KEY(target,source))')
            db.executescript('''CREATE TABLE IF NOT EXISTS state(scope TEXT PRIMARY KEY,data TEXT);
                CREATE TABLE IF NOT EXISTS category_catalog(scope TEXT PRIMARY KEY,data TEXT);
                CREATE TABLE IF NOT EXISTS sets(scope TEXT,id TEXT,data TEXT,PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS posts(scope TEXT,id TEXT,status TEXT,PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS rejected(scope TEXT,context TEXT,id TEXT,PRIMARY KEY(scope,context,id));
                CREATE TABLE IF NOT EXISTS discarded(hash TEXT PRIMARY KEY,batch TEXT,data TEXT);
                CREATE TABLE IF NOT EXISTS parked(scope TEXT,post TEXT,hash TEXT,PRIMARY KEY(scope,post,hash));''')
            db.execute('CREATE TABLE IF NOT EXISTS video_references(scope TEXT,sha TEXT,data TEXT,PRIMARY KEY(scope,sha))')
            db.execute('CREATE TABLE IF NOT EXISTS individual_imports(scope TEXT,sha TEXT,data TEXT,PRIMARY KEY(scope,sha))')
            tracking.journal().install(db,tracking.ORGANIZER)
            # Upgrade every saved collection's tags without touching membership,
            # timestamps, inventory, matching results, selections or progress.
            for scope,ident,raw in db.execute('SELECT scope,id,data FROM sets').fetchall():
                group=json.loads(raw);colors=set_name_colors(group.get('name',''),group.get('colors',[]))
                if colors!=group.get('colors',[]):
                    group['colors']=colors;db.execute('UPDATE sets SET data=? WHERE scope=? AND id=?',(json.dumps(group),scope,ident))

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30)
        tracking.configure(db)
        try:
            with db:yield db
        finally:db.close()

    def bind(self):
        current=self.bulk.current or {};cat=current.get('source_catalog',{})
        key=(current.get('id'),len(cat))
        if self.bound==key:return
        if self.job['running']:return
        self.bound=key;self.catalog=dict(cat);self.posts={};self.order_cache={}
        alias='section:'+current['section_id'] if current.get('section_id') else hashlib.sha256(json.dumps(current.get('config',{}).get('roots',[]),sort_keys=True).encode()).hexdigest()
        with self.db() as db:
            collection=tracking.journal().identity(db,'collection',alias,current.get('collection_id') if current.get('collection_roots')==current.get('config',{}).get('roots',[]) else None)
            # Keep existing scope keys and explicitly bind their stable identity.
            self.scope=tracking.journal().identity(db,'organizer_scope',collection,current.get('organizer_scope') or alias)
        self.collection_id=collection
        self.merge_scopes(current.get('source_scopes',[]))
        with self.db() as db:
            for digest,raw in db.execute('SELECT sha,data FROM video_references WHERE scope=?',(self.scope,)):
                record=json.loads(raw);self.catalog[record['id']]=record
        cat=self.catalog
        for ident,item in cat.items():
            for sid,source in item.get('sources',{}).items():
                if source.get('kind')=='library':continue
                post=self.posts.setdefault(sid,{'id':sid,'label':source.get('label',sid),'kind':source.get('kind','folder'),'ids':[]})
                post['ids'].append(ident)
        # Load only saved analysis. No source-image reads, comparisons or model downloads.
        self.load_vectors()
        self.load_dispositions()
        with self.engine.db() as db:
            sketches={r['sha']:r['sketch'] for r in db.execute('SELECT sha,sketch FROM cache WHERE sketch IS NOT NULL')}
        self.quick={}
        for ident,r in cat.items():
            raw=sketches.get(r['sha'])
            if raw and len(raw)==3072:
                a=np.frombuffer(raw,dtype=np.uint8).reshape(32,32,3).astype(np.float32)/255
                # Broad color/layout ordering only, never a duplicate or membership decision.
                v=np.concatenate([a.mean((0,1)),a.reshape(4,8,4,8,3).mean((1,3)).ravel()])
                self.quick[ident]=v/(np.linalg.norm(v)+1e-8)

    def hashes(self,ident):
        item=self.catalog[ident]
        return {v for v in [item.get('sha')]+[c.get('sha') for c in item.get('copies',[])] if v}

    def load_dispositions(self):
        with self.db() as db:
            discarded={r[0] for r in db.execute('SELECT hash FROM discarded')}
            parked=list(db.execute('SELECT post,hash FROM parked WHERE scope=?',(self.scope,)))
        self.discarded={i for i in self.catalog if self.hashes(i)&discarded}
        self.parked={}
        for post,digest in parked:self.parked.setdefault(post,set()).add(digest)

    def post_ids(self,post):
        parked=self.parked.get(post,set())
        return [i for i in self.posts[post]['ids'] if i not in self.discarded and not self.hashes(i)&parked]

    def unsorted_ids(self):
        parked=set().union(*self.parked.values()) if self.parked else set()
        assigned={i for g in self.sets().values() for i in g['members']}
        return [i for i in self.catalog if i not in assigned and i not in self.discarded and not self.catalog[i].get('quarantine_only') and self.hashes(i)&parked]

    def is_mixed(self,post,evidence=None):
        # Keep the known dump excluded by default. Size alone does not prove a dump.
        if evidence is None:evidence=self.state().get('post_evidence',{})
        return evidence.get(post,post=='forum:smg:603571')

    def model(self):
        if self.encoder_type is None:
            self.encoder_type=runtime_helpers()['OutfitMatcher']
            self.recipe=self.encoder_type.MODEL_SHA+':'+self.encoder_type.SCENE_RECIPE
        return self.encoder_type

    def load_vectors(self):
        self.model();self.vector_by_id={}
        with self.bulk.db() as db:
            rows={sha:raw for sha,raw in db.execute('SELECT sha,data FROM vectors WHERE recipe=?',(self.recipe,))}
        for ident,item in self.catalog.items():
            raw=rows.get(item.get('analysis_sha',item['sha']))
            if not raw:continue
            v=np.frombuffer(raw,dtype=np.float32)
            if v.size!=2304 or not np.isfinite(v).all():continue
            v=v.reshape(3,768).copy();v/=np.maximum(np.linalg.norm(v,axis=1,keepdims=True),1e-8)
            self.vector_by_id[ident]=(v*np.sqrt(np.array([.45,.35,.20],np.float32))[:,None]).ravel()
        self.vector_ids=sorted(self.vector_by_id)
        self.matrix=np.stack([self.vector_by_id[i] for i in self.vector_ids]) if self.vector_ids else np.zeros((0,2304),np.float32)
        self.order_cache={}

    def state(self):
        with self.db() as db:row=db.execute('SELECT data FROM state WHERE scope=?',(self.scope,)).fetchone()
        return json.loads(row[0]) if row else {'revision':0,'selection':[]}

    def put_state(self,db,state):
        db.execute('INSERT OR REPLACE INTO state VALUES (?,?)',(self.scope,json.dumps(state)))

    def sets(self,include_discarded=False):
        current=self.bulk.current or {};result={}
        for sid,g in current.get('library_sets',{}).items():
            result['library:'+sid]={'id':'library:'+sid,'name':g['name'],'colors':g.get('colors') or [],'categories':g.get('categories') or [],'favorite':bool(g.get('favorite')),'in_purgatory':bool(g.get('in_purgatory')),'members':[], 'library_id':sid,'saved':False}
        for ident,item in self.catalog.items():
            if item.get('quarantine_only'):continue
            for sid in item.get('existing_sets',[]):
                if 'library:'+sid in result:result['library:'+sid]['members'].append(ident)
        with self.db() as db:
            for sid,raw in db.execute('SELECT id,data FROM sets WHERE scope=?',(self.scope,)):
                g=json.loads(raw)
                library_key='library:'+str(g.get('library_id') or '')
                if library_key!=sid and library_key in result:
                    result[sid]=result.pop(library_key)
                g.setdefault('colors',result.get(sid,{}).get('colors',[]))
                g.setdefault('categories',result.get(sid,{}).get('categories',[]))
                g.setdefault('favorite',bool(result.get(sid,{}).get('favorite')))
                g.setdefault('in_purgatory',bool(result.get(sid,{}).get('in_purgatory')))
                # Existing library members remain visible alongside locally reviewed additions.
                removed=set(g.get('removed_members',[]))
                g['members']=list(dict.fromkeys(i for i in result.get(sid,{}).get('members',[])+g['members'] if i not in removed))
                g['saved']=True;result[sid]=g
        for g in result.values():g['colors']=set_name_colors(g['name'],g.get('colors',[]))
        if not include_discarded:
            for g in result.values():g['members']=[i for i in g['members'] if i in self.catalog and i not in self.discarded]
        for g in result.values():
            # Sources and origins include confirmed duplicate-to-keeper provenance.
            # Derive this tag so removals and undone connections cannot leave a stale label.
            g['instagram']=any(self.has_instagram(self.catalog.get(i,{})) for i in g['members'])
        return result

    @staticmethod
    def has_instagram(item):
        sources=list(item.get('sources',{}).values())+item.get('origins',[])
        return any(s.get('kind')=='instagram' or str(s.get('key','')).startswith('instagram:') for s in sources)

    def switch_collection(self,body):
        with self.engine.lock,self.lock,self.bulk.lock:
            if self.engine.status['running'] or self.job['running'] or (self.bulk.current or {}).get('running'):
                raise ValueError('Finish or pause the current scan or analysis before switching collections.')
            if body.get('job')!=(self.bulk.current or {}).get('id'):
                raise ValueError('Collection changed in another window. Reload before switching.')
            ident=str(body.get('id',''))
            if ident not in {c['id'] for c in self.bulk.collections()}:
                raise ValueError('Choose an available saved collection.')
            if ident.startswith('girl:'):self.bulk.sections.activate(ident)
            else:self.bulk.activate(ident)
            self.bound=None
            self.job={'running':False,'phase':'Saved inventory ready','done':0,'total':0,'eta_seconds':None}
            return self.summary()

    def merge_scopes(self,sources):
        """Copy once; retain original rows and journal all adopted evidence."""
        with self.db() as db:
            for source in sources:
                if source==self.scope or db.execute('SELECT 1 FROM scope_merges WHERE target=? AND source=?',(self.scope,source)).fetchone():continue
                for table,columns in [('sets','id,data'),('posts','id,status'),('rejected','context,id'),('parked','post,hash'),('video_references','sha,data'),('individual_imports','sha,data')]:
                    for row in db.execute('SELECT '+columns+' FROM '+table+' WHERE scope=?',(source,)).fetchall():
                        if table=='sets':
                            old=db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.scope,row[0])).fetchone()
                            if old and old[0]!=row[1]:
                                g=json.loads(row[1]);g['id']='recovered:'+source+':'+row[0];row=(g['id'],json.dumps(g))
                        db.execute('INSERT OR IGNORE INTO '+table+' VALUES (?,?,?)',(self.scope,*row))
                other=db.execute('SELECT data FROM state WHERE scope=?',(source,)).fetchone()
                if other:
                    from character_collections import union
                    old=json.loads(other[0]);live=db.execute('SELECT data FROM state WHERE scope=?',(self.scope,)).fetchone()
                    state=json.loads(live[0]) if live else old
                    if live:
                        state['pins']=union(state.get('pins',[]),old.get('pins',[]))
                        state['post_evidence']={**old.get('post_evidence',{}),**state.get('post_evidence',{})}
                        state['duplicate_choices']={**old.get('duplicate_choices',{}),**state.get('duplicate_choices',{})}
                        # Keep independent unfinished drafts and resume states recoverable.
                        state.setdefault('previous_collections',{})[source]=old
                    self.put_state(db,state)
                db.execute('INSERT INTO scope_merges VALUES (?,?)',(self.scope,source))
                tracking.journal().observe(db,'organizer.scope_merge',self.scope+':'+source,{'source':source,'target':self.scope})

    def refresh_collections(self,body):
        with self.engine.lock,self.lock,self.bulk.lock:
            self.check_collection_idle(body)
            try:result=self.bulk.sections.sync()
            except ValueError as error:return {'connected':False,'connection_note':str(error)}
            # Adopt only a known character UUID, never an inherited display name.
            current=self.bulk.current or {}
            row=next((r for r in self.bulk.sections.rows() if self.bulk.sections.belongs(current,r)),None)
            if row:self.bulk.sections.activate(row['id']);self.bound=None
            elif not current:
                rows=self.bulk.sections.rows()
                if rows:self.bulk.sections.activate(rows[0]['id']);self.bound=None
            return result

    def check_collection_idle(self,body):
        if self.engine.status['running'] or self.job['running'] or (self.bulk.current or {}).get('running'):
            raise ValueError('Finish or pause the current scan or analysis first.')
        if body.get('job')!=(self.bulk.current or {}).get('id'):
            raise ValueError('Collection changed in another window. Reload before continuing.')

    def collection_folders(self,body):
        with self.engine.lock,self.lock,self.bulk.lock:
            self.check_collection_idle(body)
            current=self.bulk.current or {}
            if not current.get('section_id'):raise ValueError('Choose a girl in Collection first.')
            from character_collections import union
            roots=union(current['config']['roots'],body.get('roots',[]))
            if not roots:raise ValueError('Add at least one folder.')
            # All previous roots remain attached; hashes and saved decisions are reused.
            previous=copy.deepcopy(current)
            result=self.bulk.start({**current['config'],'roots':roots,'limit':0},inventory_only=True,section=previous)
            self.bound=None
            return result

    def assign_collection(self,body):
        with self.engine.lock,self.lock,self.bulk.lock:
            self.check_collection_idle(body)
            current=self.bulk.current or {}
            if not current or current.get('section_id'):raise ValueError('Choose an unassigned folder collection first.')
            row=next((r for r in self.bulk.sections.rows() if r['id']==body.get('id')),None)
            if not row:raise ValueError('Choose a girl from the library.')
            owner=current.get('config',{}).get('character_id')
            if owner and owner!=row['character_id']:raise ValueError('This collection already belongs to a different girl.')
            current['config'].update(character_id=row['character_id'],library_instance=row['library_instance'],person=row['name'])
            self.bulk.persist();self.bulk.sections.activate(row['id']);self.bound=None
            return self.summary()

    def individual_imports(self,include_applied=False):
        # Saved hashes survive rescans and verified duplicate-to-keeper changes.
        by_hash={h:i for i,r in self.catalog.items() if not r.get('quarantine_only') and i not in self.discarded for h in self.hashes(i)}
        with self.db() as db:rows=db.execute('SELECT sha,data FROM individual_imports WHERE scope=? ORDER BY rowid',(self.scope,)).fetchall()
        result=[]
        for digest,raw in rows:
            row=json.loads(raw)
            if row.get('applied_at') and not include_applied:continue
            ident=next((by_hash[h] for h in [digest]+row.get('hashes',[]) if h in by_hash),None)
            result.append(dict(row,key=digest,id=ident))
        return result

    def import_catalog(self,body):
        with self.lock,self.bulk.lock:
            self.bind();self.check_collection_idle(body)
            owner=self.category_catalog().get('character_id') or str(body.get('character_id',''))
            library=self.engine.library.request('/api/library');characters=library.get('characters',[])
            if not owner and len(characters)==1:owner=characters[0]['id']
            if not owner:return {'choose_character':[{'id':c['id'],'name':c['name']} for c in characters]}
            character=next((c for c in characters if c['id']==owner),None)
            if not character:raise ValueError('The saved character is not available in the connected library.')
            return {'character_id':owner,'library_instance':self.engine.library.request('/api/tracking/status')['instance'],'name':character['name'],'categories':[c for c in character.get('categories',[]) if c.get('media_type','image')=='image']}

    def create_import_category(self,body):
        with self.lock,self.bulk.lock:
            catalog=self.import_catalog(body)
            if not catalog.get('character_id'):raise ValueError('Choose the destination girl first.')
            name=str(body.get('name','')).strip()
            if not name or len(name)>100:raise ValueError('Enter an image category name (up to 100 characters).')
            return self.engine.library.request('/api/categories',{'character_id':catalog['character_id'],'name':name,'media_type':'image'})

    def summary(self):
        with self.lock,self.bulk.lock:
            self.bind();self.refresh_library_placement(force=True);state=self.state();state['selection']=[i for i in state.get('selection',[]) if i in self.catalog and i not in self.discarded];sets=self.sets();assigned={i for g in sets.values() for i in g['members']}
            reference=state.get('suggestion_reference')
            if reference not in self.catalog or reference in self.discarded or self.catalog[reference].get('quarantine_only'):state['suggestion_reference']='';reference=None
            with self.db() as db:statuses=dict(db.execute('SELECT id,status FROM posts WHERE scope=?',(self.scope,)))
            posts=[]
            for p in self.posts.values():
                visible=self.post_ids(p['id']);live=[i for i in visible if not self.catalog[i].get('quarantine_only')]
                posts.append({k:v for k,v in p.items() if k!='ids'}|{'count':len(visible),'remaining':sum(i not in assigned for i in live),'unresolved':len(visible)-len(live),'status':statuses.get(p['id'],'pending'),'mixed':self.is_mixed(p['id'],state.get('post_evidence',{})),'large':len(p['ids'])>=1000,'source_count':len(p['ids']),'cover':next(iter(live or visible),None)})
            posts.sort(key=lambda p:(p['status']!='pending',p['remaining']==0,natural(p['label'])))
            total=sum(not r.get('quarantine_only') and i not in self.discarded for i,r in self.catalog.items())
            return {'job':(self.bulk.current or {}).get('id'),'section_id':(self.bulk.current or {}).get('section_id'),'roots':(self.bulk.current or {}).get('config',{}).get('roots',[]),'inventory_running':bool((self.bulk.current or {}).get('running')),'scope':self.scope,'collections':self.bulk.collections(),'posts':posts,'sets':[dict(g,count=len(g['members'])) for g in sets.values()],
                'individuals':self.individual_imports(),'up_next':self.pinned_ids(state),'later_count':sum(p['status']=='deferred' for p in posts),
                'reference_image':self.image(reference)|{'analyzed':reference in self.vector_by_id} if reference else None,'category_catalog':self.category_catalog(),'state':state,'images':total,'unresolved':sum(bool(r.get('quarantine_only')) for i,r in self.catalog.items() if i not in self.discarded),'indexed':sum(i in self.vector_by_id for i,r in self.catalog.items() if not r.get('quarantine_only') and i not in self.discarded),
                'unassigned_count':sum(not r.get('quarantine_only') and i not in self.discarded and i not in assigned for i,r in self.catalog.items()),'unsorted_count':len(self.unsorted_ids()),'discarded_count':sum(not self.catalog[i].get('quarantine_only') for i in self.discarded),
                'progress':dict(self.job),'inventory_complete':bool((self.bulk.current or {}).get('inventory_complete') or (self.bulk.current or {}).get('complete'))}

    def scores(self,seeds):
        vectors=[self.vector_by_id[i] for i in seeds if i in self.vector_by_id]
        if not vectors or not len(self.matrix):return {}
        # Evenly cover the reference pool, including its newest selected image.
        chosen=np.stack([vectors[n] for n in np.linspace(0,len(vectors)-1,min(12,len(vectors)),dtype=int)])
        values=(self.matrix@chosen.T).max(axis=1)
        return dict(zip(self.vector_ids,values.tolist()))

    @staticmethod
    def original_order_key(name,source):
        if str(source).startswith('instagram:'):
            # Carousel position follows the final underscore, not the media ID.
            # Bare numbered filenames are used by some older IG downloads.
            match=re.search(r'(?:^|_)(\d+)\.[^.]+$',name)
            if match:return (0,int(match[1]),natural(name))
        return (1,0,natural(name))

    def original_name(self,ident,source):
        item=self.catalog[ident]
        paths=[o.get('original_path') or o.get('path','') for o in item.get('origins',[]) if o.get('key')==source]
        names=[re.split(r'[\\/]',p)[-1] for p in paths if p]
        return min(names,key=lambda name:self.original_order_key(name,source)) if names else re.split(r'[\\/]',item['path'])[-1]

    def ordered(self,ids,mode,source=None):
        ids=list(ids);cache=(tuple(ids),mode,source)
        if cache in self.order_cache:return self.order_cache[cache]
        if mode=='original':
            # Origin filenames supply display order only. IDs and image paths keep
            # pointing to the survivor selected during duplicate review.
            return sorted(ids,key=lambda i:(self.original_order_key(self.original_name(i,source),source),i))
        base=sorted(ids,key=lambda i:(self.catalog[i].get('quarantine_only',False),natural(self.catalog[i]['path'])))
        if mode=='filename' or len(base)<3:return base
        # Preserve coarse source neighborhoods in very large mixed posts; each block
        # is bounded so a 5,000-image folder never stalls the UI with an N² sort.
        result=[]
        for start in range(0,len(base),240):
            left=base[start:start+240];ordered=[left.pop(0)]
            while left:
                prior=ordered[-1]
                def distance(i):
                    if prior in self.vector_by_id and i in self.vector_by_id:return 2+float(self.vector_by_id[prior]@self.vector_by_id[i])
                    if prior in self.quick and i in self.quick:return float(self.quick[prior]@self.quick[i])
                    return -1
                best=max(range(len(left)),key=lambda j:distance(left[j]));ordered.append(left.pop(best))
            result.extend(ordered)
        self.order_cache[cache]=result
        if len(self.order_cache)>100:self.order_cache.pop(next(iter(self.order_cache)))
        return result

    def refresh_library_placement(self,force=False):
        # Live metadata also covers inventories saved before placement badges existed.
        # Cache across the many image() calls in one page/suggestions response.
        config=(self.bulk.current or {}).get('config',{})
        key=(self.scope,config.get('character_id'),config.get('library_instance'))
        cached=self.library_placement
        if not force and cached and cached['key']==key and time.monotonic()-cached['at']<5:return
        result={'key':key,'at':time.monotonic(),'main':None,'review':None,'purgatory':None}
        self.library_placement=result
        owner=config.get('character_id') or self.category_catalog().get('character_id')
        if not owner:return
        try:
            catalog=self.engine.library.catalog(owner)
            expected=config.get('library_instance')
            # Sections store tracking's instance ID, not the catalog's store ID.
            if expected and self.engine.library.request('/api/tracking/status')['instance']!=expected:return
            main={};review=set();purgatory=set()
            for row in catalog['files']:
                if row.get('character_id',owner)!=owner:continue
                digest=row.get('sha')
                if not digest:continue
                visible=bool(row.get('in_all',True)) and not row.get('in_review') and not row.get('in_purgatory')
                main[digest]=main.get(digest,False) or bool(visible)
                if row.get('in_review'):review.add(digest)
                if row.get('in_purgatory'):purgatory.add(digest)
            result.update(main=main,review=review,purgatory=purgatory)
        except (ValueError,OSError,KeyError,TypeError):
            # Disconnected or changed library is unknown, never "not in Main".
            pass

    def image(self,ident):
        self.refresh_library_placement()
        r=self.catalog[ident];main=self.library_placement['main']
        present=None if main is None else r.get('sha') in main
        in_main=None if main is None else main.get(r.get('sha'),False)
        in_review=None if main is None else r.get('sha') in self.library_placement['review']
        in_purgatory=None if main is None else r.get('sha') in self.library_placement['purgatory']
        return {'id':ident,'library_present':present,'in_main':in_main,'in_review':in_review,'in_purgatory':in_purgatory,'name':re.split(r'[\\/]',r['path'])[-1],'path':r['path'],'media_type':r.get('media_type','image'),'frame_seconds':r.get('frame_seconds'),'quarantined':bool(r.get('quarantine_only')),
                'sources':list(r.get('sources',{})),'origins':r.get('origins',[]),'reference':bool(r.get('reference')),'discarded':ident in self.discarded}

    def pinned_ids(self,state=None):
        """Resolve saved hashes through verified keeper/copy provenance after rescans."""
        pins=(state if state is not None else self.state()).get('pins',[])
        by_hash={}
        for ident,item in self.catalog.items():
            if item.get('quarantine_only') or ident in self.discarded:continue
            for digest in self.hashes(ident):by_hash[digest]=ident
        result=[]
        for pin in pins:
            ident=next((by_hash[h] for h in pin['hashes'] if h in by_hash),None)
            if ident and ident not in result:result.append(ident)
        return result

    def page(self,kind,ident,offset=0,order='similar',remember=True,focus_id=None):
        with self.lock,self.bulk.lock:
            self.bind()
            if kind=='post':
                group=self.posts.get(ident)
                ids=self.post_ids(ident) if group else []
            elif kind=='set':
                group=self.sets().get(ident);ids=group.get('members',[]) if group else []
            elif kind=='unsorted':group={'label':'Unsorted'};ids=self.unsorted_ids()
            elif kind=='up_next':group={'label':'★ Up next'};ids=self.pinned_ids()
            elif kind=='imports':group={'label':'Individual import queue'};ids=list(dict.fromkeys(r['id'] for r in self.individual_imports() if r['id']))
            elif kind=='all_images':group={'label':'All available images'};ids=[i for i,r in self.catalog.items() if not r.get('quarantine_only') and i not in self.discarded and r.get('media_type','image')=='image']
            elif kind=='discarded':group={'label':'Discarded · recoverable'};ids=[i for i in self.discarded if not self.catalog[i].get('quarantine_only')]
            else:raise ValueError('Invalid collection.')
            if not group:raise ValueError('Choose an available post or set.')
            ids=[i for i in ids if i in self.catalog]
            source=ident if kind=='post' else None
            ids=self.ordered(ids,order,source)
            focus_id=focus_id if focus_id in ids else None
            if focus_id is not None:offset=ids.index(focus_id)
            offset=max(0,min(int(offset),max(0,len(ids)-1)))//60*60
            if remember:
                state=self.state();state.update(view={'kind':kind,'id':ident,'offset':offset,'order':order})
                with self.db() as db:self.put_state(db,state)
            sets=self.sets();labels={}
            for g in sets.values():
                for i in g['members']:labels.setdefault(i,[]).append(g['name'])
            return {'label':group.get('label',group.get('name')),'total':len(ids),'offset':offset,'ids':ids,'focus_id':focus_id,
                    'images':[self.image(i)|{'display_name':self.original_name(i,source),'sets':labels.get(i,[])} for i in ids[offset:offset+60]],'job':self.bound[0]}

    def manual_search(self,body):
        with self.lock,self.bulk.lock:
            self.bind();self.check_collection_idle(body)
            if body.get('source','library')=='library':
                info=self.import_catalog(body)
                if not info.get('character_id'):return info
                catalog=self.engine.library.catalog(info['character_id'])
                self.search_library_catalog={'owner':info['character_id'],'catalog':catalog,'files':{r['id']:r for r in catalog['files']},'at':time.monotonic()}
                extra={}
                if body.get('duplicate_source'):
                    ident=self.valid_ids([body['duplicate_source']])[0];digest=self.catalog[ident]['sha'];candidates=set()
                    live={r['sha']:r['id'] for r in catalog['files']}
                    with self.engine.db() as db:
                        for a,b in db.execute('SELECT a.sha,b.sha FROM pairs p JOIN files a ON a.id=p.a JOIN files b ON b.id=p.b WHERE p.decision IS NULL AND a.moved=0 AND b.moved=0 AND (a.sha=? OR b.sha=?)',(digest,digest)):
                            other=b if a==digest else a
                            if other in live:candidates.add(live[other])
                    extra={'media_ids':sorted(candidates)}
                result=self.engine.library.request('/api/sets/manual-search',{**body,**extra,'character_id':info['character_id']})
                expected=(self.bulk.current or {}).get('config',{}).get('library_instance')
                if expected and expected!=result['library_instance']:raise ValueError('A different library is connected.')
                return result
            kind=body.get('kind','sets');terms=str(body.get('query','')).casefold().split();category=body.get('category','');placement=body.get('placement','all');sets=self.sets();rows=[]
            categories=self.category_catalog().get('categories',[]);names={c['id']:c['name'] for c in categories};labels={}
            for g in sets.values():
                for ident in g['members']:labels.setdefault(ident,[]).append(g)
            source=sets.values() if kind=='sets' else (self.image(i) for i,v in self.catalog.items() if not v.get('quarantine_only') and i not in self.discarded and v.get('media_type','image')=='image')
            for row in source:
                groups=labels.get(row['id'],[]);cats=row.get('categories',[]) if kind=='sets' else list({c for g in groups for c in g.get('categories',[])})
                held=bool(row.get('in_purgatory')) if kind=='sets' else any(g.get('in_purgatory') for g in groups)
                if placement=='purgatory' and not held or placement=='main' and held or placement=='unassigned' and (kind=='sets' or groups):continue
                if category and (bool(cats) if category=='__none' else category not in cats):continue
                text=' '.join([row['name'],row.get('path',''),*row.get('colors',[]),*[names.get(c,'') for c in cats],*[g['name'] for g in groups]]).casefold()
                if not all(t in text for t in terms):continue
                rows.append({'id':row['id'],'name':row['name'],'count':len(row['members']) if kind=='sets' else 1,'cover':next(iter(row['members']),None) if kind=='sets' else row['id'],'sets':[{'id':g['id'],'name':g['name']} for g in groups],'in_purgatory':held,'placement':'Set Purgatory' if held else 'Saved inventory'})
            rows.sort(key=lambda x:(x['name'].casefold(),x['id']));offset=max(0,int(body.get('offset',0)))
            return {'rows':rows[offset:offset+60],'total':len(rows),'offset':offset,'categories':categories}

    def attach_library(self,body):
        with self.lock,self.bulk.lock:
            self.bind();self.check_collection_idle(body);info=self.import_catalog(body);owner=info.get('character_id')
            if not owner:raise ValueError('Choose a girl first.')
            if body.get('library_instance')!=info['library_instance']:raise ValueError('Library changed. Search again.')
            library=self.engine.library.request('/api/library');catalog=self.engine.library.catalog(owner)
            groups={g['id']:g for g in library.get('sets',[]) if g.get('character_id')==owner and g.get('kind','set')=='set'}
            target=groups.get(body.get('set_id'));ids=target.get('media_ids',[]) if target else body.get('media_ids',[])
            if body.get('set_id') and not target:raise ValueError('Set changed. Search again.')
            files={m['id']:m for m in catalog['files']};ids=[i for i in ids if i in files] if target else ids
            if not isinstance(ids,list) or any(i not in files for i in ids):raise ValueError('Images changed. Search again.')
            current=self.bulk.current;attached=[]
            for mid in ids:
                row=files[mid];path=Path(row['path'])
                if linked(path) or not path.is_file() or sha256(path)!=row['sha']:raise ValueError('Library original changed or is missing.')
                memberships=[sid for sid,g in groups.items() if mid in g.get('media_ids',[])]
                for sid in memberships:current.setdefault('library_sets',{})[sid]={k:groups[sid].get(k) for k in ('id','name','categories','colors','favorite','in_purgatory')}
                ident=next((i for i,v in self.catalog.items() if v.get('sha')==row['sha']),row['sha'])
                old=copy.deepcopy(current.setdefault('source_catalog',{}).get(ident,{}));source={'key':'library:'+mid,'kind':'library','label':'Media library','path':str(path),'quarantine':False}
                if not old:old={'id':ident,'path':str(path),'stamp':stat_key(path),'sha':row['sha'],'sources':{source['key']:source},'origins':[source],'copies':[],'reference':True}
                old['existing_sets']=memberships;old.setdefault('sources',{})[source['key']]=source
                current['source_catalog'][ident]=old;attached.append(ident)
            if target:current.setdefault('library_sets',{})[target['id']]={k:target.get(k) for k in ('id','name','categories','colors','favorite','in_purgatory')}
            current.setdefault('config',{})['library_instance']=info['library_instance']
            current['config']['character_id']=owner
            self.bulk.persist();self.bound=None;self.bind()
            state=self.state();state['revision']=state.get('revision',0)+1
            with self.db() as db:self.put_state(db,state)
            return {'ids':attached,'target':next((g['id'] for g in self.sets().values() if target and g.get('library_id')==target['id']),None)}

    def library_image_path(self,owner,ident,size=0):
        cached=getattr(self,'search_library_catalog',{})
        catalog=cached['catalog'] if size and cached.get('owner')==owner and time.monotonic()-cached['at']<120 else self.engine.library.catalog(owner)
        row=cached['files'].get(ident) if size and catalog is cached.get('catalog') else next((r for r in catalog['files'] if r['id']==ident),None)
        if not row:raise ValueError('Library image unavailable.')
        path=Path(row['path'])
        target=self.engine.state_dir/'search-thumbnails'/(row['sha']+'.jpg')
        if size and target.is_file():return target
        if linked(path) or not path.is_file() or sha256(path)!=row['sha']:raise ValueError('Library original changed or is unavailable.')
        if size:
            if not target.is_file():
                target.parent.mkdir(exist_ok=True)
                with runtime_helpers()['Image'].open(path) as image:
                    image.thumbnail((600,600));buffer=io.BytesIO();image.convert('RGB').save(buffer,format='JPEG',quality=88)
                temp=target.with_suffix('.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(buffer.getvalue());temp.replace(target)
            return target
        return path

    def comparison_source(self,body):
        with self.lock,self.bulk.lock:
            self.bind();self.check_collection_idle(body);ident=self.valid_ids([body.get('id')])[0];path=self.original_path(ident)
            with runtime_helpers()['Image'].open(path) as image:width,height=image.size
            return {'name':path.name,'width':width,'height':height,'bytes':path.stat().st_size,'sha':self.catalog[ident]['sha']}

    def duplicate_choice(self,body):
        with self.lock,self.bulk.lock:
            self.bind();self.check_collection_idle(body);state=self.state()
            if body.get('revision')!=state.get('revision',0):raise ValueError('Import choices changed. Refresh before saving.')
            ident=self.valid_ids([body.get('id')])[0];source=self.catalog[ident]
            if source.get('media_type','image')!='image':raise ValueError('Choose a still image.')
            action=body.get('action');choices=state.setdefault('duplicate_choices',{})
            if action=='separate':choice={'action':'separate','source_sha':source['sha'],'at':time.time()}
            elif action in ('keep','replace'):
                info=self.import_catalog(body);owner=info.get('character_id');catalog=self.engine.library.catalog(owner)
                target=next((r for r in catalog['files'] if r['id']==body.get('target')),None)
                if not target or target['character_id']!=owner or body.get('target_sha')!=target['sha'] or body.get('library_instance')!=info['library_instance']:raise ValueError('Comparison changed. Search and compare again.')
                if target['sha']==source['sha']:raise ValueError('This is an exact match; the import automatically reuses it.')
                self.original_path(ident);self.library_image_path(owner,target['id'])
                choice={'action':action,'source_sha':source['sha'],'target':target['id'],'target_sha':target['sha'],'target_name':target['name'],'library_id':catalog['library_id'],'library_instance':info['library_instance'],'operation':uuid.uuid4().hex,'at':time.time()}
            else:raise ValueError('Choose Keep, Replace or Import separately.')
            choices[source['sha']]=choice;state['revision']=state.get('revision',0)+1
            with self.db() as db:self.put_state(db,state)
            return {'choice':choice}

    def related(self,body):
        with self.lock,self.bulk.lock:
            self.bind();selection=self.valid_ids(body.get('ids',[]));allsets=self.sets()
            members=allsets.get(str(body.get('target','')),{}).get('members',[])
            seeds=list(dict.fromkeys([i for i in members if i not in selection]+selection))
            reference=body.get('suggestion_reference') or ''
            if reference:self.valid_ids([reference])
            evidence_ids=[reference] if reference else seeds
            context=self.context_key(body,evidence_ids)
            if not evidence_ids:return {'images':[],'posts':[],'sets':[],'total':0}
            evidence=self.state().get('post_evidence',{})
            visual=self.scores(evidence_ids);selected=set(seeds)|set(evidence_ids);sources={s for i in evidence_ids for s in self.catalog[i]['sources'] if s in self.posts and not self.is_mixed(s,evidence)}
            with self.db() as db:rejected={r[0] for r in db.execute('SELECT id FROM rejected WHERE scope=? AND context=?',(self.scope,context))}
            ranked=[]
            assigned={i for g in allsets.values() for i in g['members']} if body.get('unassigned_only') is True else set()
            for ident,item in self.catalog.items():
                if ident in selected or ident in rejected or ident in self.discarded or ident in assigned or item.get('quarantine_only'):continue
                shared=sources & item['sources'].keys();v=visual.get(ident,0)
                if not shared and v<.60:continue
                source_score=sum(1/(max(1,len(self.posts[s]['ids']))**.5) for s in shared)
                score=min(.35,.3*source_score)+v
                ranked.append((score,ident,'Shared source post'+(' · visually similar' if v>=.60 else '') if shared else 'Visually similar'))
            ranked.sort(key=lambda r:(-r[0],r[1]));offset=min(max(0,int(body.get('offset',0))),max(0,(len(ranked)-1)//30*30));sets=[];labels={}
            for g in allsets.values():
                members=set(g['members']);overlap=len(selected & members)
                for i in members:labels.setdefault(i,[]).append(g['name'])
                shared=len(sources & {s for i in members if i in self.catalog for s in self.catalog[i]['sources']})
                v=max((visual.get(i,0) for i in members),default=0)
                if overlap or shared or v>=.60:sets.append({'id':g['id'],'name':g['name'],'count':len(members),'overlap':overlap,'score':overlap*10+bool(shared)+v,'library':bool(g.get('library_id')),'in_purgatory':bool(g.get('in_purgatory'))})
            sets.sort(key=lambda g:(-g['score'],g['name']))
            posts=[{'id':s,'label':self.posts[s]['label'],'count':len(self.posts[s]['ids']),'shared':sum(s in self.catalog[i]['sources'] for i in evidence_ids),'anchor_id':next(i for i in reversed(evidence_ids) if s in self.catalog[i]['sources'])} for s in sources]
            posts.sort(key=lambda p:(-p['shared'],p['count'],p['label']))
            return {'reference':self.image(reference)|{'analyzed':reference in self.vector_by_id} if reference else None,'context':context,'images':[self.image(i)|{'reason':reason,'sets':labels.get(i,[])} for _,i,reason in ranked[offset:offset+30]],'total':len(ranked),'offset':offset,'sets':sets[:12],'posts':posts}

    def valid_ids(self,ids):
        if not isinstance(ids,list) or len(ids)>15000:raise ValueError('Invalid selection.')
        ids=list(dict.fromkeys(ids))
        if any(i not in self.catalog or self.catalog[i].get('quarantine_only') or i in self.discarded for i in ids):raise ValueError('Select surviving images only. Quarantine remains evidence only.')
        return ids

    def context_key(self,body,ids):
        target=body.get('target')
        if body.get('suggestion_reference'):return 'reference:'+hashlib.sha256(json.dumps([target,body['suggestion_reference']]).encode()).hexdigest()
        return str(target) if target else hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()

    @staticmethod
    def colors(value):
        # Same descriptor format and limits as the media library's Set details.
        if not isinstance(value,list) or len(value)>50 or any(not isinstance(v,str) or len(v)>150 for v in value):
            raise ValueError('Invalid Set colors (up to 50 descriptors, 150 characters each).')
        return list(dict.fromkeys(title_case_label(v) for v in value if v.strip()))

    @staticmethod
    def favorite(value):
        if not isinstance(value,bool):raise ValueError('Choose a valid Set favorite setting.')
        return value

    def category_catalog(self):
        with self.db() as db:row=db.execute('SELECT data FROM category_catalog WHERE scope=?',(self.scope,)).fetchone()
        return json.loads(row[0]) if row else {'character_id':(self.bulk.current or {}).get('config',{}).get('character_id',''),'categories':[]}

    def category_action(self,action,body):
        # Explicit metadata-only actions. No media scan or library writes.
        with self.lock,self.bulk.lock:
            self.bind()
            if body.get('job')!=self.bound[0]:raise ValueError('Inventory changed. Reopen the organizer.')
            catalog=self.category_catalog()
            if action=='load_categories':
                library=self.engine.library.request('/api/library')
                characters=library.get('characters',[])
                owner=catalog['character_id'] or str(body.get('character_id',''))
                if not owner and len(characters)==1:owner=characters[0]['id']
                if not owner:return {'choose_character':[{'id':c['id'],'name':c['name']} for c in characters]}
                character=next((c for c in characters if c['id']==owner),None)
                if not character:raise ValueError('The saved character is not available in this media library.')
                catalog['character_id']=owner
                by_id={c['id']:c for c in catalog['categories']}
                for c in character.get('set_categories',[]):by_id[c['id']]={'id':c['id'],'name':c['name'],'local':False}
                catalog['categories']=list(by_id.values())
            elif action=='create_category':
                name=str(body.get('name','')).strip()
                if not name or len(name)>150:raise ValueError('Enter a category name (up to 150 characters).')
                category=next((c for c in catalog['categories'] if c['name'].casefold()==name.casefold()),None)
                if not category:
                    category={'id':uuid.uuid4().hex,'name':name,'local':True}
                    catalog['categories'].append(category)
            else:raise ValueError('Invalid category action.')
            with self.db() as db:db.execute('INSERT OR REPLACE INTO category_catalog VALUES (?,?)',(self.scope,json.dumps(catalog)))
            return {'category_catalog':catalog,**({'category':category} if action=='create_category' else {})}

    def categories(self,value,previous=()):
        valid={c['id'] for c in self.category_catalog()['categories']}|set(previous)
        if not isinstance(value,list) or any(not isinstance(c,str) or c not in valid for c in value):
            raise ValueError('Choose available Set categories.')
        return list(dict.fromkeys(value))

    @staticmethod
    def session_preferences(value):
        if not isinstance(value,dict):raise ValueError('Invalid organizer preferences.')
        result={}
        choices={'tab':('posts','sets'),'sourceFilter':('all','instagram','forum'),
            'filter':('pending','all','remaining','large','ignored','deferred','reviewed'),
            'postSort':('default','nameAsc','nameDesc','most','fewest','remaining'),
            'setFilter':('all','favorites','uncategorized','categorized','purgatory'),
            'setSort':('default','nameAsc','nameDesc','createdAsc','createdDesc','updatedDesc'),
            'order':('similar','original','filename')}
        for key,options in choices.items():
            if value.get(key) in options:result[key]=value[key]
        for key in ('search','sidebarSet'):
            if isinstance(value.get(key),str):result[key]=value[key][:500]
        for key in ('unassignedOnly','highlight','relatedVisible'):
            if isinstance(value.get(key),bool):result[key]=value[key]
        for key,maximum in [('limit',1000000),('columns',8),('sidebarWidth',5000),('sidebarOffset',1000000),('relatedOffset',1000000),('gridScroll',100000000),('navScroll',100000000),('suggestionsScroll',100000000),('savedAt',10000000000000)]:
            n=value.get(key)
            if isinstance(n,(int,float)) and 0<=n<=maximum:result[key]=int(n)
        view=value.get('view')
        if isinstance(view,dict) and view.get('kind') in ('post','set','unsorted','discarded','up_next','imports','all_images') and isinstance(view.get('id'),str):
            n=view.get('offset',0)
            if isinstance(n,(int,float)) and 0<=n<=1000000:
                result['view']={'kind':view['kind'],'id':view['id'][:500],'offset':int(n)}
        return result

    @tracking.journal().action("manual")
    def mutate(self,action,body):
        with self.lock,self.bulk.lock:
            self.bind()
            if body.get('job')!=self.bound[0]:raise ValueError('Inventory changed. Reopen the organizer.')
            state=self.state()
            if action=='session':
                ui=self.session_preferences(body.get('ui'))
                if ui.get('savedAt',0)<state.get('ui',{}).get('savedAt',0):return {'saved':False,'stale':True}
                state['ui']=ui
                with self.db() as db:self.put_state(db,state)
                return {'saved':True}
            if action=='draft':
                if 'new_name' in body:state['new_name']=str(body['new_name'])[:200]
                if 'suggestion_reference' in body:
                    reference=body['suggestion_reference']
                    if reference:self.valid_ids([reference])
                    state['suggestion_reference']=reference or ''
                state['selection']=self.valid_ids(body.get('ids',[]));state['target']=str(body.get('target',''))
                if 'new_favorite' in body:state['new_favorite']=self.favorite(body['new_favorite'])
                if 'new_colors' in body:state['new_colors']=self.colors(body['new_colors'])
                if 'new_categories' in body:state['new_categories']=self.categories(body['new_categories'],state.get('new_categories',[]))
                with self.db() as db:self.put_state(db,state)
                return {'saved':True}
            if int(body.get('revision',-1))!=state.get('revision',0):raise ValueError('Review changed in another window. Reload before saving.')
            previous_undo=copy.deepcopy(state.get('undo'))
            with self.db() as db:
                if action=='pin':
                    ident=self.valid_ids([body.get('id')])[0];hashes=self.hashes(ident)
                    if not isinstance(body.get('pinned'),bool):raise ValueError('Choose star or unstar.')
                    pins=[p for p in state.get('pins',[]) if not hashes.intersection(p['hashes'])]
                    if body['pinned']:pins.append({'hashes':sorted(hashes),'created':time.time()})
                    state['pins']=pins
                elif action in ('queue_individuals','remove_individuals'):
                    ids=self.valid_ids(body.get('ids',[]))
                    keys=body.get('keys',[]) if action=='remove_individuals' else []
                    if not isinstance(keys,list) or any(not isinstance(k,str) for k in keys):raise ValueError('Choose valid queued images.')
                    if not ids and not keys:raise ValueError('Select at least one image.')
                    if any(self.catalog[i].get('media_type','image')!='image' for i in ids):raise ValueError('Select images for individual import. Video matching remains separate.')
                    existing=self.individual_imports(include_applied=True)
                    if any(k not in {r['key'] for r in existing} for k in keys):raise ValueError('Import queue changed. Refresh it.')
                    touched={self.catalog[i]['sha'] for i in ids}|{r['key'] for r in existing if r['id'] in ids or r['key'] in keys}
                    previous={key:(db.execute('SELECT data FROM individual_imports WHERE scope=? AND sha=?',(self.scope,key)).fetchone() or [None])[0] for key in touched}
                    if action=='queue_individuals':
                        options=runtime_helpers()['LibraryStore'].organizer_options(body.get('options',{}))
                        owner=self.category_catalog().get('character_id') or str(body.get('character_id',''))
                        if not owner:raise ValueError('Choose the destination girl first.')
                        if body.get('character_id') and body['character_id']!=owner:raise ValueError('The selected images belong to another girl.')
                        if options['destination']=='categories' and not options['categories']:raise ValueError('Choose a category or use Main.')
                    state['undo']={'action':'individuals','previous':previous,'selection':ids}
                    for key in touched:db.execute('DELETE FROM individual_imports WHERE scope=? AND sha=?',(self.scope,key))
                    if action=='queue_individuals':
                        for ident in ids:
                            item=self.catalog[ident];row={'hashes':sorted(self.hashes(ident)),'name':self.image(ident)['name'],'character_id':owner,'library_instance':body.get('library_instance') or (self.bulk.current or {}).get('config',{}).get('library_instance'),'options':options,'created':time.time()}
                            db.execute('INSERT OR REPLACE INTO individual_imports VALUES (?,?,?)',(self.scope,item['sha'],json.dumps(row)))
                    state['selection']=[]
                elif action=='save':
                    ids=self.valid_ids(body.get('ids',[]))
                    if not ids:raise ValueError('Select at least one image.')
                    target=str(body.get('target',''));allsets=self.sets(include_discarded=True);previous=allsets.get(target)
                    if target and not previous:raise ValueError('Set no longer available.')
                    name=title_case_label(body.get('name') or (previous or {}).get('name',''))
                    if not name or len(name)>250:raise ValueError('Give the set a name (up to 250 characters).')
                    # Adding the same keeper from another source post must not
                    # silently place it in a second set. Re-check on every save.
                    already=set((previous or {}).get('members',[]))
                    adding=set(ids)-already;memberships={i:[] for i in adding}
                    for sid,g in allsets.items():
                        if sid==target:continue
                        for i in adding.intersection(g.get('members',[])):
                            memberships[i].append({'id':sid,'name':g['name']})
                    conflicts=[{'id':i,'name':self.image(i)['name'],'sets':sorted(memberships[i],key=lambda g:g['id'])} for i in ids if memberships.get(i)]
                    if conflicts:
                        signature=hashlib.sha256(json.dumps({'target':target,'ids':sorted(ids),'conflicts':conflicts},sort_keys=True).encode()).hexdigest()
                        if body.get('membership_confirmation')!=signature:
                            return {'confirmation_required':True,'conflicts':conflicts,'membership_confirmation':signature,'destination':name}
                    ident=target or uuid.uuid4().hex
                    old=db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.scope,ident)).fetchone()
                    state['undo']={'action':'set','id':ident,'previous':old[0] if old else None,'selection':ids}
                    # A confirmed assignment is a move, matching the main library.
                    moved={}
                    for sid,other in allsets.items():
                        if sid==ident or not adding.intersection(other['members']):continue
                        old_other=db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.scope,sid)).fetchone()
                        moved[sid]=old_other[0] if old_other else None
                        other=dict(other,members=[i for i in other['members'] if i not in adding],
                            removed_members=list(set(other.get('removed_members',[]))|adding.intersection(other['members'])),updated=time.time())
                        db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(self.scope,sid,json.dumps(other)))
                    state['undo']['moved']=moved
                    members=list(dict.fromkeys((previous or {}).get('members',[])+ids))
                    colors=self.colors(body.get('colors',(previous or {}).get('colors',state.get('new_colors',[]))))
                    categories=self.categories(body.get('categories',(previous or {}).get('categories',state.get('new_categories',[]))),(previous or {}).get('categories',[]))
                    stamp=time.time()
                    favorite=self.favorite(body.get('favorite',(previous or {}).get('favorite',state.get('new_favorite',False))))
                    group=dict(previous or {},id=ident,name=name,colors=set_name_colors(name,colors),categories=categories,favorite=favorite,members=members,updated=stamp,library_id=(previous or {}).get('library_id'))
                    group['removed_members']=[i for i in group.get('removed_members',[]) if i not in ids]
                    if previous is None:group['created']=stamp
                    db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(self.scope,ident,json.dumps(group)))
                    state.update(selection=[],target='',new_name='',new_colors=[],new_categories=[],new_favorite=False)
                elif action in ('set_colors','set_details'):
                    target=str(body.get('target',''));group=self.sets(include_discarded=True).get(target)
                    if not group:raise ValueError('Choose an available set.')
                    colors=self.colors(body.get('colors',group.get('colors',[])))
                    categories=self.categories(body.get('categories',group.get('categories',[])),group.get('categories',[]))
                    old=db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.scope,target)).fetchone()
                    state['undo']={'action':'set','id':target,'previous':old[0] if old else None,'selection':state.get('selection',[])}
                    favorite=self.favorite(body.get('favorite',group.get('favorite',False)))
                    if 'in_purgatory' in body and self.favorite(body['in_purgatory'])!=bool(group.get('in_purgatory')):group['purgatory_edited']=True
                    group.update(colors=set_name_colors(group['name'],colors),categories=categories,favorite=favorite,in_purgatory=self.favorite(body.get('in_purgatory',group.get('in_purgatory',False))),updated=time.time())
                    db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(self.scope,target,json.dumps(group)))
                elif action=='remove':
                    target=str(body.get('target',''));old=db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.scope,target)).fetchone()
                    if not old:raise ValueError('Only locally saved drafts can be edited here.')
                    group=json.loads(old[0])
                    if group.get('library_id'):raise ValueError('Existing library membership is preserved; edit removals in the media library.')
                    ids=self.valid_ids(body.get('ids',[]));state['undo']={'action':'set','id':target,'previous':old[0],'selection':ids}
                    group['members']=[i for i in group['members'] if i not in ids];group['updated']=time.time()
                    db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(self.scope,target,json.dumps(group)));state['selection']=[]
                elif action in ('discard','restore_discard','unsort','restore_unsorted'):
                    ids=body.get('ids',[])
                    if action=='unsort' and body.get('remaining'):
                        post=body.get('post')
                        if post not in self.posts:raise ValueError('Choose a post.')
                        assigned={i for g in self.sets().values() for i in g['members']}
                        ids=[i for i in self.post_ids(post) if i not in assigned and not self.catalog[i].get('quarantine_only')]
                    if action=='restore_discard':
                        if not isinstance(ids,list) or len(ids)>15000 or any(i not in self.discarded for i in ids):raise ValueError('Choose discarded images to restore.')
                    else:ids=self.valid_ids(ids)
                    if not ids:raise ValueError('No eligible images selected.')
                    hashes=set().union(*(self.hashes(i) for i in ids))
                    if action in ('discard','restore_discard'):
                        old=[list(row) for row in db.execute('SELECT hash,batch,data FROM discarded') if row[0] in hashes]
                        if action=='discard':
                            batch=uuid.uuid4().hex;metadata=json.dumps({'created':time.time(),'ids':ids})
                            for digest in hashes:db.execute('INSERT OR REPLACE INTO discarded VALUES (?,?,?)',(digest,batch,metadata))
                        else:
                            # Restore hashes belonging to the chosen image and its known copies.
                            for digest in hashes:db.execute('DELETE FROM discarded WHERE hash=?',(digest,))
                        state['undo']={'action':'disposition','table':'discarded','hashes':sorted(hashes),'previous':old}
                    else:
                        assigned={i for g in self.sets().values() for i in g['members']}
                        if action=='unsort' and any(i in assigned for i in ids):raise ValueError('Move only images not assigned to any set.')
                        post=str(body.get('post',''))
                        if action=='unsort' and (post not in self.posts or any(i not in self.posts[post]['ids'] for i in ids)):raise ValueError('Choose images from the current post.')
                        old=[list(row) for row in db.execute('SELECT scope,post,hash FROM parked WHERE scope=?',(self.scope,)) if row[2] in hashes and (action=='restore_unsorted' or row[1]==post)]
                        if action=='unsort':
                            for digest in hashes:db.execute('INSERT OR IGNORE INTO parked VALUES (?,?,?)',(self.scope,post,digest))
                        else:
                            for digest in hashes:db.execute('DELETE FROM parked WHERE scope=? AND hash=?',(self.scope,digest))
                        state['undo']={'action':'disposition','table':'parked','post':post if action=='unsort' else None,'hashes':sorted(hashes),'previous':old}
                    state['selection']=[]
                elif action=='post_evidence':
                    ident=body.get('id');ignored=body.get('ignored')
                    if ident not in self.posts or not isinstance(ignored,bool):raise ValueError('Choose a post and a valid grouping setting.')
                    evidence=state.setdefault('post_evidence',{})
                    state['undo']={'action':'post_evidence','id':ident,'previous':evidence.get(ident)}
                    evidence[ident]=ignored
                elif action=='post':
                    ident=body.get('id');status=body.get('status')
                    if ident not in self.posts or status not in ('pending','reviewed','deferred'):raise ValueError('Invalid post status.')
                    old=db.execute('SELECT status FROM posts WHERE scope=? AND id=?',(self.scope,ident)).fetchone()
                    state['undo']={'action':'post','id':ident,'previous':old[0] if old else None}
                    db.execute('INSERT OR REPLACE INTO posts VALUES (?,?,?)',(self.scope,ident,status))
                elif action=='reject':
                    ids=self.valid_ids(body.get('ids',[]));context=str(body.get('context',''))
                    if not context or len(context)>200:raise ValueError('Invalid suggestion context.')
                    for ident in ids:db.execute('INSERT OR IGNORE INTO rejected VALUES (?,?,?)',(self.scope,context,ident))
                    state['undo']={'action':'reject','context':context,'ids':ids}
                elif action=='undo':
                    undo=state.pop('undo',None)
                    if not undo:raise ValueError('No organizer action to undo.')
                    if undo['action']=='set':
                        db.execute('DELETE FROM sets WHERE scope=? AND id=?',(self.scope,undo['id']))
                        if undo['previous']:db.execute('INSERT INTO sets VALUES (?,?,?)',(self.scope,undo['id'],undo['previous']))
                        for sid,raw in undo.get('moved',{}).items():
                            db.execute('DELETE FROM sets WHERE scope=? AND id=?',(self.scope,sid))
                            if raw:db.execute('INSERT INTO sets VALUES (?,?,?)',(self.scope,sid,raw))
                        state['selection']=undo.get('selection',[])
                    elif undo['action']=='individuals':
                        for key,raw in undo['previous'].items():
                            db.execute('DELETE FROM individual_imports WHERE scope=? AND sha=?',(self.scope,key))
                            if raw:db.execute('INSERT INTO individual_imports VALUES (?,?,?)',(self.scope,key,raw))
                        state['selection']=undo.get('selection',[])
                    elif undo['action']=='disposition':
                        table=undo['table']
                        if table=='discarded':
                            for digest in undo['hashes']:db.execute('DELETE FROM discarded WHERE hash=?',(digest,))
                            db.executemany('INSERT OR REPLACE INTO discarded VALUES (?,?,?)',undo['previous'])
                        else:
                            for digest in undo['hashes']:
                                if undo.get('post'):db.execute('DELETE FROM parked WHERE scope=? AND post=? AND hash=?',(self.scope,undo['post'],digest))
                                else:db.execute('DELETE FROM parked WHERE scope=? AND hash=?',(self.scope,digest))
                            db.executemany('INSERT OR REPLACE INTO parked VALUES (?,?,?)',undo['previous'])
                    elif undo['action']=='post_evidence':
                        evidence=state.setdefault('post_evidence',{})
                        if undo['previous'] is None:evidence.pop(undo['id'],None)
                        else:evidence[undo['id']]=undo['previous']
                    elif undo['action']=='post':
                        db.execute('DELETE FROM posts WHERE scope=? AND id=?',(self.scope,undo['id']))
                        if undo['previous']:db.execute('INSERT INTO posts VALUES (?,?,?)',(self.scope,undo['id'],undo['previous']))
                    elif undo['action']=='reject':
                        for ident in undo['ids']:db.execute('DELETE FROM rejected WHERE scope=? AND context=? AND id=?',(self.scope,undo['context'],ident))
                else:raise ValueError('Unknown organizer action.')
                if action=='undo':
                    history=state.get('undo_stack',[])
                    if history:state['undo']=history.pop()
                elif action!='pin' and previous_undo and state.get('undo')!=previous_undo:
                    state['undo_stack']=(state.get('undo_stack',[])+[previous_undo])[-19:]
                state['revision']=state.get('revision',0)+1;self.put_state(db,state)
            self.load_dispositions()
            return self.summary()

    def index(self,only=None):
        with self.lock,self.bulk.lock:
            self.bind()
            if self.job['running'] or self.engine.status['running'] or (self.bulk.current or {}).get('running'):raise ValueError('Wait for the current operation.')
            todo=[copy.copy(r) for i,r in self.catalog.items() if not r.get('quarantine_only') and i not in self.vector_by_id and i not in self.discarded]
            if only is not None:
                requested=set(self.valid_ids(only));todo=[r for r in todo if r['id'] in requested]
            if not todo:return dict(self.job)|{'phase':'All saved images already indexed','remaining':0}
            self.cancel.clear();self.job={'running':True,'phase':'Preparing visual matching','done':0,'total':len(todo),'eta_seconds':None,'elapsed_seconds':0,'reused':len(self.vector_by_id),'issues':[]}
            self.thread=threading.Thread(target=self.run_index,args=(todo,),daemon=True);self.thread.start();return dict(self.job)

    def run_index(self,todo):
        owner=self;base=self.model();started=time.monotonic()
        class Encoder(base):
            stage_started=time.monotonic()
            stage_done=0
            def update(self,ident,**fields):
                with owner.lock:
                    if 'phase' in fields and fields['phase']!=owner.job['phase']:
                        self.stage_started=time.monotonic();self.stage_done=0
                        owner.job.update(done=0,total=fields.get('total',0),eta_seconds=None)
                    owner.job.update({k:v for k,v in fields.items() if k in ('phase','done','total')})
                    elapsed=time.monotonic()-self.stage_started;done=owner.job['done'];total=owner.job['total']
                    owner.job.update(elapsed_seconds=round(elapsed),eta_seconds=round(elapsed/done*max(0,total-done)) if done and total else None)
            def _check_cancel(self,ident):
                if owner.cancel.is_set():raise InterruptedError('Paused. Completed visual analysis is saved.')
        encoder=Encoder(SimpleNamespace(root=Path((self.bulk.current or {}).get('model_root') or self.engine.state_dir/'bulk-models'),_hash_file=sha256))
        try:
            encoder._prepare('organizer');encoder._prepare_scene('organizer');started=time.monotonic()
            with self.lock:self.job.update(phase='Analyzing missing images',done=0,total=len(todo),elapsed_seconds=0,eta_seconds=None)
            for at,item in enumerate(todo):
                encoder._check_cancel('organizer')
                try:
                    path=Path(item['path'])
                    if linked(path) or (stat_key(path)!=item['stamp'] and not self.engine.recovered_original(item)):raise ValueError('File changed since the saved inventory.')
                    search_path=Path(item.get('matching_frame_path') or path)
                    value=np.concatenate((encoder._encode(search_path),encoder._encode_scene(search_path).reshape(-1))).astype(np.float32)
                    if value.size!=2304 or not np.isfinite(value).all():raise ValueError('Invalid visual analysis')
                    if stat_key(path)!=item['stamp'] and not self.engine.recovered_original(item):raise ValueError('File changed during analysis.')
                    with self.bulk.db() as db:db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?)',(item.get('analysis_sha',item['sha']),self.recipe,value.tobytes()))
                except InterruptedError:raise
                except Exception as e:
                    with self.lock:self.job['issues'].append({'path':item['path'],'message':str(e)})
                elapsed=time.monotonic()-started
                with self.lock:self.job.update(phase='Analyzing missing images',done=at+1,elapsed_seconds=round(elapsed),eta_seconds=round(elapsed/(at+1)*(len(todo)-at-1)))
            with self.lock:self.job.update(phase='Visual analysis saved',eta_seconds=0)
        except Exception as e:
            with self.lock:self.job.update(phase=str(e),eta_seconds=None)
        finally:
            with self.lock:self.load_vectors();self.job['running']=False

    def original_path(self,ident):
        with self.lock,self.bulk.lock:
            self.bind();item=self.catalog.get(ident)
            if not item or item.get('media_type','image')!='image':raise ValueError('Choose an image from the saved inventory.')
            path=Path(item['path'])
            if linked(path) or (stat_key(path)!=item['stamp'] and not self.engine.recovered_original(item)):raise ValueError('Image changed or moved since inventory.')
            return path

    def preview(self,ident,size):
        with self.lock,self.bulk.lock:
            self.bind();item=self.catalog.get(ident)
            if not item:raise ValueError('Image is not in the saved inventory.')
            path=Path(item['path']);stamp=stat_key(path)
            if linked(path) or (stamp!=item['stamp'] and not self.engine.recovered_original(item)):raise ValueError('Image changed or moved since inventory.')
            size=min(2400,max(240,int(size)))
            key=hashlib.sha256((item.get('analysis_sha',item['sha'])+':'+stamp+':'+str(size)+':preview-v1').encode()).hexdigest()
            path=Path(item.get('matching_frame_path') or path)
        target=self.engine.state_dir/'organizer-thumbnails'/key[:2]/(key+'.jpg')
        if target.is_file():return target.read_bytes()
        im,_,_=load_image(path,size);out=io.BytesIO();im.save(out,format='JPEG',quality=94)
        data=out.getvalue();target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name(key+'.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(data);temp.replace(target)
        return data

    def export(self,include_tracking=True):
        with self.lock,self.bulk.lock:
            self.bind();summary=self.summary()
            with self.db() as db:
                dispositions={'discarded':[list(r) for r in db.execute('SELECT hash,batch,data FROM discarded')],'parked':[list(r) for r in db.execute('SELECT scope,post,hash FROM parked WHERE scope=?',(self.scope,))]}
            return {'tracking':tracking.export_history(self.engine,self.bulk,self) if include_tracking else None,'format':'folder-organizer-2','collection_id':self.collection_id,'dispositions':dispositions,'source_job':self.bound[0],'config':(self.bulk.current or {}).get('config',{}),'sets':summary['sets'],'individuals':self.individual_imports(include_applied=True),'state':summary['state'],'category_catalog':summary['category_catalog'],
                    'post_review':[{k:p[k] for k in ('id','status')} for p in summary['posts']],'source_catalog':self.catalog,
                    'notice':'Local set drafts and individual import choices; source files stay in place.'}

    def transfer(self,action,body):
        with self.lock,self.bulk.lock:
            self.bind()
            if body.get('job')!=self.bound[0]:raise ValueError('Collection changed. Preview again.')
            if self.job['running'] or self.engine.status['running'] or (self.bulk.current or {}).get('running'):
                raise ValueError('Pause analysis before applying drafts.')
            if action=='preview':
                library=self.engine.library.request('/api/library')
                owner=str(body.get('character_id') or self.category_catalog().get('character_id') or (self.bulk.current or {}).get('config',{}).get('character_id') or '')
                if not owner:
                    owners={r['character_id'] for r in self.individual_imports()}
                    if len(owners)==1:owner=owners.pop()
                if not owner and len(library.get('characters',[]))==1:owner=library['characters'][0]['id']
                if not owner:return {'choose_character':[{'id':c['id'],'name':c['name']} for c in library.get('characters',[])]}
                draft=self.export(include_tracking=False);draft['scope']=self.scope
                draft['sets']=[g for g in draft['sets'] if g.get('saved')] if body.get('include_sets',True) else []
                draft['individuals']=self.individual_imports() if body.get('include_individuals',True) else []
                if any(not r['id'] for r in draft['individuals']):raise ValueError('A queued image is unavailable or discarded. Restore it or remove it from the import queue before applying.')
                if len({r['id'] for r in draft['individuals']})!=len(draft['individuals']):raise ValueError('Queued copies now share a keeper. Select that image and save its import choices again to combine them.')
                wanted={i for g in draft['sets'] for i in g['members']+g.get('removed_members',[])}|{r['id'] for r in draft['individuals']}
                draft['source_catalog']={i:r for i,r in self.catalog.items() if i in wanted}
                result=self.engine.library.request('/api/organizer/preview',{'character_id':owner,'draft':draft})
                if draft['individuals'] and 'individuals' not in result:raise ValueError('Update the Media Library companion to use individual Workbench imports. Nothing has been imported.')
                if (any(g.get('purgatory_edited') for g in draft['sets']) or draft['state'].get('duplicate_choices')) and 'duplicates' not in result:raise ValueError('Update and restart the companion to apply Set Purgatory and duplicate choices. Nothing has been imported.')
                self.transfer_plan={'token':result['token'],'revision':self.state()['revision'],'scope':self.scope,'individuals':draft['individuals']}
                return result
            plan=getattr(self,'transfer_plan',{})
            if plan.get('token')!=body.get('token') or plan.get('scope')!=self.scope or plan.get('revision')!=self.state()['revision']:
                raise ValueError('Drafts changed. Preview again to resume safely.')
            if action=='import':return self.engine.library.request('/api/organizer/import',{'token':body['token'],'id':body.get('id')})
            if action!='apply':raise ValueError('Unknown transfer action.')
            tracking.transfer(self.engine,self.bulk,self)
            result=self.engine.library.request('/api/organizer/apply',{'token':body['token'],'conflicts':body.get('conflicts','move')})
            with self.db() as db:
                for row in plan.get('individuals',[]):
                    outcome=result.get('individuals',{}).get(row['id'])
                    if not outcome:continue
                    saved={**row,'applied_at':time.time(),'library_id':outcome['id'],'outcome':outcome}
                    db.execute('UPDATE individual_imports SET data=? WHERE scope=? AND sha=?',(json.dumps(saved),self.scope,row['key']))
                for ident,sid in result['mapping'].items():
                    row=db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.scope,ident)).fetchone()
                    if not row:continue
                    group=json.loads(row[0]);group['library_id']=sid;group['applied_at']=time.time();group['purgatory_edited']=False;group['applied_partial']=bool(result.get('skipped'))
                    db.execute('UPDATE sets SET data=? WHERE scope=? AND id=?',(json.dumps(group),self.scope,ident))
            result['library_url']=self.engine.library.base+'/library'
            return result

    def missing_file_records(self):
        with self.lock,self.bulk.lock:
            if self.engine.status['running'] or self.job['running'] or (self.bulk.current or {}).get('running'):
                raise ValueError('Pause scanning and analysis before checking original files.')
            self.bind()
            return [{'id':self.scope+':'+i,'name':Path(r['path']).name,'collection':str((self.bulk.current or {}).get('id','')),
                     'path':r['path'],'sha256':r.get('sha',''),'bytes':None}
                    for i,r in self.catalog.items() if not r.get('quarantine_only') and i not in self.discarded]

    def file_finder(self):
        if not hasattr(self,'_file_finder'):
            self._file_finder=runtime_helpers()['MissingFileFinder'](self.missing_file_records,self.lock,self.engine.authorize_original_recovery)
        return self._file_finder

    def video_queue(self):
        from bulk.sources import source_of
        with self.lock,self.bulk.lock:
            self.bind();roots=(self.bulk.current or {}).get('config',{}).get('roots',[])
            self.video_files={};rows=[];assigned={i for g in self.sets().values() for i in g['members']}
            references={r['path']:r for r in self.catalog.values() if r.get('media_type')=='video'}
            for root in roots:
                folder=Path(root)
                if not folder.is_dir() or linked(folder):continue
                for path in folder.rglob('*'):
                    if path.suffix.lower() not in ('.mp4','.webm','.mov','.mkv','.m4v','.avi') or not path.is_file() or linked(path):continue
                    if any('_Duplicate_Review_Quarantine'==p for p in path.parts):continue
                    key=hashlib.sha256(str(path).encode()).hexdigest();self.video_files[key]=path
                    record=references.get(str(path));source=source_of(str(path))
                    rows.append({'id':key,'name':path.name,'source':source.get('label',''),'frame_seconds':record.get('frame_seconds') if record else None,
                        'assigned':bool(record and record['id'] in assigned)})
                    if len(rows)>=10000:break
            return {'videos':sorted(rows,key=lambda r:(r['assigned'],natural(r['name'])))}

    def video_action(self,action,body):
        with self.lock,self.bulk.lock:
            self.bind()
            if body.get('job')!=(self.bulk.current or {}).get('id'):raise ValueError('Collection changed. Reopen videos.')
            if self.job['running']:raise ValueError('Pause analysis before changing its reference frames.')
            path=getattr(self,'video_files',{}).get(str(body.get('id')))
            if not path or not path.is_file() or linked(path):raise ValueError('Video unavailable. Refresh the video queue.')
            scope=self.scope;stamp=stat_key(path)
        result=runtime_helpers()['video_frame_data'](path,body.get('seconds',0),self.engine.state_dir/'video-tools',int(body.get('direction',0)),capture=action=='frame')
        if action=='step':return result
        if action!='frame':raise ValueError('Unknown video action.')
        from bulk.sources import source_of
        digest=sha256(path);frame_sha=hashlib.sha256(result['image']).hexdigest();frame=self.engine.state_dir/'video-frames'/(frame_sha+'.jpg');frame.parent.mkdir(exist_ok=True);frame.write_bytes(result['image'])
        with self.lock,self.bulk.lock:
            if self.scope!=scope or stat_key(path)!=stamp:raise ValueError('Video or collection changed. Select the frame again.')
            source=source_of(str(path));ident='video:'+digest
            record={'id':ident,'sha':digest,'analysis_sha':frame_sha,'path':str(path),'stamp':stamp,'media_type':'video',
                'matching_frame_path':str(frame),'frame_seconds':result['seconds'],'origins':[source],'sources':{source['key']:source},'copies':[],'reference':False,'existing_sets':[]}
            with self.db() as db:db.execute('INSERT OR REPLACE INTO video_references VALUES (?,?,?)',(scope,digest,json.dumps(record)))
            self.bound=None;self.bind();state=self.state();state['suggestion_reference']=ident
            with self.db() as db:self.put_state(db,state)
            return {'id':ident,'seconds':result['seconds'],'state':self.summary()}
