"""Offline stage-label data. Imports never change the game's fact vocabulary."""
from __future__ import annotations
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import zipfile

DATA = Path(__file__).with_name('stage-data')
MAX_BYTES = 32 * 1024 * 1024
CLIENT_LED_ORAL = 'throat_fuck__worker_receives'
CONDITIONS = {
    'meeting.arrival': {'activity_id'},
    'meeting.stage': {'stage_index', 'stage_count', 'activity_id'},
    'meeting.finishing': {'activity_id', 'outcome_id'},
    'meeting.cleanup': {'activity_id', 'outcome_id'},
    'meeting.complete': {'activity_id', 'outcome_id'},
}
FALLBACKS = {
    'meeting.arrival': '{worker} welcomes a customer',
    'meeting.stage': '{worker} continues the session',
    'meeting.finishing': '{worker} wraps things up',
    'meeting.cleanup': '{worker} cleans up',
    'meeting.complete': '{worker} finishes the booking',
}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Invalid JSON number: ' + value)


def read_json(raw):
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_object,
                          parse_constant=_constant)
    except (UnicodeError, RecursionError, json.JSONDecodeError):
        raise ValueError('Choose a valid UTF-8 JSON label pack.') from None


@lru_cache(maxsize=2)
def catalog(*, original=False):
    """Legacy saves use the supplied vocabulary. New writing also sees game additions."""
    vocabulary = read_json((DATA / 'catalog.json').read_bytes())
    if not original:
        vocabulary['activities'][CLIENT_LED_ORAL] = 'Throat fuck (client-led oral activity).'
    return vocabulary


def valid_text(text):
    return (isinstance(text, str) and 0 < len(text.strip()) <= 512
            and text.count('{worker}') == 1
            and not any(c in text.replace('{worker}', '') for c in '{}')
            and not any(ord(c) < 32 or ord(c) == 127 or c in '\u2028\u2029' for c in text))


def valid_fact(key, value):
    if key in ('stage_index', 'stage_count'):
        return type(value) is int and value > 0
    if key in ('activity_id', 'outcome_id'):
        return isinstance(value, str) and value in catalog()[
            'activities' if key == 'activity_id' else 'outcomes']
    return False


def matches(when, facts):
    """Unknown, missing and null facts never satisfy an explicit condition."""
    return all(valid_fact(k, facts.get(k)) and type(facts[k]) is type(v)
               and facts[k] == v for k, v in when.items())


class LabelPack:
    def __init__(self, raw):
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError('Label packs must be between 1 byte and 32 MB.')
        pack = read_json(raw)
        if not isinstance(pack, dict) or set(pack) != {'format', 'version', 'entries'}:
            raise ValueError('Expected a stage-label pack with format, version and entries.')
        if pack['format'] != 'after-hours-stage-labels' or type(pack['version']) is not int or pack['version'] not in (1, 2):
            raise ValueError('Supported stage-label pack versions are 1 and 2.')
        if not isinstance(pack['entries'], list) or not 1 <= len(pack['entries']) <= 100000:
            raise ValueError('A label pack needs 1–100,000 entries.')
        ids, counts, warnings = set(), Counter(), []
        self.groups = defaultdict(dict)
        for entry in pack['entries']:
            if not isinstance(entry, dict) or set(entry) != {'id', 'slot', 'when', 'text'}:
                raise ValueError('Each label needs exactly id, slot, when and text.')
            ident, slot, when = entry['id'], entry['slot'], entry['when']
            if not isinstance(ident, str) or not ident.strip() or len(ident) > 128 or ident in ids:
                raise ValueError('Every label needs a unique ID of 1–128 characters.')
            ids.add(ident)
            if not isinstance(slot, str) or slot not in CONDITIONS or not isinstance(when, dict):
                raise ValueError(ident + ': unknown slot or invalid conditions.')
            allowed = CONDITIONS[slot] if pack['version'] == 2 else (
                {'stage_index', 'stage_count'} if slot == 'meeting.stage' else set())
            if set(when) - allowed or any(not valid_fact(k, v) for k, v in when.items()):
                raise ValueError(ident + ': unsupported condition or unregistered identifier.')
            if when.get('stage_index', 1) > when.get('stage_count', when.get('stage_index', 1)):
                raise ValueError(ident + ': stage_index exceeds stage_count.')
            if not valid_text(entry['text']):
                raise ValueError(ident + ': use one {worker}, no other tokens, and one line of text (up to 512 characters).')
            count = len(entry['text'].split())
            if not 2 <= count <= 6:
                warnings.append({'id': ident, 'words': count})
            counts[slot] += 1
            key = tuple(sorted(when.items()))
            self.groups[slot].setdefault(key, []).append(entry)
        # File order cannot alter a seeded variation choice.
        for groups in self.groups.values():
            for entries in groups.values():
                entries.sort(key=lambda e: e['id'])
        self.raw = raw
        self.digest = hashlib.sha256(raw).hexdigest()
        self.summary = {'version': pack['version'], 'entries': len(ids),
                        'counts': dict(counts), 'length_warnings': len(warnings),
                        'sha256': self.digest}

    def choose(self, slot, facts, rng, recent):
        eligible = [entry for conditions, entries in self.groups.get(slot, {}).items()
                    if matches(dict(conditions), facts) for entry in entries]
        pool = [entry for entry in eligible if entry['id'] not in recent] or eligible
        if not pool:
            text = FALLBACKS[slot]
            if slot == 'meeting.stage' and facts.get('activity_id') == CLIENT_LED_ORAL:
                text = '{worker} · Throat fuck'
            return {'id': None, 'text': text, 'pack': None}
        selected = rng.choice(sorted(pool, key=lambda e: e['id']))
        return {'id': selected['id'], 'text': selected['text'], 'pack': self.digest}


def load_upload(raw):
    """Read only the named JSON member; never extract or execute ZIP contents."""
    if len(raw) > MAX_BYTES:
        raise ValueError('The label upload exceeds 32 MB.')
    if raw.startswith(b'PK'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                files = [i for i in archive.infolist() if i.filename == 'stage-labels.json']
                if len(archive.infolist()) > 64 or len(files) != 1 or files[0].file_size > MAX_BYTES:
                    raise ValueError('The ZIP needs one stage-labels.json file no larger than 32 MB.')
                with archive.open(files[0]) as source:
                    raw = source.read(MAX_BYTES + 1)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise ValueError('Unable to read this label ZIP.') from None
    return LabelPack(raw)


@lru_cache(maxsize=1)
def bundled():
    return LabelPack((DATA / 'stage-labels.json').read_bytes())
