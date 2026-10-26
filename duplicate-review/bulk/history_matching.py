"""Run the ordinary duplicate matcher on unresolved quarantine vs survivors.

Only analysis caches are shared with the normal checker. Review groups, keep/split
choices and move journals are never rewritten by historical matching.
"""
from pathlib import Path
from engine import Engine, ALGORITHM, stat_key
import crop_match

RECIPE = f'ordinary-dupes-v1:{ALGORITHM}:{crop_match.FEATURE_VERSION}'


class HistoryMatcher(Engine):
    def __init__(self, work):
        self.work=work
        super().__init__(work.engine.state_dir/'history-matching')
        self.cancel=work.cancel
        self.matches={}
        self.target_shas=set()
        self.families={}
        with work.engine.db() as db:
            self.separated={tuple(row) for row in db.execute('SELECT a,b FROM separations')}

    def set_status(self,**fields):
        super().set_status(**fields)
        self.work.update(**fields)

    def add_pair(self,db,a,b,kind,score,ignored):
        if (a['sha'] in self.target_shas)==(b['sha'] in self.target_shas):return
        target,keeper=(a,b) if a['sha'] in self.target_shas else (b,a)
        # The normal matcher analyzes one representative per exact-pixel family.
        # Carry its result to every unresolved digest without losing any origins.
        for row in self.families[target.get('pixel') or target['sha']]:
            if row['sha'] not in self.target_shas:continue
            if tuple(sorted((row['sha'],keeper['sha']))) in self.separated:continue
            pair={'id':keeper['catalog_id'],'score':score,'kind':kind}
            previous=self.matches.setdefault(row['sha'],{}).get(keeper['catalog_id'])
            if previous is None or score>previous['score']:
                self.matches[row['sha']][keeper['catalog_id']]=pair

    def records(self,catalog):
        # Quarantine duplicates with identical bytes need only one fingerprint;
        # confirmation still validates and preserves every physical copy.
        chosen={}
        for item in catalog.values():chosen.setdefault(item['sha'],item)
        result=[];reused=0
        shared=self.work.engine
        with shared.db() as db:
            cached_paths={}
            for row in db.execute('''SELECT c.sha,c.path,f.path AS feature_path FROM cache c
                LEFT JOIN features f ON f.path=c.path AND f.stamp=c.stamp AND f.version=?
                WHERE c.algorithm=?''',(crop_match.FEATURE_VERSION,ALGORITHM)):
                if row['sha'] not in cached_paths or row['feature_path']:
                    cached_paths[row['sha']]=row['path']
            for at,item in enumerate(chosen.values()):
                self.work.check()
                path=Path(item['path'])
                try:
                    if stat_key(path)!=item['stamp']:raise ValueError('File changed after inventory. Refresh duplicate history.')
                    cached_path=cached_paths.get(item['sha'])
                    cached=db.execute('SELECT * FROM cache WHERE path=?',(cached_path,)).fetchone() if cached_path else None
                    feature=db.execute('SELECT data FROM features WHERE path=? AND stamp=? AND version=?',
                        (cached_path,cached['stamp'],crop_match.FEATURE_VERSION)).fetchone() if cached else None
                    prior=dict(cached) if cached else None
                    if prior:prior.update(path=str(path),stamp=item['stamp'],size=path.stat().st_size)
                    r,changed,error=self.prepare_image(path,item['stamp'],prior,feature[0] if feature else None)
                    if r['sha']!=item['sha']:raise ValueError('File contents changed after inventory.')
                    if changed or cached_path!=str(path):
                        db.execute('INSERT OR REPLACE INTO cache(path,stamp,algorithm,sha,w,h,ph,mh,sketch,size,pixel) VALUES (:path,:stamp,:algorithm,:sha,:w,:h,:ph,:mh,:sketch,:size,:pixel)',r)
                    if r['features'] is not None and (not feature or cached_path!=str(path)):
                        db.execute('INSERT OR REPLACE INTO features VALUES (?,?,?,?)',(str(path),item['stamp'],crop_match.FEATURE_VERSION,r['features']))
                    if error:self.work.issue(path,error)
                    if cached and feature:reused+=1
                    r.update(id=at+1,reference=bool(item.get('reference')),catalog_id=item['id'])
                    result.append(r)
                    self.families.setdefault(r.get('pixel') or r['sha'],[]).append(r)
                    if item.get('quarantine_only'):self.target_shas.add(r['sha'])
                except InterruptedError:raise
                except Exception as e:self.work.issue(path,'Duplicate matching: '+str(e))
                if at%32==0:db.commit()
                self.work.update(phase='Preparing original duplicate matching',done=at+1,total=len(chosen),history_cached_images=reused)
        return result

    def run(self):
        catalog=self.work.current['source_catalog']
        # Nothing to review: do not reanalyze an already resolved collection.
        if not any(i.get('quarantine_only') for i in catalog.values()):return {}
        records=self.records(catalog)
        config=self.work.current['config'];mode=config['duplicate_mode']
        self.match(records,mode,target_shas=self.target_shas)
        self.match_aligned(records,mode,config['workers'],target_shas=self.target_shas)
        for item in catalog.values():
            self.work.check()
            try:
                if stat_key(Path(item['path']))!=item['stamp']:raise ValueError('File changed during duplicate matching. Refresh history.')
            except Exception as e:self.work.issue(item['path'],e)
        return {sha:sorted(rows.values(),key=lambda r:(-r['score'],r['id'])) for sha,rows in self.matches.items()}
