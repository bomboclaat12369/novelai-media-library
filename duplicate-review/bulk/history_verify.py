"""Strict verification of an existing history queue; no inventory or matching pass."""
import copy
import json
from functools import lru_cache
from pathlib import Path
import threading
import time

import same_photo
from engine import sha256, stat_key
from .history_matching import RECIPE


def save_job(work, db):
    db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)',
               (work.current['id'], time.time(), json.dumps(work.current)))


def start(work, body):
    with work.engine.lock, work.lock:
        current = work.current
        if not current or body.get('job') != current['id'] or current['running'] or work.engine.status['running']:
            raise ValueError('Evaluation changed or another operation is running.')
        if current.get('history_match_recipe') != RECIPE:
            raise ValueError('Prepare duplicate history first. Saved matching results are required.')
        current.pop('error', None)
        current.update(running=True, history_verifying=True, interrupted=False)
        current.setdefault('history_verified', {})
        current['history_verification'] = {'started': True, 'checked': 0, 'linked_files': 0}
        work.cancel.clear()
        work.update(phase='Verifying saved duplicate candidates', done=0, total=0)
        work.persist()
        work.thread = threading.Thread(target=run, args=(work,), daemon=True)
        work.thread.start()
        return work.status()


def run(work):
    report = work.current['history_verification']
    checked = work.current['history_verified']
    catalog = work.current['source_catalog']
    # Decode only the saved candidate pairs, keeping a small bounded image cache.
    @lru_cache(maxsize=12)
    def prepared(path):
        return same_photo.prepare(Path(path))

    validated = {}
    def validate(item):
        path = Path(item['path'])
        stamp = stat_key(path)
        if stamp != item['stamp']:
            raise ValueError('File changed since inventory; connection left unresolved.')
        key = (str(path), stamp, item['sha'])
        if key not in validated:
            if sha256(path) != item['sha']:
                raise ValueError('File contents changed; connection left unresolved.')
            validated[key] = True
        return path

    try:
        with work.db() as db:
            statuses = dict(db.execute('SELECT sha,status FROM origin_review'))
        with work.engine.db() as db:
            separated = {tuple(row) for row in db.execute('SELECT a,b FROM separations')}
        families = {}
        for item in catalog.values():
            if item.get('quarantine_only') and statuses.get(item['sha'], 'pending') == 'pending':
                families.setdefault(item['sha'], []).append(item)
        work.update(total=len(families))
        for at, (digest, rows) in enumerate(sorted(families.items())):
            work.check()
            linked = False
            errors = []
            candidates = work.current.get('history_matches', {}).get(digest, [])
            for candidate in candidates:
                work.check()
                keeper = catalog.get(candidate['id'])
                if not keeper or keeper.get('quarantine_only') or tuple(sorted((digest, keeper['sha']))) in separated:
                    continue
                try:
                    paths = [validate(row) for row in rows]
                    keeper_path = validate(keeper)
                    with work.db() as db:
                        cached = db.execute('SELECT accepted FROM aliases WHERE target=? AND keeper=? AND recipe=?',
                                            (digest, keeper['sha'], same_photo.VERSION)).fetchone()
                    if cached is None:
                        accepted = bool(same_photo.verify(prepared(str(paths[0])), prepared(str(keeper_path))))
                        # Validation must still hold after the expensive verification.
                        for item in rows + [keeper]:
                            validate(item)
                        with work.db() as db:
                            db.execute('INSERT OR REPLACE INTO aliases VALUES (?,?,?,?)',
                                       (digest, keeper['sha'], same_photo.VERSION, int(accepted)))
                    else:
                        accepted = bool(cached[0])
                    work.check()
                    if not accepted:
                        continue
                    with work.lock, work.db() as db:
                        # Journal and saved catalog are committed together, one connection at a time.
                        undo = work.current.get('origin_undo')
                        if not undo or undo.get('kind') != 'auto':
                            undo = {'kind': 'auto', 'keepers': {}, 'rows': [], 'priors': {},
                                    'previous': copy.deepcopy(undo), 'checked_previous': {}}
                            work.current['origin_undo'] = undo
                        undo['keepers'].setdefault(keeper['id'], copy.deepcopy(keeper))
                        undo['rows'].extend(copy.deepcopy(rows))
                        undo['checked_previous'][digest] = checked.get(digest)
                        prior = db.execute('SELECT keeper,created FROM confirmed_origins WHERE target=?', (digest,)).fetchone()
                        undo['priors'][digest] = prior
                        db.execute('INSERT OR REPLACE INTO confirmed_origins VALUES (?,?,?)', (digest, keeper['sha'], time.time()))
                        for row in rows:
                            keeper['sources'].update(row['sources'])
                            keeper['origins'].extend(row['origins'])
                            keeper.setdefault('copies', []).append({'path': row['path'], 'sha': digest,
                                'quarantine': True, 'reference': False, 'proof': 'verified saved history candidate'})
                            del catalog[row['id']]
                        if keeper['id'] in work.current.get('items', {}):
                            work.current['items'][keeper['id']] = copy.deepcopy(keeper)
                        work.current['inventory']['unlinked_quarantine'] -= len(rows)
                        report['linked_files'] += len(rows)
                        checked[digest] = 'linked'
                        save_job(work, db)
                    linked = True
                    break
                except InterruptedError:
                    raise
                except (OSError, ValueError) as exc:
                    errors.append(str(exc))
            if not linked:
                checked[digest] = 'error' if errors else 'needs_review'
                if errors:
                    work.issue(rows[0]['path'], 'Saved-match verification: ' + errors[0])
            report['checked'] = at + 1
            work.update(done=at + 1)
            work.persist()
        work.update(phase='Saved-match verification complete')
    except InterruptedError:
        work.update(phase='Saved-match verification paused. Verify saved matches to resume.')
    except Exception as exc:
        work.update(phase='Saved-match verification stopped: ' + str(exc))
    finally:
        prepared.cache_clear()
        work.update(running=False, history_verifying=False)
        work.persist()


def undo_batch(work, undo):
    catalog = work.current['source_catalog']
    with work.db() as db:
        for digest, prior in undo['priors'].items():
            db.execute('DELETE FROM confirmed_origins WHERE target=?', (digest,))
            if prior:
                db.execute('INSERT INTO confirmed_origins VALUES (?,?,?)', (digest, *prior))
            # Do not leave an accepted cache entry that silently reapplies an undone batch on refresh.
            db.execute('DELETE FROM aliases WHERE target=? AND recipe=?', (digest, same_photo.VERSION))
            previous = undo['checked_previous'].get(digest)
            if previous is None:
                work.current.get('history_verified', {}).pop(digest, None)
            else:
                work.current['history_verified'][digest] = previous
        for ident, keeper in undo['keepers'].items():
            catalog[ident] = keeper
            if ident in work.current.get('items', {}):
                work.current['items'][ident] = copy.deepcopy(keeper)
        for row in undo['rows']:
            catalog[row['id']] = row
        work.current['inventory']['unlinked_quarantine'] += len(undo['rows'])
        if undo['previous']:
            work.current['origin_undo'] = undo['previous']
        else:
            work.current.pop('origin_undo', None)
        work.current['history_verification'] = {'started': True, 'checked': 0, 'linked_files': 0}
        save_job(work, db)
    return {**work.status(), 'restored_target': undo['rows'][0]['sha']}
