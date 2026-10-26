"""Verified, versioned app updates. User data and the launcher's environment stay put."""
from __future__ import annotations
import base64, hashlib, io, json, os, re, shutil, sys, threading, time, urllib.request, zipfile
from pathlib import Path

REPOSITORY='https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/'
MANIFEST=REPOSITORY+'main/release-duplicate-review.json'
MAX_DOWNLOAD=24*1024*1024

def version(v):
    if not re.fullmatch(r'\d+\.\d+\.\d+',str(v)):raise ValueError('Invalid release version.')
    return tuple(map(int,v.split('.')))

def state_directory():
    if '--state-dir' in sys.argv:return Path(sys.argv[sys.argv.index('--state-dir')+1]).expanduser().resolve()
    for argument in sys.argv[1:]:
        if argument.startswith('--state-dir='):return Path(argument.split('=',1)[1]).expanduser().resolve()
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'LocalDuplicateReview'

def active_program(state):
    root=(state/'updates').resolve()
    try:
        active=json.loads((root/'active.json').read_text());v=active['version'];version(v)
        path=root/'versions'/v/'duplicate-review'/'app.py'
        if not path.is_file() or not (path.parent.parent/'ready.json').is_file():return None
        if not path.resolve().is_relative_to(root):return None
        return path
    except (OSError,ValueError,KeyError):return None

def launch_active():
    """The original shortcut always opens the latest installed, complete program."""
    path=active_program(state_directory())
    if path and path.resolve()!=Path(sys.argv[0]).resolve():os.execv(sys.executable,[sys.executable,str(path),*sys.argv[1:]])

