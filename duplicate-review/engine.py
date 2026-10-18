"""Local Duplicate Review — scanning and reversible, explicitly approved moves."""
from __future__ import annotations
import hashlib
from contextlib import contextmanager
import json
import re
from datetime import date
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
import warnings
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

# Fingerprinting is tiny; extra BLAS threads waste CPU and hurt desktop responsiveness.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np
from PIL import Image, ImageOps
from library_bridge import LibraryClient
import crop_match
import same_photo
from search_index import SearchIndexes

VERSION = '1.7.3'
ALGORITHM = 1
QUARANTINE = '_Duplicate_Review_Quarantine'
EXTENSIONS = {'.jpg', '.jpeg', '.jpe', '.jfif', '.png', '.webp', '.bmp', '.tif', '.tiff', '.avif', '.gif'}
# Turn the decoder's large-image warning into a per-file error, never a crash.
warnings.simplefilter('error', Image.DecompressionBombWarning)
DCT = np.cos(np.pi / 32 * (np.arange(32) + .5)[None, :] * np.arange(8)[:, None])
MASK = np.ones((32, 32), dtype=bool)
MASK[23:, 23:] = False
MODES = {'strict': (6, .995, 10), 'balanced': (9, .985, 16), 'broad': (12, .965, 23)}


def canonical(path):
    return Path(path).expanduser().resolve()


def inside(path, root):
    return path == root or root in path.parents


def stat_key(path):
    st = path.stat()
    return f'{st.st_size}:{st.st_mtime_ns}:{st.st_ctime_ns}:{st.st_ino}'


def linked(path):
    # Reparse-point detection also works on Python 3.11 (before Path.is_junction).
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def sha256(path, cancel=None):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            if cancel is not None and cancel.is_set():
                raise InterruptedError('Scan cancelled')
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            value.update(chunk)
    return value.hexdigest()


def load_image(path, size=1800):
    with Image.open(path) as original:
        if getattr(original, 'n_frames', 1) > 1:
            raise ValueError('Animated or multi-page image: skipped')
        w, h = original.size
        orientation = original.getexif().get(274, 1)
        if orientation in (5, 6, 7, 8):
            w, h = h, w
        original.draft('RGB', (size, size))
        original.thumbnail((size, size), Image.Resampling.LANCZOS)
        im = ImageOps.exif_transpose(original)
        # Use the same white matte for every image with transparency.
        rgba = im.convert('RGBA')
        rgb = Image.new('RGB', rgba.size, 'white')
        rgb.paste(rgba, mask=rgba.getchannel('A'))
        return rgb, w, h


def pixel_digest(path):
    """Full-resolution decoded pixels, never a thumbnail or similarity score."""
    with Image.open(path) as original:
        if getattr(original, 'n_frames', 1) > 1:
            raise ValueError('Animated or multi-page image: skipped')
        image = ImageOps.exif_transpose(original)
        if image.mode in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA'):
            image = image.convert('RGBA')
        digest = hashlib.sha256()
        digest.update(f'{image.mode}:{image.width}:{image.height}'.encode())
        # Color profiles and display interpretation must agree as well.
        digest.update(original.info.get('icc_profile', b''))
        digest.update(repr([original.info.get(k) for k in ('gamma','srgb','chromaticity')]).encode())
        for y in range(0, image.height, 64):
            digest.update(image.crop((0,y,image.width,min(image.height,y+64))).tobytes())
        return digest.hexdigest()


def folder_rank(record):
    parent = Path(record['path']).parent
    newest = 0
    for component in reversed(parent.parts):
        match = re.search(r'(?<!\d)((?:19|20)\d{2})[-_](\d{2})[-_](\d{2})(?!\d)', component)
        if match:
            try:
                newest = date(*map(int, match.groups())).toordinal()
                break
            except ValueError:
                pass
    natural = tuple((1,int(t)) if t.isdigit() else (0,t.casefold())
                    for t in re.split(r'(\d+)', str(parent)))
    return newest, natural


def preferred(records):
    # Stable highest-folder ordering, followed by reference protection.
    ordered = sorted(sorted(records,key=lambda r:(r['path'].casefold(),r['path'])), key=folder_rank, reverse=True)
    return sorted(ordered, key=lambda r:not r['reference'])


def phash(rgb):
    gray = np.asarray(Image.fromarray(rgb).convert('L'), dtype=float)
    values = (DCT @ gray @ DCT.T).ravel()[1:]
    median = np.median(values)
    out = 0
    for value in values:
        out = (out << 1) | int(value > median)
    return out


def fingerprint(path):
    im, w, h = load_image(path, 256)
    small = np.asarray(im.resize((32, 32), Image.Resampling.LANCZOS))
    masked = small.copy()
    masked[~MASK] = np.median(small[MASK], axis=0)
    return w, h, str(phash(small)), str(phash(masked)), small.tobytes()


class BKTree:
    """Hamming-distance index; identical hashes share one node."""
    def __init__(self):
        self.root = None

    def add(self, key, value):
        if self.root is None:
            self.root = [key, [value], {}]
            return
        node = self.root
        while True:
            distance = (key ^ node[0]).bit_count()
            if not distance:
                node[1].append(value)
                return
            child = node[2].get(distance)
            if child is None:
                node[2][distance] = [key, [value], {}]
                return
            node = child

    def query(self, key, radius):
        stack = [self.root] if self.root else []
        while stack:
            node = stack.pop()
            distance = (key ^ node[0]).bit_count()
            if distance <= radius:
                yield from node[1]
            stack.extend(child for edge, child in node[2].items()
                         if distance - radius <= edge <= distance + radius)


def similarity(a, b, mode):
    radius, min_corr, max_error = MODES[mode]
    if abs((a['w']/a['h'])/(b['w']/b['h'])-1) > .03:
        return None
    if min((int(a['ph']) ^ int(b['ph'])).bit_count(),
           (int(a['mh']) ^ int(b['mh'])).bit_count()) > radius:
        return None
    x = np.frombuffer(a['sketch'], dtype=np.uint8).reshape(32, 32, 3).astype(float)
    y = np.frombuffer(b['sketch'], dtype=np.uint8).reshape(32, 32, 3).astype(float)
    best = None
    for mask, label in ((np.ones((32, 32), dtype=bool), 'Visual match'),
                        (MASK, 'Visual match · corner ignored')):
        xx, yy = x[mask], y[mask]
        gx, gy = xx.mean(axis=1), yy.mean(axis=1)
        # Flat images are too ambiguous for visual matching (exact matching still works).
        if min(gx.std(), gy.std()) < 6:
            continue
        corr = float(np.dot(gx-gx.mean(), gy-gy.mean()) /
                     (np.linalg.norm(gx-gx.mean()) * np.linalg.norm(gy-gy.mean())))
        err = float(np.abs(xx-yy).mean())
        if corr >= min_corr and err <= max_error:
            score = round(100 * max(0, min(1, corr - err / 2550)), 1)
            if best is None or score > best[0]:
                best = (score, label)
    return best


def pair_key(a, b):
    # Decisions apply to these particular paths and contents, not every identical file.
    parts = sorted([a['path']+'\0'+a['sha'], b['path']+'\0'+b['sha']])
    return hashlib.sha256('\n'.join(parts).encode()).hexdigest()


