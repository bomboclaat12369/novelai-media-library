"""Run an isolated preview; optionally read an existing library folder without editing it."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sys
import tempfile
import urllib.parse
import webbrowser
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from game.catalog import demo_catalog,read_library,public_catalog
from game.engine import PACKS,UPGRADES,RuleError,forecast,upkeep,recurring_cost,hire_cost,upgrade_cost
from game.store import GameStore,Conflict
from game import management

WEB=Path(__file__).resolve().parent/'web'
PROJECT=WEB.parents[1]
RENDERER={key:next(p for p in json.loads((PROJECT/'release-standalone.json').read_text())['parts'] if p.endswith('.'+suffix+'.txt'))
          for key,suffix in [('ranks','ranks'),('collection','collection'),('editions','editions'),('base','base-layout')]}


def renderer_assets():
    def urls(value):
        if isinstance(value,str) and value.startswith('assets/'): return '/game/'+value
        if isinstance(value,list): return [urls(v) for v in value]
        if isinstance(value,dict): return {k:urls(v) for k,v in value.items()}
        return value
    config=json.loads((PROJECT/'release-standalone.json').read_text())
    return urls({'editions':json.loads((PROJECT/config['edition_catalog']).read_text()),
                 'base':json.loads((PROJECT/config['base_catalog']).read_text()),'titles':config['title_artwork']})


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass

    def permitted(self):
        if self.server.preview: return True
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}

    def send(self,status,body,mime='application/json',extra=None):
        if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
        if isinstance(body,str): body=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob:; font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers();self.wfile.write(body)

    def state_payload(self,result=None):
        result=result or self.server.store.read();s=result['state']
        if s:
            result['derived']={'demand':forecast(s)[0],'recurring':recurring_cost(s),'upkeep':upkeep(s),
                                'hire_cost':hire_cost(s),'upgrade_costs':{k:upgrade_cost(s,k) for k in UPGRADES},**management.derived(s)}
        return result

    def do_GET(self):
        if not self.permitted(): return self.send(403,{'error':'Host not allowed.'})
        path=urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        if path.startswith('/game/'): path=path[5:]
        if path=='/api/bootstrap':
            return self.send(200,{'token':self.server.token,'catalog':public_catalog(self.server.store.catalog),
                                  'packs':PACKS,'upgrades':UPGRADES,'projects':management.PROJECTS,
                                  'stays':management.STAYS,'departments':management.DEPARTMENTS,
                                  'decisions':management.DECISIONS,'profiles':management.PROFILES,**self.state_payload()})
        if path=='/api/state': return self.send(200,self.state_payload())
        if path=='/api/backups': return self.send(200,{'backups':self.server.store.backups(),'save_name':self.server.store.path.name})
        if path=='/api/renderer': return self.send(200,renderer_assets())
        if path=='/api/export':
            return self.send(200,self.server.store.export(),extra={'Content-Disposition':'attachment; filename="club-game-save.json"'})
        if path.startswith('/api/image/'):
            ident=path.removeprefix('/api/image/');card=self.server.store.catalog['cards'].get(ident)
            state=self.server.store.read()['state']
            if not state or ident not in state['owned']: return self.send(403,{'error':'Collect this card in the game before viewing its artwork.'})
            if not card or not card.get('available') or not card.get('image'):
                return self.send(404,{'error':'Artwork unavailable.'})
            query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get('original')==['1'] and not card.get('original'): return self.send(404,{'error':'Original artwork unavailable.'})
            file=Path(card.get('original') if query.get('original')==['1'] and card.get('original') else card['image']).resolve()
            root=self.server.library_root
            if not root or root not in file.parents or not file.is_file(): return self.send(404,{'error':'Artwork unavailable.'})
            return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        if path.startswith('/renderer/') and path.endswith('.js'):
            key=path[10:-3]
            if key not in RENDERER: return self.send(404,{'error':'Unknown renderer module.'})
            return self.send(200,(PROJECT/RENDERER[key]).read_bytes(),'text/javascript; charset=utf-8')
        if path.startswith('/assets/cards/'):
            file=(PROJECT/path.lstrip('/')).resolve();root=(PROJECT/'assets'/'cards').resolve()
            if root not in file.parents or not file.is_file(): return self.send(404,{'error':'Asset not found.'})
            return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        name='index.html' if path in ('/','/game','/game/') else path.lstrip('/')
        if name not in ('index.html','app.js','style.css','favicon.svg','renderer.js','management-ui.js'): return self.send(404,{'error':'Not found.'})
        file=WEB/name
        return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'text/plain')

    def do_POST(self):
        if not self.permitted(): return self.send(403,{'error':'Host not allowed.'})
        path=urllib.parse.urlparse(self.path).path
        if path.startswith('/game/'): path=path[5:]
        if path not in ('/api/action','/api/refresh','/api/restore','/api/backup'): return self.send(404,{'error':'Not found.'})
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:
            return self.send(403,{'error':'Origin not allowed.'})
        if not secrets.compare_digest(self.headers.get('X-Game-Token',''),self.server.token):
            return self.send(403,{'error':'Refresh this game tab to reconnect.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=(32*1024*1024 if path=='/api/restore' else 65536): raise RuleError('Invalid request size.')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise RuleError('Expected JSON.')
            request=json.loads(self.rfile.read(length))
            if not isinstance(request,dict) or not isinstance(request.get('body',{}),dict): raise RuleError('Invalid request.')
            if path=='/api/restore':
                with self.server.operation_lock:
                    if self.server.store.read()['revision']!=request.get('revision'): raise Conflict('The game changed before restore. Refresh and try again.')
                    restored=self.server.store.restore(request.get('export'),request.get('backup'))
                    self.server.store=restored;self.server.token=secrets.token_urlsafe(32)
                    pointer=self.server.save_origin.with_suffix('.active.json')
                    temp=pointer.with_suffix('.tmp');temp.write_text(json.dumps({'file':restored.path.name}),encoding='utf-8');os.replace(temp,pointer)
                return self.send(200,{'restored':True,'token':self.server.token,**self.state_payload()})
            if path=='/api/backup':
                self.server.store.backup()
                return self.send(200,{'backups':self.server.store.backups()})
            if path=='/api/refresh':
                cat=read_library(self.server.library_root) if self.server.library_root else demo_catalog()
                self.server.store.refresh_catalog(cat,request.get('revision'))
                return self.send(200,{'catalog':public_catalog(self.server.store.catalog),**self.state_payload()})
            with self.server.operation_lock:
                result=self.server.store.apply(request.get('action'),request.get('body',{}),request.get('id'),request.get('revision'))
            self.send(200,self.state_payload(result))
        except Conflict as exc:
            self.send(409,{'error':str(exc),**self.state_payload()})
        except (RuleError,ValueError,TypeError,KeyError) as exc:
            self.send(400,{'error':str(exc)})
        except Exception:
            self.send(500,{'error':'The action could not be saved. Refresh before trying again.'})


def build_server(port=8877,save=None,library=None,preview=False):
    if preview and library: raise ValueError('Managed preview uses demo data only.')
    root=Path(library).resolve() if library else None
    cat=read_library(root) if root else demo_catalog()
    if save is None:
        home=Path(os.environ.get('AFTER_HOURS_DATA') or Path(__file__).resolve().parent/('test-data' if preview else 'data'))
        save=home/(hashlib.sha256(cat['source_id'].encode()).hexdigest()[:16]+'.sqlite3')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.save_origin=Path(save).resolve()
    pointer=server.save_origin.with_suffix('.active.json')
    if pointer.exists():
        name=json.loads(pointer.read_text(encoding='utf-8')).get('file','')
        candidate=(server.save_origin.parent/name).resolve()
        if candidate.parent!=server.save_origin.parent or not candidate.is_file(): raise RuleError('The selected restored save is missing. Preserve the data folder and review the restore pointer.')
        save=candidate
    server.store=GameStore(save,cat);server.token=secrets.token_urlsafe(32)
    server.preview=preview;server.library_root=root
    server.operation_lock=threading.RLock()
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT',8877)))
    parser.add_argument('--host',choices=['127.0.0.1'],default='127.0.0.1',help=argparse.SUPPRESS)
    parser.add_argument('--strictPort',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--save');parser.add_argument('--library');parser.add_argument('--preview',action='store_true')
    parser.add_argument('--open',action='store_true');parser.add_argument('--choose-library',action='store_true')
    args=parser.parse_args()
    if args.choose_library:
        import tkinter as tk
        from tkinter import filedialog
        window=tk.Tk();window.withdraw()
        selected=filedialog.askopenfilename(title='Select your library.json (read-only)',filetypes=[('Media library','library.json')])
        window.destroy()
        if not selected: return
        args.library=str(Path(selected).parent)
    server=build_server(args.port,args.save,args.library,args.preview)
    url=f'http://127.0.0.1:{server.server_port}/game/'
    print(f'After Hours: {url}',flush=True)
    print('Demo catalog' if not args.library else 'Read-only library catalog; separate game save',flush=True)
    if args.open: webbrowser.open_new_tab(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
