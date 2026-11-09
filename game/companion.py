"""Local companion route adapter. Game access never constructs a LibraryStore."""
from __future__ import annotations
import threading
from .server import Handler, build_server

_lock=threading.RLock()


def dispatch(handler):
    """Serve /game through an existing companion HTTP listener, isolated state."""
    if handler.path.split('?',1)[0] not in ('/game','/game/') and not handler.path.startswith('/game/'):
        return False
    if handler.headers.get('Host') not in {f'127.0.0.1:{handler.server.server_port}',f'localhost:{handler.server.server_port}'}:
        handler._send_json(403,{'error':'Host not allowed.'})
        return True
    with _lock:
        if not hasattr(handler.server,'after_hours'):
            root=handler.server.store.root
            # build_server resolves stable library identity and active-restore pointer.
            service=build_server(0,library=root,save=None)
            service.server_close()
            service.server_port=handler.server.server_port
            handler.server.after_hours=service
    proxy=Handler.__new__(Handler)
    proxy.__dict__.update(handler.__dict__)
    proxy.server=handler.server.after_hours
    if handler.command=='GET':proxy.do_GET()
    elif handler.command=='POST':proxy.do_POST()
    else:proxy.send(405,{'error':'Method not allowed.'})
    return True
