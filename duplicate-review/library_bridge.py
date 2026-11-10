"""Local companion transport. Images never leave the computer."""
import json
import errno
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler


class LibraryClient:
    JSON_LIMIT = 24 * 1024 * 1024

    def __init__(self, port=8765):
        self.base = f'http://127.0.0.1:{int(port)}'
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, body=None, raw=False):
        route = path.split('?', 1)[0]
        operation = {'/api/organizer/preview': 'Import preview', '/api/organizer/import': 'Copying an import',
                     '/api/organizer/apply': 'Applying imports'}.get(route, 'Media Library request')
        if body is not None and not raw:
            body = json.dumps(body, separators=(',', ':')).encode()
            if len(body) > self.JSON_LIMIT:
                raise ValueError(f'{operation} is too large for the companion ({len(body)/1024/1024:.1f} MB; limit 24 MB). '
                                 'The request was not sent. Reduce the selected import batch and retry.')
        timeout = 180 if path.startswith(('/api/checkpoints/', '/api/organizer/')) else 30
        request = Request(self.base + path, data=body,
                          headers={'Content-Type': 'application/octet-stream' if raw else 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                message = json.load(error).get('error', str(error))
            except Exception:
                message = str(error)
            raise ValueError(message) from error
        except (URLError, TimeoutError, OSError) as error:
            reason = getattr(error, 'reason', error)
            if isinstance(reason, TimeoutError):
                message = f'{operation}: the companion did not respond within {timeout} seconds.'
            elif getattr(reason, 'errno', None) in (errno.ECONNREFUSED, 10061):
                message = f'{operation}: no companion is accepting connections at {self.base}. Open or restart the Media Library companion.'
            elif isinstance(reason, (ConnectionError, BrokenPipeError)):
                message = f'{operation}: the companion closed the connection before replying. It may have rejected the request or restarted.'
            else:
                message = f'{operation}: the companion connection failed ({reason}).'
            if route == '/api/organizer/preview':
                message += ' No images were imported by this preview. Retry the preview.'
            elif body is not None:
                message += ' The change may have completed. Refresh before retrying; imports can be resumed from a fresh preview.'
            raise ValueError(message) from error

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
