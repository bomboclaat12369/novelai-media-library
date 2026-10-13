"""Local companion transport. Images never leave the computer."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler


class LibraryClient:
    def __init__(self, port=8765):
        self.base = f'http://127.0.0.1:{int(port)}'
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, body=None, raw=False):
        if body is not None and not raw:
            body = json.dumps(body).encode()
        request = Request(self.base + path, data=body,
                          headers={'Content-Type': 'application/octet-stream' if raw else 'application/json'})
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                message = json.load(error).get('error', str(error))
            except Exception:
                message = str(error)
            raise ValueError(message) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ValueError('Cannot reach the media companion. Start or restart it, then retry. The action may have completed; use Resume or Undo if it was interrupted.') from error

    def catalog(self, character_id=''):
        health = self.request('/api/health')
        if not health.get('duplicate_review'):
            raise ValueError('Update and restart the media companion to enable library comparison (runtime 2.7.36 or later).')
        result = self.request('/api/duplicate-review/catalog?' + urlencode({'character_id': character_id}))
        if result.get('coverage_version', 0) < 2:
            raise ValueError('Update and restart the media companion (2.7.38 or later) to verify Main, Sets, Review and Purgatory coverage.')
        return result

    def operation(self, operation, library_id):
        return self.request('/api/duplicate-review/operation?' + urlencode(dict(operation=operation, library_id=library_id)))

    def replace(self, payload, **fields):
        return self.request('/api/duplicate-review/replace?' + urlencode(fields), payload, raw=True)

    def undo(self, operation, library_id):
        return self.request('/api/duplicate-review/undo', dict(operation=operation, library_id=library_id))

    def item(self, media_id, library_id):
        return self.request('/api/duplicate-review/item?' + urlencode(dict(media_id=media_id, library_id=library_id)))

    def cleanup(self, operation, library_id, selection):
        return self.request('/api/duplicate-review/cleanup', dict(operation=operation, library_id=library_id, selection=selection))

    def cleanup_undo(self, operation, library_id):
        return self.request('/api/duplicate-review/cleanup-undo', dict(operation=operation, library_id=library_id))
