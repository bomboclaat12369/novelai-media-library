"""Coordinated, verified snapshots of companion metadata and Workbench databases.

Original files are optional. Restore refuses missing originals or changed paths;
its journal rolls back both applications after interrupted/failed installation.
"""
import hashlib,json,shutil,sqlite3,time,uuid
from pathlib import Path
from engine import linked,sha256

class Checkpoints:
    names=('review.sqlite3','bulk-preparation.sqlite3','organizer.sqlite3')
    def __init__(self,engine,bulk,organizer):
        self.engine=engine;self.bulk=bulk;self.organizer=organizer
        self.root=engine.state_dir/'checkpoints';self.root.mkdir(exist_ok=True)
        self.journal=engine.state_dir/'checkpoint-restore-pending.json'

    def ready(self):
        if self.engine.status['running'] or self.organizer.job['running'] or (self.bulk.current or {}).get('running'):
            raise ValueError('Pause scans and analysis before creating or restoring a checkpoint.')

    def snapshot_databases(self,directory):
        hashes={}
        for name in self.names:
            source=self.engine.state_dir/name
            if not source.exists():continue
            target=directory/name
            with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:src.backup(dst)
            hashes[name]=sha256(target)
        return hashes

    def create(self,body):
        with self.engine.lock,self.organizer.lock,self.bulk.lock:
            self.ready();self.organizer.bind()
            companion=self.engine.library.request('/api/checkpoints/create',{'label':body.get('label','Complete project checkpoint'),'include_media':bool(body.get('include_media'))})
            ident=companion['id'];directory=self.root/ident;directory.mkdir(exist_ok=False)
            try:
                hashes=self.snapshot_databases(directory)
                library=directory/'library-checkpoint.zip';shutil.copyfile(companion['path'],library);hashes[library.name]=sha256(library)
                files={}
                paths={r['path'] for r in self.organizer.catalog.values()}
                with self.engine.db() as db:
                    paths.update(r[0] for r in db.execute('SELECT path FROM files'))
                    for row in db.execute('SELECT src,dst FROM moves'):paths.update(row)
                for name in sorted(paths):
                    path=Path(name)
                    if not path.is_file() or linked(path):continue
                    record={'size':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns}
                    if body.get('include_media'):
                        digest=sha256(path);record['sha256']=digest;target=directory/'originals'/digest
                        target.parent.mkdir(exist_ok=True)
                        if not target.exists():shutil.copyfile(path,target)
                    files[str(path.resolve())]=record
                # Selected frames are application data, so always include them.
                frame_dir=self.engine.state_dir/'video-frames'
                if frame_dir.exists():shutil.copytree(frame_dir,directory/'video-frames')
                frame_hashes={p.name:sha256(p) for p in (directory/'video-frames').glob('*') if p.is_file()}
                manifest={'schema':1,'id':ident,'at':companion['manifest']['at'],'label':companion['manifest']['label'],
                    'include_media':bool(body.get('include_media')),'library_root':str(Path(companion['path']).parents[1]),'hashes':hashes,'files':files,'frame_hashes':frame_hashes}
                (directory/'checkpoint.json').write_text(json.dumps(manifest),encoding='utf-8')
                return {'id':ident,'path':str(directory),'include_media':manifest['include_media']}
            except Exception:
                shutil.rmtree(directory,ignore_errors=True);raise

    def read(self,ident):
        if not isinstance(ident,str) or '/' in ident or '\\' in ident or '..' in ident:raise ValueError('Choose a saved checkpoint.')
        directory=self.root/ident;manifest=json.loads((directory/'checkpoint.json').read_text('utf-8'))
        if manifest.get('schema')!=1 or manifest.get('id')!=ident:raise ValueError('Invalid project checkpoint.')
        for name,digest in manifest['hashes'].items():
            if name not in (*self.names,'library-checkpoint.zip') or sha256(directory/name)!=digest:raise ValueError('Checkpoint verification failed.')
        for name,digest in manifest.get('frame_hashes',{}).items():
            if Path(name).name!=name or sha256(directory/'video-frames'/name)!=digest:raise ValueError('Video frame checkpoint verification failed.')
        return directory,manifest

    def list(self):
        self.recover()
        entries=[]
        for path in sorted(self.root.glob('*/checkpoint.json'),reverse=True):
            try:
                m=json.loads(path.read_text('utf-8'));entries.append({k:m.get(k) for k in ('id','at','label','include_media')})
            except (OSError,ValueError):continue
        return {'checkpoints':entries}

    def fingerprint(self):
        hashes={}
        for name in self.names:
            with sqlite3.connect(self.engine.state_dir/name) as db:
                # Data version alone is connection-local; the deterministic dump
                # catches changes made through any connection/window.
                digest=hashlib.sha256()
                for line in db.iterdump():digest.update(line.encode())
                hashes[name]=digest.hexdigest()
        return hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()

    def preview(self,body):
        with self.engine.lock,self.organizer.lock,self.bulk.lock:
            self.ready();directory,m=self.read(body.get('id'))
            health=self.engine.library.request('/api/health')
            if Path(health['library_root']).resolve()!=Path(m['library_root']).resolve():raise ValueError('This checkpoint belongs to a different library folder.')
            installed=Path(m['library_root'])/'backups'/('checkpoint-'+m['id']+'.zip')
            if not installed.exists():shutil.copyfile(directory/'library-checkpoint.zip',installed)
            companion=self.engine.library.request('/api/checkpoints/preview',{'id':m['id']})
            missing=[];changed=[]
            for name,record in m['files'].items():
                p=Path(name)
                if p.exists() and linked(p):changed.append(name);continue
                if not p.exists():
                    if not record.get('sha256') or not (directory/'originals'/record['sha256']).exists():missing.append(name)
                elif record.get('sha256'):
                    if sha256(p)!=record['sha256']:changed.append(name)
                elif p.stat().st_size!=record['size'] or p.stat().st_mtime_ns!=record['mtime_ns']:changed.append(name)
            token=hashlib.sha256((self.fingerprint()+companion['token']+sha256(directory/'checkpoint.json')).encode()).hexdigest()
            return {'id':m['id'],'token':token,'companion':companion,'missing_files':missing,'changed_files':changed,
                'databases':list(self.names),'originals_included':m['include_media']}

    def install_databases(self,directory):
        for name in self.names:
            if not (directory/name).exists():continue
            with sqlite3.connect(directory/name) as src,sqlite3.connect(self.engine.state_dir/name) as dst:src.backup(dst)
        frames=directory/'video-frames'
        if frames.exists():shutil.copytree(frames,self.engine.state_dir/'video-frames',dirs_exist_ok=True)
        from bulk.workbench import Workbench
        fresh=Workbench(self.engine);self.bulk.current=fresh.current;self.bulk._collections_cache=None
        self.engine.groups_cache=None;self.engine.verified_plan=None;self.engine.exact_plan=None;self.engine.revision+=1
        self.organizer.bound=None;self.organizer.bind()

    def recover(self):
        if not self.journal.exists():return
        with self.engine.lock,self.organizer.lock,self.bulk.lock:
            journal=json.loads(self.journal.read_text('utf-8'));directory,_=self.read(journal['rollback'])
            plan=self.engine.library.request('/api/checkpoints/preview',{'id':journal['rollback']})
            self.engine.library.request('/api/checkpoints/restore',{'id':journal['rollback'],'token':plan['token']})
            self.install_databases(directory);self.journal.unlink()

    def restore(self,body):
        with self.engine.lock,self.organizer.lock,self.bulk.lock:
            self.recover();plan=self.preview(body)
            if plan['token']!=body.get('token'):raise ValueError('Project changed. Preview restore again.')
            if plan['missing_files'] or plan['changed_files'] or plan['companion']['missing_media']:raise ValueError('Restore the missing/changed originals before restoring this checkpoint.')
            directory,m=self.read(body['id']);rollback=self.create({'label':'Before complete project restore'})
            self.journal.write_text(json.dumps({'rollback':rollback['id'],'target':body['id']}),encoding='utf-8')
            try:
                for name,record in m['files'].items():
                    target=Path(name)
                    if target.exists():continue
                    source=directory/'originals'/record['sha256']
                    if sha256(source)!=record['sha256'] or (target.parent.exists() and linked(target.parent)):raise ValueError('Original restore verification failed.')
                    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
                self.engine.library.request('/api/checkpoints/restore',{'id':body['id'],'token':plan['companion']['token']})
                self.install_databases(directory);self.journal.unlink()
            except Exception:
                self.recover();raise
            return {'restored':body['id'],'rollback':rollback['id']}