class Engine:
    def __init__(self, state_dir):
        self.state_dir = canonical(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.database = self.state_dir / 'review.sqlite3'
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.status = {'running': False, 'phase': 'Ready', 'done': 0, 'total': 0, 'errors': 0}
        self.thread = None
        self.revision = 0
        self.groups_cache = None
        self.verified_plan = None
        self.exact_plan = None
        self.library = LibraryClient()
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cache(path TEXT PRIMARY KEY, stamp TEXT, algorithm INTEGER,
                    sha TEXT, w INTEGER, h INTEGER, ph TEXT, mh TEXT, sketch BLOB, size INTEGER);
                CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, path TEXT UNIQUE, stamp TEXT,
                    sha TEXT, w INTEGER, h INTEGER, size INTEGER, reference INTEGER, root TEXT, moved INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS pairs(id INTEGER PRIMARY KEY, a INTEGER, b INTEGER,
                    kind TEXT, score REAL, decision TEXT, key TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS ignored(key TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS moves(id TEXT PRIMARY KEY, src TEXT, dst TEXT,
                    sha TEXT, state TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS errors(path TEXT, message TEXT);
                CREATE TABLE IF NOT EXISTS features(path TEXT PRIMARY KEY, stamp TEXT, version INTEGER, data BLOB);
                CREATE TABLE IF NOT EXISTS aligned_tasks(key TEXT PRIMARY KEY, results TEXT);
                CREATE TABLE IF NOT EXISTS verified_copies(key TEXT PRIMARY KEY, accepted INTEGER);
                CREATE TABLE IF NOT EXISTS separations(a TEXT, b TEXT, PRIMARY KEY(a,b));
                CREATE TABLE IF NOT EXISTS group_links(a TEXT, b TEXT, PRIMARY KEY(a,b));
                CREATE TABLE IF NOT EXISTS keeps(path TEXT, sha TEXT, PRIMARY KEY(path,sha));
                CREATE TABLE IF NOT EXISTS library_cleanups(operation TEXT PRIMARY KEY, payload TEXT, state TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS replacements(operation TEXT PRIMARY KEY, payload TEXT, state TEXT, created REAL);
            ''')
            if 'batch' not in {r[1] for r in db.execute('PRAGMA table_info(moves)')}:
                db.execute('ALTER TABLE moves ADD COLUMN batch TEXT')
            for table in ('cache','files'):
                if 'pixel' not in {r[1] for r in db.execute(f'PRAGMA table_info({table})')}:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN pixel TEXT')
            if 'library' not in {r[1] for r in db.execute('PRAGMA table_info(files)')}:
                db.execute('ALTER TABLE files ADD COLUMN library TEXT')
        self.recover_moves()

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def config(self):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='config'").fetchone()
        return json.loads(row[0]) if row else {'incoming': [], 'reference': [], 'mode': 'balanced'}

    def set_status(self, **kwargs):
        with self.lock:
            self.status.update(kwargs)

    def start(self, incoming, reference, mode, library_character='', library_id='', workers=8, scan_kind='folders'):
        with self.lock:
            if self.status['running']:
                raise ValueError('A scan is already running.')
            with self.db() as db:
                if db.execute("SELECT 1 FROM replacements WHERE state NOT IN ('complete','undone','cancelled')").fetchone():
                    raise ValueError('Resume or undo the unfinished replacement before starting a new scan.')
                if db.execute("SELECT 1 FROM library_cleanups WHERE state='pending'").fetchone():
                    raise ValueError('Resume or undo the unfinished library cleanup before scanning.')
            if scan_kind not in ('folders', 'library'):
                raise ValueError('Choose a scan type.')
            if scan_kind == 'library':
                incoming, reference = [], []
                if not library_character:
                    raise ValueError('Connect to the companion and choose All characters or a character.')
            if mode not in MODES:
                raise ValueError('Choose a matching sensitivity.')
            workers = max(1,min(32,int(workers)))
            incoming = list(dict.fromkeys(str(canonical(p)) for p in incoming if p.strip()))
            reference = list(dict.fromkeys(str(canonical(p)) for p in reference if p.strip()))
            if not incoming and scan_kind != 'library':
                raise ValueError('Add at least one incoming folder.')
            catalog = self.library.catalog(library_character) if library_character else None
            if scan_kind == 'library' and not (catalog or {}).get('library_cleanup'):
                raise ValueError('Restart the media companion to install library duplicate cleanup (2.7.40 or later).')
            if catalog:
                if catalog['library_id'] != library_id:
                    raise ValueError('The active library changed. Connect again before scanning.')
                root = canonical(catalog['root'])
                if any(inside(canonical(p), root) or inside(root, canonical(p)) for p in incoming):
                    raise ValueError('Choose an incoming folder outside the media library.')
                reference = [p for p in reference if not inside(canonical(p), root)]
            for p in incoming + reference:
                if not Path(p).is_dir():
                    raise ValueError('Folder not found: '+p)
                if QUARANTINE in Path(p).parts:
                    raise ValueError('Quarantine folders cannot be scanned.')
            for p in incoming:
                if any(inside(Path(p), Path(r)) for r in reference):
                    raise ValueError('An incoming folder is inside a reference folder. Choose separate folders.')
            self.exact_plan = None
            self.cancel.clear()
            self.invalidate_groups()
            self.status = {'running': True, 'phase': 'Finding images', 'done': 0, 'total': 0, 'errors': 0}
            config = {'incoming': incoming, 'reference': reference, 'mode': mode,
                      'library_character': library_character, 'library_id': library_id if catalog else '',
                      'library_root': catalog['root'] if catalog else '', 'workers':workers, 'scan_kind':scan_kind}
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO settings VALUES ('config', ?)", (json.dumps(config),))
                db.execute('DELETE FROM files')
                db.execute('DELETE FROM pairs')
                db.execute('DELETE FROM errors')
                db.execute("DELETE FROM settings WHERE key='coverage'")
            self.thread = threading.Thread(target=self.scan, args=(config, catalog), daemon=True)
            self.thread.start()

    def discover(self, config, catalog=None):
        seen = set()
        files = []
        reference = [Path(p) for p in config['reference']]
        library_root = canonical(catalog['root']) if catalog else None
        for item in (catalog or {}).get('files', []):
            path = canonical(item['path'])
            if path in seen:
                continue
            if not inside(path, library_root):
                raise ValueError('Library catalog contains a path outside the library')
            seen.add(path)
            files.append((path, True, library_root))
        # Reference priority even where trees overlap. Never follow junctions or symlinks.
        roots = [(Path(p), True) for p in config['reference']]+[(Path(p), False) for p in config['incoming']]
        for root, is_ref in roots:
            for base, dirs, names in os.walk(root, followlinks=False, onerror=lambda e: self.error(str(root), str(e))):
                if self.cancel.is_set():
                    raise InterruptedError()
                dirs[:] = sorted(d for d in dirs if d != QUARANTINE and not linked(Path(base)/d)
                                 and not (library_root and inside(canonical(Path(base)/d), library_root)))
                for name in sorted(names):
                    path = Path(base) / name
                    if path.suffix.lower() in {'.heic','.heif','.jxl','.svg','.raw','.dng'}:
                        self.error(path,'Unsupported image format; not compared. Convert a copy to PNG/JPEG before checking.')
                        continue
                    if path.suffix.lower() not in EXTENSIONS:
                        continue
                    if linked(path):
                        self.error(path,'Linked image skipped; select its real folder to compare it.')
                        continue
                    try:
                        p = canonical(path)
                        if library_root and inside(p, library_root):
                            continue
                        if p in seen:
                            continue
                        seen.add(p)
                        protected = is_ref or any(inside(p, r) for r in reference)
                        files.append((p, protected, root))
                    except OSError as e:
                        self.error(str(path), str(e))
                self.set_status(total=len(files))
        return files

    def error(self, path, message):
        with self.db() as db:
            db.execute('INSERT INTO errors VALUES (?,?)', (str(path), str(message)))
        with self.lock:
            self.status['errors'] += 1

    def scan(self, config, catalog=None):
        try:
            files = self.discover(config, catalog)
            library_items = {str(canonical(r['path'])):r for r in (catalog or {}).get('files', [])}
            self.set_status(phase='Reading images', total=len(files), done=0)
            records = []
            # One decoder keeps memory/CPU demand predictable; cache makes repeated scans much cheaper.
            with self.db() as db:
                for index, (path, reference, root) in enumerate(files):
                    if self.cancel.is_set():
                        raise InterruptedError()
                    try:
                        stamp = stat_key(path)
                        cached = db.execute('SELECT * FROM cache WHERE path=? AND stamp=? AND algorithm=?',
                                            (str(path), stamp, ALGORITHM)).fetchone()
                        if cached:
                            r = dict(cached)
                        else:
                            digest = sha256(path, self.cancel)
                            w, h, ph, mh, sketch = fingerprint(path)
                            if stamp != stat_key(path):
                                raise ValueError('Changed during scan; run another scan after downloads finish.')
                            r = dict(path=str(path), stamp=stamp, algorithm=ALGORITHM, sha=digest,
                                     w=w, h=h, ph=ph, mh=mh, sketch=sketch, size=path.stat().st_size)
                        if not r.get('pixel'):
                            r['pixel'] = pixel_digest(path)
                            if stamp != stat_key(path):
                                raise ValueError('Changed during scan; run another scan after downloads finish.')
                        db.execute('INSERT OR REPLACE INTO cache(path,stamp,algorithm,sha,w,h,ph,mh,sketch,size,pixel) VALUES (:path,:stamp,:algorithm,:sha,:w,:h,:ph,:mh,:sketch,:size,:pixel)', r)
                        try:
                            feature = db.execute('SELECT data FROM features WHERE path=? AND stamp=? AND version=?',
                                                 (str(path),stamp,crop_match.FEATURE_VERSION)).fetchone()
                            if feature:
                                r['features'] = feature[0]
                            else:
                                image,_,_ = load_image(path, 1000)
                                r['features'] = crop_match.describe(image)
                                if stamp != stat_key(path):
                                    raise ValueError('Changed during scan; scan again after downloads finish.')
                                db.execute('INSERT OR REPLACE INTO features VALUES (?,?,?,?)',
                                           (str(path),stamp,crop_match.FEATURE_VERSION,r['features']))
                        except Exception as error:
                            r['features'] = None
                            db.execute('INSERT INTO errors VALUES (?,?)',(str(path),'Crop analysis unavailable: '+str(error)))
                            with self.lock:
                                self.status['errors'] += 1
                        meta = library_items.get(str(path))
                        if meta and meta['sha'] != r['sha']:
                            raise ValueError('Library source changed during the scan. Scan again.')
                        r.update(reference=reference, root=str(root), library=json.dumps({**meta, 'library_id':catalog['library_id']}) if meta else None)
                        cursor = db.execute('INSERT INTO files(path,stamp,sha,w,h,size,reference,root,pixel,library) VALUES (:path,:stamp,:sha,:w,:h,:size,:reference,:root,:pixel,:library)', r)
                        r['id'] = cursor.lastrowid
                        records.append(r)
                    except InterruptedError:
                        raise
                    except Exception as e:
                        # Use this connection while it owns the write transaction.
                        db.execute('INSERT INTO errors VALUES (?,?)', (str(path), str(e)))
                        with self.lock:
                            self.status['errors'] += 1
                    if index % 50 == 0:
                        db.commit()
                    self.set_status(done=index+1)
                db.commit()
            self.match(records, config['mode'])
            self.match_aligned(records, config['mode'], config.get('workers',8))
            for r in records:
                try:
                    if stat_key(Path(r['path'])) != r['stamp']:
                        self.error(r['path'],'File changed after analysis. Scan again before importing.')
                except OSError as error:
                    self.error(r['path'],'File unavailable after analysis: '+str(error))
            if catalog:
                try:
                    current = self.library.catalog(config['library_character'])
                    before = {(r['id'],r['sha'],r['path']) for r in catalog['files']}
                    after = {(r['id'],r['sha'],r['path']) for r in current['files']}
                    if current['library_id'] != catalog['library_id'] or before != after:
                        self.error('Media library','Library images changed during scanning. Scan again to include the latest files.')
                except Exception as error:
                    self.error('Media library','Could not confirm the final library contents: '+str(error))
            coverage = {'scanned' :len(records),'discovered':len(files),
                        'library_expected':len(library_items), 'library_scanned':sum(bool(r.get('library')) for r in records),
                        'review':sum(bool(json.loads(r['library']).get('in_review')) for r in records if r.get('library')),
                        'purgatory':sum(bool(json.loads(r['library']).get('in_purgatory')) for r in records if r.get('library'))}
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO settings VALUES ('coverage',?)",(json.dumps(coverage),))
            self.invalidate_groups()
            self.set_status(phase='Scan complete' if not self.status['errors'] else
                            f"Scan incomplete · {self.status['errors']} issues — check skipped files")
        except InterruptedError:
            self.set_status(phase='Cancelled — run Scan to build a complete review')
        except Exception as e:
            self.set_status(phase='Scan failed: '+str(e))
        finally:
            self.set_status(running=False)

    def match(self, records, mode):
        self.set_status(phase='Comparing images', done=0, total=len(records))
        trees = [BKTree(), BKTree()]
        by_sha, by_pixel = {}, {}
        # Put protected / larger originals first to make exact groups a compact review list.
        records = preferred(records)
        with self.db() as db:
            ignored = {r[0] for r in db.execute('SELECT key FROM ignored')}
            by_id = {r['id']: r for r in records}
            for index, r in enumerate(records):
                if self.cancel.is_set():
                    raise InterruptedError()
                byte_match = by_sha.get(r['sha'])
                exact = byte_match or by_pixel.get(r.get('pixel'))
                if exact:
                    self.add_pair(db, exact, r, 'Exact bytes' if byte_match else 'Exact pixels', 100, ignored)
                    by_sha.setdefault(r['sha'], r)
                    # Same content only needs one representative in visual indexes.
                else:
                    candidates = set(trees[0].query(int(r['ph']), MODES[mode][0]))
                    candidates.update(trees[1].query(int(r['mh']), MODES[mode][0]))
                    for k in candidates:
                        if self.cancel.is_set():
                            raise InterruptedError()
                        other = by_id[k]
                        result = similarity(r, other, mode)
                        if result:
                            self.add_pair(db, other, r, result[1], result[0], ignored)
                    by_sha[r['sha']] = r
                    if r.get('pixel'):
                        by_pixel[r['pixel']] = r
                    trees[0].add(int(r['ph']), r['id'])
                    trees[1].add(int(r['mh']), r['id'])
                if index % 50 == 0:
                    db.commit()
                self.set_status(done=index+1)
            by_digest = {}
            for r in records:
                by_digest.setdefault(r['sha'], []).append(r)
            for link in db.execute('SELECT a,b FROM group_links').fetchall():
                a, b = by_digest.get(link[0], []), by_digest.get(link[1], [])
                if a and b:
                    self.add_pair(db, a[0], b[0], 'Manually grouped', 0, ignored)
            db.commit()

    def match_aligned(self, records, mode, workers=8):
        """Same retrieval and match thresholds, bounded concurrent verification."""
        import cv2
        workers = max(1,min(int(workers),32,os.cpu_count() or 1))
        unique, identities = [], set()
        for record in preferred(records):
            if not record.get('features'): continue
            identity = record.get('pixel') or record['sha']
            if identity not in identities:
                unique.append(record)
                identities.add(identity)
        @lru_cache(maxsize=2048)
        def feature(i):
            return crop_match.unpack(unique[i]['features'])
        starts = list(range(0,len(unique),256))
        total = sum(max(0,len(unique)-start-1) for start in starts)
        completed, reused = 0, 0
        started = time.monotonic()
        self.set_status(phase='Comparing crops, rotations and mirrors',done=0,total=total,
                        workers=workers,elapsed_seconds=0,eta_seconds=None,cached_tasks=0)
        def progress():
            elapsed = time.monotonic()-started
            active = completed-reused
            remaining = total-completed
            eta = elapsed/active*remaining if active>=10 else None
            self.set_status(done=completed,elapsed_seconds=round(elapsed),
                            eta_seconds=round(eta) if eta is not None else None,cached_tasks=reused)
        with self.db() as db, ThreadPoolExecutor(max_workers=workers,thread_name_prefix='crop') as pool:
            ignored = {r[0] for r in db.execute('SELECT key FROM ignored')}
            for start in starts:
                if self.cancel.is_set(): raise InterruptedError()
                stop = min(start+256,len(unique))
                block_ids = list(range(start,stop))
                signature = hashlib.sha256(json.dumps([unique[i]['sha'] for i in block_ids]).encode()).hexdigest()
                # Cache raw matching results, not review decisions or path-based IDs.
                # Changing a file, mode, block membership/order or matcher version invalidates it.
                jobs = []
                for j in range(start+1,len(unique)):
                    key = hashlib.sha256(json.dumps(['aligned-v2',crop_match.FEATURE_VERSION,mode,
                                                    signature,unique[j]['sha'],min(j-start,256)]).encode()).hexdigest()
                    cached = db.execute('SELECT results FROM aligned_tasks WHERE key=?',(key,)).fetchone()
                    if cached:
                        for i,score,label in json.loads(cached[0]):
                            self.add_pair(db,unique[j],unique[start+i],label,score,ignored)
                        completed += 1; reused += 1
                    else:
                        jobs.append((j,key))
                progress()
                if not jobs: continue
                arrays, owners = [], []
                for i in block_ids:
                    desc = feature(i)['desc']
                    if len(desc):
                        arrays.append(desc); owners.extend([i]*len(desc))
                if not arrays:
                    for j,key in jobs:
                        db.execute('INSERT OR REPLACE INTO aligned_tasks VALUES (?,?)',(key,'[]'))
                    completed += len(jobs); progress(); db.commit(); continue
                descriptors = np.concatenate(arrays)
                owner_array = np.array(owners,dtype=np.int32)
                indexes = SearchIndexes(descriptors, workers)
                def compare(j):
                    if self.cancel.is_set(): raise InterruptedError()
                    query = feature(j)
                    # Independent copies share identical trees, allowing concurrent
                    # searches without concurrent access to a single native index.
                    with indexes.acquire() as index:
                        choices = [(mirrored,crop_match.candidates(query['mirror_desc' if mirrored else 'desc'],index,owner_array))
                                   for mirrored in (False,True)]
                    results, found = [], set()
                    for mirrored, candidates in choices:
                        for i in candidates:
                            if self.cancel.is_set(): raise InterruptedError()
                            if i>=j or i in found: continue
                            result = crop_match.verify(query,feature(i),mode,mirrored)
                            if result:
                                found.add(i);results.append([i-start,result[0],result[1]])
                    return results
                pending = {}
                iterator = iter(jobs)
                committed = time.monotonic()
                try:
                    while True:
                        if self.cancel.is_set(): raise InterruptedError()
                        while len(pending)<workers*2:
                            job = next(iterator,None)
                            if job is None: break
                            j,key = job
                            pending[pool.submit(compare,j)] = (j,key)
                        if not pending: break
                        ready,_ = wait(pending,timeout=.25,return_when=FIRST_COMPLETED)
                        for future in ready:
                            j,key = pending.pop(future)
                            matches = future.result()
                            db.execute('INSERT OR REPLACE INTO aligned_tasks VALUES (?,?)',(key,json.dumps(matches)))
                            for i,score,label in matches:
                                self.add_pair(db,unique[j],unique[start+i],label,score,ignored)
                            completed += 1
                        progress()
                        # Avoid a disk flush for every worker completion. Keep the
                        # durable checkpoint delay below half a second while running.
                        if ready and time.monotonic()-committed >= .5:
                            db.commit()
                            committed = time.monotonic()
                finally:
                    # Workers must finish before releasing this block's index or rebinding closures.
                    for future in pending: future.cancel()
                    if pending: wait(pending)
                    indexes.close()
                    # Save completed tasks even when Stop interrupts this block.
                    db.commit()
                db.commit()
        feature.cache_clear()
        progress()

    @staticmethod
    def add_pair(db, a, b, kind, score, ignored):
        if a['id'] == b['id']:
            return
        key = pair_key(a, b)
        separated = db.execute('SELECT 1 FROM separations WHERE a=? AND b=?', tuple(sorted((a['sha'], b['sha'])))).fetchone()
        if key not in ignored and not separated:
            db.execute('INSERT OR IGNORE INTO pairs(a,b,kind,score,decision,key) VALUES (?,?,?,?,NULL,?)',
                       (a['id'], b['id'], kind, score, key))

    def view(self, offset=0, filter_kind='all'):
        clause = "p.decision IS NULL AND a.moved=0 AND b.moved=0"
        if filter_kind == 'exact':
            clause += " AND p.kind='Exact bytes'"
        elif filter_kind == 'visual':
            clause += " AND p.kind!='Exact bytes'"
        with self.db() as db:
            base = ' FROM pairs p JOIN files a ON a.id=p.a JOIN files b ON b.id=p.b WHERE '+clause
            count = db.execute('SELECT COUNT(*)'+base).fetchone()[0]
            rows = db.execute('SELECT p.*'+base+" ORDER BY (p.kind='Exact bytes') DESC,p.score DESC,p.id LIMIT 60 OFFSET ?", (max(0, offset),)).fetchall()
            pairs = []
            for row in rows:
                p = dict(row)
                p['left'] = dict(db.execute('SELECT * FROM files WHERE id=?', (p['a'],)).fetchone())
                p['right'] = dict(db.execute('SELECT * FROM files WHERE id=?', (p['b'],)).fetchone())
                pairs.append(p)
            stats = dict(total=db.execute('SELECT COUNT(*) FROM files').fetchone()[0],
                         moved=db.execute("SELECT COUNT(*) FROM moves WHERE state='moved'").fetchone()[0],
                         kept=db.execute('SELECT COUNT(*) FROM ignored').fetchone()[0],
                         library_removed=sum(len(json.loads(r[0])['selection']) for r in db.execute("SELECT payload FROM library_cleanups WHERE state='removed'")),
                         pending_cleanups=db.execute("SELECT COUNT(*) FROM library_cleanups WHERE state='pending'").fetchone()[0],
                         replacements=db.execute("SELECT COUNT(*) FROM replacements WHERE state NOT IN ('undone','cancelled')").fetchone()[0],
                         pending_replacements=db.execute("SELECT COUNT(*) FROM replacements WHERE state NOT IN ('complete','undone','cancelled')").fetchone()[0])
            errors = [dict(r) for r in db.execute('SELECT * FROM errors LIMIT 100')]
            summary = db.execute("SELECT value FROM settings WHERE key='coverage'").fetchone()
            coverage = json.loads(summary[0]) if summary else {}
            dismissed = db.execute('SELECT COUNT(*) FROM ignored').fetchone()[0]
            splits = db.execute('SELECT COUNT(*) FROM separations').fetchone()[0]
        with self.lock:
            status = self.status.copy()
            plan = self.verified_plan
            verified_preview = {'token':plan['token'], 'count':len(plan['moves'])} if plan and plan['revision'] == self.revision else None
        return dict(verified_preview=verified_preview, pairs=pairs, count=count, stats=stats, status=status, errors=errors, coverage=coverage, dismissed=dismissed, splits=splits, revision=self.revision, scan_kind=self.config().get('scan_kind','folders'))

    def record(self, ident):
        with self.db() as db:
            row = db.execute('SELECT * FROM files WHERE id=? AND moved=0', (ident,)).fetchone()
        if row is None:
            raise ValueError('This file is no longer available; refresh the results.')
        return dict(row)

    def validate(self, record, verify_hash=True):
        if verify_hash and record.get('library'):
            meta = json.loads(record['library'])
            current = self.library.item(meta['id'], meta['library_id'])
            if current['sha'] != record['sha'] or str(canonical(current['path'])) != record['path']:
                raise ValueError('The imported image changed or was removed. Scan again before cleaning up copies.')
        path = Path(record['path'])
        if not path.is_file() or linked(path) or str(canonical(path)) != record['path']:
            raise ValueError('The file moved or is a link. Scan again before reviewing it.')
        if stat_key(path) != record['stamp']:
            raise ValueError('File changed since the scan. Scan again before moving anything.')
        if verify_hash and sha256(path) != record['sha']:
            raise ValueError('File contents changed. Scan again.')
        return path

    def review(self, pair_id, action):
        with self.lock:
            if self.status['running']:
                raise ValueError('Wait for the scan to finish before making decisions.')
            self.exact_plan = None
            with self.db() as db:
                row = db.execute('SELECT * FROM pairs WHERE id=? AND decision IS NULL', (pair_id,)).fetchone()
                if row is None:
                    raise ValueError('This pair has already been reviewed.')
                a, b = self.record(row['a']), self.record(row['b'])
                if action == 'keep':
                    db.execute('INSERT OR IGNORE INTO ignored VALUES (?)', (row['key'],))
                    db.execute("UPDATE pairs SET decision='keep' WHERE id=?", (pair_id,))
                    self.invalidate_groups()
                    return {'message': 'Kept both. This pair will stay dismissed on later scans.'}
                if action not in ('left', 'right'):
                    raise ValueError('Choose the copy to move.')
                target, survivor = (a, b) if action == 'left' else (b, a)
                return self._move_records(db, target, survivor)

    def _move_records(self, db, target, survivor, batch=None):
        pending = db.execute("SELECT operation FROM replacements WHERE state NOT IN ('complete','undone','cancelled')").fetchall()
        if any(r['operation'] != batch for r in pending):
            raise ValueError('Resume or undo the unfinished replacement before moving other copies.')
        # Only explicit whole-group quarantine may proceed without a keeper.
        if survivor is not None:
            self.validate(survivor)
        source = self.validate(target)
        config = self.config()
        if target['reference'] or target.get('library') or any(inside(source, canonical(p)) for p in config['reference']):
            raise ValueError('Reference folders are protected and cannot be moved.')
        root = canonical(target['root'])
        if not inside(source, root) or root not in [canonical(p) for p in config['incoming']]:
            raise ValueError('File is outside the incoming folders.')
        qroot = root / QUARANTINE
        if qroot.exists() and (linked(qroot) or canonical(qroot) != qroot):
            raise ValueError('Quarantine must be a regular local folder, not a link.')
        move_id = uuid.uuid4().hex
        destination = qroot / move_id / source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=False)
        # Commit the journal BEFORE rename, so an interrupted move can be recovered.
        db.execute('INSERT INTO moves(id,src,dst,sha,state,created,batch) VALUES (?,?,?,?,?,?,?)',
                   (move_id, str(source), str(destination), target['sha'], 'pending', time.time(), batch))
        db.commit()
        try:
            source.rename(destination)  # Same-volume; no copy/delete fallback.
        except Exception:
            db.execute("UPDATE moves SET state='failed' WHERE id=?", (move_id,))
            raise
        db.execute("UPDATE moves SET state='moved' WHERE id=?", (move_id,))
        db.execute('UPDATE files SET moved=1 WHERE id=?', (target['id'],))
        # An exact group uses one representative. If that representative is
        # moved, transfer its comparisons to a byte-identical survivor; never
        # infer a new visual match through a merely similar image.
        replacement = db.execute('SELECT * FROM files WHERE moved=0 AND (sha=? OR (pixel IS NOT NULL AND pixel=?)) ORDER BY reference DESC,id LIMIT 1', (target['sha'],target.get('pixel'))).fetchone()
        if replacement:
            replacement = dict(replacement)
            dismissed = {r[0] for r in db.execute('SELECT key FROM ignored')}
            for edge in db.execute('SELECT * FROM pairs WHERE (a=? OR b=?) AND decision IS NULL', (target['id'], target['id'])).fetchall():
                other_id = edge['b'] if edge['a'] == target['id'] else edge['a']
                if other_id == replacement['id']:
                    continue
                other = db.execute('SELECT * FROM files WHERE id=? AND moved=0', (other_id,)).fetchone()
                if other and not (replacement['reference'] and other['reference']):
                    self.add_pair(db, replacement, dict(other), 'Exact pixels' if edge['kind']=='Exact bytes' and replacement['sha']!=other['sha'] else edge['kind'], edge['score'], dismissed)
        self.invalidate_groups()
        # Do not discard match edges: Undo restores them immediately.
        return {'message': 'Moved to quarantine. Undo is available.', 'destination': str(destination)}

    def recover_moves(self):
        with self.db() as db:
            for row in db.execute("SELECT * FROM moves WHERE state IN ('pending','restoring')").fetchall():
                src, dst = Path(row['src']), Path(row['dst'])
                state = None
                if dst.is_file() and not src.exists() and sha256(dst) == row['sha']:
                    state = 'moved'
                elif src.is_file() and not dst.exists() and sha256(src) == row['sha']:
                    state = 'restored'
                if state:
                    db.execute('UPDATE moves SET state=? WHERE id=?', (state, row['id']))
                    db.execute('UPDATE files SET moved=? WHERE path=?', (int(state == 'moved'), row['src']))

    def _restore(self, db, row):
        src, dst = Path(row['src']), Path(row['dst'])
        if src.exists() or src.is_symlink():
            raise ValueError('Cannot restore: the original path is occupied. Move that file elsewhere first. Nothing was overwritten.')
        if not dst.is_file() or linked(dst) or sha256(dst) != row['sha']:
            raise ValueError('The quarantined file is missing or changed; it was not restored.')
        if any(linked(parent) for parent in src.parents if parent.exists()):
            raise ValueError('The original folder now contains a link. Restore it manually.')
        src.parent.mkdir(parents=True, exist_ok=True)
        db.execute("UPDATE moves SET state='restoring' WHERE id=?", (row['id'],))
        db.commit()
        # Exclusive creation prevents overwrite even if another process creates src now.
        # Windows rename fails if destination exists. POSIX use atomic hard-link + unlink.
        try:
            if os.name == 'nt':
                dst.rename(src)
            else:
                os.link(dst, src)
                dst.unlink()
        except Exception:
            db.execute("UPDATE moves SET state='moved' WHERE id=?", (row['id'],))
            db.commit()
            raise
        db.execute("UPDATE moves SET state='restored' WHERE id=?", (row['id'],))
        db.execute('UPDATE files SET moved=0,stamp=? WHERE path=?', (stat_key(src), str(src)))
        self.invalidate_groups()

    def remove_library_selection(self, selection, revision):
        with self.lock:
            if self.status['running'] or revision != self.revision:
                raise ValueError('The review changed. Review your selection again.')
            config = self.config()
            if config.get('scan_kind') != 'library' or not 1 <= len(selection) <= 500:
                raise ValueError('Choose 1–500 copies in a library-only scan.')
            self.groups()
            membership = self.groups_cache['membership']
            targets = {int(item['target']) for item in selection}
            if len(targets) != len(selection):
                raise ValueError('A copy was selected more than once.')
            requests, records = [], []
            for item in selection:
                target, keeper = self.record(int(item['target'])), self.record(int(item['keeper']))
                if not target.get('library') or not keeper.get('library') or keeper['id'] in targets or item.get('proof', 'manual') != 'manual':
                    raise ValueError('Choose a library keeper that will not be removed.')
                if membership.get(target['id']) is None or membership[target['id']] != membership.get(keeper['id']):
                    raise ValueError('The copy and keeper must be in the same review group.')
                a, b = json.loads(target['library']), json.loads(keeper['library'])
                if a['library_id'] != config['library_id'] or b['library_id'] != config['library_id']:
                    raise ValueError('The active library changed. Scan again.')
                requests.append(dict(target=a['id'], keeper=b['id'], target_sha=target['sha'], keeper_sha=keeper['sha']))
                records.append(dict(path=target['path'], sha=target['sha']))
            operation = uuid.uuid4().hex
            payload = dict(operation=operation, library_id=config['library_id'], selection=requests, records=records)
            with self.db() as db:
                if db.execute("SELECT 1 FROM library_cleanups WHERE state='pending'").fetchone():
                    raise ValueError('Resume or undo the unfinished library cleanup first.')
                db.execute('INSERT INTO library_cleanups VALUES (?,?,?,?)', (operation,json.dumps(payload),'pending',time.time()))
            return self._apply_library_cleanup(payload)

    def _apply_library_cleanup(self, payload):
        result = self.library.cleanup(payload['operation'], payload['library_id'], payload['selection'])
        if result['state'] not in ('removed', 'restored'):
            raise ValueError('Unexpected cleanup status. Resume or undo this action.')
        with self.db() as db:
            db.execute('UPDATE library_cleanups SET state=? WHERE operation=?', (result['state'],payload['operation']))
            for record in payload['records']:
                db.execute('UPDATE files SET moved=? WHERE path=? AND sha=?', (int(result['state']=='removed'),record['path'],record['sha']))
            if result['state'] == 'removed':
                ignored = {r[0] for r in db.execute('SELECT key FROM ignored')}
                for record in payload['records']:
                    target = db.execute('SELECT * FROM files WHERE path=? AND sha=?', (record['path'],record['sha'])).fetchone()
                    if not target:
                        continue
                    survivor = db.execute('SELECT * FROM files WHERE moved=0 AND (sha=? OR (pixel IS NOT NULL AND pixel=?)) LIMIT 1', (target['sha'],target['pixel'])).fetchone()
                    if survivor:
                        for edge in db.execute('SELECT * FROM pairs WHERE (a=? OR b=?) AND decision IS NULL', (target['id'],target['id'])).fetchall():
                            other_id = edge['b'] if edge['a']==target['id'] else edge['a']
                            other = db.execute('SELECT * FROM files WHERE id=? AND moved=0', (other_id,)).fetchone()
                            if other and other['id'] != survivor['id']:
                                kind = 'Exact pixels' if edge['kind']=='Exact bytes' and survivor['sha']!=other['sha'] else edge['kind']
                                self.add_pair(db, dict(survivor), dict(other), kind, edge['score'], ignored)
        self.invalidate_groups()
        return {'message':f"Removed {len(payload['selection'])} library copies. Originals and records are retained for Undo."}

    def resume_library_cleanup(self):
        with self.lock:
            if self.status['running']:
                raise ValueError('Wait for the scan to finish.')
            with self.db() as db:
                row = db.execute("SELECT payload FROM library_cleanups WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
            if not row:
                raise ValueError('No unfinished library cleanup.')
            return self._apply_library_cleanup(json.loads(row[0]))

    def undo_library_cleanup(self, row):
        payload = json.loads(row['payload'])
        result = self.library.cleanup_undo(payload['operation'], payload['library_id'])
        if result['state'] not in ('missing', 'restored'):
            raise ValueError('The library cleanup could not be undone.')
        with self.db() as db:
            db.execute("UPDATE library_cleanups SET state='restored' WHERE operation=?", (payload['operation'],))
            for record in payload['records']:
                db.execute('UPDATE files SET moved=0 WHERE path=? AND sha=?', (record['path'],record['sha']))
        self.invalidate_groups()
        return {'message':'Library cleanup undone. Original records and Set memberships restored.'}

    def undo(self):
        with self.lock:
            if self.status['running']:
                raise ValueError('Wait for the current operation to finish.')
            self.exact_plan = None
            with self.db() as db:
                row = db.execute("SELECT * FROM moves WHERE state='moved' ORDER BY created DESC LIMIT 1").fetchone()
                replacement = db.execute("SELECT * FROM replacements WHERE state NOT IN ('undone','cancelled') ORDER BY created DESC LIMIT 1").fetchone()
                cleanup = db.execute("SELECT * FROM library_cleanups WHERE state IN ('pending','removed') ORDER BY created DESC LIMIT 1").fetchone()
                if cleanup and cleanup['created'] > max(row['created'] if row else 0, replacement['created'] if replacement else 0):
                    return self.undo_library_cleanup(dict(cleanup))
                if replacement and (not row or row['batch'] == replacement['operation'] or replacement['created'] > row['created']):
                    return self.undo_replacement(dict(replacement))
                if row is None:
                    raise ValueError('There are no moves to undo.')
                rows = (db.execute("SELECT * FROM moves WHERE state='moved' AND batch=? ORDER BY created DESC", (row['batch'],)).fetchall()
                        if row['batch'] else [row])
                if len(rows) == 1:
                    self._restore(db, row)
                    return {'message': 'Restored '+Path(row['src']).name+'.'}
                # Start an undo job so a large batch does not freeze the interface.
                self.cancel.clear()
                self.status.update(running=True, phase='Restoring exact duplicates', done=0, total=len(rows))
                self.thread = threading.Thread(target=self._undo_batch, args=([dict(r) for r in rows],), daemon=True)
                self.thread.start()
                return {'message': 'Restoring the last batch. Existing files will not be overwritten.'}

    def _undo_batch(self, rows):
        restored, failed = 0, 0
        try:
            for index, row in enumerate(rows):
                if self.cancel.is_set():
                    break
                try:
                    with self.lock, self.db() as db:
                        self._restore(db, row)
                    restored += 1
                except Exception as e:
                    failed += 1
                    self.error(row['src'], str(e))
                self.set_status(done=index+1)
            self.set_status(phase=f'Restored {restored} copies' + (f' · {failed} could not be restored (see issues)' if failed else '') + (' · Stopped; Undo can restore the rest' if self.cancel.is_set() else ''))
        finally:
            self.set_status(running=False)

    def preview_exact(self, scope='all', include_pixels=False):
        if self.config().get('scan_kind') == 'library':
            raise ValueError('Review library copies and choose their keepers manually; their metadata may differ.')
        with self.lock:
            if self.status['running']:
                raise ValueError('Wait for the current operation to finish.')
            if scope not in ('all', 'folder'):
                raise ValueError('Choose a valid folder scope.')
            with self.db() as db:
                records = [dict(r) for r in db.execute('SELECT * FROM files WHERE moved=0')]
                ignored = {r[0] for r in db.execute('SELECT key FROM ignored')}
                kept = {(r[0],r[1]) for r in db.execute('SELECT path,sha FROM keeps')}
            groups = {}
            for r in records:
                key = ((r.get('pixel') or r['sha']) if include_pixels else r['sha'], str(Path(r['path']).parent) if scope == 'folder' else '')
                groups.setdefault(key, []).append(r)
            moves, skipped_groups = [], 0
            for group in groups.values():
                if len(group) < 2 or all(r['reference'] for r in group):
                    continue
                # A manual keep-both choice takes precedence over bulk cleanup.
                if ignored and any(pair_key(a,b) in ignored for i,a in enumerate(group) for b in group[i+1:]):
                    skipped_groups += 1
                    continue
                group = preferred(group)
                keeper = next((r for r in group if r['reference']), None) or next((r for r in group if (r['path'],r['sha']) in kept), group[0])
                for target in group:
                    if target['id'] != keeper['id'] and not target['reference'] and (target['path'],target['sha']) not in kept:
                        moves.append({'target':target, 'keeper':keeper, 'proof':'bytes' if target['sha']==keeper['sha'] else 'pixels'})
            token = uuid.uuid4().hex
            self.exact_plan = {'token':token, 'moves':moves}
            return {'token':token, 'count':len(moves), 'bytes':sum(m['target']['size'] for m in moves),
                    'skipped_groups':skipped_groups, 'scope':scope,
                    'moves':[{'move':m['target']['path'], 'keep':m['keeper']['path'], 'target':m['target']['id'], 'keeper':m['keeper']['id'], 'proof':m['proof']} for m in moves],
                    'missing_pixels':sum(not r.get('pixel') for r in records)}

    def start_verified(self, revision, scope='all', preview=False):
        with self.lock:
            if self.status['running'] or revision != self.revision:
                raise ValueError('The review changed. Reload and try again.')
            if self.config().get('scan_kind') == 'library':
                raise ValueError('Library-only cleanup requires manual choices to preserve assignments.')
            if scope not in ('all', 'folder'):
                raise ValueError('Choose a valid folder scope.')
            self.groups()
            groups = [list(g['files']) for g in self.groups_cache['groups']]
            with self.db() as db:
                ignored = {r[0] for r in db.execute('SELECT key FROM ignored')}
                separated = {tuple(r) for r in db.execute('SELECT a,b FROM separations')}
            self.exact_plan = None
            self.cancel.clear()
            workers = max(1, min(8, int(self.config().get('workers', 8))))
            self.status.update(running=True, phase='Verifying same-photo copies', done=0,
                               total=len(groups), workers=workers, elapsed_seconds=0,
                               eta_seconds=None, cached_tasks=0)
            self.verified_plan = None
            self.thread = threading.Thread(target=self._run_verified,
                args=(groups, ignored, separated, scope, workers, preview), daemon=True)
            self.thread.start()
            return {'message':'Preparing preview. No files will move.' if preview else 'Verifying copies, then quarantining matches. Uncertain images stay for review.'}

    def _verified_group(self, files, ignored, separated, scope):
        # Stable MP sort preserves the UI's left-to-right ordering on ties.
        ordered = sorted(files, key=lambda r:-(r['w']*r['h']))
        keepers, moves = [], []
        failed = set()
        @lru_cache(maxsize=8)
        def prepared(ident):
            r = next(r for r in files if r['id']==ident)
            try:
                path = self.validate(r)
                image = same_photo.prepare(path)
                self.validate(r, verify_hash=False)
                return image
            except Exception as e:
                if ident not in failed:
                    failed.add(ident)
                    self.error(r['path'], str(e))
                return None
        for target in ordered:
            if self.cancel.is_set():
                break
            chosen = None
            if not target['keep'] and not target['reference'] and not target.get('library'):
                for keeper in keepers:
                    if self.cancel.is_set():
                        break
                    if scope == 'folder' and Path(target['path']).parent != Path(keeper['path']).parent:
                        continue
                    if pair_key(target, keeper) in ignored or tuple(sorted((target['sha'],keeper['sha']))) in separated:
                        continue
                    proof = None
                    if target['sha'] == keeper['sha']:
                        proof = 'bytes'
                    elif target.get('pixel') and target['pixel'] == keeper.get('pixel'):
                        proof = 'pixels'
                    else:
                        key = same_photo.VERSION+':'+target['sha']+':'+keeper['sha']
                        with self.db() as db:
                            cached = db.execute('SELECT accepted FROM verified_copies WHERE key=?',(key,)).fetchone()
                        if cached is not None:
                            accepted = bool(cached[0])
                        else:
                            accepted = same_photo.verify(prepared(target['id']), prepared(keeper['id']))
                            if target['id'] not in failed and keeper['id'] not in failed:
                                with self.db() as db:
                                    db.execute('INSERT OR REPLACE INTO verified_copies VALUES (?,?)',(key,int(accepted)))
                        if accepted:
                            proof = 'same_photo'
                    if proof:
                        chosen = {'target':target, 'keeper':keeper, 'proof':proof}
                        break
            if chosen:
                moves.append(chosen)
            else:
                keepers.append(target)
        # No chain: every keeper remains on disk, and every target was checked
        # directly against that keeper, not inferred from group membership.
        return moves

    def _run_verified(self, groups, ignored, separated, scope, workers, preview=False):
        started = time.monotonic()
        moves = []
        try:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='verify') as pool:
                pending = {pool.submit(self._verified_group, g, ignored, separated, scope) for g in groups}
                done = 0
                while pending:
                    finished, pending = wait(pending, timeout=.2, return_when=FIRST_COMPLETED)
                    for future in finished:
                        moves.extend(future.result())
                        done += 1
                    self.set_status(done=done, elapsed_seconds=round(time.monotonic()-started))
                    if self.cancel.is_set():
                        for future in pending:
                            future.cancel()
                        break
            if self.cancel.is_set():
                self.set_status(phase='Verification stopped. No files moved.')
                return
            if not moves:
                self.set_status(phase='No additional verified copies. Remaining images need manual review; check Issues for any failures.')
                return
            if preview:
                # Save server-owned pairs; approval may only select a subset, never change keepers.
                moves.sort(key=lambda m:(m['keeper']['path'], m['target']['path']))
                with self.lock:
                    self.verified_plan = {'token':uuid.uuid4().hex, 'revision':self.revision, 'moves':moves}
                self.set_status(phase=f'Preview ready: {len(moves)} proposed removals. No files moved.')
                return
            self.set_status(phase='Moving verified copies to quarantine', done=0, total=len(moves),
                            workers=0, eta_seconds=None)
            # Existing move journal, live source+keeper hashing and Undo batch.
            self._run_exact(moves, uuid.uuid4().hex, finish=False)
        except Exception as e:
            self.error('Automatic copy verification', str(e))
            self.set_status(phase='Automatic verification failed. Check Issues before retrying.')
        finally:
            self.set_status(running=False)

    def verified_preview(self):
        with self.lock:
            plan = self.verified_plan
            if self.status['running'] or not plan or plan['revision'] != self.revision:
                raise ValueError('Preview unavailable or outdated. Run Preview auto-quarantine again.')
            def details(r):
                return {k:r.get(k) for k in ('id','path','w','h','size')}
            return {'token':plan['token'], 'moves':[
                {'target':details(m['target']), 'keeper':details(m['keeper']), 'proof':m['proof']}
                for m in plan['moves']]}

    def apply_verified_preview(self, token, targets):
        with self.lock:
            plan = self.verified_plan
            if self.status['running'] or not plan or token != plan['token'] or plan['revision'] != self.revision:
                raise ValueError('The review changed. Preview the batch again before moving files.')
            if not isinstance(targets, list) or any(type(i) is not int for i in targets):
                raise ValueError('Choose valid preview items.')
            approved = set(targets)
            available = {m['target']['id'] for m in plan['moves']}
            if not approved or not approved <= available:
                raise ValueError('Choose at least one item from this preview.')
            moves = [m for m in plan['moves'] if m['target']['id'] in approved]
            self.verified_plan = None
            self.exact_plan = None
            self.cancel.clear()
            self.status.update(running=True, phase='Moving approved copies to quarantine', done=0, total=len(moves))
            self.thread = threading.Thread(target=self._run_exact, args=(moves, uuid.uuid4().hex), daemon=True)
            self.thread.start()
            return {'message':f'Moving {len(moves)} approved copies. Undo restores this batch.'}

    def start_exact(self, token):
        with self.lock:
            if self.status['running']:
                raise ValueError('Wait for the current operation to finish.')
            if not self.exact_plan or token != self.exact_plan['token']:
                raise ValueError('The review changed. Preview the batch again before moving files.')
            moves = self.exact_plan['moves']
            self.exact_plan = None
            if not moves:
                return {'message':'No exact duplicates to move.'}
            self.cancel.clear()
            self.status.update(running=True, phase='Moving selected copies', done=0, total=len(moves))
            self.thread = threading.Thread(target=self._run_exact, args=(moves, uuid.uuid4().hex), daemon=True)
            self.thread.start()
            return {'message':f'Moving {len(moves)} selected copies to quarantine…'}

    def _run_exact(self, moves, batch, keep_records=None, finish=True):
        moved, failed = 0, 0
        try:
            for index, item in enumerate(moves):
                if self.cancel.is_set():
                    break
                try:
                    with self.lock, self.db() as db:
                        target = self.record(item['target']['id'])
                        keeper = self.record(item['keeper']['id'])
                        if (target['sha'] != item['target']['sha'] or keeper['sha'] != item['keeper']['sha']
                                or target['path'] != item['target']['path'] or keeper['path'] != item['keeper']['path']):
                            raise ValueError('The files no longer match the approved batch.')
                        proof = item.get('proof','bytes')
                        if proof == 'bytes' and target['sha'] != keeper['sha']:
                            raise ValueError('Files are not byte-identical.')
                        if proof == 'pixels' and (not target.get('pixel') or target['pixel'] != keeper.get('pixel')):
                            raise ValueError('Files are not pixel-identical. Scan again.')
                        # Rehash BOTH actual files before each move, not just cached fingerprints.
                        self._move_records(db, target, keeper, batch=batch)
                    moved += 1
                except Exception as e:
                    failed += 1
                    self.error(item['target']['path'], str(e))
                self.set_status(done=index+1)
            if keep_records and not failed and moved == len(moves):
                with self.lock, self.db() as db:
                    self._dismiss_pairs(db, keep_records)
                    self.invalidate_groups()
            self.set_status(phase=f'Moved {moved} selected copies' + (f' · {failed} skipped (see issues)' if failed else '') + (' · Stopped' if self.cancel.is_set() else '') + ' · Undo last action restores this batch')
        finally:
            if finish:
                self.set_status(running=False)

    def reset_dismissed(self):
        with self.lock:
            if self.status['running']:
                raise ValueError('Wait for the scan to finish.')
            self.exact_plan = None
            with self.db() as db:
                db.execute('DELETE FROM ignored')
                db.execute('DELETE FROM separations')
                db.execute('DELETE FROM group_links')
                db.execute('DELETE FROM keeps')
                db.execute("UPDATE pairs SET decision=NULL WHERE decision IN ('keep','different')")
            self.invalidate_groups()
            return {'message': 'Kept-both decisions cleared. Scan again to include pairs from older scans.'}

    def history(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM moves ORDER BY created DESC LIMIT 200')]

    def invalidate_groups(self):
        self.verified_plan = None
        self.revision += 1
        self.groups_cache = None

    def groups(self, group_id=None, sort='most'):
        with self.lock:
            if self.status['running']:
                return {'groups':[], 'files':[], 'revision':self.revision, 'running':True}
            library_mode = self.config().get('scan_kind') == 'library'
            if self.groups_cache is None:
                with self.db() as db:
                    records = {r['id']:dict(r) for r in db.execute('SELECT * FROM files WHERE moved=0')}
                    keeps = {(r[0],r[1]) for r in db.execute('SELECT path,sha FROM keeps')}
                    for record in records.values():
                        record['protected'] = bool(record['reference'] and not (library_mode and record.get('library')))
                        record['keep'] = bool(record['protected'] or (record['path'],record['sha']) in keeps)
                        record['library_info'] = json.loads(record['library']) if record.get('library') else None
                    edges = [dict(r) for r in db.execute('SELECT * FROM pairs WHERE decision IS NULL')
                             if r['a'] in records and r['b'] in records]
                parent = {}
                def find(x):
                    parent.setdefault(x,x)
                    while parent[x] != x:
                        parent[x] = parent[parent[x]]
                        x = parent[x]
                    return x
                for edge in edges:
                    a,b = find(edge['a']),find(edge['b'])
                    parent[b] = a
                clusters = {}
                for ident in parent:
                    clusters.setdefault(find(ident),[]).append(records[ident])
                groups = []
                membership = {}
                for members in clusters.values():
                    if not library_mode and all(r['reference'] for r in members):
                        continue
                    ordered = preferred(members)
                    ident = min(r['id'] for r in members)
                    for r in members:
                        membership[r['id']] = ident
                    same = len({r.get('pixel') or r['sha'] for r in members}) == 1
                    groups.append({'id':ident,'count':len(members),'duplicates':len(members)-1,
                                   'name':(ordered[0].get('library_info') or {}).get('name') or Path(ordered[0]['path']).name,
                                   'folder':('Library · '+' · '.join(filter(None,[ordered[0]['library_info'].get('character_name',''), 'Review' if ordered[0]['library_info'].get('in_review') else 'Purgatory' if ordered[0]['library_info'].get('in_purgatory') else '',*ordered[0]['library_info']['sets']]))) if ordered[0].get('library_info') else str(Path(ordered[0]['path']).parent),
                                   'kind':'Verified identical' if same else 'Possible visual matches',
                                   'files':ordered})
                self.groups_cache = {'groups':groups, 'membership':membership}
            groups = list(self.groups_cache['groups'])
            groups.sort(key=lambda g:((-g['count'] if sort!='fewest' else g['count']),g['folder'].casefold(),g['id']))
            if sort == 'folder':
                groups.sort(key=lambda g:folder_rank(g['files'][0]), reverse=True)
            chosen = next((g for g in groups if g['id']==group_id), None)
            return {'groups':[{k:v for k,v in g.items() if k!='files'} for g in groups],
                    'files':chosen['files'] if chosen else [], 'revision':self.revision, 'running':False}

    def dismiss_group(self, group_id, revision):
        with self.lock:
            if self.status['running'] or revision != self.revision:
                raise ValueError('The review changed. Reload the group and try again.')
            files = self.groups(group_id)['files']
            if not files:
                raise ValueError('Group no longer exists.')
            ids = {r['id'] for r in files}
            with self.db() as db:
                for edge in db.execute('SELECT * FROM pairs WHERE decision IS NULL').fetchall():
                    if edge['a'] in ids and edge['b'] in ids:
                        db.execute('INSERT OR IGNORE INTO ignored VALUES (?)',(edge['key'],))
                        db.execute("UPDATE pairs SET decision='keep' WHERE id=?",(edge['id'],))
            self.exact_plan = None
            self.invalidate_groups()
            return {'message':'Group kept. No files moved.'}

    def move_selection(self, selection, revision):
        if self.config().get('scan_kind') == 'library':
            return self.remove_library_selection(selection, revision)
        with self.lock:
            if self.status['running'] or revision != self.revision:
                raise ValueError('The review changed. Review your selection again.')
            if not selection or len(selection)>10000:
                raise ValueError('Select between 1 and 10,000 copies to move.')
            self.groups()
            membership = self.groups_cache['membership']
            targets = {int(item['target']) for item in selection}
            if len(targets)!=len(selection):
                raise ValueError('A copy was selected more than once.')
            moves = []
            for item in selection:
                target,keeper = self.record(int(item['target'])),self.record(int(item['keeper']))
                if target['reference'] or target['id']==keeper['id'] or keeper['id'] in targets:
                    raise ValueError('Keep at least one copy of each selection; reference files are protected.')
                proof=item.get('proof','manual')
                if proof=='manual' and (membership.get(target['id']) is None or membership[target['id']]!=membership.get(keeper['id'])):
                    raise ValueError('The selected copy and keeper must be in the same review group.')
                if proof not in ('manual','bytes','pixels'):
                    raise ValueError('Invalid matching rule.')
                if proof=='bytes' and target['sha']!=keeper['sha']:
                    raise ValueError('Auto-selection requires identical file bytes.')
                if proof=='pixels' and (not target.get('pixel') or target['pixel']!=keeper.get('pixel')):
                    raise ValueError('Auto-selection requires identical decoded pixels. Run Scan once to add this check.')
                moves.append({'target':target,'keeper':keeper,'proof':proof})
            token=uuid.uuid4().hex
            self.exact_plan={'token':token,'moves':moves}
            return self.start_exact(token)

    def _group_for_change(self, group_id, revision):
        if self.status['running'] or revision != self.revision:
            raise ValueError('The review changed. Reload the group and try again.')
        files = self.groups(group_id)['files']
        if not files:
            raise ValueError('Group no longer exists.')
        return files

    @staticmethod
    def _dismiss_pairs(db, records):
        for index,a in enumerate(records):
            for b in records[index+1:]:
                key = pair_key(a,b)
                db.execute('INSERT OR IGNORE INTO ignored VALUES (?)', (key,))
                db.execute("UPDATE pairs SET decision='keep' WHERE key=?", (key,))

    def mark_keep(self, group_id, ident, keep, revision):
        with self.lock:
            files = self._group_for_change(group_id, revision)
            r = next((r for r in files if r['id']==ident), None)
            if not r or (r['reference'] and not (self.config().get('scan_kind') == 'library' and r.get('library'))):
                raise ValueError('Imported and reference images are always protected.')
            with self.db() as db:
                if keep:
                    db.execute('INSERT OR IGNORE INTO keeps VALUES (?,?)', (r['path'],r['sha']))
                else:
                    db.execute('DELETE FROM keeps WHERE path=? AND sha=?', (r['path'],r['sha']))
            self.exact_plan = None
            self.invalidate_groups()
            return {'message':'Keep choice saved. No files moved.'}

    def quarantine_group(self, group_id, revision):
        """Explicitly discard every incoming copy in this group, with batch Undo."""
        with self.lock:
            if self.config().get('scan_kind') == 'library':
                raise ValueError('Quarantine all incoming is only available for incoming folder scans.')
            files = self._group_for_change(group_id, revision)
            targets = [r for r in files if not r['reference'] and not r.get('library')]
            if not targets:
                raise ValueError('This group has no incoming images to quarantine.')
            self.exact_plan = None
            self.cancel.clear()
            self.status.update(running=True, phase='Moving all incoming copies in group', done=0, total=len(targets))
            self.thread = threading.Thread(target=self._run_quarantine_group, args=(targets, uuid.uuid4().hex), daemon=True)
            self.thread.start()
            return {'message': f'Moving all {len(targets)} incoming images in this group to quarantine. Undo restores the batch.'}

    def _run_quarantine_group(self, targets, batch):
        moved, failed = 0, 0
        try:
            for index, approved in enumerate(targets):
                if self.cancel.is_set():
                    break
                try:
                    with self.lock, self.db() as db:
                        target = self.record(approved['id'])
                        if target['sha'] != approved['sha'] or target['path'] != approved['path']:
                            raise ValueError('The file no longer matches the approved group.')
                        # Revalidate/hash each original and journal before renaming;
                        # this explicit action deliberately includes manual Keep choices.
                        self._move_records(db, target, None, batch=batch)
                    moved += 1
                except Exception as e:
                    failed += 1
                    self.error(approved['path'], str(e))
                self.set_status(done=index+1)
            self.set_status(phase=f'Moved {moved} incoming images to quarantine' + (f' · {failed} skipped (see issues)' if failed else '') + (' · Stopped' if self.cancel.is_set() else '') + ' · Undo last action restores this batch')
        finally:
            self.set_status(running=False)

    def finish_group(self, group_id, revision):
        with self.lock:
            files = self._group_for_change(group_id, revision)
            keepers = [r for r in files if r['keep']]
            if not keepers:
                raise ValueError('Mark at least one image Keep before finishing.')
            moves = [dict(target=r, keeper=keepers[0], proof='manual') for r in files if not r['keep']]
            if not moves:
                return self.dismiss_group(group_id, revision)
            if self.config().get('scan_kind') == 'library':
                return self.remove_library_selection([{'target':m['target']['id'],'keeper':m['keeper']['id'],'proof':'manual'} for m in moves], revision)
            self.exact_plan = None
            self.cancel.clear()
            self.status.update(running=True, phase='Moving selected copies', done=0, total=len(moves))
            self.thread = threading.Thread(target=self._run_exact, args=(moves,uuid.uuid4().hex,keepers), daemon=True)
            self.thread.start()
            return {'message':'Keeping your choices and moving other incoming copies to quarantine.'}

    def split_group(self, group_id, selected_ids, revision):
        with self.lock:
            files = self._group_for_change(group_id, revision)
            ids = set(map(int,selected_ids))
            if not ids or not ids < {r['id'] for r in files}:
                raise ValueError('Select this different image and its copies, leaving at least one image in the original group.')
            chosen = [r for r in files if r['id'] in ids]
            remaining = [r for r in files if r['id'] not in ids]
            for a in chosen:
                for b in remaining:
                    if a['sha']==b['sha'] or (a.get('pixel') and a['pixel']==b.get('pixel')):
                        raise ValueError('Include every verified identical copy of the selected image in the new group.')
            with self.db() as db:
                for a in chosen:
                    for b in remaining:
                        digests = tuple(sorted((a['sha'],b['sha'])))
                        db.execute('INSERT OR IGNORE INTO separations VALUES (?,?)', digests)
                        db.execute('DELETE FROM group_links WHERE a=? AND b=?', digests)
                        key = pair_key(a,b)
                        db.execute('INSERT OR IGNORE INTO ignored VALUES (?)',(key,))
                        db.execute("UPDATE pairs SET decision='different' WHERE key=?",(key,))
                # Preserve each chosen family even when the original match graph was a star.
                ignored = {r[0] for r in db.execute('SELECT key FROM ignored')}
                for family in (chosen,remaining):
                    for r in family[1:]:
                        if family[0]['sha'] != r['sha']:
                            db.execute('INSERT OR IGNORE INTO group_links VALUES (?,?)', tuple(sorted((family[0]['sha'],r['sha']))))
                        self.add_pair(db,family[0],r,'Manually grouped',0,ignored)
            self.exact_plan = None
            self.invalidate_groups()
            return {'message':'Split saved. Each image and its copies can be reviewed separately. No files moved.'}

    def replace_library(self, group_id, source_id, target_id, revision):
        with self.lock:
            files = self._group_for_change(group_id, revision)
            by_id = {r['id']:r for r in files}
            source, target = by_id.get(source_id), by_id.get(target_id)
            if not source or source['reference'] or not target or not target.get('library'):
                raise ValueError('Choose an incoming image and an imported target from this group.')
            with self.db() as db:
                if db.execute("SELECT 1 FROM replacements WHERE state NOT IN ('complete','undone','cancelled')").fetchone():
                    raise ValueError('Resume or undo the unfinished replacement first.')
            self.validate(source); self.validate(target)
            operation = uuid.uuid4().hex
            payload = {'source':source, 'target':target, 'meta':json.loads(target['library'])}
            with self.db() as db:
                db.execute('INSERT INTO replacements VALUES (?,?,?,?)', (operation,json.dumps(payload),'pending',time.time()))
            return self._complete_replacement(operation,payload)

    def _replacement_state(self, operation, state):
        with self.db() as db:
            db.execute('UPDATE replacements SET state=? WHERE operation=?',(state,operation))

    def _sync_library_record(self, target, result):
        """Verify committed bytes before changing scan references or moving a download."""
        path = canonical(result['path'])
        meta = json.loads(target['library'])
        if not inside(path,canonical(target['root'])) or linked(path):
            raise ValueError('Replacement path is outside the expected library')
        item = result['item']
        if not item or item['id'] != meta['id'] or sha256(path) != item['sha256']:
            raise ValueError('Could not verify the library replacement. The incoming image was not moved.')
        stamp = stat_key(path)
        _,w,h = load_image(path,256)
        pixel = pixel_digest(path)
        if stat_key(path) != stamp:
            raise ValueError('Library source changed during verification')
        meta.update(path=str(path),sha=item['sha256'],name=item.get('original_name',''))
        with self.db() as db:
            candidates = [dict(r) for r in db.execute('SELECT * FROM files WHERE library IS NOT NULL AND moved=0')]
            r = next((r for r in candidates if json.loads(r['library'])['id']==meta['id'] and json.loads(r['library'])['library_id']==meta['library_id']),None)
            if r:
                db.execute('UPDATE files SET path=?,stamp=?,sha=?,w=?,h=?,size=?,pixel=?,library=? WHERE id=?',
                           (str(path),stamp,item['sha256'],w,h,path.stat().st_size,pixel,json.dumps(meta),r['id']))
                ident = r['id']
            else:
                cursor = db.execute('INSERT INTO files(path,stamp,sha,w,h,size,reference,root,pixel,library) VALUES (?,?,?,?,?,?,1,?,?,?)',
                                    (str(path),stamp,item['sha256'],w,h,path.stat().st_size,target['root'],pixel,json.dumps(meta)))
                ident = cursor.lastrowid
        self.invalidate_groups()
        return self.record(ident)

    def _complete_replacement(self, operation, payload):
        source,target,meta = payload['source'],payload['target'],payload['meta']
        result = self.library.operation(operation,meta['library_id'])
        if result['state'] == 'missing':
            path = self.validate(source)
            self.validate(target)
            if path.stat().st_size > 256*1024*1024:
                raise ValueError('Replacement images must be smaller than 256 MB.')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != source['sha']:
                raise ValueError('Incoming image changed before replacement')
            result = self.library.replace(data,name=path.name,media_id=meta['id'],expected_sha=target['sha'],
                                          operation=operation,library_id=meta['library_id'])
        if result['state'] == 'undone':
            self._replacement_state(operation,'undone')
            return {'message':'This replacement was already undone.'}
        if result.get('new_sha') != source['sha'] or not result.get('item') or result['item']['sha256'] != source['sha']:
            raise ValueError('Library image changed after replacement. Undo or inspect it before continuing. The download was not moved.')
        self._replacement_state(operation,'applied')
        keeper = self._sync_library_record(target,result)
        with self.db() as db:
            moved = db.execute("SELECT * FROM moves WHERE batch=? AND state='moved'",(operation,)).fetchone()
            if not moved:
                live = db.execute('SELECT * FROM files WHERE path=? AND sha=? AND moved=0',(source['path'],source['sha'])).fetchone()
                if not live:
                    raise ValueError('Incoming scan record is missing. The verified library replacement remains safe.')
                self._move_records(db,dict(live),keeper,batch=operation)
        self._replacement_state(operation,'complete')
        self.invalidate_groups()
        return {'message':'Library image replaced and verified. Download moved to quarantine. Undo restores both.'}

    def resume_replacements(self):
        with self.lock:
            if self.status['running']:
                raise ValueError('Wait for the current operation to finish.')
            with self.db() as db:
                rows = [dict(r) for r in db.execute("SELECT * FROM replacements WHERE state NOT IN ('complete','undone','cancelled') ORDER BY created")]
            for row in rows:
                if row['state']=='undoing':
                    self.undo_replacement(row)
                else:
                    self._complete_replacement(row['operation'],json.loads(row['payload']))
            return {'message':'Unfinished replacements recovered.'}

    def undo_replacement(self, row):
        payload = json.loads(row['payload'])
        operation,meta = row['operation'],payload['meta']
        result = self.library.operation(operation,meta['library_id'])
        if result['state']=='missing':
            self._replacement_state(operation,'cancelled')
            return {'message':'Unfinished replacement cancelled. No files were changed.'}
        self._replacement_state(operation,'undoing')
        with self.db() as db:
            moved = db.execute("SELECT * FROM moves WHERE batch=? AND state='moved'",(operation,)).fetchone()
            if moved:
                self._restore(db,moved)
        # Restore the incoming file first; a network interruption can never lose it.
        result = self.library.undo(operation,meta['library_id'])
        self._sync_library_record(payload['target'],result)
        self._replacement_state(operation,'undone')
        self.invalidate_groups()
        return {'message':'Restored the old library original and the downloaded image. Metadata kept.'}
