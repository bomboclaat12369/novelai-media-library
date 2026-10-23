"""Persistent, read-only bulk evaluation beside the existing duplicate reviewer.

The first release deliberately produces drafts, not library mutations. It measures
whether grouping is useful on the real collection before enabling bulk import.
"""
from __future__ import annotations
import copy
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import runpy
import sqlite3
import threading
import time
from types import SimpleNamespace
import uuid
from functools import lru_cache
import same_photo

import numpy as np
from engine import linked, sha256, stat_key, pixel_digest, QUARANTINE, BKTree
from .sources import source_of
from .grouping import propose, RECIPE

EXTENSIONS={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff','.avif','.gif'}


class Workbench:
    def __init__(self, engine, encoder_factory=None):
        self.engine=engine
        self.path=engine.state_dir/'bulk-preparation.sqlite3'
        self.lock=threading.RLock();self.cancel=threading.Event();self.thread=None
        self.encoder_factory=encoder_factory
        self.current=None
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, updated REAL, data TEXT);
                CREATE TABLE IF NOT EXISTS hashes(path TEXT PRIMARY KEY, stamp TEXT, sha TEXT, pixel TEXT);
                CREATE TABLE IF NOT EXISTS vectors(sha TEXT, recipe TEXT, data BLOB, PRIMARY KEY(sha,recipe));
                CREATE TABLE IF NOT EXISTS aliases(target TEXT, keeper TEXT, recipe TEXT, accepted INTEGER, PRIMARY KEY(target,keeper,recipe));''')
            row=db.execute('SELECT data FROM jobs ORDER BY updated DESC LIMIT 1').fetchone()
        if row:
            self.current=json.loads(row[0])
            if self.current['running']:
                self.current.update(running=False,phase='Interrupted. Start again to reuse cached work.',interrupted=True)
                self.persist()

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30)
        db.execute('PRAGMA journal_mode=WAL')
        try:
            with db:yield db
        finally:db.close()

    def persist(self):
        with self.lock,self.db() as db:
            if self.current:
                db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)',(self.current['id'],time.time(),json.dumps(self.current)))

    def update(self,**fields):
        with self.lock:
            self.current.update(fields)

    def check(self):
        if self.cancel.is_set():raise InterruptedError('Stopped. Restart with the same settings to reuse cached work.')

    def status(self):
        with self.lock:
            if not self.current:return {'running':False,'phase':'Ready for a local evaluation','groups':[], 'jobs':self.jobs()}
            out={k:copy.deepcopy(v) for k,v in self.current.items() if k not in ('items','proposals','unassigned','duplicate_families')}
            out['groups']=[{k:v for k,v in g.items() if k not in ('members','original_members','sources','evidence')}|{'count':len(g['members'])} for g in self.current.get('proposals',[])]
            reviews=[g for g in self.current.get('proposals',[]) if g.get('review')=='accepted']
            out['evaluation']={'accepted':len(reviews),'unchanged':sum(set(g['members'])==set(g['original_members']) for g in reviews),
                               'edited':sum(set(g['members'])!=set(g['original_members']) for g in reviews),
                               'skipped':sum(g.get('review')=='skipped' for g in self.current.get('proposals',[])),
                               'splits':self.current.get('splits',0),
                               'unassigned':len(self.current.get('unassigned',[]))}
            out['jobs']=self.jobs()
            return out

    def jobs(self):
        with self.db() as db:
            rows=db.execute('SELECT id,updated FROM jobs ORDER BY updated DESC LIMIT 12').fetchall()
        return [{'id':r[0],'at':r[1]} for r in rows]

    def activate(self,ident):
        with self.lock:
            if self.current and self.current['running']:raise ValueError('Stop the current scan first.')
            with self.db() as db:row=db.execute('SELECT data FROM jobs WHERE id=?',(ident,)).fetchone()
            if not row:raise ValueError('Evaluation not found.')
            self.current=json.loads(row[0]);self.current['running']=False
            return self.status()

    def context(self):
        result={'characters':[], 'connected':False}
        try:
            library=self.engine.library.request('/api/library')
            result.update(connected=True,characters=[{k:c.get(k,[] if k=='set_categories' else '') for k in ('id','name','set_categories')} for c in library['characters']])
        except ValueError as e:result['connection_note']=str(e)
        result['config']=self.current.get('config',{}) if self.current else {}
        return result

    def start(self,body):
        with self.engine.lock,self.lock:
            if self.engine.status['running'] or (self.current and self.current['running']):raise ValueError('Wait for the current scan or file operation to finish.')
            roots=[]
            for raw in body.get('roots',[]):
                p=Path(str(raw)).expanduser()
                if not p.is_dir() or linked(p):raise ValueError('Choose ordinary image folders, not links: '+str(p))
                roots.append(str(p.resolve()))
            if not roots or len(roots)>20:raise ValueError('Choose 1–20 source folders.')
            limit=int(body.get('limit',400))
            if limit not in (200,400,1000,0):raise ValueError('Choose a supported evaluation size.')
            forum=str(body.get('forum','smg')).strip().casefold()
            if not forum or len(forum)>80:raise ValueError('Give the source forum a short unique label.')
            config={'roots':list(dict.fromkeys(roots)), 'limit':limit, 'forum':forum,
                    'person':str(body.get('person','Collection'))[:120], 'character_id':str(body.get('character_id',''))}
            self.current={'id':uuid.uuid4().hex,'config':config,'recipe':RECIPE,'running':True,'phase':'Inventorying original and quarantined files',
                          'done':0,'total':0,'issues':[],'items':{},'proposals':[],'unassigned':[], 'created':time.time()}
            self.cancel.clear();self.persist()
            self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
            return self.status()

    def issue(self,path,message):
        with self.lock:self.current['issues'].append({'path':str(path),'message':str(message)})

    def inventory(self,config):
        seen=set();found=[]
        for root in config['roots']:
            for base,dirs,files in os.walk(root,followlinks=False):
                self.check()
                dirs[:]=sorted(d for d in dirs if not linked(Path(base)/d))
                for name in sorted(files):
                    path=Path(base)/name
                    if path.suffix.casefold() not in EXTENSIONS:continue
                    if linked(path):self.issue(path,'Linked image omitted');continue
                    path=path.resolve();key=str(path)
                    if key in seen:continue
                    seen.add(key)
                    source=source_of(key,config['forum'],config['person'])
                    found.append({'path':key,'source':source,'reference':False,'existing_sets':[]})
                self.update(done=len(found),phase='Inventorying files (including quarantine for source recovery)')
        self.current['library_sets']={}
        if config['character_id']:
            catalog=self.engine.library.catalog(config['character_id'])
            library=self.engine.library.request('/api/library')
            self.current['model_root']=catalog['root']
            memberships={}
            for group in library.get('sets',[]):
                if group.get('character_id')!=config['character_id'] or group.get('kind','set')!='set':continue
                self.current['library_sets'][group['id']]={k:group.get(k) for k in ('id','name','categories','colors')}
                for mid in group.get('media_ids',[]):memberships.setdefault(mid,[]).append(group['id'])
            for row in catalog['files']:
                key=str(Path(row['path']).resolve())
                if key in seen:
                    # Never classify an actual managed-library original as incoming.
                    prior=next(x for x in found if x['path']==key)
                    prior.update(reference=True,media_id=row['id'],existing_sets=memberships.get(row['id'],[]));continue
                seen.add(key)
                found.append({'path':key,'source':{'key':'library:'+row['id'],'kind':'library','label':'Media library','path':key,'quarantine':False},
                              'reference':True,'media_id':row['id'],'existing_sets':memberships.get(row['id'],[])})
        return found

    def identities(self,found):
        # Read only the compact identity columns, never the 8 GB analysis blobs.
        uri=self.engine.database.resolve().as_uri()+'?mode=ro'
        with closing(sqlite3.connect(uri,uri=True,timeout=30)) as old:
            cached={r[0]:r[1:] for r in old.execute('SELECT path,stamp,sha,pixel FROM cache')}
            moves={r[0]:r[1] for r in old.execute("SELECT dst,src FROM moves WHERE state='moved'")}
        hashed=[]
        with self.db() as db:
            for index,record in enumerate(found):
                self.check();path=Path(record['path'])
                try:
                    stamp=stat_key(path)
                    previous=db.execute('SELECT sha,pixel FROM hashes WHERE path=? AND stamp=?',(str(path),stamp)).fetchone()
                    origin=moves.get(str(path),str(path));known=cached.get(origin)
                    if previous: digest,pixel=previous
                    else:
                        digest=known[1] if known and known[0]==stamp else sha256(path,self.cancel)
                        pixel=known[2] if known and known[1]==digest else None
                        if not pixel:pixel=pixel_digest(path)
                        if stamp!=stat_key(path):raise ValueError('Image changed while being read')
                        db.execute('INSERT OR REPLACE INTO hashes VALUES (?,?,?,?)',(str(path),stamp,digest,pixel))
                    record.update(sha=digest,pixel=pixel,stamp=stamp)
                    hashed.append(record)
                except InterruptedError:raise
                except Exception as e:self.issue(path,e)
                if index%64==0:db.commit()
                self.update(phase='Recovering image identities and original posts',done=index+1,total=len(found))
        # Only exact bytes/pixels form equivalence classes. Broad dupe suggestions
        # and manually kept-both relations never become identity proof.
        families={}
        for record in hashed:
            families.setdefault(record['pixel'] or record['sha'],[]).append(record)
        active=[];unmatched={}
        for records in families.values():
            live=[r for r in records if not r['source']['quarantine']]
            if not live:
                for r in records:unmatched.setdefault(r['sha'],[]).append(r)
                continue
            live.sort(key=lambda r:(not r['reference'],r['path'].casefold()))
            first=live[0]
            sources={r['source']['key']:r['source'] for r in records}
            item={'id':first['sha'],'path':first['path'],'stamp':first['stamp'],'sha':first['sha'],
                  'sources':sources,'origins':[r['source'] for r in records],
                  'copies':[{'path':r['path'],'sha':r['sha'],'quarantine':r['source']['quarantine'],'reference':r['reference']} for r in records],
                  'reference':first['reference'],'existing_sets':sorted({s for r in records for s in r['existing_sets']})}
            active.append(item)
        # Recover directly verified visual-copy links only. No transitive chains,
        # no assumption that every quarantined image was discarded as a duplicate.
        live_sha={c['sha']:item for item in active for c in item['copies'] if not c['quarantine']}
        resolved=set()
        with closing(sqlite3.connect(uri,uri=True,timeout=30)) as old:
            for (key,) in old.execute('SELECT key FROM verified_copies WHERE accepted=1'):
                self.check();parts=key.split(':')
                if len(parts)!=3 or parts[0]!=same_photo.VERSION:continue
                target,keeper=parts[-2:]
                if target not in unmatched or keeper not in live_sha or target in resolved:continue
                item=live_sha[keeper]
                for r in unmatched[target]:
                    item['origins'].append(r['source']);item['sources'][r['source']['key']]=r['source']
                    item['copies'].append({'path':r['path'],'sha':r['sha'],'quarantine':True,'reference':False,'proof':'verified visual copy'})
                resolved.add(target)
        recovered=self.recover_visual_aliases(active,unmatched,resolved,uri)
        self.current['inventory']={'files':len(found),'readable':len(hashed),'unique_survivors':len(active),
            'quarantined_files':sum(r['source']['quarantine'] for r in hashed),
            'unlinked_quarantine':sum(len(v) for k,v in unmatched.items() if k not in resolved),
            'verified_visual_links':len(resolved),'newly_verified_links':recovered,'multiple_source_images':sum(len(i['sources'])>1 for i in active),
            'repeated_live_copies':sum(max(0,sum(not c['quarantine'] for c in i['copies'])-1) for i in active)}
        return active

    def recover_visual_aliases(self,active,unmatched,resolved,uri):
        remaining=[sha for sha in unmatched if sha not in resolved]
        if not remaining or not active:return 0
        # Use saved crop candidates and perceptual hashes to shortlist. Neither
        # is proof: every recovered association passes same-photo verification.
        with closing(sqlite3.connect(uri,uri=True,timeout=30)) as old:
            features={r[0]:(r[1],r[2]) for r in old.execute('SELECT sha,ph,mh FROM cache')}
            edges={}
            for a,b in old.execute('SELECT a.sha,b.sha FROM pairs p JOIN files a ON a.id=p.a JOIN files b ON b.id=p.b'):
                edges.setdefault(a,set()).add(b);edges.setdefault(b,set()).add(a)
            separated={tuple(r) for r in old.execute('SELECT a,b FROM separations')}
        live={c['sha']:i for i,item in enumerate(active) for c in item['copies'] if not c['quarantine']}
        trees=[BKTree(),BKTree()]
        for i,item in enumerate(active):
            self.check()
            pair=next((features[c['sha']] for c in item['copies'] if c['sha'] in features),None)
            if pair:
                for tree,value in zip(trees,pair):tree.add(int(value),i)
        @lru_cache(maxsize=12)
        def prepared(path):return same_photo.prepare(Path(path))
        recovered=0
        with self.db() as db:
            for at,digest in enumerate(remaining):
                self.check();records=unmatched[digest];neighbors=edges.get(digest,set())
                candidates={live[s] for s in neighbors if s in live}
                # Walking saved candidates is only discovery, never a transitive
                # duplicate claim. This recovers a moved former representative.
                for s in neighbors:
                    candidates.update(live[t] for t in edges.get(s,()) if t in live)
                pair=features.get(digest)
                if pair:
                    for tree,value in zip(trees,pair):candidates.update(tree.query(int(value),12))
                def order(i):
                    other=features.get(active[i]['sha'])
                    return min((int(a)^int(b)).bit_count() for a,b in zip(pair,other)) if pair and other else 100
                for i in sorted(candidates,key=lambda i:(order(i),active[i]['sha']))[:8]:
                    self.check();item=active[i]
                    if tuple(sorted((digest,item['sha']))) in separated:continue
                    saved=db.execute('SELECT accepted FROM aliases WHERE target=? AND keeper=? AND recipe=?',(digest,item['sha'],same_photo.VERSION)).fetchone()
                    try:
                        if saved is None:
                            # Never associate a changed source with its old digest.
                            if any(stat_key(Path(r['path']))!=r['stamp'] for r in records) or stat_key(Path(item['path']))!=item['stamp']:raise ValueError('File changed during source reconstruction')
                            accepted=bool(same_photo.verify(prepared(records[0]['path']),prepared(item['path'])))
                            db.execute('INSERT OR REPLACE INTO aliases VALUES (?,?,?,?)',(digest,item['sha'],same_photo.VERSION,int(accepted)));db.commit()
                        else:accepted=bool(saved[0])
                    except InterruptedError:raise
                    except Exception as e:self.issue(records[0]['path'],'Source recovery: '+str(e));continue
                    if not accepted:continue
                    for r in records:
                        item['origins'].append(r['source']);item['sources'][r['source']['key']]=r['source']
                        item['copies'].append({'path':r['path'],'sha':r['sha'],'quarantine':True,'reference':False,'proof':'reverified visual copy'})
                    resolved.add(digest);recovered+=1;break
                self.update(phase='Verifying missing source links against surviving copies',done=at+1,total=len(remaining))
        prepared.cache_clear()
        return recovered

    def sample(self,items,limit):
        incoming=[i for i in items if not i['reference']]
        if not limit or len(incoming)<=limit:return items
        # Distribute seeds across sources instead of taking the first directory.
        by_source={}
        for item in incoming:
            for key in item['sources']:by_source.setdefault(key,[]).append(item)
        selected={}
        for key in sorted(by_source,key=lambda k:hashlib.sha256(k.encode()).hexdigest()):
            group=by_source[key]
            if selected and len(selected)+sum(i['id'] not in selected for i in group)>limit:continue
            for item in group[:max(limit,200)]:selected[item['id']]=item
            if len(selected)>=limit:break
        if len(selected)<limit:
            for item in sorted(incoming,key=lambda i:i['id']):
                selected.setdefault(item['id'],item)
                if len(selected)>=limit:break
        return list(selected.values())+[i for i in items if i['reference']]

    def encoder(self):
        if self.encoder_factory:return self.encoder_factory(self)
        source=Path(__file__).resolve().parents[2]/'runtime-src'/'companion-runtime.pyw'
        if not source.is_file():raise ValueError('Extract the complete repository ZIP, including runtime-src, then run the duplicate-review launcher.')
        base=runpy.run_path(str(source))['OutfitMatcher'];work=self
        class LocalEncoder(base):
            def update(self,ident,**fields):work.update(**fields)
            def _check_cancel(self,ident):work.check()
        store=SimpleNamespace(root=Path(self.current.get('model_root') or self.engine.state_dir/'bulk-models'),_hash_file=sha256)
        enc=LocalEncoder(store);enc._prepare('bulk');enc._prepare_scene('bulk')
        return enc

    def encode(self,items):
        enc=self.encoder();recipe=enc.MODEL_SHA+':'+enc.SCENE_RECIPE
        kept=[];outfits=[];scenes=[];hits=0
        with self.db() as db:
            for at,item in enumerate(items):
                self.check()
                try:
                    path=Path(item['path'])
                    if linked(path) or stat_key(path)!=item['stamp']:raise ValueError('File changed after inventory; scan again')
                    row=db.execute('SELECT data FROM vectors WHERE sha=? AND recipe=?',(item['sha'],recipe)).fetchone()
                    value=np.frombuffer(row[0],dtype=np.float32).copy() if row else np.array([])
                    if value.size==2304 and np.isfinite(value).all():hits+=1
                    else:
                        value=np.concatenate((enc._encode(path),enc._encode_scene(path).reshape(-1))).astype(np.float32)
                        if value.size!=2304 or not np.isfinite(value).all():raise ValueError('Invalid matching features')
                        if stat_key(path)!=item['stamp']:raise ValueError('File changed during analysis')
                        db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?)',(item['sha'],recipe,value.tobytes()));db.commit()
                    kept.append(item);outfits.append(value[:768]);scenes.append(value[768:].reshape(2,768))
                except InterruptedError:raise
                except Exception as e:self.issue(item['path'],e)
                self.update(phase='Indexing outfits and photoshoot details',done=at+1,total=len(items),cached_features=hits)
        if not kept:return [],np.zeros((0,768)),np.zeros((0,2,768))
        return kept,np.stack(outfits),np.stack(scenes)

    def run(self):
        try:
            config=self.current['config'];found=self.inventory(config);items=self.identities(found)
            chosen=self.sample(items,config['limit'])
            if not chosen:raise ValueError('No readable surviving images found. Choose the parent containing the cleaned image folders, not quarantine alone.')
            self.current['sampled']=sum(not i['reference'] for i in chosen)
            self.current['outside_evaluation']=sum(not i['reference'] for i in items)-self.current['sampled']
            self.persist();chosen,outfit,scene=self.encode(chosen)
            groups,singles,capped=propose(chosen,outfit,scene,self.update,self.check)
            proposals=[]
            for n,g in enumerate(groups):
                ids=[chosen[r['index']]['id'] for r in g['members']]
                evidence={chosen[r['index']]['id']:{**{k:v for k,v in r.items() if k not in ('index','alternatives')},
                          'alternatives':[chosen[j]['id'] for j in r['alternatives']]} for r in g['members']}
                source_names=sorted({s['label'] for r in g['members'] for s in chosen[r['index']]['sources'].values() if s['kind'] in ('forum','instagram')})
                existing=[self.current['library_sets'][s] for s in g['existing_sets'] if s in self.current['library_sets']]
                name=existing[0]['name'] if len(existing)==1 else (source_names[0] if source_names else config['person'])+' · group '+str(n+1)
                proposals.append({'id':hashlib.sha256('|'.join(sorted(ids)).encode()).hexdigest()[:24], 'name':name,
                    'members':ids,'original_members':ids[:],'evidence':evidence,'priority':g['priority'],'existing_sets':existing,
                    'categories':existing[0].get('categories') or [] if len(existing)==1 else [],'colors':existing[0].get('colors') or [] if len(existing)==1 else [],
                    'notes':'','review':'pending','sources':source_names})
            self.current.update(items={i['id']:i for i in chosen},proposals=proposals,unassigned=[chosen[i]['id'] for i in singles],
                                source_candidate_caps=capped,phase='Evaluation ready — review draft sets',done=len(chosen),total=len(chosen),complete=True)
        except InterruptedError as e:self.update(phase=str(e),interrupted=True)
        except Exception as e:self.update(phase='Evaluation stopped',error=str(e))
        finally:self.update(running=False);self.persist()

    def detail(self,ident):
        with self.lock:
            if not self.current:raise ValueError('Start an evaluation first.')
            if ident=='unassigned':g={'id':ident,'name':'Unassigned images','members':self.current.get('unassigned',[]),'evidence':{},'review':'unassigned'}
            else:g=next((g for g in self.current.get('proposals',[]) if g['id']==ident),None)
            if not g:raise ValueError('Proposal not found.')
            result=copy.deepcopy(g)
            result['images']=[self.image_info(mid) for mid in g['members']]
            result['alternatives']={mid:self.image_info(mid) for ev in g.get('evidence',{}).values() for mid in ev.get('alternatives',[]) if mid not in g['members']}
            return result

    def image_info(self,mid):
        item=self.current['items'][mid]
        return {k:copy.deepcopy(item.get(k)) for k in ('id','path','sources','origins','reference','existing_sets')}

    def preview_path(self,mid):
        with self.lock:
            if not self.current or mid not in self.current['items']:raise ValueError('Unknown evaluation image')
            item=self.current['items'][mid];path=Path(item['path'])
            if linked(path) or stat_key(path)!=item['stamp']:raise ValueError('Image changed or moved. Run a fresh evaluation.')
            return path

    def review(self,body):
        with self.lock:
            if not self.current or self.current['running'] or body.get('job')!=self.current['id']:raise ValueError('Evaluation changed. Refresh before saving.')
            group=next((g for g in self.current.get('proposals',[]) if g['id']==body.get('group')),None)
            if not group:raise ValueError('Proposal not found.')
            action=body.get('action');members=list(dict.fromkeys(body.get('members',group['members'])))
            if action not in ('accepted','skipped','pending'):raise ValueError('Unknown review action.')
            if not members or any(mid not in self.current['items'] for mid in members):raise ValueError('Choose valid evaluation images.')
            if action=='accepted':
                if len(members)<2:raise ValueError('A set draft needs at least two images.')
                for mid in members:self.preview_path(mid)
                conflicts=[g['name'] for g in self.current['proposals'] if g is not group and g['review']=='accepted' and set(members)&set(g['members'])]
                if conflicts:raise ValueError('An image is already accepted in: '+', '.join(conflicts))
            name=str(body.get('name',group['name'])).strip()
            if not name or len(name)>250:raise ValueError('Enter a set name, up to 250 characters.')
            categories=body.get('categories',group['categories']);colors=body.get('colors',group['colors']);notes=body.get('notes',group['notes'])
            if not isinstance(categories,list) or not isinstance(colors,list) or any(not isinstance(v,str) or len(v)>150 for v in categories+colors):raise ValueError('Invalid categories or colors')
            if not isinstance(notes,str) or len(notes)>5000:raise ValueError('Notes are too long')
            removed=set(group['members'])-set(members)
            self.current['unassigned']=list(dict.fromkeys([i for i in self.current['unassigned'] if i not in members]+sorted(removed)))
            group.update(name=name,members=members,review=action,categories=categories,colors=colors,notes=notes,reviewed_at=time.time())
            self.persist();return self.status()

    def split(self,body):
        with self.lock:
            if not self.current or self.current['running'] or body.get('job')!=self.current['id']:raise ValueError('Evaluation changed. Refresh before splitting.')
            group=next((g for g in self.current.get('proposals',[]) if g['id']==body.get('group')),None)
            selected=set(body.get('members',[]))
            if not group or not selected < set(group['members']) or len(selected)<2:raise ValueError('Select at least two images, leaving some in the original group.')
            if group['review']=='accepted':raise ValueError('Split a pending proposal before accepting it.')
            new=copy.deepcopy(group);new.update(id=uuid.uuid4().hex[:24],name=group['name']+' · split',members=[m for m in group['members'] if m in selected],review='pending')
            group['members']=[m for m in group['members'] if m not in selected]
            if len(group['members'])==1:
                self.current['unassigned'].extend(group['members']);group['members']=[];group['review']='skipped'
            self.current['proposals'].append(new);self.current['splits']=self.current.get('splits',0)+1
            self.persist();return self.status()

    def export(self):
        with self.lock:
            if not self.current:raise ValueError('No evaluation to export.')
            out=copy.deepcopy(self.current);out['evaluation']=self.status().get('evaluation',{})
            out['notice']='Evaluation drafts only. No files were moved or imported. Scores are not calibrated probabilities. Contains local paths; no image bytes.'
            return out
