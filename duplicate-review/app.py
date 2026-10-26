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
    bulk_html = (Path(__file__).parent / 'bulk' / 'ui.html').read_text(encoding='utf-8')

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
            if url.path == '/':
                return self.send(200, html.replace('__TOKEN__', token).replace('__VERSION__', VERSION).encode(), 'text/html; charset=utf-8')
            if self.headers.get('X-Review-Token') != token and params.get('token', [''])[0] != token:
                return self.send(403, {'error': 'Reopen the app using its launcher.'})
            try:
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
            if not self.allowed() or self.headers.get('X-Review-Token') != token:
                return self.send(403, {'error': 'Local access only'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2000000:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(length))
                path = urlparse(self.path).path
                if bulk.current and bulk.current['running'] and path not in ('/api/bulk/cancel','/api/pick','/api/quit'):
                    raise ValueError('Stop the bulk evaluation before changing files or starting another operation.')
                if path == '/api/bulk/start':
                    result = bulk.start(body)
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
        print('Local Duplicate Review is already running. Use its existing window.')
        return
    engine = Engine(state)
    server = make_server(engine, args.port)
    url = f'http://127.0.0.1:{server.server_port}/'
    (state/'running-url.txt').write_text(url)
    print(f'Local Duplicate Review {VERSION}\n{url}\nKeep this window open. Use Quit in the app when finished.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.bulk.cancel.set()
        if server.bulk.thread:
            server.bulk.thread.join(timeout=10)
        engine.cancel.set()
        if engine.thread:
            engine.thread.join(timeout=10)
        server.server_close()
        lock.close()


if __name__ == '__main__':
    main()
