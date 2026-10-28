"""Folder-first review over a saved inventory. No automatic scans or file moves."""
from __future__ import annotations
import copy, hashlib, io, json, re, runpy, sqlite3, threading, time, uuid
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from engine import load_image, sha256, stat_key, linked


@lru_cache(maxsize=1)
def runtime_helpers():
    # The same runtime ships with both apps; share the actual saved-label rules.
    return runpy.run_path(str(Path(__file__).resolve().parents[1]/'runtime-src'/'companion-runtime.pyw'))


def title_case_label(value):
    return runtime_helpers()['title_case_label'](value)


def natural(value):
    return tuple((1,int(x)) if x.isdigit() else (0,x.casefold()) for x in re.split(r'(\d+)',str(value)))


class Organizer:
    def __init__(self, engine, bulk):
        self.engine=engine;self.bulk=bulk;self.path=engine.state_dir/'organizer.sqlite3'
        self.lock=threading.RLock();self.cancel=threading.Event();self.thread=None
        self.job={'running':False,'phase':'Saved inventory ready','done':0,'total':0,'eta_seconds':None}
        self.bound=None;self.catalog={};self.posts={};self.order_cache={};self.vector_by_id={};self.quick={}
        self.encoder_type=None;self.recipe=None;self.scope='';self.revision=0;self.discarded=set();self.parked={}
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS state(scope TEXT PRIMARY KEY,data TEXT);
                CREATE TABLE IF NOT EXISTS category_catalog(scope TEXT PRIMARY KEY,data TEXT);
                CREATE TABLE IF NOT EXISTS sets(scope TEXT,id TEXT,data TEXT,PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS posts(scope TEXT,id TEXT,status TEXT,PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS rejected(scope TEXT,context TEXT,id TEXT,PRIMARY KEY(scope,context,id));
                CREATE TABLE IF NOT EXISTS discarded(hash TEXT PRIMARY KEY,batch TEXT,data TEXT);
                CREATE TABLE IF NOT EXISTS parked(scope TEXT,post TEXT,hash TEXT,PRIMARY KEY(scope,post,hash));''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30)
        try:
            with db:yield db
        finally:db.close()

    def bind(self):
        current=self.bulk.current or {};cat=current.get('source_catalog',{})
        key=(current.get('id'),len(cat))
        if self.bound==key:return
        if self.job['running']:return
        self.bound=key;self.catalog=cat;self.posts={};self.order_cache={}
        self.scope=hashlib.sha256(json.dumps(current.get('config',{}).get('roots',[]),sort_keys=True).encode()).hexdigest()
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
            raw=rows.get(item['sha'])
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
            result['library:'+sid]={'id':'library:'+sid,'name':g['name'],'colors':g.get('colors') or [],'categories':g.get('categories') or [],'members':[], 'library_id':sid,'saved':False}
        for ident,item in self.catalog.items():
            if item.get('quarantine_only'):continue
            for sid in item.get('existing_sets',[]):
                if 'library:'+sid in result:result['library:'+sid]['members'].append(ident)
        with self.db() as db:
            for sid,raw in db.execute('SELECT id,data FROM sets WHERE scope=?',(self.scope,)):
                g=json.loads(raw)
                g.setdefault('colors',result.get(sid,{}).get('colors',[]))
                g.setdefault('categories',result.get(sid,{}).get('categories',[]))
                # Existing library members remain visible alongside locally reviewed additions.
                g['members']=list(dict.fromkeys(result.get(sid,{}).get('members',[])+g['members']))
                g['saved']=True;result[sid]=g
        if not include_discarded:
            for g in result.values():g['members']=[i for i in g['members'] if i in self.catalog and i not in self.discarded]
        return result

    def summary(self):
        with self.lock,self.bulk.lock:
            self.bind();state=self.state();state['selection']=[i for i in state.get('selection',[]) if i in self.catalog and i not in self.discarded];sets=self.sets();assigned={i for g in sets.values() for i in g['members']}
            with self.db() as db:statuses=dict(db.execute('SELECT id,status FROM posts WHERE scope=?',(self.scope,)))
            posts=[]
            for p in self.posts.values():
                visible=self.post_ids(p['id']);live=[i for i in visible if not self.catalog[i].get('quarantine_only')]
                posts.append({k:v for k,v in p.items() if k!='ids'}|{'count':len(visible),'remaining':sum(i not in assigned for i in live),'unresolved':len(visible)-len(live),'status':statuses.get(p['id'],'pending'),'mixed':self.is_mixed(p['id'],state.get('post_evidence',{})),'large':len(p['ids'])>=1000,'source_count':len(p['ids']),'cover':next(iter(live or visible),None)})
            posts.sort(key=lambda p:(p['status']!='pending',p['remaining']==0,natural(p['label'])))
            total=sum(not r.get('quarantine_only') and i not in self.discarded for i,r in self.catalog.items())
            return {'job':(self.bulk.current or {}).get('id'),'posts':posts,'sets':[dict(g,count=len(g['members'])) for g in sets.values()],
                'category_catalog':self.category_catalog(),'state':state,'images':total,'unresolved':sum(bool(r.get('quarantine_only')) for i,r in self.catalog.items() if i not in self.discarded),'indexed':sum(i in self.vector_by_id for i,r in self.catalog.items() if not r.get('quarantine_only') and i not in self.discarded),
                'unsorted_count':len(self.unsorted_ids()),'discarded_count':sum(not self.catalog[i].get('quarantine_only') for i in self.discarded),
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

    def image(self,ident):
        r=self.catalog[ident]
        return {'id':ident,'name':re.split(r'[\\/]',r['path'])[-1],'path':r['path'],'quarantined':bool(r.get('quarantine_only')),
                'sources':list(r.get('sources',{})),'origins':r.get('origins',[]),'reference':bool(r.get('reference')),'discarded':ident in self.discarded}

    def page(self,kind,ident,offset=0,order='similar',remember=True,focus_id=None):
        with self.lock,self.bulk.lock:
            self.bind()
            if kind=='post':
                group=self.posts.get(ident)
                ids=self.post_ids(ident) if group else []
            elif kind=='set':
                group=self.sets().get(ident);ids=group.get('members',[]) if group else []
            elif kind=='unsorted':group={'label':'Unsorted'};ids=self.unsorted_ids()
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

    def related(self,body):
        with self.lock,self.bulk.lock:
            self.bind();selection=self.valid_ids(body.get('ids',[]));allsets=self.sets()
            members=allsets.get(str(body.get('target','')),{}).get('members',[])
            seeds=list(dict.fromkeys([i for i in members if i not in selection]+selection))
            context=self.context_key(body,seeds)
            if not seeds:return {'images':[],'posts':[],'sets':[],'total':0}
            evidence=self.state().get('post_evidence',{})
            visual=self.scores(seeds);selected=set(seeds);sources={s for i in seeds for s in self.catalog[i]['sources'] if s in self.posts and not self.is_mixed(s,evidence)}
            with self.db() as db:rejected={r[0] for r in db.execute('SELECT id FROM rejected WHERE scope=? AND context=?',(self.scope,context))}
            ranked=[]
            for ident,item in self.catalog.items():
                if ident in selected or ident in rejected or ident in self.discarded or item.get('quarantine_only'):continue
                shared=sources & item['sources'].keys();v=visual.get(ident,0)
                if not shared and v<.60:continue
                source_score=sum(1/(max(1,len(self.posts[s]['ids']))**.5) for s in shared)
                score=min(.35,.3*source_score)+v
                ranked.append((score,ident,'Shared source post'+(' · visually similar' if v>=.60 else '') if shared else 'Visually similar'))
            ranked.sort(key=lambda r:(-r[0],r[1]));offset=max(0,int(body.get('offset',0)));sets=[];labels={}
            for g in allsets.values():
                members=set(g['members']);overlap=len(selected & members)
                for i in members:labels.setdefault(i,[]).append(g['name'])
                shared=len(sources & {s for i in members if i in self.catalog for s in self.catalog[i]['sources']})
                v=max((visual.get(i,0) for i in members),default=0)
                if overlap or shared or v>=.60:sets.append({'id':g['id'],'name':g['name'],'count':len(members),'overlap':overlap,'score':overlap*10+bool(shared)+v,'library':bool(g.get('library_id'))})
            sets.sort(key=lambda g:(-g['score'],g['name']))
            posts=[{'id':s,'label':self.posts[s]['label'],'count':len(self.posts[s]['ids']),'shared':sum(s in self.catalog[i]['sources'] for i in seeds),'anchor_id':next(i for i in reversed(seeds) if s in self.catalog[i]['sources'])} for s in sources]
            posts.sort(key=lambda p:(-p['shared'],p['count'],p['label']))
            return {'context':context,'images':[self.image(i)|{'reason':reason,'sets':labels.get(i,[])} for _,i,reason in ranked[offset:offset+30]],'total':len(ranked),'offset':offset,'sets':sets[:12],'posts':posts}

    def valid_ids(self,ids):
        if not isinstance(ids,list) or len(ids)>15000:raise ValueError('Invalid selection.')
        ids=list(dict.fromkeys(ids))
        if any(i not in self.catalog or self.catalog[i].get('quarantine_only') or i in self.discarded for i in ids):raise ValueError('Select surviving images only. Quarantine remains evidence only.')
        return ids

    def context_key(self,body,ids):
        target=body.get('target')
        return str(target) if target else hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()

    @staticmethod
    def colors(value):
        # Same descriptor format and limits as the media library's Set details.
        if not isinstance(value,list) or len(value)>50 or any(not isinstance(v,str) or len(v)>150 for v in value):
            raise ValueError('Invalid Set colors (up to 50 descriptors, 150 characters each).')
        return list(dict.fromkeys(title_case_label(v) for v in value if v.strip()))

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

    def mutate(self,action,body):
        with self.lock,self.bulk.lock:
            self.bind()
            if body.get('job')!=self.bound[0]:raise ValueError('Inventory changed. Reopen the organizer.')
            state=self.state()
            if action=='draft':
                state['selection']=self.valid_ids(body.get('ids',[]));state['target']=str(body.get('target',''))
                if 'new_colors' in body:state['new_colors']=self.colors(body['new_colors'])
                if 'new_categories' in body:state['new_categories']=self.categories(body['new_categories'],state.get('new_categories',[]))
                with self.db() as db:self.put_state(db,state)
                return {'saved':True}
            if int(body.get('revision',-1))!=state.get('revision',0):raise ValueError('Review changed in another window. Reload before saving.')
            with self.db() as db:
                if action=='save':
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
                    members=list(dict.fromkeys((previous or {}).get('members',[])+ids))
                    colors=self.colors(body.get('colors',(previous or {}).get('colors',state.get('new_colors',[]))))
                    categories=self.categories(body.get('categories',(previous or {}).get('categories',state.get('new_categories',[]))),(previous or {}).get('categories',[]))
                    stamp=time.time()
                    group=dict(previous or {},id=ident,name=name,colors=colors,categories=categories,members=members,updated=stamp,library_id=(previous or {}).get('library_id'))
                    if previous is None:group['created']=stamp
                    db.execute('INSERT OR REPLACE INTO sets VALUES (?,?,?)',(self.scope,ident,json.dumps(group)))
                    state.update(selection=[],target='',new_colors=[],new_categories=[])
                elif action in ('set_colors','set_details'):
                    target=str(body.get('target',''));group=self.sets(include_discarded=True).get(target)
                    if not group:raise ValueError('Choose an available set.')
                    colors=self.colors(body.get('colors',group.get('colors',[])))
                    categories=self.categories(body.get('categories',group.get('categories',[])),group.get('categories',[]))
                    old=db.execute('SELECT data FROM sets WHERE scope=? AND id=?',(self.scope,target)).fetchone()
                    state['undo']={'action':'set','id':target,'previous':old[0] if old else None,'selection':state.get('selection',[])}
                    group.update(colors=colors,categories=categories,updated=time.time())
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
                state['revision']=state.get('revision',0)+1;self.put_state(db,state)
            self.load_dispositions()
            return self.summary()

    def index(self):
        with self.lock,self.bulk.lock:
            self.bind()
            if self.job['running'] or self.engine.status['running'] or (self.bulk.current or {}).get('running'):raise ValueError('Wait for the current operation.')
            todo=[copy.copy(r) for i,r in self.catalog.items() if not r.get('quarantine_only') and i not in self.vector_by_id and i not in self.discarded]
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
                    if linked(path) or stat_key(path)!=item['stamp']:raise ValueError('File changed since the saved inventory.')
                    value=np.concatenate((encoder._encode(path),encoder._encode_scene(path).reshape(-1))).astype(np.float32)
                    if value.size!=2304 or not np.isfinite(value).all():raise ValueError('Invalid visual analysis')
                    if stat_key(path)!=item['stamp']:raise ValueError('File changed during analysis.')
                    with self.bulk.db() as db:db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?)',(item['sha'],self.recipe,value.tobytes()))
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

    def preview(self,ident,size):
        with self.lock,self.bulk.lock:
            self.bind();item=self.catalog.get(ident)
            if not item:raise ValueError('Image is not in the saved inventory.')
            path=Path(item['path']);stamp=stat_key(path)
            if linked(path) or stamp!=item['stamp']:raise ValueError('Image changed or moved since inventory.')
            size=min(2400,max(240,int(size)))
            key=hashlib.sha256((item['sha']+':'+stamp+':'+str(size)+':preview-v1').encode()).hexdigest()
        target=self.engine.state_dir/'organizer-thumbnails'/key[:2]/(key+'.jpg')
        if target.is_file():return target.read_bytes()
        im,_,_=load_image(path,size);out=io.BytesIO();im.save(out,format='JPEG',quality=94)
        data=out.getvalue();target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name(key+'.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(data);temp.replace(target)
        return data

    def export(self):
        with self.lock,self.bulk.lock:
            self.bind();summary=self.summary()
            with self.db() as db:
                dispositions={'discarded':[list(r) for r in db.execute('SELECT hash,batch,data FROM discarded')],'parked':[list(r) for r in db.execute('SELECT scope,post,hash FROM parked WHERE scope=?',(self.scope,))]}
            return {'format':'folder-organizer-2','dispositions':dispositions,'source_job':self.bound[0],'config':(self.bulk.current or {}).get('config',{}),'sets':summary['sets'],'state':summary['state'],'category_catalog':summary['category_catalog'],
                    'post_review':[{k:p[k] for k in ('id','status')} for p in summary['posts']],'source_catalog':self.catalog,
                    'notice':'Locally saved set drafts; no images moved, restored or imported.'}