def fetch(url,limit=MAX_DOWNLOAD):
    if not url.startswith(REPOSITORY):raise ValueError('Unexpected update source.')
    req=urllib.request.Request(url,headers={'User-Agent':'LocalDuplicateReview-Updater','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=30) as response:
        payload=response.read(limit+1)
    if len(payload)>limit:raise ValueError('Update exceeded size limit.')
    return payload

class Updater:
    def __init__(self,state,current,program_root=None,fetcher=fetch):
        self.root=Path(state)/'updates';self.current=current;self.program_root=Path(program_root or Path(__file__).parent)
        self.fetch=fetcher;self.lock=threading.RLock();self.thread=None;self.manifest=None;self.restart=False
        self.info={'current':current,'available':False,'running':False,'phase':'Check for updates','ready':False,'done':0,'total':0,'eta_seconds':None}

    def status(self):
        with self.lock:return dict(self.info)

    def start(self,install=False):
        with self.lock:
            if self.info['running']:return self.status()
            self.info.update(running=True,phase='Checking for updates',error=None,eta_seconds=None,done=0,total=0)
            self.thread=threading.Thread(target=self.run,args=(install,),daemon=True);self.thread.start();return self.status()

    def run(self,install):
        try:
            manifest=json.loads(self.fetch(MANIFEST,128*1024));wanted=manifest['version'];version(wanted)
            if manifest.get('schema')!=1:raise ValueError('Unsupported update manifest.')
            with self.lock:
                if self.info.get('version')!=wanted:self.info['ready']=False
                self.manifest=manifest;self.info.update(version=wanted,available=version(wanted)>version(self.current),notes=str(manifest.get('notes',''))[:2000])
            if version(wanted)<=version(self.current):
                with self.lock:self.info.update(phase='Up to date')
                return
            if not install:
                with self.lock:self.info.update(phase='Update '+wanted+' available')
                return
            parts=manifest.get('parts',[])
            if not isinstance(parts,list) or not 1<=len(parts)<=64:raise ValueError('Invalid update payload.')
            chunks=[];received=0;started=time.monotonic()
            for at,p in enumerate(parts):
                # Payloads are immutable: manifest pins a Git commit, never main.
                url=p['url']
                if not re.match(re.escape(REPOSITORY)+r'[0-9a-f]{40}/',url):raise ValueError('Update payload is not pinned to a commit.')
                raw=self.fetch(url)
                if hashlib.sha256(raw).hexdigest()!=p['sha256']:raise ValueError('Update part verification failed.')
                received+=len(raw)
                if received>MAX_DOWNLOAD:raise ValueError('Update too large.')
                chunks.append(raw.strip());elapsed=time.monotonic()-started
                with self.lock:self.info.update(phase='Downloading update',done=at+1,total=len(parts),eta_seconds=round(elapsed/(at+1)*(len(parts)-at-1)))
            payload=base64.b64decode(b''.join(chunks),validate=True)
            if hashlib.sha256(payload).hexdigest()!=manifest['sha256']:raise ValueError('Update verification failed.')
            self.stage(payload,wanted)
            with self.lock:self.info.update(phase='Ready to restart',ready=True,eta_seconds=0)
        except Exception as e:
            with self.lock:self.info.update(phase='Update unavailable',error=str(e))
        finally:
            with self.lock:self.info['running']=False

    def stage(self,payload,wanted):
        version(wanted);self.root.mkdir(parents=True,exist_ok=True)
        stage=self.root/('stage-'+str(time.time_ns()));stage.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as z:
                if sum(i.file_size for i in z.infolist())>40*1024*1024:raise ValueError('Expanded update too large.')
                for info in z.infolist():
                    name=info.filename;parts=Path(name).parts
                    if '\\' in name or name.startswith('/') or any(p in ('..','.') or ':' in p for p in parts):raise ValueError('Unsafe update path.')
                    if not (name.startswith('duplicate-review/') or name=='runtime-src/companion-runtime.pyw'):raise ValueError('Unexpected update file.')
                    if any(p.startswith('.') for p in parts) or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsupported update entry.')
                    dest=stage/name
                    if not dest.resolve().is_relative_to(stage.resolve()):raise ValueError('Unsafe update destination.')
                    if info.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
                    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(info))
            required=['app.py','engine.py','updater.py','organizer.py','ui.html','organizer.html','history-review.js','update-ui.js','requirements.txt','bulk/workbench.py']
            if any(not (stage/'duplicate-review'/p).is_file() for p in required) or not (stage/'runtime-src/companion-runtime.pyw').is_file():raise ValueError('Update is incomplete.')
            if (stage/'duplicate-review/requirements.txt').read_bytes()!=(self.program_root/'requirements.txt').read_bytes():raise ValueError('This release needs a dependency upgrade; keep using the installed version.')
            for path in stage.rglob('*.py'):compile(path.read_text(encoding='utf-8'),str(path),'exec')
            compile((stage/'runtime-src/companion-runtime.pyw').read_text(encoding='utf-8'),'companion-runtime.pyw','exec')
            text=(stage/'duplicate-review/engine.py').read_text()
            if not re.search(r"^VERSION\s*=\s*['\"]"+re.escape(wanted)+r"['\"]",text,re.M):raise ValueError('Release version does not match payload.')
            (stage/'ready.json').write_text(json.dumps({'version':wanted,'sha256':hashlib.sha256(payload).hexdigest()}))
            target=self.root/'versions'/wanted;target.parent.mkdir(exist_ok=True)
            if target.exists():
                if (target/'ready.json').read_bytes()!=(stage/'ready.json').read_bytes():raise ValueError('Installed release contents conflict.')
            else:stage.rename(target)
        finally:
            if stage.exists():shutil.rmtree(stage)

    def activate(self):
        with self.lock:
            if not self.info['ready'] or self.info['running']:raise ValueError('Download and verify the update first.')
            wanted=self.info['version'];target=self.root/'versions'/wanted
            if not (target/'ready.json').is_file():raise ValueError('Verified update is missing.')
            data={'version':wanted,'previous':self.current};temp=self.root/'active.new'
            temp.write_text(json.dumps(data));os.replace(temp,self.root/'active.json')
            self.restart=True;return {'restarting':True,'message':'Update installed. Reopening the app with your saved data.'}
