"""Source identity is independent of batch folders, dates and quarantine move IDs."""
import re
from pathlib import PureWindowsPath, PurePosixPath

POST = re.compile(r'(?:^|\s)Post\s+(\d+)(?:\s|$)', re.I)
SHORTCODE = re.compile(r'^[A-Za-z0-9_-]{8,32}$')
QUARANTINE = '_Duplicate_Review_Quarantine'


def source_of(path, forum='smg', owner=''):
    parts = list((PureWindowsPath(path) if '\\' in str(path) else PurePosixPath(path)).parts)
    quarantine = next((i for i, p in enumerate(parts) if p.casefold() == QUARANTINE.casefold()), None)
    if quarantine is not None:
        # Only strip the quarantine wrapper. Keep the original ancestry intact.
        parts = parts[:quarantine] + parts[quarantine + 2:]
    original = str((PureWindowsPath if '\\' in str(path) else PurePosixPath)(*parts))
    locations = {'original_path': original, 'quarantine_path': str(path)} if quarantine is not None else {}
    parent = parts[:-1]
    for part in reversed(parent):
        match = POST.search(part)
        if match:
            return {'key': 'forum:' + forum.strip().casefold() + ':' + match[1],
                    'kind': 'forum', 'label': part, 'post_id': match[1],
                    'path': str(path), 'quarantine': quarantine is not None, **locations}
    for i, part in enumerate(parent):
        if re.search(r'(?:^|[\s_-])(ig|instagram)(?:$|[\s_-])', part, re.I) and i + 2 < len(parent):
            user, post = parent[i+1:i+3]
            if SHORTCODE.fullmatch(post):
                return {'key': 'instagram:' + user.casefold() + ':' + post,
                        'kind': 'instagram', 'label': user + ' / ' + post,
                        'post_id': post, 'path': str(path), 'quarantine': quarantine is not None, **locations}
    # Unknown folders remain auditable but receive NO same-post boost.
    return {'key': 'folder:' + owner + ':' + '/'.join(parent).casefold(), 'kind': 'folder',
            'label': parent[-1] if parent else 'Unknown source', 'post_id': None,
            'path': str(path), 'quarantine': quarantine is not None, **locations}
