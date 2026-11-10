"""Loopback-only desktop browser UI. No image uploads, analytics, or cloud APIs."""
from __future__ import annotations
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

if __name__ == '__main__' and '--pick-folder' not in sys.argv:
    from updater import launch_active
    launch_active()

# Avoid loading NumPy for the native folder dialog subprocess.
if '--pick-folder' in sys.argv:
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    selected = filedialog.askdirectory(parent=root, title='Choose an image folder')
    root.destroy()
    print(selected)
    raise SystemExit()

from engine import Engine, VERSION, load_image


def make_server(engine, port=0, token=None):
    token = token or secrets.token_urlsafe(32)
    html = (Path(__file__).parent / 'ui.html').read_text(encoding='utf-8')
    html = html.replace('__HISTORY_REVIEW__', (Path(__file__).parent / 'history-review.js').read_text(encoding='utf-8'))
    from bulk.workbench import Workbench
    bulk = Workbench(engine)
    from organizer import Organizer
    from updater import Updater
    organizer = Organizer(engine, bulk)
    from library_editing import LibraryEditor
    library_editor = LibraryEditor(organizer)
    from checkpoints import Checkpoints
    checkpoints=Checkpoints(engine,bulk,organizer)
    checkpoints.recover()
    updater = Updater(engine.state_dir, VERSION)
    operation_lock = threading.RLock()
    bulk_html = (Path(__file__).parent / 'bulk' / 'ui.html').read_text(encoding='utf-8')
    organizer_html = (Path(__file__).parent / 'organizer.html').read_text(encoding='utf-8')
    update_js = (Path(__file__).parent / 'update-ui.js').read_text(encoding='utf-8')
    update_tag = '<script nonce="__TOKEN__">'+update_js+'</script>'
    html = html.replace('</body>',update_tag+'</body>')
    bulk_html = bulk_html.replace('</body>',update_tag+'</body>')
    organizer_html = organizer_html.replace('__UPDATER__',update_js)
    organizer_html = organizer_html.replace('__ORGANIZER_WORKFLOW__',(Path(__file__).parent/'missing-files.js').read_text(encoding='utf-8')+'\n'+(Path(__file__).parent/'organizer-workflow.js').read_text(encoding='utf-8')+'\n'+(Path(__file__).parent/'organizer-search.js').read_text(encoding='utf-8'))
    organizer_html = organizer_html.replace('__ORGANIZER_SESSION__',(Path(__file__).parent/'organizer-session.js').read_text(encoding='utf-8'))

    autofill_js=(Path(__file__).parent/'no-autofill.js').read_text(encoding='utf-8')
    def no_autofill(page):
        return page.replace('<html ', '<html data-local-duplicate-review="1" ',1).replace('</body>', '<script nonce="__TOKEN__">'+autofill_js+'</script></body>')
    html=no_autofill(html);bulk_html=no_autofill(bulk_html);organizer_html=no_autofill(organizer_html)

    image_slots = threading.Semaphore(2)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, data, kind='application/json'):
            if kind == 'application/json':
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'nonce-"+token+"'; style-src 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def allowed(self):
            host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != host:
                return False
            origin = self.headers.get('Origin')
            return not origin or origin == 'http://'+host

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {'error': 'Local access only'})
            url = urlparse(self.path)
            params = parse_qs(url.query)
            if url.path == '/bulk':
                return self.send(200, bulk_html.replace('__TOKEN__', token).encode(), 'text/html; charset=utf-8')
            if url.path == '/organizer':
                return self.send(200, organizer_html.replace('__TOKEN__', token).encode(), 'text/html; charset=utf-8')
            if url.path == '/':
                return self.send(200, html.replace('__TOKEN__', token).replace('__VERSION__', VERSION).encode(), 'text/html; charset=utf-8')
            if self.headers.get('X-Review-Token') != token and params.get('token', [''])[0] != token:
                return self.send(403, {'error': 'Reopen the app using its launcher.'})
            try:
                if url.path == '/api/organizer/checkpoints':
                    return self.send(200,checkpoints.list())
                if url.path == '/api/organizer/diagnostics':
                    return self.send(200,{'workbench_version':VERSION,'job':(bulk.current or {}).get('id'),'organizer':organizer.summary()['progress'],'library':engine.library.request('/api/diagnostics')})
                if url.path == '/api/organizer/videos':
                    return self.send(200,organizer.video_queue())
                if url.path == '/api/organizer/missing-status':
                    return self.send(200,organizer.file_finder().status(params.get('id',[None])[0],params.get('offset',[0])[0],params.get('limit',[100])[0]))
                if url.path in ('/api/organizer/video-file','/api/organizer/original','/api/organizer/library-image'):
                    path=organizer.original_path(params.get('id',[''])[0]) if url.path.endswith('/original') else getattr(organizer,'video_files',{}).get(params.get('id',[''])[0])
                    if url.path.endswith('/library-image'):
                        with image_slots:path=organizer.library_image_path(params.get('owner',[''])[0],params.get('id',[''])[0],int(params.get('size',[0])[0]))
                    if not path or not path.is_file():raise ValueError('Refresh the video list.')
                    import re,mimetypes
                    size=path.stat().st_size;start=0;end=size-1;partial=False
                    requested=self.headers.get('Range','')
                    if requested:
                        match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                        if not match:raise ValueError('Unsupported video range.')
                        if match[1]:start=int(match[1]);end=min(end,int(match[2])) if match[2] else end
                        else:start=max(0,size-int(match[2]))
                        if start>end or start>=size:raise ValueError('Video range unavailable.')
                        partial=True
                    self.send_response(206 if partial else 200);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'video/mp4')
                    self.send_header('Content-Security-Policy',"sandbox; default-src 'none'");self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
                    if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    with path.open('rb') as stream:
                        stream.seek(start);remaining=end-start+1
                        while remaining:
                            chunk=stream.read(min(1024*1024,remaining))
                            if not chunk:break
                            self.wfile.write(chunk);remaining-=len(chunk)
                    return
                if url.path == '/api/update/status':
                    return self.send(200, updater.status())
                if url.path == '/api/organizer/state':
                    return self.send(200, organizer.summary())
                if url.path == '/api/organizer/page':
                    return self.send(200, organizer.page(params.get('kind',['post'])[0],params['id'][0],int(params.get('offset',[0])[0]),params.get('order',['similar'])[0],params.get('peek',['0'])[0]!='1',params.get('focus',[''])[0]))
                if url.path == '/api/organizer/progress':
                    with organizer.lock:progress=dict(organizer.job)
                    return self.send(200, progress)
                if url.path == '/api/organizer/export':
                    return self.send(200, organizer.export())
                if url.path == '/api/organizer/image':
                    with image_slots:
                        payload=organizer.preview(params['id'][0],int(params.get('size',[1000])[0]))
                    return self.send(200,payload,'image/jpeg')
                if url.path == '/api/bulk/state':
                    return self.send(200, bulk.status())
                if url.path == '/api/bulk/context':
                    return self.send(200, bulk.context())
                if url.path == '/api/bulk/group':
                    return self.send(200, bulk.detail(params['id'][0]))
                if url.path == '/api/bulk/origin-audit':
                    return self.send(200, bulk.origin_audit(int(params['offset'][0]) if 'offset' in params else None,params.get('q',[''])[0],int(params.get('page',[0])[0]),params.get('mode',['suggested'])[0],params.get('filter',['all'])[0],params.get('target',[None])[0]))
                if url.path == '/api/bulk/neighbors':
                    return self.send(200, bulk.neighbors(params['id'][0],int(params.get('offset',[0])[0])))
                if url.path == '/api/bulk/export':
                    return self.send(200, bulk.export())
                if url.path == '/api/bulk/image':
                    path = bulk.preview_path(params['id'][0])
                    with image_slots:
                        image, _, _ = load_image(path, min(2000,max(160,int(params.get('size',[800])[0]))))
                        output = io.BytesIO(); image.save(output, format='JPEG', quality=92)
                    return self.send(200, output.getvalue(), 'image/jpeg')
                if url.path == '/api/state':
                    return self.send(200, engine.view(int(params.get('offset', [0])[0]), params.get('filter', ['all'])[0]))
                if url.path == '/api/groups':
                    return self.send(200, engine.groups(int(params['group'][0]) if 'group' in params else None, params.get('sort',['most'])[0]))
                if url.path == '/api/verified/preview':
                    return self.send(200, engine.verified_preview())
                if url.path == '/api/ui-preferences':
                    return self.send(200, engine.ui_preferences())
                if url.path == '/api/config':
                    return self.send(200, engine.config())
                if url.path == '/api/library':
                    return self.send(200, engine.library.catalog())
                if url.path == '/api/history':
                    return self.send(200, engine.history())
                if url.path == '/api/preview':
                    record = engine.record(int(params['id'][0]))
                    path = engine.validate(record, verify_hash=False)
                    with image_slots:
                        image, _, _ = load_image(path, min(2000,max(160,int(params.get('size',[2000])[0]))))
                        output = io.BytesIO()
                        image.save(output, format='JPEG', quality=94)
                    return self.send(200, output.getvalue(), 'image/jpeg')
                return self.send(404, {'error': 'Not found'})
            except Exception as e:
                return self.send(400, {'error': str(e)})

        def do_POST(self):
            with operation_lock:
                self.handle_post()

        def handle_post(self):
            if not self.allowed() or self.headers.get('X-Review-Token') != token:
                return self.send(403, {'error': 'Local access only'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2000000:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(length))
                path = urlparse(self.path).path
                if updater.restart:
                    raise ValueError('The app is restarting to apply an update.')
                if organizer.job['running'] and not (path.startswith('/api/organizer/') or path in ('/api/ui-preferences','/api/quit','/api/history/open','/api/history/reveal','/api/update/check','/api/update/install')):
                    raise ValueError('Pause visual analysis before changing the source inventory or restarting.')
                if bulk.current and bulk.current['running'] and path not in ('/api/ui-preferences','/api/bulk/cancel','/api/pick','/api/quit'):
                    raise ValueError('Stop the bulk evaluation before changing files or starting another operation.')
                if path == '/api/ui-preferences':
                    result=engine.ui_preferences(body)
                elif path == '/api/update/check':
                    result=updater.start()
                elif path == '/api/update/install':
                    result=updater.start(install=True)
                elif path == '/api/update/apply':
                    if engine.status['running'] or organizer.job['running'] or (bulk.current or {}).get('running'):
                        raise ValueError('Finish or stop the active scan before restarting. Your progress is saved.')
                    result=updater.activate()
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                elif path in ('/api/organizer/missing-start','/api/organizer/missing-stop','/api/organizer/missing-recover'):
                    finder=organizer.file_finder()
                    result=finder.start(body) if path.endswith('-start') else finder.stop(body.get('job_id')) if path.endswith('-stop') else finder.recover(body)
                elif path in ('/api/organizer/checkpoint-create','/api/organizer/checkpoint-preview','/api/organizer/checkpoint-restore'):
                    method=path.rsplit('-',1)[-1];result=getattr(checkpoints,method)(body)
                elif path in ('/api/organizer/transfer-preview','/api/organizer/transfer-import','/api/organizer/transfer-apply'):
                    if path.endswith('transfer-apply') and not getattr(organizer,'transfer_checkpoint',None):
                        organizer.transfer_checkpoint=checkpoints.create({'label':'Before organizer application'})['id']
                    result=organizer.transfer(path.rsplit('-',1)[-1],body)
                    if path.endswith('transfer-preview'):organizer.transfer_checkpoint=None
                elif path == '/api/organizer/switch':
                    result=organizer.switch_collection(body)
                elif path == '/api/organizer/collections':
                    result=organizer.refresh_collections(body)
                elif path == '/api/organizer/folders':
                    result=organizer.collection_folders(body)
                elif path == '/api/organizer/assign-collection':
                    result=organizer.assign_collection(body)
                elif path in ('/api/organizer/import-catalog','/api/organizer/import-category-create'):
                    result=organizer.create_import_category(body) if path.endswith('-create') else organizer.import_catalog(body)
                elif path in ('/api/organizer/edit-read','/api/organizer/edit-save'):
                    result=library_editor.read(body) if path.endswith('-read') else library_editor.save(body)
                elif path == '/api/organizer/manual-search':
                    result=organizer.manual_search(body)
                elif path == '/api/organizer/attach-library':
                    result=organizer.attach_library(body)
                elif path == '/api/organizer/comparison-source':
                    result=organizer.comparison_source(body)
                elif path == '/api/organizer/duplicate-choice':
                    result=organizer.duplicate_choice(body)
                elif path == '/api/organizer/related':
                    result=organizer.related(body)
                elif path == '/api/organizer/index':
                    result=organizer.index(body.get('ids'))
                elif path in ('/api/organizer/video-step','/api/organizer/video-frame'):
                    result=organizer.video_action(path.rsplit('-',1)[-1],body)
                elif path == '/api/organizer/pause':
                    organizer.cancel.set();result={'paused':True}
                elif path in ('/api/organizer/load_categories','/api/organizer/create_category'):
                    result=organizer.category_action(path.rsplit('/',1)[-1],body)
                elif path.startswith('/api/organizer/'):
                    result=organizer.mutate(path.rsplit('/',1)[-1],body)
                elif path == '/api/bulk/start':
                    result = bulk.start(body)
                elif path == '/api/history/verify':
                    result = bulk.verify_history(body)
                elif path == '/api/history/inventory':
                    result = bulk.start(body,inventory_only=True)
                elif path == '/api/bulk/reevaluate':
                    result = bulk.reevaluate(body)
                elif path == '/api/bulk/cancel':
                    bulk.cancel.set();result = {'message':'Stopping after the current operation…'}
                elif path == '/api/bulk/activate':
                    result = bulk.activate(str(body['id']))
                elif path == '/api/bulk/mark-origin':
                    result = bulk.mark_origin(body)
                elif path == '/api/bulk/undo-origin':
                    result = bulk.undo_origin(body)
                elif path == '/api/bulk/confirm-origin':
                    result = bulk.confirm_origin(body)
                elif path == '/api/bulk/transfer':
                    result = bulk.transfer(body)
                elif path == '/api/bulk/undo-review':
                    result = bulk.undo_review(body)
                elif path == '/api/bulk/split':
                    result = bulk.split(body)
                elif path == '/api/bulk/review':
                    result = bulk.review(body)
                elif path == '/api/scan':
                    engine.start(body.get('incoming', []), body.get('reference', []), body.get('mode', 'balanced'),
                                 body.get('library_character',''), body.get('library_id',''), body.get('workers',8), body.get('scan_kind','folders'))
                    result = {'message': 'Scan started'}
                elif path == '/api/cancel':
                    engine.cancel.set()
                    result = {'message': 'Stopping after the current file…'}
                elif path == '/api/review':
                    result = engine.review(int(body['pair']), body['action'])
                elif path == '/api/verified/start':
                    result = engine.start_verified(int(body['revision']), body.get('scope', 'all'), preview=body.get('preview') is True)
                elif path == '/api/verified/apply':
                    result = engine.apply_verified_preview(body['token'], body['targets'])
                elif path == '/api/exact/preview':
                    result = engine.preview_exact(body.get('scope', 'all'),bool(body.get('include_pixels')))
                elif path == '/api/exact/start':
                    result = engine.start_exact(body['token'])
                elif path == '/api/selection/move':
                    result = engine.move_selection(body['selection'], int(body['revision']))
                elif path == '/api/group/dismiss':
                    result = engine.dismiss_group(int(body['group']), int(body['revision']))
                elif path == '/api/group/keep':
                    result = engine.mark_keep(int(body['group']),int(body['id']),bool(body['keep']),int(body['revision']))
                elif path == '/api/group/quarantine':
                    result = engine.quarantine_group(int(body['group']),int(body['revision']))
                elif path == '/api/group/finish':
                    result = engine.finish_group(int(body['group']),int(body['revision']))
                elif path == '/api/group/split':
                    result = engine.split_group(int(body['group']),body['ids'],int(body['revision']))
                elif path == '/api/library/replace':
                    result = engine.replace_library(int(body['group']),int(body['source']),int(body['target']),int(body['revision']))
                elif path == '/api/library/cleanup-resume':
                    result = engine.resume_library_cleanup()
                elif path == '/api/library/resume':
                    result = engine.resume_replacements()
                elif path == '/api/undo':
                    result = engine.undo()
                elif path == '/api/reset':
                    result = engine.reset_dismissed()
                elif path == '/api/pick':
                    args = [sys.executable, str(Path(__file__).resolve()), '--pick-folder']
                    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    child = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                           timeout=300, creationflags=flags,
                                           env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                    if child.returncode:
                        raise ValueError('Folder picker unavailable. Paste the folder path into the box instead.')
                    result = {'path': child.stdout.strip()}
                elif path in ('/api/open','/api/reveal','/api/history/open','/api/history/reveal'):
                    if path.startswith('/api/history/'):
                        file = bulk.preview_path(str(body['id']))
                    else:
                        record = engine.record(int(body['id']))
                        file = engine.validate(record, verify_hash=False)
                    if path.endswith('/reveal') and os.name == 'nt':
                        subprocess.Popen(['explorer.exe','/select,',str(file)])
                    elif path.endswith('/reveal') and sys.platform == 'darwin':
                        subprocess.Popen(['open','-R',str(file)])
                    elif path.endswith('/reveal'):
                        subprocess.Popen(['xdg-open',str(file.parent)])
                    elif os.name == 'nt':
                        os.startfile(str(file))
                    elif sys.platform == 'darwin':
                        subprocess.Popen(['open', str(file)])
                    else:
                        subprocess.Popen(['xdg-open', str(file)])
                    result = {'message': 'Opened the original in your image viewer.'}
                elif path == '/api/quit':
                    organizer.cancel.set()
                    bulk.cancel.set()
                    engine.cancel.set()
                    result = {'message': 'App closed. You can close this tab.'}
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    return self.send(404, {'error': 'Not found'})
                self.send(200, result)
            except Exception as e:
                self.send(400, {'error': str(e)})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.bulk = bulk
    server.organizer = organizer
    server.updater = updater
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    state = Path(args.state_dir) if args.state_dir else Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'LocalDuplicateReview'
    state.mkdir(parents=True, exist_ok=True)
    # One app per data directory: prevents two windows moving the same files.
    lock = open(state/'app.lock', 'a+b')
    lock.seek(0)
    lock.write(b'0')
    lock.flush()
    try:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            old_url = (state/'running-url.txt').read_text().strip()
            webbrowser.open(old_url)
        except OSError:
            pass
        print('Media Workbench is already running. Use its existing window.')
        return
    engine = Engine(state)
    server = make_server(engine, args.port)
    # One background check on launch; no periodic network traffic while idle.
    server.updater.start()
    url = f'http://127.0.0.1:{server.server_port}/organizer'
    (state/'running-url.txt').write_text(url)
    print(f'Media Workbench {VERSION}\n{url}\nKeep this window open. Use Quit in the app when finished.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.organizer.cancel.set()
        if server.organizer.thread:
            server.organizer.thread.join(timeout=10)
        server.bulk.cancel.set()
        if server.bulk.thread:
            server.bulk.thread.join(timeout=10)
        engine.cancel.set()
        if engine.thread:
            engine.thread.join(timeout=10)
        server.server_close()
        lock.close()
    if server.updater.restart:
        from updater import active_program
        program=active_program(state)
        if program:os.execv(sys.executable,[sys.executable,str(program),*sys.argv[1:]])


if __name__ == '__main__':
    main()
