from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import mimetypes
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

HOST = "127.0.0.1"
PORT = 8765
APP_NAME = "NovelAI Media Library"
API_VERSION = 9


def title_case_label(value: str) -> str:
    """Title case a saved Set label, preserving punctuation and deliberate acronyms."""
    value = str(value or '').strip()
    minor = {'a', 'an', 'the', 'and', 'as', 'at', 'but', 'by', 'for', 'from',
             'in', 'into', 'nor', 'of', 'on', 'onto', 'or', 'over', 'per', 'than',
             'through', 'to', 'upon', 'via', 'vs', 'with', 'without', 'yet'}
    words = list(re.finditer(r"[^\W_]+(?:['’][^\W_]+)*", value, re.UNICODE))
    if not words:
        return value
    pieces = []; end = 0
    for index, match in enumerate(words):
        gap = value[end:match.start()]; word = match.group(); lower = word.lower()
        boundary = index == 0 or index == len(words)-1 or bool(re.search(r'[:.!?—–]\s*$', gap))
        if lower in minor:
            word = lower[:1].upper() + lower[1:] if boundary else lower
        elif word.isupper() and len(word) > 1:
            pass  # Explicit AI, PVC, USA, etc. remain intact.
        elif any(c.isupper() for c in word[1:]) and not word.isupper():
            pass  # Preserve deliberate spelling such as iPhone or McQueen.
        else:
            word = lower[:1].upper() + lower[1:]
        pieces.extend((gap, word)); end = match.end()
    return ''.join(pieces) + value[end:]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_library_root() -> Path:
    home = Path.home()
    docs = home / "Documents"
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            # CSIDL_PERSONAL = the user's current Documents known folder.
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                docs = Path(buf.value)
        except Exception:
            pass
    base = docs if docs.exists() else home
    return base / APP_NAME


def safe_component(value: str, fallback: str = "item") -> str:
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", value).strip().rstrip(".")
    value = re.sub(r"\s+", " ", value)
    return (value[:120] or fallback)


def json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class OutfitMatcher:
    """On-demand local image retrieval. Never writes library metadata or originals."""
    MODEL_URL = 'https://huggingface.co/Marqo/marqo-fashionSigLIP/resolve/c56244cc94f92419e8369fa71efdaf403b124ce8/onnx/vision_model.onnx'
    MODEL_SHA = 'a7e773846b27a699c45ba7e3978514b7fca420662d7e69e3b9226982f09f4a13'
    MODEL_BYTES = 371715502
    SCENE_URL = 'https://huggingface.co/Xenova/dinov2-base/resolve/d623d125a29e343851bcedff293fdc8b6bda292b/onnx/model.onnx'
    SCENE_SHA = 'de9c675d214f0171285f90f1d1d7716bce1c5e280e93826d071d57f7b9314d98'
    SCENE_BYTES = 346555570
    # Full-frame resize deliberately retains setting details that a center crop loses.
    SCENE_RECIPE = SCENE_SHA + ':full-frame224-cls-outer-patches-v1'

    def __init__(self, store):
        self.store = store
        self.cache = store.root / '.outfit-search'
        self.lock = threading.RLock()
        self.jobs = {}
        self.contexts = {}
        self.session = None
        self.scene_session = None
        self.thread = None
        self.vector_cache = {}
        self.scene_vector_cache = {}
        self.query_cache = {}
        self.cache_hits = 0
        self.encoded_images = 0

    def status(self, ident):
        with self.lock:
            if ident not in self.jobs:
                raise ValueError('Search expired. Click Find matching Sets again.')
            return copy.deepcopy(self.jobs[ident])

    def update(self, ident, **fields):
        with self.lock:
            self.jobs[ident].update(fields)

    def start(self, body, scan=False):
        owner = str(body.get('character_id', ''))
        target_set_id = str(body.get('target_set_id', ''))
        media_id = str(body.get('media_id', ''))
        encoded = body.get('image_base64', '')
        source_id = str(body.get('source_media_id', ''))
        if scan and (media_id or encoded or source_id):
            raise ValueError('Scan uses existing library images only.')
        if not isinstance(encoded, str) or len(encoded) > 6 * 1024 * 1024:
            raise ValueError('Search image is too large.')
        if not scan and bool(media_id) == bool(encoded):
            raise ValueError('Choose one image to find matching Sets.')
        query_bytes = base64.b64decode(encoded, validate=True) if encoded else None
        example_ids, example_images = body.get('example_media_ids', []), body.get('example_images', [])
        if not isinstance(example_ids, list) or not isinstance(example_images, list) or len(example_ids)+len(example_images)>4 or (scan and (example_ids or example_images)):
            raise ValueError('Choose at most five examples of the same outfit or shoot.')
        if any(not isinstance(mid, str) for mid in example_ids) or any(not isinstance(value, str) or len(value)>6*1024*1024 for value in example_images):
            raise ValueError('Invalid matching example.')
        example_bytes = [base64.b64decode(value, validate=True) for value in example_images]
        with self.lock, self.store.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Another Set search is running. Wait for it to finish, then retry.')
            if not any(c['id'] == owner for c in self.store.data['characters']):
                raise ValueError('Choose a character first.')
            mode = body.get('matching_mode', self.store.matching_preferences(owner)['mode'])
            if mode not in ('outfit', 'photoshoot'):
                raise ValueError('Choose Outfit or Photoshoot matching.')
            media = {m['id']: m for m in self.store.data['media'] if m.get('character_id') == owner and m.get('media_type', 'image') == 'image'}
            if any(mid not in media for mid in example_ids) or (media_id and media_id not in media) or (source_id and source_id not in media):
                raise ValueError('Choose an image from this character.')
            sets = copy.deepcopy([s for s in self.store.data.get('sets', []) if s.get('character_id') == owner and s.get('kind', 'set') == 'set'])
            if target_set_id and (not scan or not any(s['id'] == target_set_id for s in sets)):
                raise ValueError('Choose an existing Set for this character.')
            candidates = copy.deepcopy(media)
            query = copy.deepcopy(media.get(media_id))
            revision = self.store.revision
            if len(self.jobs) >= 8:
                expired = next(iter(self.jobs))
                self.jobs.pop(expired)
                self.contexts.pop(expired, None)
            ident = uuid.uuid4().hex
            self.jobs[ident] = {'id': ident, 'character_id': owner, 'matching_mode': mode, 'scan': scan, 'running': True, 'phase': 'Preparing Set scan' if scan else 'Preparing ' + mode + ' search', 'done': 0, 'total': len(candidates), 'results': [], 'individual_results': [], 'scan_results': [], 'assigned_ids': [], 'issues': []}
            self.contexts[ident] = {'owner': owner, 'media': candidates, 'stamps': {}, 'query_id': (media_id or source_id) if not scan else '', 'target_set_id': target_set_id, 'example_ids': list(dict.fromkeys(example_ids)), 'example_bytes': example_bytes}
            self.thread = threading.Thread(target=self._run, args=(ident, sets, candidates, query, query_bytes, revision, owner, scan), daemon=True)
            self.thread.start()
            return self.status(ident)

    def _prepare(self, ident):
        if self.session is not None:
            return
        self.cache.mkdir(parents=True, exist_ok=True)
        # Separate dependencies from the companion environment; installed only on request.
        deps = self.cache / ('python-' + str(sys.version_info.major) + '.' + str(sys.version_info.minor))
        if deps.is_dir() and str(deps) not in sys.path:
            sys.path.insert(0, str(deps))
        try:
            import numpy as np
            import onnxruntime as ort
        except ImportError:
            import importlib
            self.update(ident, phase='First search: installing local matching engine (internet required)')
            stage = self.cache / ('install-' + uuid.uuid4().hex)
            try:
                proc = subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location',
                                       '--only-binary=:all:', '--target', str(stage), 'onnxruntime==1.31.0', 'numpy>=1.26,<3'],
                                      capture_output=True, timeout=600, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if proc.returncode:
                    raise ValueError('Could not install the matching engine. Check internet access and use 64-bit Python 3.11 or newer. ' + proc.stderr.decode(errors='replace')[-700:])
                if deps.exists():
                    shutil.rmtree(deps)
                stage.rename(deps)
            finally:
                if stage.exists():
                    shutil.rmtree(stage, ignore_errors=True)
            if str(deps) not in sys.path:
                sys.path.insert(0, str(deps))
            importlib.invalidate_caches()
            import numpy as np
            import onnxruntime as ort
        model = self.cache / 'fashion-siglip.onnx'
        if not model.exists() or self.store._hash_file(model) != self.MODEL_SHA:
            self.update(ident, phase='First search: downloading outfit model (355 MB)', done=0, total=self.MODEL_BYTES)
            temp = self.cache / 'fashion-siglip.download'
            try:
                digest = hashlib.sha256();received = 0
                with urllib.request.urlopen(self.MODEL_URL, timeout=45) as response, temp.open('wb') as output:
                    while True:
                        self._check_cancel(ident)
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        received += len(block)
                        if received > self.MODEL_BYTES:
                            raise ValueError('Outfit model download exceeded expected size.')
                        output.write(block);digest.update(block)
                        self.update(ident, done=received)
                if received != self.MODEL_BYTES or digest.hexdigest() != self.MODEL_SHA:
                    raise ValueError('Outfit model download was incomplete. Retry Find matching Sets.')
                os.replace(temp, model)
            finally:
                temp.unlink(missing_ok=True)
        self.update(ident, phase='Loading outfit model', done=0, total=0)
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 1)
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
        self.np = np

    def _prepare_scene(self, ident):
        if self.scene_session is not None:
            return
        import onnxruntime as ort
        model = self.cache / 'dinov2-base.onnx'
        if not model.exists() or self.store._hash_file(model) != self.SCENE_SHA:
            self.update(ident, phase='First Photoshoot search: downloading scene model (331 MB)', done=0, total=self.SCENE_BYTES)
            temp = self.cache / 'dinov2-base.download'
            try:
                digest = hashlib.sha256(); received = 0
                with urllib.request.urlopen(self.SCENE_URL, timeout=45) as response, temp.open('wb') as output:
                    while True:
                        self._check_cancel(ident)
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        received += len(block)
                        if received > self.SCENE_BYTES:
                            raise ValueError('Scene model download exceeded expected size.')
                        output.write(block); digest.update(block)
                        self.update(ident, done=received)
                if received != self.SCENE_BYTES or digest.hexdigest() != self.SCENE_SHA:
                    raise ValueError('Scene model download was incomplete. Retry Photoshoot search.')
                os.replace(temp, model)
            finally:
                temp.unlink(missing_ok=True)
        self._check_cancel(ident)
        self.update(ident, phase='Loading scene model', done=0, total=0)
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 1)
        options.inter_op_num_threads = 1
        self.scene_session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])

    def _encode_scene(self, source, angle=0):
        if Image is None:
            raise ValueError('Pillow is required for image matching.')
        np = self.np
        with Image.open(source) as original:
            im = ImageOps.exif_transpose(original).convert('RGB')
            if angle:
                im = im.rotate(angle, expand=True)
            array = np.asarray(im.resize((224, 224), Image.Resampling.BICUBIC), dtype=np.float32) / 255
        array = (array - np.array([.485, .456, .406], dtype=np.float32)) / np.array([.229, .224, .225], dtype=np.float32)
        tensor = np.transpose(array, (2, 0, 1))[None].copy()
        tokens = self.scene_session.run(None, {self.scene_session.get_inputs()[0].name: tensor})[0]
        if tokens.shape != (1, 257, 768) or not np.isfinite(tokens).all():
            raise ValueError('Invalid scene embedding.')
        # Context is the outer three quarters of the image, not person segmentation.
        # Normalize patches before pooling so one high-norm patch cannot dominate.
        patches = tokens[0, 1:].reshape(16, 16, 768)
        patches = patches / np.maximum(np.linalg.norm(patches, axis=2, keepdims=True), 1e-8)
        outer = np.ones((16, 16), dtype=bool); outer[4:12, 4:12] = False
        features = np.stack([tokens[0, 0], patches[outer].mean(axis=0)])
        norms = np.linalg.norm(features, axis=1, keepdims=True)
        if not np.isfinite(features).all() or (norms <= 0).any():
            raise ValueError('Invalid scene features.')
        return (features / norms).astype(np.float32)

    def _encode(self, source, angle=0):
        if Image is None:
            raise ValueError('Pillow is required for image matching.')
        with Image.open(source) as original:
            im = ImageOps.exif_transpose(original).convert('RGB')
            if angle:
                im = im.rotate(angle, expand=True)
            im = im.resize((224, 224), Image.Resampling.BICUBIC)
            array = self.np.asarray(im, dtype=self.np.float32) / 127.5 - 1
        tensor = self.np.transpose(array, (2, 0, 1))[None].copy()
        vector = self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0].reshape(-1)
        norm = self.np.linalg.norm(vector)
        if vector.size != 768 or not self.np.isfinite(vector).all() or norm <= 0:
            raise ValueError('Invalid image embedding.')
        return vector / norm

    def _vector(self, db, media, scene=False, count=True):
        path = (self.store.root / media['stored_rel']).resolve()
        if not path.is_relative_to(self.store.root.resolve()) or not path.is_file():
            raise ValueError('Original image missing or outside library.')
        stat = path.stat()
        stamp = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        recipe = self.SCENE_RECIPE if scene else self.MODEL_SHA
        shape = (2, 768) if scene else (768,)
        cache = self.scene_vector_cache if scene else self.vector_cache
        key = hashlib.sha256(json_bytes([recipe, str(path), media.get('sha256'), stamp])).hexdigest()
        cached = cache.get(media['id'])
        if cached and cached[0] == key:
            self.cache_hits += int(count)
            return cached[1]
        row = db.execute('SELECT vector FROM embeddings WHERE key=?', (key,)).fetchone()
        if row:
            value = self.np.frombuffer(row[0], dtype=self.np.float32).copy()
            if value.size == (1536 if scene else 768) and self.np.isfinite(value).all() and (self.np.linalg.norm(value.reshape(shape), axis=-1) > 0).all():
                value = value.reshape(shape)
                cache[media['id']] = (key, value)
                self.cache_hits += int(count)
                return value
        vector = self._encode_scene(path) if scene else self._encode(path)
        self.encoded_images += int(count)
        after = path.stat()
        if stamp != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Image changed during matching. Retry search.')
        db.execute('INSERT OR REPLACE INTO embeddings VALUES (?,?)', (key, vector.astype(self.np.float32).tobytes()))
        cache[media['id']] = (key, vector)
        return vector

    @staticmethod
    def _catalog_signature(sets, media):
        return (sorted((s['id'], s['name'], tuple(sorted(s.get('media_ids', [])))) for s in sets),
                sorted((m['id'], m.get('stored_rel'), m.get('sha256')) for m in media.values()))

    def cancel(self, ident):
        with self.lock:
            if ident not in self.jobs:
                raise ValueError('Search expired.')
            self.jobs[ident]['cancel_requested'] = True
            return self.status(ident)

    def _check_cancel(self, ident):
        with self.lock:
            if self.jobs[ident].get('cancel_requested'):
                raise InterruptedError('Scan stopped. Cached image descriptions are kept.')

    def _orientations(self, db, query, query_bytes, base_vector, scene=False):
        import io
        recipe = self.SCENE_RECIPE if scene else self.MODEL_SHA
        cache = self.scene_vector_cache if scene else self.vector_cache
        shape = (2, 768) if scene else (768,)
        source_key = cache[query['id']][0] if query else hashlib.sha256(query_bytes).hexdigest()
        key = 'query-orientation-v1:' + recipe + ':' + source_key
        row = db.execute('SELECT vector FROM embeddings WHERE key=?', (key,)).fetchone()
        rotated = self.np.frombuffer(row[0], dtype=self.np.float32).copy() if row else self.np.array([])
        if rotated.size != (3072 if scene else 1536) or not self.np.isfinite(rotated).all() or not (self.np.linalg.norm(rotated.reshape((2,) + shape), axis=-1) > 0).all():
            source = self.store.root / query['stored_rel'] if query else None
            encode = self._encode_scene if scene else self._encode
            rotated = self.np.stack([encode(source if query else io.BytesIO(query_bytes), angle) for angle in (90, 270)])
            if query:
                stat = source.stat()
                current_key = hashlib.sha256(json_bytes([recipe, str(source.resolve()), query.get('sha256'), (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)])).hexdigest()
                if current_key != source_key:
                    raise ValueError('Image changed during matching. Retry search.')
            db.execute('INSERT OR REPLACE INTO embeddings VALUES (?,?)', (key, rotated.astype(self.np.float32).tobytes()))
        return self.np.concatenate([base_vector.reshape((1,) + shape), rotated.reshape((2,) + shape)])

    def _uploaded_vector(self, data, scene=False):
        import io
        key = (self.SCENE_RECIPE if scene else self.MODEL_SHA) + ':' + hashlib.sha256(data).hexdigest()
        vector = self.query_cache.get(key)
        if vector is None:
            vector = self._encode_scene(io.BytesIO(data)) if scene else self._encode(io.BytesIO(data))
            if len(self.query_cache) >= 32:
                self.query_cache.pop(next(iter(self.query_cache)))
            self.query_cache[key] = vector
        return vector

    @staticmethod
    def _rank_sets(sets, scores):
        results = []
        for group in sets:
            ranked = sorted([(scores[mid], mid) for mid in set(group.get('media_ids', [])) if mid in scores], reverse=True)
            if ranked:
                results.append({'set_id': group['id'], 'name': group['name'], 'score': ranked[0][0],
                                'matches': [mid for score, mid in ranked[:3]], 'image_count': len(ranked)})
        results.sort(key=lambda r: (-r['score'], r['name'].casefold(), r['set_id']))
        return results

    @staticmethod
    def _stronger_lead(results):
        # A conservative review filter, NOT a calibrated probability or absence test.
        return bool(results and results[0]['score'] >= .86 and
                    (len(results) == 1 or results[0]['score'] - results[1]['score'] >= .025))

    @staticmethod
    def _description(media):
        return {'media_id': media['id'], 'name': media.get('original_name') or 'Library image',
                'placement': 'Purgatory' if media.get('in_purgatory') else 'Review' if media.get('in_review') else 'Main' if media.get('in_all') else 'Library'}

    def _stamp(self, media):
        path = (self.store.root / media['stored_rel']).resolve()
        if not path.is_relative_to(self.store.root.resolve()):
            raise ValueError('Image is outside the library.')
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def _run(self, ident, sets, candidates, query, query_bytes, revision, owner, scan=False):
        import sqlite3
        started = time.monotonic()
        self.cache_hits = self.encoded_images = 0
        photoshoot = self.jobs[ident]['matching_mode'] == 'photoshoot'
        grouped = {mid for group in sets for mid in group.get('media_ids', [])}
        ungrouped = [mid for mid in candidates if mid not in grouped]
        try:
            if not candidates or (scan and (not ungrouped or not grouped.intersection(candidates))):
                self.update(ident, phase='No ungrouped images to scan' if scan and not ungrouped else 'No existing Set images to compare' if scan else 'No library images to compare', unsearchable_sets=len(sets), indexed_images=0)
                return
            self._prepare(ident)
            if photoshoot:
                self._prepare_scene(ident)
            self._check_cancel(ident)
            issues = [];vectors = {};scenes = {}
            self.vector_cache = {mid: value for mid, value in self.vector_cache.items() if mid in candidates}
            self.scene_vector_cache = {mid: value for mid, value in self.scene_vector_cache.items() if mid in candidates}
            with sqlite3.connect(self.cache / 'embeddings.sqlite') as db:
                db.execute('CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector BLOB NOT NULL)')
                self.update(ident, phase='Checking scene cache; indexing new Photoshoot images' if photoshoot else 'Checking image cache; indexing new library images', done=0, total=len(candidates))
                for index, (mid, media) in enumerate(candidates.items()):
                    self._check_cancel(ident)
                    try:
                        before = self._stamp(media)
                        vector = self._vector(db, media, count=not photoshoot)
                        scene = self._vector(db, media, scene=True) if photoshoot else None
                        if before != self._stamp(media):
                            raise ValueError('Image changed during matching.')
                        vectors[mid] = vector
                        if photoshoot:
                            scenes[mid] = scene
                        self.contexts[ident]['stamps'][mid] = before
                    except Exception as exc:
                        issues.append({'media_id': mid, 'message': str(exc)})
                    if (index + 1) % 32 == 0:
                        db.commit()
                    self.update(ident, done=index+1, cached_images=self.cache_hits, new_images=self.encoded_images)
                db.commit()
                target_ids = [mid for mid in vectors if not scan or mid in grouped]
                matrix = self.np.stack([vectors[mid] for mid in target_ids]) if target_ids else None
                scene_matrix = self.np.stack([scenes[mid] for mid in target_ids]) if photoshoot and target_ids else None
                def compare(views, scene_views=None):
                    if matrix is None:
                        return {}
                    values = views @ matrix.T
                    if photoshoot:
                        # Score each orientation coherently before taking the best one.
                        # Setting and surrounding detail outweigh clothing; no skin/face classifier.
                        values = .10 * values + .55 * (scene_views[:, 0] @ scene_matrix[:, 0].T) + .35 * (scene_views[:, 1] @ scene_matrix[:, 1].T)
                    values = self.np.clip(values.max(axis=0), -1, 1)
                    return {mid: float(values[i]) for i, mid in enumerate(target_ids)}
                def query_scores(item, data=None):
                    self._check_cancel(ident)
                    if item and item['id'] not in vectors:
                        raise ValueError('A query or selected example could not be checked. Check its original file or remove the example.')
                    vector = vectors[item['id']] if item else self._uploaded_vector(data)
                    views = self._orientations(db, item, data, vector)
                    scene_views = None
                    if photoshoot:
                        self._check_cancel(ident)
                        scene = scenes[item['id']] if item else self._uploaded_vector(data, scene=True)
                        scene_views = self._orientations(db, item, data, scene, scene=True)
                    return compare(views, scene_views)
                results = [];individuals = [];scan_results = []
                if scan:
                    self.update(ident, phase='Checking non-set images against existing Sets', done=0, total=len(ungrouped))
                    for index, mid in enumerate(ungrouped):
                        self._check_cancel(ident)
                        if mid in vectors:
                            try:
                                targets = [s for s in sets if s["id"] == self.contexts[ident]["target_set_id"]] if self.contexts[ident].get("target_set_id") else sets
                                ranked = self._rank_sets(targets, query_scores(candidates[mid]))
                                row = self._description(candidates[mid])
                                row.update(results=ranked[:5], stronger=self._stronger_lead(ranked))
                                scan_results.append(row)
                            except Exception as exc:
                                issues.append({'media_id': mid, 'message': str(exc)})
                        if (index + 1) % 16 == 0:
                            db.commit()
                        self.update(ident, done=index+1)
                    scan_results.sort(key=lambda row: (not row['stronger'], -(row['results'][0]['score'] if row['results'] else -1), row['media_id']))
                else:
                    self.update(ident, phase='Comparing setting, surrounding details and outfit' if photoshoot else 'Analyzing query outfit and orientation', done=0, total=0)
                    scores = query_scores(query, query_bytes)
                    evidence = [scores]
                    context = self.contexts[ident]
                    for mid in context['example_ids']:
                        if mid == context['query_id']:
                            continue
                        evidence.append(query_scores(candidates[mid]))
                    for data in context['example_bytes']:
                        evidence.append(query_scores(None, data))
                    if len(evidence)>1:
                        # Preserve a strong angle while rewarding agreement across outfit examples.
                        scores = {mid: .75*max(e[mid] for e in evidence)+.25*sum(e[mid] for e in evidence)/len(evidence) for mid in scores}
                    results = self._rank_sets(sets, scores)
                    for mid in ungrouped:
                        if mid in scores and mid != self.contexts[ident]['query_id'] and mid not in self.contexts[ident]['example_ids']:
                            item = self._description(candidates[mid]);item['score'] = scores[mid];individuals.append(item)
                    individuals.sort(key=lambda row: (-row['score'], row['media_id']))
            self._check_cancel(ident)
            with self.store.lock:
                if self.store.revision != revision:
                    live_sets = [s for s in self.store.data.get('sets', []) if s.get('character_id') == owner and s.get('kind', 'set') == 'set']
                    live_media = {m['id']: m for m in self.store.data['media'] if m.get('character_id') == owner and m.get('media_type', 'image') == 'image'}
                    if self._catalog_signature(sets, candidates) != self._catalog_signature(live_sets, live_media):
                        raise ValueError('Set images changed during search. Run the search again to refresh results.')
            searchable_sets = sum(any(mid in vectors for mid in group.get('media_ids', [])) for group in sets)
            self.update(ident, results=results, individual_results=individuals, scan_results=scan_results,
                        query_sets=[{'set_id': group['id'], 'name': group['name']} for group in sets if self.contexts[ident]['query_id'] in group.get('media_ids', [])],
                        issues=issues, unsearchable_sets=len(sets)-searchable_sets, indexed_images=len(vectors),
                        phase=f"Scanned {len(scan_results)} non-set images against {searchable_sets} Sets" if scan else f"Compared {len(vectors)} library images across {searchable_sets} Sets and {len(individuals)} ungrouped images")
        except InterruptedError as exc:
            self.update(ident, cancelled=True, phase=str(exc))
        except Exception as exc:
            self.update(ident, error=str(exc), phase='Set search could not finish')
        finally:
            self.update(ident, running=False, elapsed_seconds=round(time.monotonic()-started, 2))

    def _completed(self, ident):
        job = self.jobs.get(ident)
        if not job or job['running'] or job.get('error') or job.get('cancelled'):
            raise ValueError('Run a complete search before assigning images.')
        return job, self.contexts[ident]

    def _validate_match_media(self, context, mid):
        expected = context['media'].get(mid)
        current = self.store.media_item(mid)
        if (not current or not expected or any(current.get(k) != expected.get(k) for k in ('character_id', 'stored_rel', 'sha256', 'media_type'))
                or self._stamp(current) != context['stamps'].get(mid)):
            raise ValueError('A matching image changed or was removed. Search again before assigning it.')
        return current

    def assign_scan(self, body):
        ident, mid, sid = str(body.get('job_id', '')), str(body.get('media_id', '')), str(body.get('set_id', ''))
        with self.lock, self.store.lock:
            job, context = self._completed(ident)
            row = next((r for r in job['scan_results'] if r['media_id'] == mid), None)
            result = next((r for r in row['results'] if r['set_id'] == sid), None) if row else None
            target = self.store.set_item(sid)
            if not job['scan'] or not result or not target or target.get('character_id') != context['owner']:
                raise ValueError('This scan suggestion is no longer available.')
            self._validate_match_media(context, mid)
            if any(mid in s.get('media_ids', []) for s in self.store.data.get('sets', []) if s.get('kind', 'set') == 'set'):
                raise ValueError('This image already belongs to a Set. It was not moved.')
            for example in result['matches']:
                self._validate_match_media(context, example)
                if example not in target.get('media_ids', []):
                    raise ValueError('The suggested Set changed. Search again before assigning.')
            item = self.store.update_set(sid, add_media_ids=[mid], preserve_placement=True)
            job['assigned_ids'].append(mid)
            return copy.deepcopy(item)

    def create_from_matches(self, body):
        ident = str(body.get('job_id', ''))
        ids = body.get('media_ids', [])
        if not isinstance(ids, list) or not ids or any(not isinstance(mid, str) for mid in ids):
            raise ValueError('Select matching library images first.')
        ids = list(dict.fromkeys(ids))
        with self.lock, self.store.lock:
            job, context = self._completed(ident)
            if job['scan']:
                raise ValueError('Use individual image matching to create a Set.')
            available = {r['media_id'] for r in job['individual_results']}
            if not set(ids).issubset(available):
                raise ValueError('Selected images are not in these search results.')
            query_id = str(body.get('query_media_id', ''))
            target_id = str(body.get('target_set_id', ''))
            if query_id:
                # Only the query used for this job may be included or anchor a Set.
                if query_id != context.get('query_id'):
                    raise ValueError('Query image does not match this search.')
                self._validate_match_media(context, query_id)
            memberships = [s for s in self.store.data.get('sets', []) if s.get('kind', 'set') == 'set']
            for mid in ids:
                self._validate_match_media(context, mid)
                if any(mid in group.get('media_ids', []) for group in memberships):
                    raise ValueError('A selected image already belongs to a Set. Search again; nothing was moved.')
            if target_id:
                target = self.store.set_item(target_id)
                if not query_id or not target or target.get('character_id') != context['owner'] or query_id not in target.get('media_ids', []):
                    raise ValueError('The query image is no longer in this Set.')
                return copy.deepcopy(self.store.update_set(target_id, add_media_ids=ids, preserve_placement=True))
            if query_id:
                if any(query_id in group.get('media_ids', []) for group in memberships):
                    raise ValueError('The query already belongs to a Set. Search again to add matches to that Set.')
                ids.append(query_id)
            return copy.deepcopy(self.store.create_set(context['owner'], str(body.get('name', '')), ids, preserve_placement=True))


class BattleRankings:
    """Personal rankings, atomic vote persistence and resumable per-character rounds."""
    MODEL = 'joint-history-v1'
    def __init__(self, store):
        self.store = store
        self.path = store.root / 'battles.json'
        self.data = None
        self.rng = random.SystemRandom()

    def _load(self):
        if self.data is None:
            self.data = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'version':1, 'boards':{}}
            if self.data.get('version') != 1 or not isinstance(self.data.get('boards'), dict):
                self.data = None
                raise ValueError('Battle rankings could not be read. Existing rankings have not been replaced.')
            if self.data.get('boards') and self.data.get('rating_model') != self.MODEL:
                try:
                    migrated = copy.deepcopy(self.data)
                    for board in migrated['boards'].values():
                        self._priors(board)
                        self._fit_history(board)
                        board['revision'] = uuid.uuid4().hex
                    migrated['rating_model'] = self.MODEL
                    self._save(migrated)
                except Exception:
                    self.data = None
                    raise
        return self.data

    def _save(self, data):
        temporary = self.path.with_suffix('.json.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                if data.get('rating_model') == self.MODEL and (self.data or {}).get('rating_model') != self.MODEL:
                    migration = self.store.backup_dir / 'battles-before-joint-history.json'
                    if not migration.exists():
                        shutil.copy2(self.path, migration)
                if data.get('rating_model') and not (self.data or {}).get('rating_model'):
                    migration = self.store.backup_dir / 'battles-before-placement.json'
                    if not migration.exists():
                        shutil.copy2(self.path, migration)
                shutil.copy2(self.path, self.store.backup_dir / 'battles-previous.json')
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.data = data

    @staticmethod
    def _active_history(board):
        undone = {e.get('vote_id') for e in board.get('history', []) if e.get('type') == 'undo'}
        return [e for e in board.get('history', []) if e.get('type') == 'vote' and e.get('id') not in undone]

    def _priors(self, board):
        """Freeze pre-log evidence, NOT the latest rating that already includes the log.

        Earliest before-values include older unlogged battles. Even an undone first
        event supplies the correct starting point. New entries start at 1200/350.
        """
        if 'history_priors' in board:
            return board['history_priors']
        priors = {}
        for event in board.get('history', []):
            if event.get('type') != 'vote':
                continue
            for ident, score in zip((event['left'], event['right']), event['before']):
                priors.setdefault(ident, {'rating':score['rating'], 'rd':score['rd']})
        for ident in board['ratings']:
            score = self._score(board, ident)
            priors.setdefault(ident, {'rating':score['rating'], 'rd':score['rd']})
        board['history_priors'] = priors
        return priors

    @staticmethod
    def _inverse_diagonal(diagonal, edges):
        """Exact dense Cholesky inverse diagonal for medium-sized boards.

        Factor once instead of running one iterative solve per rated entry.
        Keep sparse PCG for large boards to bound dense memory and cubic work.
        No change to priors, evidence, convergence or uncertainty semantics.
        """
        n = len(diagonal)
        if not 24 <= n <= 384 or len(edges) < n * 3:
            return None
        lower = [[0.] * n for _ in range(n)]
        for i, value in enumerate(diagonal):
            lower[i][i] = value
        for a, b, weight in edges:
            lower[max(a,b)][min(a,b)] -= weight
        for i, row in enumerate(lower):
            for j in range(i):
                other = lower[j]
                row[j] = (row[j] - sum(row[k]*other[k] for k in range(j))) / other[j]
            pivot = row[i] - sum(row[k]*row[k] for k in range(i))
            if not math.isfinite(pivot) or pivot <= 0:
                return None  # Retain the established solver on numerical failure.
            row[i] = math.sqrt(pivot)
        inverse = [[0.] * n for _ in range(n)]
        for i, row in enumerate(lower):
            inverse[i][i] = 1 / row[i]
            for j in range(i):
                inverse[i][j] = -sum(row[k]*inverse[k][j] for k in range(j,i)) / row[i]
        return [sum(inverse[k][i]**2 for k in range(i,n)) for i in range(n)]

    def _fit_history(self, board, confidence=True):
        """Regularized joint Bradley-Terry fit; a tie is one half-result.

        Fixed Gaussian priors anchor the scale; each active vote enters once.
        Newton/PCG solves the sparse convex problem. Marginal Laplace variances
        include opponent uncertainty (not just the Hessian diagonal). No numeric
        dependencies or arbitrary re-awarding of old Elo gains are needed.
        """
        priors = self._priors(board)
        events = self._active_history(board)
        ids = sorted(set(board['ratings']) | {e[k] for e in events for k in ('left','right')})
        if not ids:
            return
        scale = 400 / math.log(10)
        index = {ident:i for i,ident in enumerate(ids)}
        n = len(ids)
        means, precision = [], []
        for ident in ids:
            prior = priors.setdefault(ident, {'rating':1200., 'rd':350.})
            means.append((prior['rating'] - 1200) / scale)
            precision.append((scale / max(50., min(350., prior['rd']))) ** 2)
        aggregated = {}
        for event in events:
            a, b = index[event['left']], index[event['right']]
            value = {'left':1., 'right':0., 'tie':.5}[event['outcome']]
            if a > b:
                a, b, value = b, a, 1-value
            count, wins = aggregated.get((a,b), (0,0.))
            aggregated[a,b] = (count+1, wins+value)
        pairs = [(a,b,count,wins) for (a,b),(count,wins) in sorted(aggregated.items())]

        def system(x):
            diagonal = list(precision)
            gradient = [precision[i]*(x[i]-means[i]) for i in range(n)]
            edges = []
            loss = sum(.5*precision[i]*(x[i]-means[i])**2 for i in range(n))
            for a,b,count,wins in pairs:
                difference = x[a]-x[b]
                probability = 1 / (1 + math.exp(-max(-40.,min(40.,difference))))
                residual = count*probability-wins
                gradient[a] += residual; gradient[b] -= residual
                weight = count*probability*(1-probability)
                diagonal[a] += weight; diagonal[b] += weight
                edges.append((a,b,weight))
                loss += count*(max(difference,0)+math.log1p(math.exp(-abs(difference))))-wins*difference
            return loss, gradient, diagonal, edges

        def solve(rhs, diagonal, edges):
            # Symmetric positive definite: positive prior precision fixes even
            # disconnected components and perfectly one-sided win records.
            result = [0.]*n
            residual = list(rhs)
            direction = [residual[i]/diagonal[i] for i in range(n)]
            product = sum(residual[i]*direction[i] for i in range(n))
            threshold = max(1e-22, sum(v*v for v in rhs)*1e-18)
            for _ in range(max(20,n*2)):
                if sum(v*v for v in residual) <= threshold:
                    break
                hd = [diagonal[i]*direction[i] for i in range(n)]
                for a,b,weight in edges:
                    hd[a] -= weight*direction[b]; hd[b] -= weight*direction[a]
                denominator = sum(direction[i]*hd[i] for i in range(n))
                if denominator <= 0:
                    raise ValueError('Historical rating solver failed; no vote has been saved.')
                alpha = product/denominator
                result = [result[i]+alpha*direction[i] for i in range(n)]
                residual = [residual[i]-alpha*hd[i] for i in range(n)]
                z = [residual[i]/diagonal[i] for i in range(n)]
                updated = sum(residual[i]*z[i] for i in range(n))
                beta = updated/product
                direction = [z[i]+beta*direction[i] for i in range(n)]
                product = updated
            return result

        x = list(means)  # deterministic; the saved current ratings are NOT evidence
        for _ in range(40):
            loss, gradient, diagonal, edges = system(x)
            if max(abs(g) for g in gradient) < 1e-8:
                break
            step = solve(gradient, diagonal, edges)
            factor = 1.
            while factor > 1e-8:
                candidate = [x[i]-factor*step[i] for i in range(n)]
                if system(candidate)[0] <= loss+1e-12:
                    break
                factor *= .5
            x = candidate
        _, gradient, diagonal, edges = system(x)
        if max(abs(g) for g in gradient) > 1e-5:
            raise ValueError('Historical ratings did not converge; no vote has been saved.')
        variances = self._inverse_diagonal(diagonal, edges) if confidence else None
        for ident,i in index.items():
            if ident not in board['ratings']:
                continue
            score = board['ratings'][ident]
            score['rating'] = 1200 + scale*x[i]
            if confidence:
                if variances is None:
                    unit = [0.]*n; unit[i] = 1.
                    variance = solve(unit,diagonal,edges)[i]
                else:
                    variance = variances[i]
                score['rd'] = max(50., min(350., scale*math.sqrt(max(0.,variance))))

    @staticmethod
    def _score(board, ident):
        score = dict(board['ratings'].get(ident, {'rating':1200., 'played':0, 'wins':0, 'ties':0, 'losses':0}))
        # Retain old Elo scores; their uncertainty is only an initial estimate.
        score.setdefault('rd', max(160., 350. / math.sqrt(1 + score['played']/3)))
        score.setdefault('opponents', {})
        score.setdefault('last_seen', 0)
        return score

    @staticmethod
    def _quality(score):
        varied = len(score.get('opponents', {}))
        if not score['played']:
            return 'Unrated'
        if score['played'] < 6 or varied < 4 or score['rd'] > 140:
            return 'Provisional'
        if score['played'] >= 12 and varied >= 8 and score['rd'] <= 85:
            return 'Established'
        return 'Developing'

    @staticmethod
    def _glicko(rating, rd, games):
        """Glickman original Glicko, static preferences: no inactivity inflation.
        games contains pre-update (opponent rating, RD, result) tuples.
        https://www.glicko.net/glicko/glicko.pdf ; a one-vote rating period.
        """
        q = math.log(10)/400
        information = evidence = 0.
        for other_rating, other_rd, outcome in games:
            g = 1/math.sqrt(1 + 3*q*q*other_rd*other_rd/(math.pi*math.pi))
            expected = 1/(1+10**max(-12., min(12., -g*(rating-other_rating)/400)))
            information += q*q*g*g*expected*(1-expected)
            evidence += g*(outcome-expected)
        precision = 1/(rd*rd) + information
        return rating + q*evidence/precision, max(50., math.sqrt(1/precision))

    def _entries(self, owner, kind):
        media = {m['id']:m for m in self.store.data['media'] if m.get('character_id') == owner
                 and (kind=='sets' or m.get('media_type') != 'video') and not m.get('in_review') and not m.get('in_purgatory')}
        groups=[g for g in self.store.data.get('sets',[]) if g.get('character_id')==owner and g.get('kind','set')=='set']
        if kind == 'images':
            memberships,captains={},{}
            for group in groups:
                label={'id':group['id'],'name':group.get('name','Set')}
                for ident in group.get('media_ids',[]):memberships.setdefault(ident,[]).append(label)
                captain=self._captain(owner,group,media)
                if captain:captains.setdefault(captain,[]).append(label)
            return {ident:{'id':ident, 'name':m.get('original_name',m.get('filename','Image')), 'images':[ident], 'count':1,
                           'categories':list(m.get('categories',[])), 'flagged_for_removal':bool(m.get('flagged_for_removal')),
                           'sets':memberships.get(ident,[]),'captain_sets':captains.get(ident,[])}
                    for ident,m in media.items() if self.store._in_main(m)}
        entries = {}
        for group in groups:
            images = list(dict.fromkeys(i for i in group.get('media_ids',[]) if i in media))
            if not images:continue
            cover = group.get('cover_media_id')
            if cover in images:images.remove(cover);images.insert(0,cover)
            entries[group['id']] = {'id':group['id'], 'name':group.get('name','Set'), 'images':images, 'count':len(images),
                                    'categories':list(group.get('categories',[])), 'captain_id':self._captain(owner,group,media),
                                    'preview_id':self._captain(owner,group,media) or images[0],
                                    'video_ids':[i for i in images if media[i].get('media_type')=='video']}
            entries[group['id']]['video_count']=len(entries[group['id']]['video_ids'])
            entries[group['id']]['image_count']=len(images)-entries[group['id']]['video_count']
        return entries

    def _captain(self, owner, group, media):
        collection=self.store.character(owner).get('collection') or {}
        # Legacy data did not distinguish a chosen captain from an automatic cover.
        if collection.get('captain_schema')!=2:return None
        saved=collection.get('captains',{}).get(group['id'])
        return saved if saved in group.get('media_ids',[]) and saved in media and media[saved].get('media_type')!='video' else None

    def _sync_cards(self, board, entries):
        """Observe eligibility, never infer unrecorded historical ranks."""
        eligible={i:e for i,e in entries.items() if not e.get('flagged_for_removal')}
        now=now_iso();cards=board.get('cards')
        if cards is None:
            cards=board['cards']={'started_at':now,'eligible':list(eligible),'arrivals':{},'leaders':{},'best':{}}
        previous=set(cards['eligible'])
        for ident in set(eligible)-previous:
            cards['arrivals'][ident]={'at':now,'token':uuid.uuid4().hex,'seen':False}
        cards['eligible']=list(eligible)
        rows=self._ranked_rows(board,entries)
        qualified=sum(not r['provisional'] for r in rows)>=10
        for row in rows:
            if not row['provisional']:
                best=cards['best'].setdefault(row['id'],{'rating':row['rating'],'position':row.get('position'),'at':now})
                if row['rating']>best['rating']:best.update(rating=row['rating'],at=now)
                if row.get('position'):best['position']=min(best.get('position') or row['position'],row['position'])
            if qualified and row['leader'] and row['rating_status']=='Established' and row['id'] in eligible:
                cards['leaders'].setdefault(row['id'],now)
        return cards

    def _card_metadata(self, board, rows, owner, kind):
        cards=board.get('cards') or {};collection=self.store.character(owner).get('collection') or {};prefs=collection.get('titles',{})
        for row in rows:
            row['arrival']=copy.deepcopy(cards.get('arrivals',{}).get(row['id']))
            row['best_recorded']=copy.deepcopy(cards.get('best',{}).get(row['id']))
            row['titles']=[]
            at=cards.get('leaders',{}).get(row['id'])
            if at and not row.get('leader'):
                row['titles'].append({'id':'former_number_one','name':'Former #1','at':at,'detail':'Recorded as outright #1 with Established confidence in a pool of at least 10 placed '+kind+'.'})
            # Captain lettering is only for eligible main images, never set cards.
            if kind=='images' and row.get('captain_sets'):
                row['titles'].append({'id':'team_captain','name':'Captain','detail':'Captain of '+', '.join(g['name'] for g in row['captain_sets'])})
            key=('set:' if kind=='sets' else '')+row['id']
            row['automatic_title_ids']=[t['id'] for t in row['titles']]
            overrides=collection.get('title_overrides',{}).get(key,{})
            allowed={'former_number_one':'Former #1',**({'team_captain':'Captain'} if kind=='images' else {})}
            row['title_overrides']={i:v for i,v in overrides.items() if i in allowed and v in ('grant','suppress')}
            for ident,name in allowed.items():
                value=row['title_overrides'].get(ident)
                if value=='suppress':row['titles']=[t for t in row['titles'] if t['id']!=ident]
                elif value=='grant' and ident not in row['automatic_title_ids']:
                    row['titles'].append({'id':ident,'name':name,'detail':'Manually restored in title corrections.','manual':True})
            row['titles'].sort(key=lambda t:0 if t['id']=='former_number_one' else 1)
            row['title_choice']=prefs.get(key,'auto')

    @staticmethod
    def _in_scope(entry, session, scheduling=False):
        return (entry['count'] >= session['minimum'] and
                (not session.get('category') or session['category'] in entry.get('categories',[])) and
                (not scheduling or not entry.get('flagged_for_removal')))

    def _pair(self, board, entries, champion=None, rng=None):
        rng = rng or self.rng
        session = board['session']
        pool = [e for e in entries.values() if self._in_scope(e,session,scheduling=True)]
        refining = session['mode'] in ('refine10', 'refine25')
        if refining:
            pool = sorted((e for e in pool if self._score(board,e['id'])['played']),
                          key=lambda e:(-self._score(board,e['id'])['rating'],e['id']))[:int(session['mode'][6:])]
        by_id = {e['id']:e for e in pool}
        if len(pool) < 2:
            return None
        scores = {e['id']:self._score(board, e['id']) for e in pool}
        recent = {tuple(sorted(p)) for p in board.get('recent', [])}
        scheduler = board.setdefault('scheduler', {'batch':[]})
        waiting = [e['id'] for e in pool if self._quality(scores[e['id']]) in ('Unrated','Provisional')]
        # First spread a few observations across the collection. Then rotate
        # unfinished entries by recency and uncertainty; no sticky batch can starve them.
        waiting.sort(key=lambda i:(scores[i]['played']>=4, scores[i]['played'] if scores[i]['played']<4 else scores[i]['last_seen'],
                                   -scores[i]['rd'], scores[i]['last_seen'], rng.random()))
        batch = waiting[:8]
        scheduler['batch'] = batch
        target = session.get('target_id')
        forced = champion if champion in by_id else target if target in by_id else None
        if target and target not in by_id:
            return None
        if forced:
            candidates = [by_id[forced]]
        elif waiting and not refining and (session['mode']=='placements' or board.get('votes',0)%8 != 7):
            candidates = [by_id[i] for i in waiting]
        else:
            if session['mode']=='placements' and not waiting:
                return None
            # Developing ratings get attention; established images mainly serve
            # as opponents. Occasional recency-first turns preserve broad coverage.
            candidates = sorted(pool,key=lambda e:((scores[e['id']]['last_seen'], -scores[e['id']]['rd'])
                                if board.get('votes',0)%8==7 else
                                (self._quality(scores[e['id']])=='Established',-scores[e['id']]['rd'],scores[e['id']]['last_seen'])))
        if not forced and session['mode']!='placements':
            chosen = {e['id'] for e in candidates}
            candidates += [e for e in pool if e['id'] not in chosen]
        for attempt in range(2):
            for left in candidates:
                ls = scores[left['id']]
                choices = [e for e in pool if e['id'] != left['id'] and
                           (not session['similar'] or max(e['count'],left['count']) <= 2*min(e['count'],left['count'])) and
                           (attempt or tuple(sorted((left['id'],e['id']))) not in recent)]
                if not choices:
                    continue
                def utility(right):
                    rs = scores[right['id']]
                    q = math.log(10)/400
                    g = 1/math.sqrt(1+3*q*q*rs['rd']**2/(math.pi**2))
                    probability = 1/(1+10**max(-12.,min(12.,-g*(ls['rating']-rs['rating'])/400)))
                    information = g*g*probability*(1-probability)
                    # Reliable, similarly rated and varied opponents are informative.
                    diversity = 1/math.sqrt(1+ls.get('opponents',{}).get(right['id'],0))
                    return information*diversity*(.9+.2*rng.random())
                choices.sort(key=utility,reverse=True)
                # Periodic broad comparisons keep rating ranges connected.
                right = rng.choice(choices[:min(8,len(choices))]) if board.get('votes',0)%8 == 7 else choices[0]
                ids = [left['id'],right['id']]
                if rng.random()<.5:
                    ids.reverse()
                return {'id':uuid.uuid4().hex, 'left':ids[0], 'right':ids[1],
                        'reason':'Focus comparisons' if target else 'Refine top rankings' if refining else 'Initial comparisons' if ls['played']<4 else 'Finish placement' if left['id'] in waiting else 'Calibration'}
        return None

    def _ranked_rows(self, board, entries):
        rows = [{**e, **self._score(board, i)} for i, e in entries.items()]
        rows.sort(key=lambda r: (r['played'] == 0, -r['rating'], -r['played'], r['id']))
        for row in rows:
            row['rating_status'] = self._quality(row)
            row['opponent_count'] = len(row.pop('opponents', {}))
        placed = sorted((r for r in rows if r['rating_status'] in ('Developing','Established')), key=lambda r: -r['rating'])
        enough = len(placed) >= 5 and round(placed[0]['rating'], 8) > round(placed[-1]['rating'], 8)
        positions, counts = {}, {}
        for index, item in enumerate(placed, 1):
            rating = round(item['rating'], 8)
            positions.setdefault(rating, index)
            counts[rating] = counts.get(rating, 0) + 1
        for row in rows:
            row['provisional'] = row['rating_status'] in ('Unrated','Provisional')
            row['tier_rank'] = None
            if not row['played']:
                tier = 'Unranked'
            elif row['provisional']:
                tier = 'Provisional'
            elif not enough:
                tier = 'Placement'
            else:
                rating = round(row['rating'], 8)
                rank = positions[rating]
                row['tier_rank'] = rank
                tier = next((name for fraction,name in ((.01,'Grandmaster'),(.05,'Master'),(.10,'Diamond'),(.25,'Platinum'),(.50,'Gold'),(.80,'Silver'))
                             if rank <= max(1,math.ceil(len(placed)*fraction))), 'Bronze')
            row['leader'] = bool(enough and row['tier_rank'] == 1 and counts.get(round(row['rating'],8)) == 1)
            row['tier'] = tier
        positions = {}
        played = [r for r in rows if r['played']]
        for index,row in enumerate(played,1):
            row['position'] = positions.setdefault(round(row['rating'],8),index)
            neighbors = played[max(0,index-2):min(len(played),index+1)]
            row['close_contender'] = any(other is not row and abs(row['rating']-other['rating']) <= math.hypot(row['rd'],other['rd']) for other in neighbors)
        return rows

    def _awards(self, board, rows, legacy=False):
        awards = {}
        def add(key, title, detail, level='Gold', entry=None):
            awards[key] = {'id': key, 'title': title, 'detail': detail, 'level': level,
                           'entry_id': entry['id'] if entry else None,
                           'name': entry['name'] if entry else '',
                           'image_id': entry['images'][0] if entry else None,
                           'earned_at': None if legacy else now_iso(), 'legacy': legacy}
        for family in self._achievement_progress(board, rows):
            for milestone in family['milestones']:
                if family['value'] >= milestone:
                    add('progress:'+family['id']+':'+str(milestone),family['title'],str(milestone)+family['unit'],
                        'Grandmaster' if family['id']=='grandmaster' else 'Gold')
        return awards

    @staticmethod
    def _achievement_progress(board, rows):
        placed=sum(not r['provisional'] for r in rows)
        specifications=[('placements','Placement progress',placed,[10,25,50,100,250,500,1000],' entries placed'),
                        ('coverage','Collection coverage',100*placed/len(rows) if rows else 0,[25,50,75,100],'% placed'),
                        ('established','Established collection',sum(r['rating_status']=='Established' for r in rows),[5,10,25,50,100,250],' established entries'),
                        ('grandmaster','First Grandmaster',int(any(r['tier']=='Grandmaster' for r in rows)),[1],' Grandmaster'),
                        ('votes','Comparisons completed',board.get('votes',0),[1,25,100,500,1000,2500,5000],' saved comparisons')]
        awards=board.get('trophies',{})
        result=[]
        for ident,title,value,milestones,unit in specifications:
            earned=[m for m in milestones if value>=m or 'progress:'+ident+':'+str(m) in awards or
                    (ident=='votes' and 'votes:'+str(m) in awards) or
                    (ident=='grandmaster' and any(k.startswith(('tier:Grandmaster:','tier:Champion:')) for k in awards))]
            achieved=max(earned,default=0)
            result.append({'id':ident,'title':title,'value':value,'milestones':milestones,'achieved':achieved,
                           'next':next((m for m in milestones if m>achieved),None),'unit':unit})
        return result

    def _record_rating_path(self, board, before, action, pair):
        paths=board.setdefault('rating_paths',{})
        clock=board['path_clock']=board.get('path_clock',0)+1
        at=now_iso()
        participants={pair.get('left'),pair.get('right')}
        for ident in set(before)|set(board['ratings'])|participants:
            if not ident:continue
            old=self._score({'ratings':before},ident);new=self._score(board,ident)
            values=lambda s:[round(s['rating'],1),round(s['rd'],1),s['played']]
            if values(old)==values(new):continue
            points=paths.setdefault(ident,[[clock-1,at,*values(old),'baseline']])
            points.append([clock,at,*values(new),'undo' if action=='undo' else 'direct' if ident in participants else 'indirect'])
            # Keep a long overview and detailed recent history, bounded per entry.
            if len(points)>400:paths[ident]=points[:200:2]+points[200:]

    def _rating_path(self, board, ident, entries):
        if ident not in entries:raise ValueError('This entry is no longer eligible for this leaderboard.')
        points=board.get('rating_paths',{}).get(ident,[])
        past=[]
        cutoff=points[0][1] if points else None
        for event in self._active_history(board):
            if ident not in (event['left'],event['right']) or (cutoff and event['at']>=cutoff):continue
            side=0 if event['left']==ident else 1
            score=event['after'][side]
            past.append([len(past),event['at'],round(score['rating'],1),round(score['rd'],1),score['played'],'older direct'])
        # Downsample only the older display points; raw vote history is preserved.
        if len(past)>200:past=[past[round(i*(len(past)-1)/199)] for i in range(200)]
        opponents=[]
        for event in reversed(self._active_history(board)):
            if ident not in (event['left'],event['right']):continue
            side='left' if event['left']==ident else 'right';other=event['right' if side=='left' else 'left']
            opponents.append({'at':event['at'],'opponent':entries.get(other,{}).get('name','Unavailable entry'),
                              'result':'Tie' if event['outcome']=='tie' else 'Win' if event['outcome']==side else 'Loss'})
            if len(opponents)==20:break
        return {'entry':entries[ident],'points':past+points,'comparisons':opponents,
                'note':'Older points show recorded direct results only. New history includes indirect changes and Undo. Older graph points may be sampled.'}

    def _apply_comparison(self, board, pair, outcome):
        ids=[pair['left'],pair['right']]
        a,b=[self._score(board,i) for i in ids]
        result={'left':1.,'right':0.,'tie':.5}[outcome]
        for ident,other_id,score,opponent,value in ((ids[0],ids[1],a,b,result),(ids[1],ids[0],b,a,1-result)):
            updated=dict(score)
            updated['rating'],updated['rd']=self._glicko(score['rating'],score['rd'],[(opponent['rating'],opponent['rd'],value)])
            updated['played']+=1
            updated['opponents']=dict(score['opponents'])
            updated['opponents'][other_id]=updated['opponents'].get(other_id,0)+1
            updated['last_seen']=board['votes']+1
            updated['wins' if value==1 else 'losses' if value==0 else 'ties']+=1
            updated['streak']=score.get('streak',0)+1 if value==1 else 0
            updated['best_streak']=max(score.get('best_streak',0),updated['streak'])
            board['ratings'][ident]=updated
        board['session']['done']+=1
        board['votes']+=1
        return a,b

    @staticmethod
    def _finish_focus(session):
        target=session.pop('target_id',None)
        session.update(session.pop('return_settings',{'mode':'rank','limit':0,'minimum':session['minimum'],'similar':False}))
        session['done']=0
        session['focus_completed']=target

    def _advance_pair(self, board, entries, previous_pair, outcome):
        session=board['session']
        if 'challenge_return' in session:
            restored=session['challenge_return']
            board['session']=session=restored
        if session.get('target_id') and session['done']>=10:
            self._finish_focus(session)
        champion=previous_pair[outcome] if session['mode']=='winner' and outcome in ('left','right') else None
        # Stable seed for likely next opponents. Forecasts approximate confidence;
        # only saved votes run the full joint uncertainty calculation.
        rng=random.Random(previous_pair['id']+':'+outcome)
        session['pair']=self._pair(board,entries,champion,rng) if not session['limit'] or session['done']<session['limit'] else None

    def _forecast(self, board, entries):
        session=board.get('session') or {};pair=session.get('pair')
        if not pair or any(pair[k] not in entries for k in ('left','right')):
            return []
        candidates=[]
        for outcome in ('left','right','tie','skip'):
            # Do not copy the growing history or undo buffers for previews.
            forecast={key:copy.deepcopy(board.get(key,default)) for key,default in
                      (('ratings',{}),('session',{}),('scheduler',{}),('recent',[]),('votes',0))}
            forecast['recent']=(forecast['recent']+[[pair['left'],pair['right']]])[-32:]
            if outcome!='skip':
                self._apply_comparison(forecast,pair,outcome)
                # A cheap provisional estimate is sufficient for image preloading.
                # Only the actual saved vote fits the complete comparison history.
            self._advance_pair(forecast,entries,pair,outcome)
            upcoming=forecast['session'].get('pair')
            if upcoming:
                for side in ('left','right'):
                    if upcoming[side] not in candidates:candidates.append(upcoming[side])
        return candidates

    def _view(self, board, entries, owner, kind, preload=True):
        session = copy.deepcopy(board.get('session'))
        if session and session.get('pair'):
            pair=session['pair']
            session['available'] = all(i in entries and self._in_scope(entries[i],session) for i in (pair['left'],pair['right']))
        rows = self._ranked_rows(board, entries)
        self._card_metadata(board,rows,owner,kind)
        baseline = (session or {}).get('baseline', {})
        for row in rows:
            row['round_change'] = round(row['rating'] - baseline.get(row['id'], row['rating']), 1)
        awards = board.get('trophies')
        if awards is None:
            awards = self._awards(board, rows, legacy=True)
        # Historical awards remain, even if their entry is no longer eligible.
        existing_media = {m['id'] for m in self.store.data['media'] if m.get('character_id') == owner}
        trophies = [{**award, 'kind': kind, 'image_id': award.get('image_id') if award.get('image_id') in existing_media else None}
                    for award in awards.values()]
        trophies.sort(key=lambda t: (t.get('earned_at') or '', t['id']), reverse=True)
        if session:session.pop('baseline',None)
        return {'character_id':owner,'kind':kind,'revision':board['revision'], 'entries':rows,
                'session':session, 'can_undo':bool(board.get('undo')), 'votes':board.get('votes',0),
                'trophies':trophies, 'ranked_count':sum(not r['provisional'] for r in rows), 'rating_model':self.MODEL,
                'achievements':self._achievement_progress(board,rows),
                'scope_count':sum(self._in_scope(e,session or {'minimum':5 if kind=='sets' else 1},True) for e in entries.values()),
                'unfinished_count':sum(r['provisional'] and self._in_scope(r,session or {'minimum':5 if kind=='sets' else 1},True) for r in rows),
                'placement_batch':list(board.get('scheduler',{}).get('batch',[])),
                'new_count':sum(bool(r.get('arrival')) and not r['arrival']['seen'] and not r.get('flagged_for_removal') for r in rows),
                'cards_started_at':(board.get('cards') or {}).get('started_at'),
                'recorded_votes':len(self._active_history(board)),
                'preload_entries':self._forecast(board,entries) if preload else []}

    def request(self, action, body):
        with self.store.lock:
            owner=str(body.get('character_id',''));kind=body.get('kind','images')
            if not self.store.character(owner) or kind not in ('images','sets'):
                raise ValueError('Choose one character and a valid battle type.')
            data=dict(self._load());data['boards']=dict(data['boards']);key=owner+':'+kind
            board=copy.deepcopy(data['boards'].get(key,{'revision':uuid.uuid4().hex,'ratings':{},'recent':[],'undo':[],'votes':0,'session':None}))
            data['boards'][key]=board
            entries=self._entries(owner,kind)
            if action=='cards':
                data.setdefault('rating_model',self.MODEL)
                before=copy.deepcopy(board.get('cards'))
                self._sync_cards(board,entries)
                if board['cards']!=before:
                    board['revision']=uuid.uuid4().hex
                    self._save(data)
                return self._view(board,entries,owner,kind)
            if action=='history':return self._rating_path(board,str(body.get('entry_id','')),entries)
            if action=='summary':return self._view(board,entries,owner,kind,preload=False)
            if action=='state':return self._view(board,entries,owner,kind)
            # New boards can be started without persisting a read-only state request.
            existing=self._load()['boards'].get(key)
            if existing and body.get('revision') != existing['revision']:
                raise ValueError('Rankings changed in another window. Refresh battles before continuing.')
            if 'trophies' not in board:
                board['trophies'] = self._awards(board, self._ranked_rows(board, entries), legacy=True)
            data['rating_model'] = self.MODEL
            board.setdefault('history', [])
            self._priors(board)
            if action=='seen':
                cards=self._sync_cards(board,entries);tokens=body.get('tokens',{})
                if not isinstance(tokens,dict) or len(tokens)>200:raise ValueError('Invalid arrival selection.')
                for ident,token in tokens.items():
                    arrival=cards['arrivals'].get(ident)
                    if ident in entries and arrival and arrival['token']==token:arrival['seen']=True
            elif action=='challenge':
                left,right=body.get('entry_id'),body.get('opponent_id')
                if left==right or any(i not in entries or entries[i].get('flagged_for_removal') for i in (left,right)):
                    raise ValueError('Choose two different eligible opponents belonging to this person.')
                previous=copy.deepcopy(board.get('session')) or {'mode':'rank','limit':0,'done':0,'minimum':1,'similar':False,'category':'','baseline':{i:self._score(board,i)['rating'] for i in entries}}
                if 'challenge_return' in previous:previous=previous['challenge_return']
                board['session']={'mode':'rank','limit':0,'done':0,'minimum':1,'similar':False,'category':'','baseline':previous.get('baseline',{}),
                                  'challenge_return':previous,'pair':{'id':uuid.uuid4().hex,'left':left,'right':right,'reason':'Direct challenge'}}
            elif action in ('start','place'):
                target = str(body.get('entry_id','')) if action=='place' else None
                if action=='place' and target not in entries:
                    raise ValueError('This entry is not eligible for battles. Images must be in Main; Review, Purgatory and videos are excluded.')
                mode = 'rank' if target else body.get('mode','rank')
                previous = board.get('session') or {}
                return_settings={k:previous.get(k,v) for k,v in {'mode':'rank','limit':0,'minimum':1 if kind=='images' else min(5,entries[target]['count']) if target else 5,'similar':False,'category':''}.items()}
                if previous.get('target_id'):return_settings=copy.deepcopy(previous.get('return_settings',return_settings))
                limit = 10 if target else body.get('limit',0)
                minimum = min(5,entries[target]['count']) if target and kind=='sets' else body.get('minimum',5) if kind=='sets' else 1
                if mode not in ('rank','placements','winner','refine10','refine25') or type(limit) is not int or limit not in (0,10,25,50):
                    raise ValueError('Choose a valid mode and round length.')
                if type(minimum) is not int or not 1<=minimum<=10000:
                    raise ValueError('Minimum set size must be between 1 and 10,000 images.')
                category='' if target else str(body.get('category',''))
                categories=self.store.character(owner).get('categories' if kind=='images' else 'set_categories',[])
                if category and not any(c['id']==category and (kind=='sets' or c.get('media_type','image')=='image') for c in categories):
                    raise ValueError('Choose a valid category for this battle type.')
                board['session']={'mode':mode,'limit':limit,'done':0,'minimum':minimum,
                                  'category':category,
                                  'similar':not target and kind=='sets' and body.get('similar') is True, 'target_id':target,
                                  'baseline':{i:self._score(board,i)['rating'] for i in entries}}
                if target:board['session']['return_settings']=return_settings
                pair=self._pair(board,entries)
                if not pair and mode!='placements':raise ValueError('Not enough eligible opponents in this category. Check the minimum size and removal flags.')
                board['session']['pair']=pair
            elif action=='resume':
                if not (board.get('session') or {}).get('target_id'):raise ValueError('No focused comparison is active.')
                previous_pair=board['session']['pair']
                self._finish_focus(board['session'])
                self._advance_pair(board,entries,previous_pair,'skip')
            elif action=='vote':
                session=board.get('session');pair=(session or {}).get('pair');outcome=body.get('outcome')
                if not pair or pair['id']!=body.get('pair_id') or outcome not in ('left','right','tie','skip'):
                    raise ValueError('This matchup is no longer active. Refresh battles.')
                ids=[pair['left'],pair['right']]
                if any(i not in entries or not self._in_scope(entries[i],session) for i in ids):
                    raise ValueError('An opponent is no longer eligible. Start a new round.')
                before={'session':copy.deepcopy(session),'recent':list(board['recent']),'votes':board['votes'],
                        'ratings':{i:copy.deepcopy(board['ratings'].get(i)) for i in ids}, 'card_record_before':{k:copy.deepcopy((board.get('cards') or {}).get(k,{})) for k in ('leaders','best')}, 'awarded_trophy_ids':[], 'scheduler':copy.deepcopy(board.get('scheduler',{}))}
                board['recent']=(board['recent']+[ids])[-32:]
                champion=None
                if outcome!='skip':
                    previous_ratings=copy.deepcopy(board['ratings'])
                    a,b=self._apply_comparison(board,pair,outcome)
                    event_id=uuid.uuid4().hex
                    before['history_vote_id']=event_id
                    summary=lambda score:{k:score[k] for k in ('rating','rd','played')}
                    board['history'].append({'id':event_id,'type':'vote','at':now_iso(),'left':ids[0],'right':ids[1],
                                             'outcome':outcome,'model':self.MODEL,'before':[summary(a),summary(b)],
                                             'after':[summary(board['ratings'][i]) for i in ids]})
                    self._fit_history(board)
                    self._record_rating_path(board,previous_ratings,'vote',pair)
                    board['history'][-1]['after'] = [summary(board['ratings'][i]) for i in ids]
                    awards = self._awards(board, self._ranked_rows(board, entries))
                    for trophy_id, award in awards.items():
                        if trophy_id not in board['trophies']:
                            board['trophies'][trophy_id] = award
                            before['awarded_trophy_ids'].append(trophy_id)
                    board['undo']=(board['undo']+[before])[-20:]
                    if session['mode']=='winner' and outcome in ('left','right'):champion=pair[outcome]
                self._advance_pair(board,entries,pair,outcome)
            elif action=='undo':
                if not board['undo']:raise ValueError('No vote to undo in this round.')
                previous_ratings=copy.deepcopy(board['ratings'])
                before=board['undo'].pop()
                for ident,score in before['ratings'].items():
                    if score is None:board['ratings'].pop(ident,None)
                    else:board['ratings'][ident]=score
                for field in ('session','recent','votes'):board[field]=before[field]
                board['scheduler']=before.get('scheduler',{'batch':[]})
                if 'card_record_before' in before and 'cards' in board:
                    board['cards'].update(copy.deepcopy(before['card_record_before']))
                board['history'].append({'type':'undo','at':now_iso(),'vote_id':before.get('history_vote_id'),
                                         'legacy':not bool(before.get('history_vote_id'))})
                if not before.get('history_vote_id'):
                    # An undo from before event logging changes the legacy prior.
                    for ident in before['ratings']:
                        score = self._score(board, ident)
                        board['history_priors'][ident] = {k:score[k] for k in ('rating','rd')}
                self._fit_history(board)
                self._record_rating_path(board,previous_ratings,'undo',before['session'].get('pair') or {})
                if 'awarded_trophy_ids' in before:
                    for trophy_id in before['awarded_trophy_ids']:
                        board['trophies'].pop(trophy_id, None)
                else:
                    board['trophies'] = self._awards(board, self._ranked_rows(board, entries), legacy=True)
            else:raise ValueError('Unknown battle action.')
            self._sync_cards(board,entries)
            board['revision']=uuid.uuid4().hex
            self._save(data)
            return self._view(board,entries,owner,kind)


class LibraryStore:
    def __init__(self, root: Path):
        self.root = root
        self.media_dir = root / "media"
        self.thumb_dir = root / "thumbnails"
        self.backup_dir = root / "backups"
        self.db_path = root / "library.json"
        self.lock = threading.RLock()
        self.revision = uuid.uuid4().hex
        self.last_import_debug: dict[str, Any] = {}
        self._thumbnail_queue = queue.Queue()
        self._thumbnail_worker = None
        self._preview_lock = threading.Lock()
        self._metadata_index_worker = None
        self._metadata_index = {"running": False, "total": 0, "processed": 0, "updated": 0}
        self.root.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        if self._refresh_auto_set_covers():
            self.save()
        self._upload_lock = threading.RLock()
        self._uploads: dict[str, dict[str, Any]] = {}
        self._upload_dir = self.root / ".incoming" / "chunked-uploads"
        self.battles = BattleRankings(self)
        self.outfit_matcher = OutfitMatcher(self)

    def _empty(self) -> dict[str, Any]:
        return {
            "version": API_VERSION,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "characters": [],
            "media": [],
            "sets": [],
        }

    def _load(self) -> dict[str, Any]:
        if not self.db_path.exists():
            data = self._empty()
            self._write_atomic(data, backup_existing=False)
            return data
        try:
            with self.db_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("library.json is not a JSON object")
            data.setdefault("version", API_VERSION)
            data.setdefault("characters", [])
            data.setdefault("media", [])
            data.setdefault("sets", [])
            if not isinstance(data.get("sets"), list):
                data["sets"] = []
            set_member_ids = {
                str(media_id)
                for item in data.get("sets", [])
                if item.get("kind", "set") == "set"
                for media_id in (item.get("media_ids", []) if isinstance(item.get("media_ids", []), list) else [])
            }
            changed = False
            retired = [item for item in data["sets"] if item.get("kind") == "connection"]
            if retired:
                # Retire only the removed feature's metadata. Keep originals,
                # placement flags and all existing Sets exactly as they were.
                backup = self.backup_dir / f"library-before-connections-removal-{uuid.uuid4().hex}.json"
                shutil.copy2(self.db_path, backup)
                retired_ids = {item.get("id") for item in retired}
                data["sets"] = [item for item in data["sets"] if item.get("id") not in retired_ids]
                for entry in data.get("undo_history", []):
                    if "sets" in entry:
                        entry["sets"] = [change for change in entry["sets"] if change.get("id") not in retired_ids]
                changed = True
            # Categories are media-type specific. Existing categories predate
            # video categories, so they retain their established image-only type.
            for character in data.get("characters", []):
                if not isinstance(character.get("categories"), list):
                    character["categories"] = []
                    changed = True
                for category in character["categories"]:
                    if category.get("media_type") not in ("image", "video"):
                        category["media_type"] = "image"
                        changed = True
            for m in data.get("media", []):
                if "favorite" not in m:
                    m["favorite"] = False
                    changed = True
                if "featured" not in m:
                    m["featured"] = False
                    changed = True
                if "file_bytes" not in m:
                    m["file_bytes"] = None
                    changed = True
                if "width" not in m:
                    m["width"] = None
                    changed = True
                if "height" not in m:
                    m["height"] = None
                    changed = True
                if "in_review" not in m:
                    m["in_review"] = False
                    changed = True
                if "in_purgatory" not in m:
                    m["in_purgatory"] = False
                    changed = True
                if "categories" not in m or not isinstance(m.get("categories"), list):
                    m["categories"] = []
                    changed = True
                if "crop_top" not in m:
                    m["crop_top"] = 0.0
                    changed = True
                if "crop_bottom" not in m:
                    m["crop_bottom"] = 0.0
                    changed = True
                if "in_all" not in m:
                    # Before this flag existed, set-only images were visible in All
                    # only after receiving a custom category. Preserve that behavior
                    # for existing libraries while making the choice explicit.
                    m["in_all"] = False if m.get("media_type") == "video" else (False if m.get("id") in set_member_ids and not m.get("categories") else True)
                    changed = True
                if m.get("media_type") == "video":
                    if "in_videos" not in m:
                        m["in_videos"] = True
                        changed = True
                    if m.get("in_all"):
                        m["in_all"] = False
                        changed = True
                    if not isinstance(m.get("video_markers"), list) or len(m.get("video_markers")) != 3:
                        markers = m.get("video_markers") if isinstance(m.get("video_markers"), list) else []
                        m["video_markers"] = [markers[i] if i < len(markers) else None for i in range(3)]
                        changed = True
                    if "video_thumb_seconds" not in m:
                        m["video_thumb_seconds"] = 0.0
                        changed = True
                else:
                    if "video_markers" not in m:
                        m["video_markers"] = [None, None, None]
                        changed = True
                    if "video_thumb_seconds" not in m:
                        m["video_thumb_seconds"] = None
                        changed = True
            if changed:
                self._write_atomic(data, backup_existing=True)
            return data
        except Exception:
            broken = self.backup_dir / f"library-corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            try:
                shutil.copy2(self.db_path, broken)
            except Exception:
                pass
            raise

    def _write_atomic(self, data: dict[str, Any], backup_existing: bool = True) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if backup_existing and self.db_path.exists():
            try:
                shutil.copy2(self.db_path, self.backup_dir / "library-before-last-change.json")
                daily = self.backup_dir / f"library-{datetime.now().strftime('%Y-%m-%d')}.json"
                if not daily.exists():
                    shutil.copy2(self.db_path, daily)
            except Exception:
                pass
        temp = self.db_path.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, self.db_path)

    def _refresh_auto_set_covers(self) -> bool:
        """Prefer Main images without changing manual or unknown legacy covers."""
        media = {m["id"]: m for m in self.data.get("media", [])}
        changed = False
        for group in self.data.get("sets", []):
            if group.get("cover_source") != "auto":
                continue
            members = [mid for mid in group.get("media_ids", []) if mid in media]
            preferred = [mid for mid in members if media[mid].get("media_type") != "video" and self._in_main(media[mid])]
            choices = preferred or members
            cover = group.get("cover_media_id")
            if cover not in choices:
                next_cover = choices[0] if choices else None
                if cover != next_cover:
                    group["cover_media_id"] = next_cover
                    changed = True
        return changed

    def save(self) -> None:
        with self.lock:
            self._refresh_auto_set_covers()
            self.data["updated_at"] = now_iso()
            self._write_atomic(self.data)
            self.revision = uuid.uuid4().hex

    def undo_history(self) -> dict[str, Any]:
        with self.lock:
            entries = self.data.get("undo_history", [])
            return {"limit": 20, "entries": [
                {"id": e["id"], "label": e["label"], "filename": e.get("filename", ""),
                 "recorded_at": e["recorded_at"], "media_id": e["media_id"]}
                for e in reversed(entries)
            ]}

    def _protected_media_files(self) -> set:
        protected = {m.get(k) for m in self.data["media"] + self.data.get("rapid_queue", []) for k in ("stored_rel", "thumb_rel")}
        for entry in self.data.get("undo_history", []):
            if entry["kind"] == "delete":
                protected.update(entry["media"].get(k) for k in ("stored_rel", "thumb_rel"))
            elif entry["kind"] == "replace":
                protected.update(entry[side].get("stored_rel") for side in ("before", "after"))
        for operation in self.data.get("duplicate_replacements", {}).values():
            protected.update(operation[side].get("stored_rel") for side in ("before", "after"))
        for operation in self.data.get("duplicate_cleanups", {}).values():
            if operation["state"] == "removed":
                for record in operation["records"]:
                    protected.update(record["media"].get(k) for k in ("stored_rel", "thumb_rel"))
        return protected

    def _purge_undo_files(self, expired: list[dict[str, Any]]) -> None:
        protected = self._protected_media_files()
        for entry in expired:
            if entry["kind"] == "delete":
                paths = [entry["media"].get(k) for k in ("stored_rel", "thumb_rel")]
            elif entry["kind"] == "replace":
                paths = [entry[side].get("stored_rel") for side in ("before", "after")]
            else:
                continue
            for rel in paths:
                if not rel or rel in protected:
                    continue
                path = (self.root / rel).resolve()
                if not any(path.is_relative_to(folder.resolve()) for folder in (self.media_dir, self.thumb_dir)):
                    continue
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass  # Windows may still have the file open.

    def _save_undo(self, entry: dict[str, Any]) -> None:
        previous = self.data.get("undo_history", [])
        entry.update(id=uuid.uuid4().hex, recorded_at=now_iso())
        combined = previous + [entry]
        self.data["undo_history"] = combined[-20:]
        try:
            self.save()
        except Exception:
            self.data["undo_history"] = previous
            raise
        self._purge_undo_files(combined[:-20])

    @staticmethod
    def _in_main(media: dict[str, Any]) -> bool:
        return not media.get("in_review") and not media.get("in_purgatory") and bool(
            media.get("in_videos" if media.get("media_type") == "video" else "in_all", True))

    def _stamp_main_entry(self, media: dict[str, Any], was_in_main: bool) -> None:
        if not was_in_main and self._in_main(media):
            media["main_added_at"] = now_iso()

    def _change_media(self, media: dict[str, Any], changes: dict[str, Any], label: str) -> dict[str, Any]:
        dates = dict(media.get('category_added_at') or {})
        added = set(changes.get('categories', media.get('categories', []))) - set(media.get('categories', []))
        for flag, category in [('favorite','favorites'),('featured','featured'),('in_review','review'),('in_purgatory','purgatory')]:
            if changes.get(flag) and not media.get(flag):added.add(category)
        if added:
            dates.update({key:now_iso() for key in added})
            changes = {**changes, 'category_added_at':dates}
        if not self._in_main(media) and self._in_main({**media, **changes}):
            changes = {**changes, "main_added_at": now_iso()}
        changes = {k: v for k, v in changes.items() if media.get(k) != v}
        if not changes:
            return media
        before = {k: copy.deepcopy(media.get(k)) for k in changes}
        missing = [k for k in changes if k not in media]
        media.update(changes)
        try:
            self._save_undo({"kind": "fields", "media_id": media["id"], "filename": media.get("original_name", ""),
                             "label": label, "before": before, "missing": missing, "after": copy.deepcopy(changes)})
        except Exception:
            media.update(before)
            for k in missing:
                media.pop(k, None)
            raise
        return media

    def set_needs_replacement(self, media_id: str, needed: bool) -> dict[str, Any]:
        with self.lock:
            media = self.media_item(media_id)
            if not media:
                raise KeyError("Media not found")
            if media.get("media_type") != "image":
                raise ValueError("Only images can be marked for replacement")
            return self._change_media(media, {"needs_replacement": bool(needed), "replacement_auto": False,
                "replacement_override_sha": media.get("sha256")}, "Change replacement flag")

    def set_featured(self, media_id: str, featured: bool) -> dict[str, Any]:
        with self.lock:
            media = self.media_item(media_id)
            if not media:
                raise KeyError("Media not found")
            # Featured is a library-wide quality marker, so it applies to images and videos.
            if bool(media.get("featured")) == bool(featured):
                return media
            return self._change_media(media, {"featured": bool(featured)}, "Change Featured status")

    def set_removal_flag(self, media_id, flagged):
        if type(flagged) is not bool:raise ValueError('Removal flag must be true or false.')
        with self.lock:
            media=self.media_item(media_id)
            if not media or media.get('media_type')!='image':raise ValueError('Choose an image to flag.')
            return self._change_media(media, {'flagged_for_removal':flagged}, 'Change removal flag')

    def undo_last(self, entry_id: str) -> dict[str, Any]:
        with self.lock:
            history = self.data.get("undo_history", [])
            if not history or history[-1]["id"] != entry_id:
                raise ValueError("History changed. Reopen Undo before trying again.")
            entry = history[-1]
            if entry["kind"] == "fields":
                media = self.media_item(entry["media_id"])
                if not media or any(media.get(k) != v for k, v in entry["after"].items()):
                    raise ValueError("This item changed after that action; it cannot be safely undone.")
                old = copy.deepcopy(media)
                restored_categories = entry["before"].get("categories")
                if restored_categories is not None and self._validate_categories(media["character_id"], restored_categories, media.get("media_type", "image")) != restored_categories:
                    raise ValueError("A category needed by this action no longer exists.")
                media.update(copy.deepcopy(entry["before"]))
                for k in entry.get("missing", []):
                    media.pop(k, None)
                self.data["undo_history"] = history[:-1]
                try:
                    self.save()
                except Exception:
                    media.clear(); media.update(old)
                    self.data["undo_history"] = history
                    raise
            elif entry["kind"] == "replace":
                media = self.media_item(entry["media_id"])
                if not media or media.get("sha256") != entry["after"]["sha256"]:
                    raise ValueError("The image source changed again. Undo its newer replacement first.")
                current = self.root / media["stored_rel"]
                retained = self.root / entry["before"]["stored_rel"]
                if not current.is_file() or self._hash_file(current) != entry["after"]["sha256"]:
                    raise ValueError("The current image source is missing or changed on disk")
                if not retained.is_file() or self._hash_file(retained) != entry["before"]["sha256"]:
                    raise ValueError("The retained original is missing or changed; nothing was restored")
                if any(m["id"] != media["id"] and m.get("character_id") == media["character_id"] and m.get("sha256") == entry["before"]["sha256"] for m in self.data["media"]):
                    raise ValueError("The old source was imported again. Undo would create a duplicate.")
                old = copy.deepcopy(media)
                for key in self._replacement_fields:
                    media.pop(key, None)
                media.update(copy.deepcopy(entry["before"]))
                media["thumb_rel"] = None
                self.data["undo_history"] = history[:-1]
                try:
                    self.save()
                except Exception:
                    media.clear(); media.update(old)
                    self.data["undo_history"] = history
                    raise
                self._purge_undo_files([entry])
            elif entry["kind"] == "delete":
                media = copy.deepcopy(entry["media"])
                if self.media_item(media["id"]) or not self.character(media["character_id"]):
                    raise ValueError("The original character is missing or this item already exists.")
                if not (self.root / media["stored_rel"]).is_file():
                    raise ValueError("The retained original file is missing; deletion cannot be undone.")
                if any(m.get("character_id") == media["character_id"] and m.get("sha256") == media.get("sha256") for m in self.data["media"]):
                    raise ValueError("This source has already been imported again; undo would create a duplicate.")
                if self._validate_categories(media["character_id"], media.get("categories", []), media.get("media_type", "image")) != media.get("categories", []):
                    raise ValueError("A category needed by this image no longer exists.")
                for change in entry.get("sets", []):
                    if self.set_item(change["id"]) != change["after"]:
                        raise ValueError("This image's set changed after deletion; it cannot be safely restored.")
                if media.get("media_type") == "image" and (not media.get("thumb_rel") or not (self.root / media["thumb_rel"]).is_file()):
                    media["thumb_rel"] = None
                previous_media, previous_sets = self.data["media"], self.data.get("sets", [])
                restored = list(previous_media)
                restored.insert(min(entry["index"], len(restored)), media)
                restores = {change["id"]: copy.deepcopy(change["before"]) for change in entry.get("sets", [])}
                self.data["media"] = restored
                self.data["sets"] = [restores.get(s["id"], s) for s in previous_sets]
                self.data["undo_history"] = history[:-1]
                try:
                    self.save()
                except Exception:
                    self.data["media"], self.data["sets"] = previous_media, previous_sets
                    self.data["undo_history"] = history
                    raise
            else:
                raise ValueError("Unknown history action")
            if entry["kind"] in ("delete", "replace") and media.get("media_type") == "image" and not media.get("thumb_rel"):
                owner = self.character(media["character_id"])
                self._queue_image_thumbnail(self.root / media["stored_rel"], media["id"], owner["name"])
            return {"ok": True, "media_id": entry["media_id"], "label": entry["label"], "kind": entry["kind"], "item": copy.deepcopy(media)}

    def clear_undo_history(self, expected_id: str) -> dict[str, Any]:
        with self.lock:
            history = self.data.get("undo_history", [])
            if history and history[-1]["id"] != expected_id:
                raise ValueError("History changed. Reopen Undo before clearing it.")
            self.data["undo_history"] = []
            try:
                self.save()
            except Exception:
                self.data["undo_history"] = history
                raise
            self._purge_undo_files(history)
            return {"ok": True}

    def manual_backup(self) -> Path:
        with self.lock:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dst = self.backup_dir / f"library-manual-{stamp}.json"
            shutil.copy2(self.db_path, dst)
            return dst

    def rapid_item(self, ident):
        return next((m for m in self.data.get('rapid_queue', []) if m['id'] == ident), None)

    def rapid_queue(self, owner):
        with self.lock:
            if not self.character(owner):
                raise ValueError('Choose a character first.')
            return copy.deepcopy({'items': [m for m in self.data.get('rapid_queue', []) if m['character_id'] == owner],
                                  'state': self.data.get('rapid_states', {}).get(owner, {})})

    def rapid_state(self, body):
        owner = str(body.get('character_id', ''))
        with self.lock:
            if not self.character(owner):
                raise ValueError('Choose a character first.')
            choices = body.get('choices', {})
            if not isinstance(choices, dict):
                raise ValueError('Invalid queue choices.')
            pending = {m['id']: m for m in self.data.get('rapid_queue', []) if m['character_id'] == owner}
            updates = []
            for ident, values in choices.items():
                if ident in pending:
                    updated = copy.deepcopy(pending[ident])
                    self._rapid_choices(updated, values)
                    updates.append((pending[ident], updated))
            states = self.data.setdefault('rapid_states', {})
            current = str(body.get('current_id', ''))
            selected = body.get('selected_ids', [])
            if not isinstance(selected, list):
                raise ValueError('Invalid queue selection.')
            scroll = float(body.get('scroll_top', 0))
            if not math.isfinite(scroll):
                raise ValueError('Invalid queue position.')
            for item, updated in updates:
                item.update(updated)
            states[owner] = {'current_id': current, 'selected_ids': [mid for mid in selected if isinstance(mid, str) and mid in pending],
                             'known_ids': list(pending), 'scroll_top': max(0, min(10000000, scroll))}
            self.save()
            return {'ok': True}

    def _rapid_choices(self, item, values):
        if not isinstance(values, dict):
            raise ValueError('Invalid queue choices.')
        if 'categories' in values:
            item['categories'] = self._validate_categories(item['character_id'], values['categories'], item['media_type'])
        for key in ('favorite', 'featured', 'needs_replacement', 'in_review', 'rapid_main', 'rapid_edited'):
            if key in values:
                if type(values[key]) is not bool:
                    raise ValueError('Invalid queue flag.')
                item[key] = values[key]
        for key in ('crop_top', 'crop_bottom'):
            if key in values:
                value = float(values[key])
                if not math.isfinite(value) or not 0 <= value < .95:
                    raise ValueError('Invalid crop.')
                item[key] = value
        if item.get('crop_top', 0) + item.get('crop_bottom', 0) >= .95:
            raise ValueError('Crop removes too much of the image.')

    def resolve_rapid(self, body):
        owner, action = str(body.get('character_id', '')), body.get('action')
        ids = body.get('media_ids', [])
        if action not in ('save', 'main', 'purgatory', 'review', 'set', 'new_set', 'discard') or not isinstance(ids, list) or not ids or any(not isinstance(mid, str) for mid in ids):
            raise ValueError('Choose queue files and an action.')
        ids = list(dict.fromkeys(ids))
        with self.lock:
            items = [self.rapid_item(mid) for mid in ids]
            if any(not m or m['character_id'] != owner for m in items):
                raise ValueError('The queue changed in another window. Resume it again before continuing.')
            group = self.set_item(str(body.get('set_id', ''))) if action == 'set' else None
            if action == 'set' and (not group or group['character_id'] != owner):
                raise ValueError('Choose a Set for this character.')
            name = str(body.get('name', '')).strip()
            if action == 'new_set' and not name:
                raise ValueError('Enter a Set name.')
            before = copy.deepcopy(self.data)
            promoted, duplicates = [], []
            try:
                for item in items:
                    self._rapid_choices(item, body.get('choices', {}).get(item['id'], {}))
                    if action == 'discard':
                        continue
                    if not (self.root / item['stored_rel']).is_file():
                        raise ValueError('A queued original is unavailable. The queue was kept.')
                    existing = next((m for m in self.data['media'] if m['character_id'] == owner and m.get('sha256') == item.get('sha256')), None)
                    if existing:
                        duplicates.append(item['id'])
                        continue  # Never change a previously imported image through a duplicate queue copy.
                    item['in_review'] = action == 'review' or (action == 'save' and item.get('in_review', False))
                    item['in_purgatory'] = action == 'purgatory'
                    item['main_explicit'] = action != 'purgatory' and (action == 'main' or bool(item.get('rapid_main')) or (action == 'save' and not item.get('categories') and not item['in_review']))
                    main = not item['in_review'] and not item['in_purgatory'] and (item['main_explicit'] or self._main_categories(item))
                    item['in_all'] = main and item['media_type'] != 'video'
                    item['in_videos'] = main and item['media_type'] == 'video'
                    if main:
                        item['main_added_at'] = now_iso()
                    item['category_added_at'] = {key:now_iso() for key in item.get('categories',[])}
                    if item['in_review']:item['category_added_at']['review']=now_iso()
                    if item['in_purgatory']:item['category_added_at']['purgatory']=now_iso()
                    self.data['media'].append(item)
                    promoted.append(item['id'])
                # Remove pending references before any Set helper persists the transaction.
                self.data['rapid_queue'] = [m for m in self.data.get('rapid_queue', []) if m['id'] not in ids]
                if action == 'new_set' and promoted:
                    group = self.create_set(owner, name, promoted, preserve_placement=True, colors=body.get("colors"), aliases=body.get("aliases"), notes=body.get("notes"))
                elif action == 'set' and promoted:
                    self.update_set(group['id'], add_media_ids=promoted, preserve_placement=True)
                self.save()
            except Exception:
                self.data = before
                self.save()
                raise
            # Only private pending copies are removed; source-folder files are never touched.
            for item in items:
                if item['id'] not in promoted:
                    for key in ('stored_rel', 'thumb_rel'):
                        if item.get(key):
                            try:
                                (self.root / item[key]).unlink(missing_ok=True)
                            except OSError:
                                pass
            return {'ok': True, 'resolved_ids': ids, 'saved_ids': promoted, 'duplicate_ids': duplicates,
                    'set': copy.deepcopy(group) if group else None}

    def reorder_categories(self, owner, media_type, ids):
        with self.lock:
            character = self.character(owner)
            if not character or media_type not in ('image', 'video') or not isinstance(ids, list):
                raise ValueError('Invalid category order.')
            cats = character.get('categories', [])
            selected = {c['id']: c for c in cats if c.get('media_type', 'image') == media_type}
            if len(ids) != len(selected) or set(ids) != set(selected):
                raise ValueError('Categories changed. Reopen the editor before ordering them.')
            ordered = iter(selected[ident] for ident in ids)
            character['categories'] = [next(ordered) if c['id'] in selected else c for c in cats]
            self.save()
            return copy.deepcopy(character)

    def reorder_set(self, ident, ids):
        with self.lock:
            group = self.set_item(ident)
            if not group or not isinstance(ids, list) or len(ids) != len(set(ids)) or set(ids) != set(group.get('media_ids', [])):
                raise ValueError('Set contents changed. Reopen the Set before ordering its images.')
            group['media_ids'] = ids
            group['manual_order'] = True
            group['updated_at'] = now_iso()
            self.save()
            return copy.deepcopy(group)

    @staticmethod
    def _set_details(aliases=None, colors=None, notes=None):
        result = {}
        for key, value in (('aliases', aliases), ('colors', colors)):
            if value is not None:
                if not isinstance(value, list) or len(value) > 50 or any(not isinstance(v, str) or len(v) > 150 for v in value):
                    raise ValueError('Invalid Set ' + key)
                result[key] = list(dict.fromkeys(title_case_label(v) if key == 'colors' else v.strip() for v in value if v.strip()))
        if notes is not None:
            if not isinstance(notes, str) or len(notes) > 5000:
                raise ValueError('Set notes must be at most 5000 characters.')
            result['notes'] = notes.strip()
        return result

    def public_library(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps({**{k: v for k, v in self.data.items() if k not in ("undo_history", "duplicate_replacements", "duplicate_cleanups", "rapid_queue", "rapid_states")}, "revision": self.revision}))

    def duplicate_catalog(self, character_id: str = "") -> dict[str, Any]:
        """Only live image records; filesystem leftovers are never reference images."""
        with self.lock:
            library_id = hashlib.sha256(str(self.db_path.resolve()).encode()).hexdigest()
            files = []
            if character_id:
                if character_id != "*" and not self.character(character_id):
                    raise ValueError("Choose an existing character")
                for item in self.data["media"]:
                    if (character_id != "*" and item.get("character_id") != character_id) or item.get("media_type") != "image":
                        continue
                    files.append({"id": item["id"], "path": str((self.root / item["stored_rel"]).resolve()),
                                  "sha": item["sha256"], "name": item.get("original_name", ""),
                                  "in_all": item.get("in_all", True),
                                  "favorite": bool(item.get("favorite")), "featured": bool(item.get("featured")),
                                  "categories": [c["name"] for c in (self.character(item["character_id"]) or {}).get("categories", []) if c["id"] in item.get("categories", [])],
                                  "in_review": bool(item.get("in_review")),
                                  "in_purgatory": bool(item.get("in_purgatory")),
                                  "character_id": item["character_id"],
                                  "character_name": (self.character(item["character_id"]) or {}).get("name", "Unknown"),
                                  "sets": [s["name"] for s in self.data.get("sets", []) if item["id"] in s.get("media_ids", [])]})
            return {"library_id": library_id, "root": str(self.root.resolve()), "revision": self.revision,
                    "characters": [{"id": c["id"], "name": c["name"]} for c in self.data["characters"]],
                    "coverage_version": 2, "library_cleanup": True, "files": files}

    def duplicate_cleanup_status(self, operation: str, library_id: str) -> dict[str, Any]:
        with self.lock:
            if library_id != self.duplicate_catalog()["library_id"]:
                raise ValueError("The active library changed. Connect and scan again.")
            entry = self.data.get("duplicate_cleanups", {}).get(operation)
            return {"operation": operation, "state": entry["state"] if entry else "missing"}

    def duplicate_cleanup(self, operation: str, library_id: str, selection: Any) -> dict[str, Any]:
        """Atomic metadata removal. Retain originals and snapshots for durable Undo."""
        if not re.fullmatch(r"[0-9a-f]{32}", operation):
            raise ValueError("Invalid library cleanup operation")
        with self.lock:
            status = self.duplicate_cleanup_status(operation, library_id)
            if status["state"] != "missing":
                if self.data["duplicate_cleanups"][operation]["selection"] != selection:
                    raise ValueError("Cleanup operation does not match its original selection")
                return status
            if not isinstance(selection, list) or not 1 <= len(selection) <= 500:
                raise ValueError("Choose between 1 and 500 library copies to remove")
            if any(not isinstance(pair, dict) or not isinstance(pair.get("target"), str) or not isinstance(pair.get("keeper"), str) for pair in selection):
                raise ValueError("Invalid library cleanup selection")
            targets = {pair["target"] for pair in selection}
            if len(targets) != len(selection) or any(pair["keeper"] in targets for pair in selection):
                raise ValueError("Keep at least one copy; a keeper cannot also be removed")
            checked = set()
            for pair in selection:
                for role in ("target", "keeper"):
                    media = self.media_item(pair[role])
                    expected = pair.get(role + "_sha")
                    if not media or media.get("media_type") != "image" or media.get("sha256") != expected:
                        raise ValueError("A selected library image changed or was removed. Scan again.")
                    if media["id"] not in checked:
                        path, _ = self.media_path(media["id"])
                        if self._hash_file(path) != expected:
                            raise ValueError("A selected original changed on disk. Scan again.")
                        checked.add(media["id"])
            before_media, before_sets = self.data["media"], self.data.get("sets", [])
            records = [{"index": i, "media": copy.deepcopy(m)} for i, m in enumerate(before_media) if m["id"] in targets]
            changes, next_sets = [], []
            for item in before_sets:
                if not targets.intersection(item.get("media_ids", [])):
                    next_sets.append(item)
                    continue
                updated = copy.deepcopy(item)
                updated["media_ids"] = [mid for mid in item["media_ids"] if mid not in targets]
                if updated.get("cover_media_id") not in updated["media_ids"]:
                    updated["cover_media_id"] = next(iter(updated["media_ids"]), None)
                    updated["cover_source"] = "auto"
                updated["updated_at"] = now_iso()
                changes.append({"id": item["id"], "before": copy.deepcopy(item), "after": copy.deepcopy(updated)})
                next_sets.append(updated)
            history = self.data.setdefault("duplicate_cleanups", {})
            history[operation] = {"state": "removed", "selection": copy.deepcopy(selection), "records": records, "sets": changes}
            self.data["media"] = [m for m in before_media if m["id"] not in targets]
            self.data["sets"] = next_sets
            try:
                self.save()
            except Exception:
                self.data["media"], self.data["sets"] = before_media, before_sets
                history.pop(operation, None)
                raise
            return self.duplicate_cleanup_status(operation, library_id)

    def duplicate_cleanup_undo(self, operation: str, library_id: str) -> dict[str, Any]:
        with self.lock:
            status = self.duplicate_cleanup_status(operation, library_id)
            if status["state"] in ("missing", "restored"):
                return status
            entry = self.data["duplicate_cleanups"][operation]
            for record in entry["records"]:
                media = record["media"]
                if self.media_item(media["id"]) or not self.character(media["character_id"]):
                    raise ValueError("The original character is missing or the image ID already exists")
                path = self.root / media["stored_rel"]
                if not path.is_file() or self._hash_file(path) != media["sha256"]:
                    raise ValueError("A retained original is missing or changed; nothing was restored")
                if self._validate_categories(media["character_id"], media.get("categories", []), media.get("media_type", "image")) != media.get("categories", []):
                    raise ValueError("A category needed by this image no longer exists")
            for change in entry["sets"]:
                if self.set_item(change["id"]) != change["after"]:
                    raise ValueError("A Set changed after cleanup. Undo its later changes before restoring this batch.")
            before_media, before_sets = self.data["media"], self.data.get("sets", [])
            restored = list(before_media)
            for record in sorted(entry["records"], key=lambda r: r["index"]):
                restored.insert(min(record["index"], len(restored)), copy.deepcopy(record["media"]))
            restores = {change["id"]: copy.deepcopy(change["before"]) for change in entry["sets"]}
            self.data["media"] = restored
            self.data["sets"] = [restores.get(item["id"], item) for item in before_sets]
            entry["state"] = "restored"
            try:
                self.save()
            except Exception:
                self.data["media"], self.data["sets"] = before_media, before_sets
                entry["state"] = "removed"
                raise
            return self.duplicate_cleanup_status(operation, library_id)

    def duplicate_operation(self, operation: str, library_id: str) -> dict[str, Any]:
        with self.lock:
            if library_id != self.duplicate_catalog()["library_id"]:
                raise ValueError("The active library changed. Connect and scan again.")
            entry = self.data.get("duplicate_replacements", {}).get(operation)
            if not entry:
                return {"state": "missing"}
            item = self.media_item(entry["media_id"])
            return {"state": entry["state"], "operation": operation, "media_id": entry["media_id"],
                    "new_sha": entry["after"]["sha256"], "old_sha": entry["before"]["sha256"],
                    "item": copy.deepcopy(item),
                    "path": str((self.root / item["stored_rel"]).resolve()) if item else None}

    def duplicate_item(self, media_id: str, library_id: str) -> dict[str, Any]:
        with self.lock:
            if self.duplicate_catalog()["library_id"] != library_id:
                raise ValueError("The active library changed")
            item = self.media_item(media_id)
            if not item or item.get("media_type") != "image":
                raise ValueError("This image is no longer in the library. Scan again.")
            return {"sha": item["sha256"], "path": str((self.root / item["stored_rel"]).resolve())}

    # These are source properties only. Undo must preserve later edits to categories,
    # favorites, set membership, crops, and other user metadata.
    _replacement_fields = ("original_name", "stored_rel", "content_type", "sha256", "source", "width", "height",
                           "file_bytes", "needs_replacement", "replacement_auto", "replacement_override_sha")

    def duplicate_replace(self, payload: bytes, name: str, media_id: str, expected_sha: str,
                          operation: str, library_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{32}", operation):
            raise ValueError("Invalid replacement operation")
        if Image is None:
            raise ValueError("Image support is unavailable. Restart the companion after installing Pillow.")
        temp = self.root / ".incoming" / (uuid.uuid4().hex + ".replace")
        temp.parent.mkdir(parents=True, exist_ok=True)
        try:
            with temp.open("xb") as handle:
                handle.write(payload); handle.flush(); os.fsync(handle.fileno())
            digest = self._hash_file(temp)
            with Image.open(temp) as image:
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Choose a still image")
                width, height = image.size
                content_type = Image.MIME.get(image.format, "image/png")
                image.verify()
            with self.lock:
                existing = self.duplicate_operation(operation, library_id)
                if existing["state"] != "missing":
                    if existing["media_id"] != media_id or existing["new_sha"] != digest or existing["old_sha"] != expected_sha:
                        raise ValueError("Replacement operation does not match the original request")
                    return existing
                item = self.media_item(media_id)
                if not item or item.get("media_type") != "image" or item.get("sha256") != expected_sha:
                    raise ValueError("The imported image changed. Scan again before replacing it.")
                old_path = self.root / item["stored_rel"]
                if self._hash_file(old_path) != expected_sha:
                    raise ValueError("The imported original changed on disk. Replacement stopped.")
                if digest == expected_sha:
                    raise ValueError("This is already the same source; keep the library copy instead.")
                if any(m["id"] != media_id and m.get("character_id") == item["character_id"] and m.get("sha256") == digest for m in self.data["media"]):
                    raise ValueError("That source is already imported for this character")
                before = {k: copy.deepcopy(item[k]) for k in self._replacement_fields if k in item}
                retained = self.root / "replacement-originals" / (operation + old_path.suffix)
                retained.parent.mkdir(parents=True, exist_ok=True)
                # A separate retained copy cannot be overwritten by a later manual replacement.
                with old_path.open("rb") as src, retained.open("wb") as dst:
                    shutil.copyfileobj(src, dst); dst.flush(); os.fsync(dst.fileno())
                if self._hash_file(retained) != expected_sha:
                    raise ValueError("Could not verify the retained original")
                before["stored_rel"] = retained.relative_to(self.root).as_posix()
                safe_name = safe_component(Path(name).name, "replacement.png")
                char_folder = self.media_dir / safe_component(self.character(item["character_id"])["name"], "Character")
                char_folder.mkdir(parents=True, exist_ok=True)
                destination = char_folder / (media_id + "_" + operation + Path(safe_name).suffix)
                os.replace(temp, destination)
                old = copy.deepcopy(item)
                item.update(original_name=safe_name, stored_rel=destination.relative_to(self.root).as_posix(),
                            content_type=content_type, sha256=digest, source={"kind": "local", "original_name": safe_name},
                            width=width, height=height, file_bytes=len(payload), thumb_rel=None,
                            needs_replacement=False, replacement_auto=False)
                item.pop("replacement_override_sha", None)
                self._apply_resolution_flag(item)
                journal = self.data.setdefault("duplicate_replacements", {})
                journal[operation] = {"state": "applied", "media_id": media_id, "created_at": now_iso(),
                                      "before": before, "after": {k: copy.deepcopy(item[k]) for k in self._replacement_fields if k in item}}
                try:
                    self.save()
                except Exception:
                    item.clear(); item.update(old); journal.pop(operation, None)
                    # Keep both files on a failed save. Never remove a possibly committed source.
                    raise
                # The durable retained copy now owns undo. Avoid keeping a second
                # redundant original in media; leave older retained backups intact.
                if old_path.is_relative_to(self.media_dir) and old["stored_rel"] not in self._protected_media_files():
                    try:
                        old_path.unlink(missing_ok=True)
                    except OSError:
                        pass  # Windows may still have the old image open.
                self._queue_image_thumbnail(destination, media_id, self.character(item["character_id"])["name"])
                return self.duplicate_operation(operation, library_id)
        finally:
            temp.unlink(missing_ok=True)

    def duplicate_undo(self, operation: str, library_id: str) -> dict[str, Any]:
        with self.lock:
            current = self.duplicate_operation(operation, library_id)
            if current["state"] == "undone":
                return current
            if current["state"] != "applied":
                raise ValueError("Replacement not found")
            entry = self.data["duplicate_replacements"][operation]
            item = self.media_item(entry["media_id"])
            if not item or item.get("sha256") != entry["after"]["sha256"]:
                raise ValueError("The library source changed again. Undo the newer replacement first.")
            if self._hash_file(self.root / item["stored_rel"]) != entry["after"]["sha256"]:
                raise ValueError("The library source changed on disk")
            retained = self.root / entry["before"]["stored_rel"]
            if self._hash_file(retained) != entry["before"]["sha256"]:
                raise ValueError("The retained original is missing or changed")
            if any(m["id"] != item["id"] and m.get("character_id") == item["character_id"] and m.get("sha256") == entry["before"]["sha256"] for m in self.data["media"]):
                raise ValueError("The old source was imported again. Undo would create a duplicate.")
            old = copy.deepcopy(item)
            for key in self._replacement_fields:
                item.pop(key, None)
            item.update(copy.deepcopy(entry["before"])); item["thumb_rel"] = None
            entry["state"] = "undone"
            try:
                self.save()
            except Exception:
                item.clear(); item.update(old); entry["state"] = "applied"
                raise
            self._queue_image_thumbnail(retained, item["id"], self.character(item["character_id"])["name"])
            return self.duplicate_operation(operation, library_id)

    def character(self, character_id: str) -> dict[str, Any] | None:
        return next((c for c in self.data["characters"] if c["id"] == character_id), None)

    def matching_preferences(self, character_id, mode=None):
        with self.lock:
            character = self.character(character_id)
            if not character:
                raise ValueError('Choose a character first.')
            if mode is not None:
                if mode not in ('outfit', 'photoshoot'):
                    raise ValueError('Choose Outfit or Photoshoot matching.')
                previous = character.get('matching_mode')
                if previous != mode:
                    character['matching_mode'] = mode
                    try:
                        self.save()
                    except Exception:
                        if previous is None:
                            character.pop('matching_mode', None)
                        else:
                            character['matching_mode'] = previous
                        raise
            saved = character.get('matching_mode')
            default = 'photoshoot' if re.match(r'^mikayla\b', character.get('name', '').strip(), re.I) else 'outfit'
            return {'character_id': character_id, 'mode': saved if saved in ('outfit', 'photoshoot') else default}

    def collection_request(self, action, body):
        """Presentation/progress metadata is independent of battle ratings and profiles."""
        with self.lock:
            owner = str(body.get('character_id', ''))
            character = self.character(owner)
            if not character:
                raise ValueError('Choose a character first.')
            previous = copy.deepcopy(character.get('collection'))
            data = copy.deepcopy(previous or {})
            data.setdefault('revision', '')
            data.setdefault('attributes', [{'label':label, 'value':None, 'weight':1} for label in ('Face','Breasts','Butt','Style')])
            data.setdefault('frames', {})
            data.setdefault('reviewed', {})
            data.setdefault('earned', {})
            data.setdefault('finish', 'obsidian')
            data.setdefault('captains', {})
            data.setdefault('titles', {})
            data.setdefault('title_overrides', {})
            if data.get('captain_schema')!=2:
                data['legacy_captains']=copy.deepcopy(data['captains'])
                data['captains']={}
                data['captain_schema']=2
            media = {m['id']:m for m in self.data['media'] if m.get('character_id') == owner and m.get('media_type') != 'video'}
            groups={g['id']:g for g in self.data.get('sets',[]) if g.get('character_id')==owner and g.get('kind','set')=='set'}
            for ident,mid in list(data['captains'].items()):
                if ident not in groups or mid not in groups[ident].get('media_ids',[]) or mid not in media:
                    data['captains'].pop(ident,None)
            if action not in ('state', 'save', 'frame', 'review', 'captain', 'title', 'title-correction'):
                raise ValueError('Unknown collection action.')
            if action != 'state' and body.get('revision', '') != data['revision']:
                raise ValueError('Collection changed in another window. Reopen it before saving.')
            if action == 'save':
                attrs = body.get('attributes', data['attributes'])
                if not isinstance(attrs, list) or len(attrs) != 4:
                    raise ValueError('A profile card has exactly four attributes.')
                cleaned = []
                for a in attrs:
                    if not isinstance(a, dict):
                        raise ValueError('Invalid attribute.')
                    label, value, weight = a.get('label'), a.get('value'), a.get('weight', 1)
                    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 18:
                        raise ValueError('Attribute labels must have 1–18 characters.')
                    if value is not None and (type(value) is not int or not 1 <= value <= 99):
                        raise ValueError('Attribute ratings must be whole numbers from 1 to 99, or blank.')
                    if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 < weight <= 10:
                        raise ValueError('Attribute weights must be greater than 0 and at most 10.')
                    cleaned.append({'label':label.strip(), 'value':value, 'weight':weight})
                data['attributes'] = cleaned
                finish = body.get('finish', data['finish'])
                required = {'obsidian':0, 'emerald':800, 'platinum':1600}
                if finish not in required or len(data['earned'])*100 < required[finish]:
                    raise ValueError('That card finish has not been unlocked.')
                data['finish'] = finish
            elif action == 'captain':
                ident,mid=body.get('set_id'),body.get('media_id')
                if ident not in groups or (mid is not None and (mid not in media or mid not in groups[ident].get('media_ids',[]))):
                    raise ValueError('Choose an image belonging to this set and person.')
                if mid is None:data['captains'].pop(ident,None)
                else:data['captains'][ident]=mid
            elif action == 'title-correction':
                ident,kind=body.get('entry_id'),body.get('kind','images')
                if kind not in ('images','sets') or ident not in self.battles._entries(owner,kind):
                    raise ValueError('Choose an eligible card belonging to this person.')
                overrides=body.get('overrides')
                allowed={'former_number_one','team_captain'} if kind=='images' else {'former_number_one'}
                if not isinstance(overrides,dict) or any(i not in allowed or v not in ('auto','grant','suppress') for i,v in overrides.items()):
                    raise ValueError('Choose automatic, grant or suppress for each available title.')
                key=('set:' if kind=='sets' else '')+ident
                data['title_overrides'][key]={i:v for i,v in overrides.items() if v!='auto'}
            elif action == 'title':
                mid,choice=body.get('entry_id',body.get('media_id')),body.get('choice')
                kind=body.get('kind','images')
                if kind not in ('images','sets'):raise ValueError('Choose images or sets.')
                rows=self.battles.request('summary',{'character_id':owner,'kind':kind})['entries']
                row=next((r for r in rows if r['id']==mid),None)
                if not row or choice not in ['auto','none']+[t['id'] for t in row['titles']]:
                    raise ValueError('Choose an available title for an eligible card.')
                data['titles'][('set:' if kind=='sets' else '')+mid]=choice
            elif action == 'frame':
                key, mid = body.get('key', ''), body.get('media_id', '')
                if mid not in media or key not in ('image:'+mid, 'profile:'+mid):
                    raise ValueError('Choose an image belonging to this person.')
                frame = body.get('frame', {})
                if not isinstance(frame, dict):
                    raise ValueError('Invalid card framing.')
                for name, low, high in [('x',-50,50),('y',-50,50),('zoom',1,3)]:
                    v = frame.get(name)
                    if type(v) not in (int,float) or not math.isfinite(v) or not low <= v <= high:
                        raise ValueError('Invalid card position or zoom.')
                data['frames'][key] = {name:frame[name] for name in ('x','y','zoom')}
            elif action == 'review':
                mid = body.get('media_id')
                if mid not in media:
                    raise ValueError('Image no longer exists in this collection.')
                if body.get('reviewed'):
                    data['reviewed'][mid] = media[mid].get('sha256') or media[mid].get('filename')
                else:
                    data['reviewed'].pop(mid, None)
            # Scope mirrors battle eligibility. Holding areas remain a separate backlog.
            boards = [self.battles.request('summary', {'character_id':owner,'kind':kind}) for kind in ('images','sets')]
            tracks = []
            for board in boards:
                rows = [e for e in board['entries'] if not e.get('flagged_for_removal')]
                placed = sum(e['rating_status'] in ('Developing','Established') for e in rows)
                established = sum(e['rating_status'] == 'Established' for e in rows)
                # A sole card cannot be placed: show this explicitly rather than a false 100%.
                tracks.append({'id':board['kind']+'-placement','label':('Image' if board['kind']=='images' else 'Set')+' placements','done':placed,'total':len(rows),'kind':board['kind'],'mode':'placements'})
                tracks.append({'id':board['kind']+'-confidence','label':('Image' if board['kind']=='images' else 'Set')+' confidence','done':established,'total':len(rows),'kind':board['kind'],'mode':'rank'})
            saved = [m for m in media.values() if not m.get('in_review') and not m.get('in_purgatory')]
            members = {mid for group in self.data.get('sets',[]) if group.get('character_id')==owner and group.get('kind','set')=='set' for mid in group.get('media_ids',[])}
            checked = {m['id'] for m in saved if m['id'] in members or data['reviewed'].get(m['id']) == (m.get('sha256') or m.get('filename'))}
            tracks.append({'id':'organization','label':'Set organization','done':len(checked),'total':len(saved)})
            photos = [mid for mid in (character.get('profile') or {}).get('photos',[]) if mid in media]
            tracks.append({'id':'profile','label':'Profile showcase','done':len(photos),'total':min(5,len(media))})
            for track in tracks:
                if track['total']:
                    for milestone in (25,50,75,100):
                        if track['done']*100 >= milestone*track['total']:
                            data['earned'].setdefault(track['id']+':'+str(milestone), {'title':track['label']+' · '+str(milestone)+'%', 'at':now_iso()})
            if action != 'state' or data != (previous or {}):
                data['revision'] = uuid.uuid4().hex
                character['collection'] = data
                try:
                    self.save()
                except Exception:
                    if previous is None: character.pop('collection', None)
                    else: character['collection'] = previous
                    raise
            active = [t for t in tracks if t['total']]
            return {'character_id':owner, 'name':character['name'], 'collection':copy.deepcopy(data), 'tracks':tracks,
                    'completion':math.floor(sum(t['done']/t['total'] for t in active)/len(active)*100 + 1e-9) if active else None,
                    'xp':len(data['earned'])*100, 'boards':boards,
                    'stats':{'images':len(media),'sets':len(boards[1]['entries']), 'review':sum(bool(m.get('in_review')) for m in media.values()),
                             'purgatory':sum(bool(m.get('in_purgatory')) for m in media.values()),'flags':sum(bool(m.get('flagged_for_removal')) for m in media.values()),'votes':sum(b.get('votes',0) for b in boards)},
                    'unorganized':[m['id'] for m in saved if m['id'] not in checked]}

    def profile_request(self, action, body):
        with self.lock:
            owner = str(body.get('character_id', ''))
            character = self.character(owner)
            if not character:
                raise ValueError('Choose a character first.')
            profile = copy.deepcopy(character.get('profile') or {})
            revision = profile.get('revision', '')
            valid = {m['id'] for m in self.data['media'] if m.get('character_id') == owner and m.get('media_type') != 'video'}
            if action == 'save':
                if body.get('revision', '') != revision:
                    raise ValueError('This profile changed in another window. Reopen it before editing.')
                proposed = body.get('profile')
                if not isinstance(proposed, dict):
                    raise ValueError('Invalid profile.')
                photos = proposed.get('photos', [])
                if not isinstance(photos, list) or len(photos) > 5 or any(not isinstance(i, str) or i not in valid for i in photos) or len(set(photos)) != len(photos):
                    raise ValueError('Choose up to five different images belonging to this person.')
                measurements = proposed.get('measurements', {})
                if not isinstance(measurements, dict):
                    raise ValueError('Invalid measurements.')
                cleaned = {}
                for key in ('height', 'bust', 'waist', 'hips', 'bra'):
                    item = measurements.get(key, {})
                    if not isinstance(item, dict):
                        raise ValueError('Invalid measurement.')
                    value = str(item.get('value', '')).strip()
                    status = item.get('status', 'estimated')
                    if status not in ('estimated', 'confirmed'):
                        raise ValueError('Choose Estimated or Confirmed.')
                    if value:
                        if key == 'bra':
                            if len(value) > 30:
                                raise ValueError('Bra size must be 30 characters or less.')
                        else:
                            try:
                                number = float(value)
                            except (ValueError, OverflowError):
                                raise ValueError('Measurements must be positive numbers in inches.')
                            if not 0 < number <= 200:
                                raise ValueError('Measurements must be between 0 and 200 inches.')
                            value = format(number, 'g')
                        cleaned[key] = {'value': value, 'status': status}
                notes = proposed.get('notes', '')
                if not isinstance(notes, str) or len(notes) > 10000:
                    raise ValueError('Notes must be 10,000 characters or less.')
                profile = {'photos': photos, 'measurements': cleaned, 'notes': notes.strip(), 'revision': uuid.uuid4().hex}
                previous = character.get('profile')
                character['profile'] = profile
                try:
                    self.save()
                except Exception:
                    if previous is None:
                        character.pop('profile', None)
                    else:
                        character['profile'] = previous
                    raise
            elif action != 'state':
                raise ValueError('Unknown profile action.')
            profile.setdefault('measurements', {})
            profile.setdefault('notes', '')
            profile.setdefault('revision', '')
            profile['photos'] = [i for i in profile.get('photos', []) if i in valid]
            return {'character_id': owner, 'name': character['name'], 'profile': profile}

    def media_item(self, media_id: str) -> dict[str, Any] | None:
        return next((m for m in self.data["media"] if m["id"] == media_id), None)

    def set_item(self, set_id: str) -> dict[str, Any] | None:
        return next((s for s in self.data.get("sets", []) if s.get("id") == set_id), None)

    def add_character(self, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Character name cannot be empty")
        with self.lock:
            for c in self.data["characters"]:
                if c["name"].casefold() == name.casefold():
                    return c
            c = {"id": uuid.uuid4().hex, "name": name, "categories": [], "created_at": now_iso()}
            self.data["characters"].append(c)
            self.save()
            return c

    def delete_character(self, character_id: str) -> dict[str, Any]:
        # Removing an accidental empty character must never delete media files.
        # Check under the import lock too, so a concurrent import cannot be orphaned.
        with self.lock:
            if not self.character(character_id):
                raise KeyError("Character not found")
            if any(m.get("character_id") == character_id for m in self.data.get("rapid_queue", [])):
                raise ValueError("This character has a pending Rapid Review queue. Finish or discard it first.")
            if any(m.get("character_id") == character_id for m in self.data["media"]):
                raise ValueError("This character contains images or videos. Remove or move them before deleting the character.")
            if any(s.get("character_id") == character_id and s.get("media_ids") for s in self.data.get("sets", [])):
                raise ValueError("This character contains set images.")
            self.data["characters"] = [c for c in self.data["characters"] if c["id"] != character_id]
            self.data["sets"] = [s for s in self.data.get("sets", []) if s.get("character_id") != character_id]
            self.save()
            return {"ok": True, "character_id": character_id}

    def add_set_category(self, character_id: str, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Set category name cannot be empty")
        with self.lock:
            owner = self.character(character_id)
            if not owner:
                raise KeyError("Character not found")
            categories = owner.setdefault("set_categories", [])
            for category in categories:
                if category["name"].casefold() == name.casefold():
                    return category
            category = {"id": uuid.uuid4().hex, "name": name, "created_at": now_iso()}
            categories.append(category)
            self.save()
            return category

    def edit_set_category(self, category_id: str, name: str | None = None) -> dict[str, Any]:
        with self.lock:
            for owner in self.data["characters"]:
                categories = owner.get("set_categories", [])
                category = next((c for c in categories if c["id"] == category_id), None)
                if category is None:
                    continue
                if name is None:
                    owner["set_categories"] = [c for c in categories if c["id"] != category_id]
                    for item in self.data.get("sets", []):
                        if item.get("character_id") == owner["id"] and category_id in item.get("categories", []):
                            item["categories"] = [c for c in item["categories"] if c != category_id]
                            item["updated_at"] = now_iso()
                else:
                    name = name.strip()
                    if not name:
                        raise ValueError("Set category name cannot be empty")
                    if any(c["id"] != category_id and c["name"].casefold() == name.casefold() for c in categories):
                        raise ValueError("A Set category with that name already exists")
                    category["name"] = name
                self.save()
                return category
            raise KeyError("Set category not found")

    def _validate_set_categories(self, character_id: str, categories: Any) -> list[str]:
        valid = {c["id"] for c in (self.character(character_id) or {}).get("set_categories", [])}
        if not isinstance(categories, list) or any(not isinstance(c, str) or c not in valid for c in categories):
            raise ValueError("Choose Set categories belonging to this character")
        return list(dict.fromkeys(categories))

    def _main_categories(self, media):
        owner = self.character(media['character_id'])
        ids = set(media.get('categories', []))
        return any(c['id'] in ids and not c.get('ghost', False) for c in (owner or {}).get('categories', []))

    def set_category_ghost(self, category_id, ghost):
        if type(ghost) is not bool:
            raise ValueError('Ghost must be true or false.')
        with self.lock:
            owner = next((c for c in self.data['characters'] if any(k['id'] == category_id for k in c.get('categories', []))), None)
            if not owner:
                raise KeyError('Category not found')
            category = next(c for c in owner['categories'] if c['id'] == category_id)
            affected = [m for m in self.data['media'] if m['character_id'] == owner['id'] and category_id in m.get('categories', [])]
            for m in affected:
                flag = 'in_videos' if m['media_type'] == 'video' else 'in_all'
                m.setdefault('main_explicit', bool(m.get(flag, True)) and not self._main_categories(m))
            category['ghost'] = ghost
            for m in affected:
                was = self._in_main(m)
                flag = 'in_videos' if m['media_type'] == 'video' else 'in_all'
                if not m.get('in_review') and not m.get('in_purgatory'):
                    m[flag] = bool(m.get('main_explicit')) or self._main_categories(m)
                self._stamp_main_entry(m, was)
            self.save()
            return owner

    def add_category(self, character_id: str, name: str, media_type: str = "image") -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        if name.casefold() == "all":
            raise ValueError("All is automatic and cannot be created as a category")
        media_type = str(media_type or "image").strip().lower()
        if media_type not in ("image", "video"):
            raise ValueError("Category type must be image or video")
        with self.lock:
            c = self.character(character_id)
            if not c:
                raise KeyError("Character not found")
            for cat in c["categories"]:
                if cat["name"].casefold() == name.casefold() and cat.get("media_type", "image") == media_type:
                    return cat
            cat = {"id": uuid.uuid4().hex, "name": name, "media_type": media_type, "created_at": now_iso()}
            c["categories"].append(cat)
            self.save()
            return cat

    def rename_category(self, category_id: str, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        if name.casefold() == "all":
            raise ValueError("All is automatic and cannot be used as a category name")
        with self.lock:
            owner = None
            category = None
            for character in self.data["characters"]:
                for candidate in character.get("categories", []):
                    if candidate.get("id") == category_id:
                        owner = character
                        category = candidate
                        break
                if category:
                    break
            if not owner or not category:
                raise KeyError("Category not found")
            media_type = category.get("media_type", "image")
            for candidate in owner.get("categories", []):
                if candidate.get("id") != category_id and candidate.get("media_type", "image") == media_type and candidate.get("name", "").casefold() == name.casefold():
                    raise ValueError(f"A {media_type} category with that name already exists")
            category["name"] = name
            self.save()
            return category

    def delete_category(self, category_id: str) -> dict[str, Any]:
        with self.lock:
            owner = None
            category = None
            for c in self.data["characters"]:
                for cat in c.get("categories", []):
                    if cat.get("id") == category_id:
                        owner = c
                        category = cat
                        break
                if owner:
                    break
            if not owner or not category:
                raise KeyError("Category not found")

            owner["categories"] = [cat for cat in owner.get("categories", []) if cat.get("id") != category_id]
            affected = 0
            for m in self.data["media"] + self.data.get("rapid_queue", []):
                if m.get("character_id") != owner.get("id"):
                    continue
                cats = list(m.get("categories", []))
                if category_id in cats:
                    m["categories"] = [x for x in cats if x != category_id]
                    affected += 1
            self.save()
            return {
                "ok": True,
                "character_id": owner.get("id"),
                "category_id": category_id,
                "category_name": category.get("name", ""),
                "media_updated": affected,
            }

    def _validate_categories(self, character_id: str, categories: list[str], media_type: str | None = None) -> list[str]:
        c = self.character(character_id)
        if not c:
            raise KeyError("Character not found")
        valid = {
            cat["id"] for cat in c["categories"]
            if media_type is None or cat.get("media_type", "image") == media_type
        }
        return [x for x in dict.fromkeys(categories) if x in valid]

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _make_thumbnail(self, original: Path, media_id: str, character_name: str) -> tuple[str | None, int | None, int | None]:
        if Image is None:
            return None, None, None
        folder = self.thumb_dir / safe_component(character_name, "Character")
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"{media_id}.webp"
        try:
            with Image.open(original) as im:
                source_width, source_height = im.size
                # JPEG can decode directly at a reduced resolution, avoiding a full-size
                # decode for thumbnails of very large source images.
                try:
                    if str(getattr(im, "format", "")).upper() == "JPEG":
                        im.draft("RGB", (840, 840))
                except Exception:
                    pass
                if ImageOps is not None:
                    im = ImageOps.exif_transpose(im)
                try:
                    im.seek(0)
                except Exception:
                    pass
                # Thumbnails are only 420px. High-effort LANCZOS + WebP method 5 can
                # take many seconds on large phone/AI images and used to block imports.
                # Use the fast thumbnail path; the untouched original is never changed.
                im.thumbnail((420, 420), Image.Resampling.BILINEAR)
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "transparency" in im.info else "RGB")
                im.save(out, "WEBP", quality=82, method=1)
            return out.relative_to(self.root).as_posix(), source_width, source_height
        except Exception:
            try:
                if out.exists():
                    out.unlink()
            except Exception:
                pass
            return None, None, None

    def _queue_image_thumbnail(self, original: Path, media_id: str, character_name: str) -> None:
        # One daemon processes the queue. A batch must not start dozens of simultaneous
        # full-size image decoders and compete with imports, Review, and the browser.
        # Enqueue only: saving the original remains the entire import critical path.
        with self.lock:
            self._thumbnail_queue.put((original, media_id, character_name))
            if self._thumbnail_worker is None or not self._thumbnail_worker.is_alive():
                self._thumbnail_worker = threading.Thread(
                    target=self._run_thumbnail_queue,
                    name="nai-thumbnails",
                    daemon=True,
                )
                self._thumbnail_worker.start()

    def _run_thumbnail_queue(self) -> None:
        while True:
            job = self._thumbnail_queue.get()
            try:
                if job is None:
                    return
                original, media_id, character_name = job
                # Skip items deleted/replaced while waiting, before decoding anything.
                with self.lock:
                    item = self.media_item(media_id) or self.rapid_item(media_id)
                    if not item or (self.root / str(item.get("stored_rel") or "")).resolve() != original.resolve():
                        continue
                # Let the successful import response flush before background work starts.
                time.sleep(0.10)
                thumbnail_result = self._make_thumbnail(original, media_id, character_name)
                # Keep the worker compatible with lightweight test/custom thumbnail
                # hooks that return only a path (or None), while the built-in path
                # returns source dimensions together with the thumbnail.
                if isinstance(thumbnail_result, tuple):
                    thumb_rel, width, height = thumbnail_result
                else:
                    thumb_rel, width, height = thumbnail_result, None, None
                if not thumb_rel:
                    continue
                with self.lock:
                    item = self.media_item(media_id) or self.rapid_item(media_id)
                    if not item or (self.root / str(item.get("stored_rel") or "")).resolve() != original.resolve():
                        (self.root / thumb_rel).unlink(missing_ok=True)
                        continue
                    item["thumb_rel"] = thumb_rel
                    item["width"] = width
                    item["height"] = height
                    self._apply_resolution_flag(item)
                    try:
                        item["file_bytes"] = original.stat().st_size
                    except Exception:
                        pass
                    self.save()
            except Exception:
                # A bad image or failed thumbnail save must not stop the remaining queue.
                try:
                    traceback.print_exc()
                except Exception:
                    pass
            finally:
                self._thumbnail_queue.task_done()

    def _make_video_thumbnail(self, original: Path, media_id: str, character_name: str, seconds: float = 0.0) -> str | None:
        folder = self.thumb_dir / safe_component(character_name, "Character")
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"{media_id}.jpg"
        seconds = max(0.0, float(seconds or 0.0))
        cmd = [
            "ffmpeg", "-y",
            "-i", str(original),
            "-ss", f"{seconds:.3f}",
            "-frames:v", "1",
            "-vf", "scale=420:420:force_original_aspect_ratio=decrease",
            "-q:v", "3",
            str(out),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120)
            if out.exists() and out.stat().st_size > 0:
                return out.relative_to(self.root).as_posix()
        except Exception:
            try:
                if out.exists():
                    out.unlink()
            except Exception:
                pass
        return None

    def _register_file(
        self,
        temp_path: Path,
        original_name: str,
        character_id: str,
        categories: list[str],
        source: dict[str, Any],
        content_type: str | None = None,
        pending: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        # Hashing can read a large video for many seconds. Do it before taking the
        # library lock so playback, metadata reads, and other UI requests remain
        # responsive while duplicate detection is in progress. The final duplicate
        # check and registration still happen under the lock, so concurrent imports
        # cannot register the same file twice.
        if not content_type:
            guessed_type, _ = mimetypes.guess_type(original_name)
            content_type = guessed_type or "application/octet-stream"
        media_type = "video" if content_type.startswith("video/") else "image"
        sha = self._hash_file(temp_path)
        width = height = None
        if media_type == "image" and Image is not None:
            try:
                with Image.open(temp_path) as image:
                    width, height = image.size
            except Exception:
                pass
        with self.lock:
            c = self.character(character_id)
            if not c:
                raise KeyError("Character not found")
            categories = self._validate_categories(character_id, categories, media_type)
            for existing in (self.data.get("rapid_queue", []) if pending else self.data["media"]):
                if existing.get("character_id") == character_id and existing.get("sha256") == sha:
                    changed = False
                    if existing.get("media_type") == "video":
                        merged = list(dict.fromkeys(existing.get("categories", []) + categories))
                        if merged != existing.get("categories", []):
                            existing["categories"] = merged
                            changed = True
                        if not isinstance(existing.get("video_markers"), list) or len(existing.get("video_markers")) != 3:
                            existing["video_markers"] = [None, None, None]
                            changed = True
                        if existing.get("video_thumb_seconds") is None:
                            existing["video_thumb_seconds"] = 0.0
                            changed = True
                    else:
                        merged = list(dict.fromkeys(existing.get("categories", []) + categories))
                        if merged != existing.get("categories", []):
                            existing["categories"] = merged
                            changed = True
                    if changed:
                        self.save()
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return existing, True

            media_id = uuid.uuid4().hex
            original_name = safe_component(Path(original_name).name, f"media-{media_id}")
            suffix = Path(original_name).suffix.lower()
            if not suffix:
                guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ""
                suffix = guessed
                original_name += suffix

            char_folder = self.media_dir / safe_component(c["name"], "Character")
            char_folder.mkdir(parents=True, exist_ok=True)
            stored_name = f"{media_id}_{original_name}"
            destination = char_folder / stored_name
            shutil.move(str(temp_path), destination)
            try:
                file_bytes = destination.stat().st_size
            except Exception:
                file_bytes = None

            # Import completion must not wait for image decoding/resizing. The media endpoint
            # already falls back to the original while thumb_rel is empty, and a background
            # worker fills in the thumbnail shortly after the successful import response.
            thumb_rel = None
            video_markers = [None, None, None]
            video_thumb_seconds = None
            if media_type == "video":
                # Video thumbnails are captured from the exact frame chosen in the browser.
                video_thumb_seconds = 0.0

            item = {
                "id": media_id,
                "character_id": character_id,
                "original_name": original_name,
                "stored_rel": destination.relative_to(self.root).as_posix(),
                "thumb_rel": thumb_rel,
                "media_type": media_type,
                "content_type": content_type,
                "categories": categories,
                "in_all": media_type != "video" and (not categories or self._main_categories({"character_id": character_id, "categories": categories})),
                "in_videos": media_type == "video" and (not categories or self._main_categories({"character_id": character_id, "categories": categories})),
                "favorite": False,
                "featured": False,
                "in_review": False,
                "crop_top": 0.0,
                "crop_bottom": 0.0,
                "sha256": sha,
                "source": source,
                "video_markers": video_markers,
                "video_thumb_seconds": video_thumb_seconds,
                "file_bytes": file_bytes,
                "width": width,
                "height": height,
                "created_at": now_iso(),
            }
            if not pending:
                item["main_added_at"] = item["created_at"]
            item['category_added_at'] = {key:item['created_at'] for key in categories}
            self._apply_resolution_flag(item)
            self.data.setdefault("rapid_queue" if pending else "media", []).append(item)
            self.save()
            if media_type == "image":
                self._queue_image_thumbnail(destination, media_id, c["name"])
            return item, False

    def cleanup_upload_orphans(self) -> None:
        # Called only after binding the port: a second companion must not remove
        # uploads belonging to the instance that is already running.
        for orphan in self._upload_dir.glob("*.part"):
            orphan.unlink(missing_ok=True)

    def _expire_uploads(self) -> None:
        # On-demand cleanup only: no idle polling or network activity.
        cutoff = time.monotonic() - 3600
        for token, job in list(self._uploads.items()):
            if job["touched"] < cutoff:
                (self._upload_dir / f"{token}.part").unlink(missing_ok=True)
                del self._uploads[token]

    def chunk_upload(self, token: str, action: str, body: dict[str, Any]) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", token):
            raise ValueError("Invalid upload ID")
        with self._upload_lock:
            self._expire_uploads()
            temp = self._upload_dir / f"{token}.part"
            job = self._uploads.get(token)
            if action == "cancel":
                if job and job["state"] == "done":
                    return {"state": "done"}
                temp.unlink(missing_ok=True)
                # A cancellation may arrive before a delayed start request.
                self._uploads[token] = {"state": "canceled", "touched": time.monotonic()}
                return {"state": "canceled"}
            if job and job["state"] == "canceled":
                raise ValueError("Import canceled")
            if action == "start":
                size = body.get("size")
                if type(size) is not int or size <= 0 or size > 16 * 1024**3:
                    raise ValueError("File must be between 1 byte and 16 GiB")
                meta = {k: body.get(k) for k in ("character_id", "filename", "size", "content_type", "categories", "source_url", "pending_review")}
                if job:
                    if job["meta"] != meta:
                        raise ValueError("Upload ID already belongs to another file")
                    job["touched"] = time.monotonic()
                    return {"offset": job["offset"], "state": job["state"]}
                if sum(j["state"] == "receiving" for j in self._uploads.values()) >= 32:
                    raise ValueError("Too many unfinished uploads; cancel or restart the companion")
                if not isinstance(meta["filename"], str) or not meta["filename"]:
                    raise ValueError("Uploaded file has no filename")
                content_type = str(meta["content_type"] or "")
                if not content_type.startswith(("image/", "video/")):
                    content_type = mimetypes.guess_type(meta["filename"])[0] or ""
                if not content_type.startswith(("image/", "video/")):
                    raise ValueError("Only image and video files are supported")
                source_url = str(meta["source_url"] or "")
                if source_url and urllib.parse.urlparse(source_url).scheme not in ("http", "https"):
                    raise ValueError("Only http:// and https:// source URLs are supported")
                with self.lock:
                    if not self.character(str(meta["character_id"])):
                        raise KeyError("Character not found")
                self._upload_dir.mkdir(parents=True, exist_ok=True)
                temp.touch(exist_ok=False)
                job = {"state": "receiving", "meta": meta, "content_type": content_type,
                       "offset": 0, "touched": time.monotonic(), "started": time.perf_counter()}
                self._uploads[token] = job
                self.last_import_debug = {"state": "receiving", "filename": meta["filename"], "received_bytes": 0, "file_bytes": size}
                return {"offset": 0, "state": "receiving"}
            if not job:
                raise ValueError("Upload expired or companion restarted; please retry saving")
            job["touched"] = time.monotonic()
            if action == "chunk":
                if job["state"] != "receiving":
                    raise ValueError("Upload is already complete")
                offset = body.get("offset")
                encoded = body.get("data")
                if type(offset) is not int or offset < 0 or not isinstance(encoded, str) or len(encoded) > 22400000:
                    raise ValueError("Invalid upload chunk")
                data = base64.b64decode(encoded, validate=True)
                if not data or len(data) > 16 * 1024**2 or hashlib.sha256(data).hexdigest() != body.get("sha256"):
                    raise ValueError("Upload chunk integrity check failed")
                end = offset + len(data)
                if end > job["meta"]["size"] or offset > job["offset"]:
                    raise ValueError("Upload chunk is out of order or exceeds file size")
                with temp.open("r+b") as output:
                    output.seek(offset)
                    if offset < job["offset"]:
                        # Lost acknowledgments can safely retry an identical chunk.
                        if end > job["offset"] or output.read(len(data)) != data:
                            raise ValueError("Retry does not match previously received bytes")
                    else:
                        output.write(data)
                        job["offset"] = end
                self.last_import_debug = {"state": "receiving", "filename": job["meta"]["filename"],
                                          "received_bytes": job["offset"], "file_bytes": job["meta"]["size"]}
                return {"offset": job["offset"]}
            if action == "finish":
                if job["state"] == "done":
                    return job["result"]
                if job["offset"] != job["meta"]["size"] or temp.stat().st_size != job["offset"]:
                    raise ValueError("Upload is incomplete")
                meta = job["meta"]
                self.last_import_debug = {"state": "registering", "filename": meta["filename"], "file_bytes": job["offset"]}
                source = {"kind": "url", "url": meta["source_url"]} if meta["source_url"] else {"kind": "local", "original_name": meta["filename"]}
                item, duplicate = self._register_file(temp, meta["filename"], str(meta["character_id"]),
                    meta["categories"] if isinstance(meta["categories"], list) else [], source, job["content_type"], pending=meta.get("pending_review") is True)
                job["result"] = {"item": item, "duplicate": duplicate}
                job["state"] = "done"
                self.last_import_debug = {"state": "done", "recorded_at_epoch_ms": int(time.time()*1000),
                    "filename": meta["filename"], "file_bytes": job["offset"], "duplicate": duplicate,
                    "debug_timing_ms": {"chunked_total": round((time.perf_counter()-job["started"])*1000, 1)}}
                return job["result"]
            raise ValueError("Unknown upload action")

    def import_bytes(
        self,
        payload: bytes,
        original_name: str,
        character_id: str,
        categories: list[str],
        source: dict[str, Any],
        content_type: str | None,
    ) -> tuple[dict[str, Any], bool]:
        temp_dir = self.root / ".incoming"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp = temp_dir / f"{uuid.uuid4().hex}.part"
        with temp.open("wb") as f:
            f.write(payload)
        return self._register_file(temp, original_name, character_id, categories, source, content_type)

    def import_bytes_profiled(
        self,
        payload: bytes,
        original_name: str,
        character_id: str,
        categories: list[str],
        source: dict[str, Any],
        content_type: str | None,
    ) -> tuple[dict[str, Any], bool, dict[str, float]]:
        timing: dict[str, float] = {}
        backend_started = time.perf_counter()
        temp_dir = self.root / ".incoming"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp = temp_dir / f"{uuid.uuid4().hex}.part"

        phase = time.perf_counter()
        with temp.open("wb") as f:
            f.write(payload)
            f.flush()
        timing["temp_write"] = round((time.perf_counter() - phase) * 1000, 1)

        phase = time.perf_counter()
        item, duplicate = self._register_file(temp, original_name, character_id, categories, source, content_type)
        timing["register"] = round((time.perf_counter() - phase) * 1000, 1)
        timing["backend_total"] = round((time.perf_counter() - backend_started) * 1000, 1)
        return item, duplicate, timing

    def performance_probe(self) -> dict[str, Any]:
        # Small explicit local-disk probe used only by the diagnostics endpoint. It does not
        # alter library.json or any media. This helps distinguish loopback/Tampermonkey delay
        # from Windows Defender/OneDrive/disk latency in the managed library directory.
        incoming = self.root / ".incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        probe = incoming / f"diag-{uuid.uuid4().hex}.tmp"
        payload = b"\0" * (2 * 1024 * 1024)
        result: dict[str, Any] = {
            "library_root": str(self.root),
            "root_mentions_onedrive": "onedrive" in str(self.root).casefold(),
            "media_count": len(self.data.get("media", [])),
            "library_json_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "probe_bytes": len(payload),
        }
        try:
            phase = time.perf_counter()
            with probe.open("wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            result["write_fsync_ms"] = round((time.perf_counter() - phase) * 1000, 1)

            phase = time.perf_counter()
            h = hashlib.sha256()
            with probe.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            result["read_hash_ms"] = round((time.perf_counter() - phase) * 1000, 1)

            phase = time.perf_counter()
            probe.unlink(missing_ok=True)
            result["delete_ms"] = round((time.perf_counter() - phase) * 1000, 1)
        finally:
            try:
                probe.unlink(missing_ok=True)
            except Exception:
                pass
        return result

    def download_url_preview(self, url: str) -> tuple[Path, str, str]:
        """Download to a temporary file without registering media or generating thumbnails."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only http:// and https:// URLs are supported")
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,video/*,*/*;q=0.8",
            },
        )
        temp_dir = self.root / ".incoming"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp = temp_dir / f"{uuid.uuid4().hex}.part"
        max_bytes = 512 * 1024 * 1024
        total = 0
        try:
            with urllib.request.urlopen(req, timeout=45) as resp, temp.open("wb") as out:
                content_type = (resp.headers.get_content_type() or "application/octet-stream").lower()
                if not (content_type.startswith("image/") or content_type.startswith("video/")):
                    raise ValueError(f"URL did not return an image or video (content type: {content_type})")
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("Remote media is larger than 512 MB")
                    out.write(chunk)
                disp = resp.headers.get("Content-Disposition", "")
                filename = None
                match = re.search(r'filename\*?=(?:UTF-8\'\')?[\"\']?([^\"\';]+)', disp, re.I)
                if match:
                    filename = urllib.parse.unquote(match.group(1).strip())
                if not filename:
                    filename = Path(urllib.parse.unquote(parsed.path)).name or "download"
                if not Path(filename).suffix:
                    filename += mimetypes.guess_extension(content_type) or ""
            return temp, filename, content_type
        except Exception:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def import_url(self, url: str, character_id: str, categories: list[str]) -> tuple[dict[str, Any], bool]:
        temp, filename, content_type = self.download_url_preview(url)
        try:
            return self._register_file(temp, filename, character_id, categories, {"kind": "url", "url": url}, content_type)
        finally:
            temp.unlink(missing_ok=True)

    def replace_media_bytes(
        self,
        payload: bytes,
        original_name: str,
        media_id: str,
        content_type: str | None,
    ) -> dict[str, Any]:
        """Replace one image's source while retaining its stable media record.

        The media ID is intentionally preserved: categories, favorites, Review state,
        crop settings, set membership, cover references, and array position all point
        at that ID. Hashing happens before taking the library lock for the same reason
        as normal imports: replacing a large source must not pause metadata requests.
        """
        temp_dir = self.root / ".incoming"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp = temp_dir / f"{uuid.uuid4().hex}.replace"
        try:
            with temp.open("wb") as f:
                f.write(payload)
                f.flush()
            sha = self._hash_file(temp)
            with self.lock:
                item = self.media_item(media_id)
                if not item:
                    raise KeyError("Media not found")
                if item.get("media_type") != "image":
                    raise ValueError("Only images can have their source replaced")
                owner = self.character(item.get("character_id", ""))
                if not owner:
                    raise KeyError("Character not found")
                for other in self.data["media"]:
                    if other.get("id") != media_id and other.get("character_id") == item.get("character_id") and other.get("sha256") == sha:
                        raise ValueError("That source image is already in this character's library")

                content_type = (content_type or "").split(";", 1)[0].strip().lower()
                if not content_type.startswith("image/"):
                    guessed, _ = mimetypes.guess_type(original_name)
                    content_type = guessed or content_type
                if not content_type.startswith("image/"):
                    raise ValueError("Only image files are supported for source replacement")

                if sha == item.get("sha256"):
                    return item
                old_path = self.root / item["stored_rel"]
                if not old_path.is_file() or self._hash_file(old_path) != item["sha256"]:
                    raise ValueError("The current source is missing or changed. Replacement stopped to protect Undo.")
                old = copy.deepcopy(item)
                before = {k: copy.deepcopy(item[k]) for k in self._replacement_fields if k in item}
                safe_name = safe_component(Path(original_name).name, f"image-{media_id}")
                if not Path(safe_name).suffix:
                    safe_name += mimetypes.guess_extension(content_type) or ".img"
                char_folder = self.media_dir / safe_component(owner["name"], "Character")
                char_folder.mkdir(parents=True, exist_ok=True)
                # Unique destinations also protect originals when names are identical.
                destination = char_folder / f"{media_id}_{uuid.uuid4().hex}_{safe_name}"
                os.replace(temp, destination)

                # Update only source-derived fields. All user/library relationships stay
                # on the same object, so its list position and set membership are stable.
                item["original_name"] = safe_name
                item["stored_rel"] = destination.relative_to(self.root).as_posix()
                item["thumb_rel"] = None
                item["content_type"] = content_type
                item["sha256"] = sha
                item["source"] = {"kind": "local", "original_name": safe_name}
                item["in_all"] = bool(item.get("in_all", True))
                item["needs_replacement"] = False
                item["replacement_auto"] = False
                item.pop("replacement_override_sha", None)
                item["width"] = item["height"] = None
                item["file_bytes"] = destination.stat().st_size
                if Image is not None:
                    try:
                        with Image.open(destination) as image:
                            item["width"], item["height"] = image.size
                    except Exception:
                        pass
                self._apply_resolution_flag(item)
                try:
                    self._save_undo({"kind": "replace", "label": "Replace image source", "media_id": media_id,
                                     "filename": str(old.get("original_name", "")) + " → " + safe_name,
                                     "before": before,
                                     "after": {k: copy.deepcopy(item[k]) for k in self._replacement_fields if k in item}})
                except Exception:
                    item.clear(); item.update(old)
                    # Both source files remain if persistence fails.
                    raise
                result = item
            self._queue_image_thumbnail(destination, media_id, owner["name"])
            return result
        finally:
            temp.unlink(missing_ok=True)

    def _validate_set_media(self, character_id: str, media_ids: list[Any]) -> list[str]:
        c = self.character(character_id)
        if not c:
            raise KeyError("Character not found")
        result: list[str] = []
        seen: set[str] = set()
        for raw in media_ids:
            media_id = str(raw or "").strip()
            if not media_id or media_id in seen:
                continue
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            if m.get("character_id") != character_id:
                raise ValueError("All collection media must belong to the selected character")
            seen.add(media_id)
            result.append(media_id)
        return result

    def _detach_set_members(self, character_id: str, media_ids: list[str], except_set_id: str | None = None) -> None:
        member_ids = set(media_ids)
        kept_sets = []
        for item in self.data.get("sets", []):
            if item.get("kind", "set") != "set" or item.get("character_id") != character_id or item.get("id") == except_set_id:
                kept_sets.append(item)
                continue
            old_members = list(item.get("media_ids", []))
            new_members = [mid for mid in old_members if mid not in member_ids]
            if new_members != old_members:
                item["media_ids"] = new_members
                if item.get("cover_media_id") not in new_members:
                    item["cover_media_id"] = new_members[0] if new_members else None
                    item["cover_source"] = "auto"
                item["updated_at"] = now_iso()
            kept_sets.append(item)
        self.data["sets"] = kept_sets

    def _unique_set_name(self, character_id: str, name: str, except_set_id: str | None = None) -> str:
        names = {str(s.get("name", "")).strip().casefold()
                 for s in self.data.get("sets", [])
                 if s.get("character_id") == character_id and s.get("kind", "set") == "set"
                 and s.get("id") != except_set_id}
        if name.casefold() not in names:
            return name
        pattern = re.compile(re.escape(name.casefold()) + r" ([0-9]+)$")
        suffix = max((int(m.group(1)) for n in names if (m := pattern.fullmatch(n))), default=0) + 1
        return f"{name} {suffix}"

    def create_set(self, character_id: str, name: str, media_ids: list[Any], cover_media_id: Any = None, kind: str = "set", preserve_placement: bool = False, cover_source: Any = None, categories: Any = None, aliases: Any = None, colors: Any = None, notes: Any = None) -> dict[str, Any]:
        if kind != "set":
            raise ValueError("Only Sets are supported")
        name = title_case_label(name)
        if not name:
            raise ValueError("Set name cannot be empty")
        details = self._set_details(aliases, colors, notes)
        with self.lock:
            if not self.character(character_id):
                raise KeyError("Character not found")
            categories = self._validate_set_categories(character_id, [] if categories is None else categories)
            name = self._unique_set_name(character_id, name)
            members = self._validate_set_media(character_id, list(media_ids or []))
            if kind == "set":
                self._detach_set_members(character_id, members)
            joined_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            for media_id in members:
                media = self.media_item(media_id)
                was_in_main = self._in_main(media) if media else False
                if media and (media.get("in_purgatory") or media.get("in_review")):
                    media["in_purgatory"] = False
                    media["in_review"] = False
                    media["in_videos" if media.get("media_type") == "video" else "in_all"] = self._main_categories(media) or bool(media.get("main_explicit"))
                elif kind == "set" and not preserve_placement and media and not self._main_categories(media) and not media.get("main_explicit"):
                    media["in_videos" if media.get("media_type") == "video" else "in_all"] = False
                if media:
                    media["set_added_at"] = joined_at
                    self._stamp_main_entry(media, was_in_main)
            cover = str(cover_media_id or "")
            if cover not in members:
                cover = members[0] if members else None
            stamp = now_iso()
            item = {
                "id": uuid.uuid4().hex,
                "character_id": character_id,
                "name": name,
                "media_ids": members,
                "kind": kind,
                "categories": categories,
                "cover_media_id": cover,
                "cover_source": "manual" if cover_source == "manual" and str(cover_media_id or "") in members else "auto",
                "favorite": False,
                "created_at": stamp,
                "updated_at": stamp,
            }
            item.update(details)
            self.data.setdefault("sets", []).append(item)
            self.save()
            return item

    def update_set(self, set_id: str, name: Any = None, media_ids: Any = None, cover_media_id: Any = None, preserve_placement: bool = False, add_media_ids: Any = None, cover_source: Any = None, favorite: Any = None, categories: Any = None, remove_media_ids: Any = None, aliases: Any = None, colors: Any = None, notes: Any = None) -> dict[str, Any]:
        details = self._set_details(aliases, colors, notes)
        with self.lock:
            item = self.set_item(set_id)
            if not item:
                raise KeyError("Set not found")
            character_id = str(item.get("character_id", ""))
            kind = item.get("kind", "set")
            next_name = str(item.get("name", "")) if name is None else title_case_label(name)
            if not next_name:
                raise ValueError("Set name cannot be empty")
            next_name = self._unique_set_name(character_id, next_name, set_id)
            if cover_source is not None and cover_source not in ("manual", "auto", "unknown"):
                raise ValueError("Invalid cover source")
            if favorite is not None and not isinstance(favorite, bool):
                raise ValueError("Invalid set favorite")
            next_categories = item.get("categories", []) if categories is None else self._validate_set_categories(character_id, categories)
            previous_members = list(item.get("media_ids", []))
            previous_member_ids = set(previous_members)
            if remove_media_ids is not None:
                if media_ids is not None or add_media_ids is not None or not isinstance(remove_media_ids, list) or any(not isinstance(mid, str) for mid in remove_media_ids):
                    raise ValueError("Invalid Set removal")
                media_ids = [mid for mid in previous_members if mid not in remove_media_ids]
            if add_media_ids is not None:
                if media_ids is not None or not isinstance(add_media_ids, list):
                    raise ValueError("Invalid collection assignment")
                media_ids = previous_members + add_media_ids
            members = previous_members if media_ids is None else self._validate_set_media(character_id, list(media_ids or []))
            if media_ids is None:
                members = self._validate_set_media(character_id, members)
            assigned_ids = set(add_media_ids) if add_media_ids is not None else (set(members) - previous_member_ids if media_ids is not None else set())
            if remove_media_ids is not None:
                assigned_ids = set()
            if kind == "set" and assigned_ids:
                self._detach_set_members(character_id, list(assigned_ids - previous_member_ids), except_set_id=set_id)
            joined_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            for media_id in members:
                media = self.media_item(media_id)
                was_in_main = self._in_main(media) if media else False
                if media_id in assigned_ids and media and (media.get("in_purgatory") or media.get("in_review")):
                    media["in_purgatory"] = False
                    media["in_review"] = False
                    media["in_videos" if media.get("media_type") == "video" else "in_all"] = self._main_categories(media) or bool(media.get("main_explicit"))
                elif media_id not in previous_member_ids and kind == "set" and not preserve_placement and media and not self._main_categories(media) and not media.get("main_explicit"):
                    media["in_videos" if media.get("media_type") == "video" else "in_all"] = False
                if media:
                    if media_id not in previous_member_ids:
                        media["set_added_at"] = joined_at
                    self._stamp_main_entry(media, was_in_main)
            cover = str(item.get("cover_media_id", "")) if cover_media_id is None else str(cover_media_id or "")
            source = item.get("cover_source", "unknown")
            if cover not in members:
                cover = members[0] if members else None
                source = "auto"
            elif cover_source is not None:
                source = cover_source
            elif cover_media_id is not None and (cover != item.get("cover_media_id") or media_ids is None):
                source = "manual"
            item.update(details)
            item["categories"] = next_categories
            item["cover_source"] = source
            if favorite is not None:
                item["favorite"] = favorite
            item["name"] = next_name
            item["media_ids"] = members
            item["cover_media_id"] = cover
            item["updated_at"] = now_iso()
            self._release_set_members(previous_member_ids - set(members))
            self.save()
            return item

    def bulk_set_categories(self, character_id: str, set_ids: Any, categories: Any, action: str) -> dict[str, Any]:
        with self.lock:
            if action not in ("add", "remove") or not isinstance(set_ids, list) or not set_ids or any(not isinstance(i, str) for i in set_ids):
                raise ValueError("Choose Sets and an add/remove action")
            categories = self._validate_set_categories(character_id, categories)
            targets = [self.set_item(i) for i in dict.fromkeys(set_ids)]
            if any(not s or s.get("character_id") != character_id for s in targets):
                raise ValueError("All Sets must belong to this character")
            before = [copy.deepcopy(s) for s in targets]
            for item in targets:
                current = item.get("categories", [])
                updated = list(dict.fromkeys(current + categories)) if action == "add" else [c for c in current if c not in categories]
                if updated != current:
                    item["categories"] = updated
                    item["updated_at"] = now_iso()
            try:
                self.save()
            except Exception:
                for item, old in zip(targets, before):
                    item.clear(); item.update(old)
                raise
            return {"ok": True, "set_ids": list(dict.fromkeys(set_ids))}

    def _release_set_members(self, media_ids) -> None:
        for media_id in media_ids:
            media = self.media_item(media_id)
            if media and not media.get("in_review") and not media.get("in_purgatory") and not any(media_id in s.get("media_ids", []) for s in self.data.get("sets", [])):
                was_in_main = self._in_main(media)
                media["in_videos" if media.get("media_type") == "video" else "in_all"] = True
                self._stamp_main_entry(media, was_in_main)

    def delete_set(self, set_id: str) -> dict[str, Any]:
        with self.lock:
            item = self.set_item(set_id)
            if not item:
                raise KeyError("Set not found")
            self.data["sets"] = [s for s in self.data.get("sets", []) if s.get("id") != set_id]
            self._release_set_members(item.get("media_ids", []))
            self.save()
            return {"ok": True, "set_id": set_id}

    def set_categories(self, media_id: str, categories: list[str], in_all: Any = None, in_videos: Any = None) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            categories = self._validate_categories(m["character_id"], categories, m.get("media_type", "image"))
            video = m.get("media_type") == "video"
            flag = "in_videos" if video else "in_all"
            explicit = in_videos if video else in_all
            next_main = bool(m.get(flag, True)) if explicit is None else bool(explicit)
            changes = {"categories": categories, flag: next_main}
            if explicit is not None:
                changes["main_explicit"] = bool(explicit)
            if video:
                changes["in_all"] = False
            if self._main_categories({**m, "categories": categories}) and explicit is None:
                changes[flag] = True
            # Only new assignments (or explicit Main) leave holding areas. Saving
            # unchanged categories or removing one must not silently release Review.
            added_categories = set(categories) - set(m.get("categories", []))
            if (m.get("in_purgatory") or m.get("in_review")) and (added_categories or explicit is True):
                main = self._main_categories({**m, "categories": categories}) or bool(changes.get("main_explicit", m.get("main_explicit")))
                changes.update({"in_purgatory": False, "in_review": False, flag: main})
            return self._change_media(m, changes, "Change video categories / All" if video else "Change categories / All")

    def set_favorite(self, media_id: str, favorite: bool) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            if bool(m.get("favorite")) == bool(favorite):
                return m
            return self._change_media(m, {"favorite": bool(favorite)}, "Change favorite")

    def clear_holding(self, media_id: str) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:raise KeyError('Media not found')
            # Explicitly leave both holding areas without promoting or changing sets.
            return self._change_media(m, {'in_review':False,'in_purgatory':False,'in_all':False,'in_videos':False,'main_explicit':False}, 'Remove from holding area')

    def set_review(self, media_id: str, in_review: bool) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            if bool(m.get("in_review")) == bool(in_review) and not (not in_review and bool(m.get("in_purgatory"))):
                return m
            if in_review:
                return self._change_media(m, {"in_review": True, "in_purgatory": False}, "Change Review status")
            # Keep the original import date; _change_media records entry into Main.
            return self._change_media(m, {"in_review": False, "in_purgatory": False, "in_all": m.get("media_type") != "video", "in_videos": m.get("media_type") == "video", "main_explicit": True}, "Promote from Review")

    def set_purgatory(self, media_id: str, in_purgatory: bool) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            target = bool(in_purgatory)
            changes = {"in_purgatory": target}
            if target:
                changes.update({"in_review": False, "in_all": False, "in_videos": False, "main_explicit": False})
            if all(m.get(key) == value for key, value in changes.items()):
                return m
            return self._change_media(m, changes, "Send to Purgatory" if target else "Restore from Purgatory")

    def set_crop(self, media_id: str, top: Any = 0.0, bottom: Any = 0.0) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            if m.get("media_type") != "image":
                raise ValueError("Only images can be cropped")
            try:
                top = float(top or 0.0)
            except Exception:
                top = 0.0
            try:
                bottom = float(bottom or 0.0)
            except Exception:
                bottom = 0.0
            top = max(0.0, min(0.89, top))
            bottom = max(0.0, min(0.89, bottom))
            total = top + bottom
            if total > 0.90:
                scale = 0.90 / total
                top *= scale
                bottom *= scale
            m["crop_top"] = round(top, 6)
            m["crop_bottom"] = round(bottom, 6)
            self.save()
            return m

    def set_video_meta(self, media_id: str, thumb_seconds: float | None = None, markers: list[Any] | None = None) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            if m.get("media_type") != "video":
                raise ValueError("Selected media is not a video")
            changed = False
            if markers is not None:
                normalized = []
                for i in range(3):
                    value = markers[i] if i < len(markers) else None
                    if value in (None, "", False):
                        normalized.append(None)
                    else:
                        normalized.append(max(0.0, float(value)))
                if normalized != m.get("video_markers"):
                    m["video_markers"] = normalized
                    changed = True
            if thumb_seconds is not None:
                seconds = max(0.0, float(thumb_seconds))
                stored_path, _ = self.media_path(media_id, thumb=False)
                owner = self.character(m["character_id"])
                thumb_rel = self._make_video_thumbnail(stored_path, media_id, owner["name"] if owner else "Character", seconds)
                m["video_thumb_seconds"] = seconds
                if thumb_rel:
                    m["thumb_rel"] = thumb_rel
                changed = True
            if changed:
                self.save()
            return m

    def set_video_thumbnail_bytes(self, media_id: str, payload: bytes, content_type: str, seconds: float | None = None, automatic: bool = False) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            if m.get("media_type") != "video":
                raise ValueError("Selected media is not a video")
            # A delayed automatic capture must never overwrite a manual choice.
            if automatic and m.get("thumb_rel"):
                return m
            if not payload or len(payload) > 12 * 1024 * 1024:
                raise ValueError("Thumbnail image is empty or too large")
            if content_type not in ("image/jpeg", "image/png", "image/webp"):
                raise ValueError("Unsupported thumbnail image format")
            owner = self.character(m.get("character_id", ""))
            folder = self.thumb_dir / safe_component(owner["name"] if owner else "Character", "Character")
            folder.mkdir(parents=True, exist_ok=True)
            ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
            out = folder / f"{media_id}{ext}"
            # Remove an older generated thumbnail with a different extension.
            for candidate in folder.glob(f"{media_id}.*"):
                if candidate != out:
                    try:
                        candidate.unlink()
                    except Exception:
                        pass
            tmp = out.with_suffix(out.suffix + ".tmp")
            with tmp.open("wb") as f:
                f.write(payload)
            os.replace(tmp, out)
            m["thumb_rel"] = out.relative_to(self.root).as_posix()
            m["video_thumb_automatic"] = automatic
            if seconds is not None:
                m["video_thumb_seconds"] = max(0.0, float(seconds))
            self.save()
            return m

    def delete_media(self, media_id: str) -> None:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            previous_media, previous_sets = self.data["media"], self.data.get("sets", [])
            changes, next_sets = [], []
            for item in previous_sets:
                if media_id not in item.get("media_ids", []):
                    next_sets.append(item)
                    continue
                updated = copy.deepcopy(item)
                updated["media_ids"] = [mid for mid in item.get("media_ids", []) if mid != media_id]
                if updated.get("cover_media_id") not in updated["media_ids"]:
                    updated["cover_media_id"] = next(iter(updated["media_ids"]), None)
                    updated["cover_source"] = "auto"
                updated["updated_at"] = now_iso()
                changes.append({"id": item["id"], "before": copy.deepcopy(item), "after": copy.deepcopy(updated)})
                next_sets.append(updated)
            entry = {"kind": "delete", "label": "Delete media", "media_id": media_id,
                     "filename": m.get("original_name", ""), "media": copy.deepcopy(m),
                     "index": previous_media.index(m), "sets": changes}
            self.data["media"] = [x for x in previous_media if x["id"] != media_id]
            self.data["sets"] = next_sets
            try:
                self._save_undo(entry)
            except Exception:
                self.data["media"], self.data["sets"] = previous_media, previous_sets
                raise

    def media_path(self, media_id: str, thumb: bool = False) -> tuple[Path, str]:
        with self.lock:
            m = self.media_item(media_id) or self.rapid_item(media_id)
            if not m:
                raise KeyError("Media not found")
            rel = m.get("thumb_rel") if thumb else m.get("stored_rel")
            if thumb and not rel:
                rel = m.get("stored_rel")
            path = (self.root / rel).resolve()
            if self.root.resolve() not in path.parents and path != self.root.resolve():
                raise ValueError("Invalid media path")
            if not path.exists():
                raise FileNotFoundError("Media file is missing")
            if thumb and m.get("thumb_rel"):
                return path, mimetypes.guess_type(path.name)[0] or "image/webp"
            return path, m.get("content_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    def grid_preview(self, media_id: str, requested_size: int) -> tuple[Path, str]:
        """On-demand sharp grid images. Never block metadata on image decoding."""
        size = next((n for n in (256, 512, 768, 1024) if n >= requested_size), 1024)
        with self.lock:
            item = self.media_item(media_id)
            if not item:
                raise KeyError("Media not found")
            # Video thumbnails preserve the chosen frame/crop. Browser captures
            # already keep full-resolution manual frames; never substitute a frame.
            video = item.get("media_type") == "video"
            source, content_type = self.media_path(media_id, thumb=video)
        if Image is None or not content_type.startswith("image/"):
            return self.media_path(media_id, thumb=True)
        info = source.stat()
        revision = hashlib.sha256(f"{source}:{info.st_mtime_ns}:{info.st_size}".encode()).hexdigest()[:20]
        folder = self.thumb_dir / "grid-previews" / media_id
        out = folder / f"{size}-{revision}.webp"
        if out.is_file():
            return out, "image/webp"
        # Only one extra decode at a time across tabs; ordinary originals and
        # edits keep their own request threads and do not take this lock.
        with self._preview_lock:
            if out.is_file():
                return out, "image/webp"
            folder.mkdir(parents=True, exist_ok=True)
            try:
                with Image.open(source) as im:
                    width, height = im.size
                    scale = min(1.0, size / max(1, min(width, height)), 2048 / max(width, height))
                    target = (max(1, round(width * scale)), max(1, round(height * scale)))
                    if im.format == "JPEG":
                        im.draft("RGB", (target[0] * 2, target[1] * 2))
                    im = ImageOps.exif_transpose(im) if ImageOps is not None else im.copy()
                    # Rotation may swap axes; preserve the source proportions.
                    ratio = min(1.0, size / max(1, min(im.size)), 2048 / max(im.size))
                    bounds = (max(1, round(im.width * ratio)), max(1, round(im.height * ratio)))
                    im.thumbnail(bounds, Image.Resampling.LANCZOS, reducing_gap=3.0)
                    if im.mode not in ("RGB", "RGBA"):
                        im = im.convert("RGBA" if "transparency" in im.info else "RGB")
                    tmp = out.with_suffix(".tmp")
                    im.save(tmp, "WEBP", quality=90, method=1)
                    os.replace(tmp, out)
                # Replace only obsolete revisions of this regenerable cache.
                for old in folder.glob("*.webp"):
                    if not old.name.endswith(f"-{revision}.webp"):
                        try:
                            old.unlink()
                        except OSError:
                            pass
                return out, "image/webp"
            except Exception:
                return self.media_path(media_id, thumb=True)

    def media_quality(self, media_id: str) -> dict[str, Any]:
        """Return lightweight source-size metadata for the selected media item."""
        with self.lock:
            item = self.media_item(media_id)
            if not item:
                raise KeyError("Media not found")
            source = self.root / str(item.get("stored_rel") or "")
            media_type = str(item.get("media_type") or "image")
        if not source.exists():
            raise FileNotFoundError("Media file not found")
        result: dict[str, Any] = {
            "media_id": media_id,
            "media_type": media_type,
            "file_bytes": source.stat().st_size,
            "width": None,
            "height": None,
        }
        if media_type == "image" and Image is not None:
            try:
                with Image.open(source) as image:
                    result["width"], result["height"] = image.size
            except Exception:
                pass
        return result

    def metadata_index_status(self) -> dict[str, Any]:
        with self.lock:
            return dict(self._metadata_index)

    def start_metadata_index(self, character_id: str | None = None, scan_quality: bool = False) -> dict[str, Any]:
        """Index existing source headers only when the user asks to sort by size."""
        with self.lock:
            if self._metadata_index_worker is not None and self._metadata_index_worker.is_alive():
                return dict(self._metadata_index)
            jobs = [
                (str(m.get("id") or ""), str(m.get("stored_rel") or ""), str(m.get("media_type") or "image"))
                for m in self.data.get("media", [])
                if m.get("stored_rel") and (not character_id or m.get("character_id") == character_id) and (
                    scan_quality or m.get("file_bytes") is None or
                    (m.get("media_type") == "image" and (m.get("width") is None or m.get("height") is None))
                )
            ]
            self._metadata_index = {"running": bool(jobs), "total": len(jobs), "processed": 0, "updated": 0}
            if not jobs:
                return dict(self._metadata_index)
            self._metadata_index_worker = threading.Thread(
                target=self._run_metadata_index, args=(jobs,), name="nai-metadata-index", daemon=True,
            )
            self._metadata_index_worker.start()
            return dict(self._metadata_index)

    def _run_metadata_index(self, jobs: list[tuple[str, str, str]]) -> None:
        dirty = False
        try:
            for position, (media_id, stored_rel, media_type) in enumerate(jobs, start=1):
                source = (self.root / stored_rel).resolve()
                file_bytes = width = height = None
                try:
                    if source.exists() and self.root.resolve() in source.parents:
                        file_bytes = source.stat().st_size
                        if media_type == "image" and Image is not None:
                            # Image.open reads headers; it does not fully decode the source.
                            with Image.open(source) as image:
                                width, height = image.size
                except Exception:
                    pass
                with self.lock:
                    item = self.media_item(media_id)
                    changed = False
                    if item and item.get("stored_rel") == stored_rel:
                        if file_bytes is not None and item.get("file_bytes") != file_bytes:
                            item["file_bytes"] = file_bytes; changed = True
                        if width and height and (item.get("width") != width or item.get("height") != height):
                            item["width"] = width; item["height"] = height; changed = True
                        changed = self._apply_resolution_flag(item) or changed
                    dirty = dirty or changed
                    self._metadata_index["processed"] = position
                    if changed:
                        self._metadata_index["updated"] += 1
                    # Persist in batches, so a large library never performs one database
                    # rewrite per item and interruption still leaves useful progress.
                    if dirty and (position % 100 == 0 or position == len(jobs)):
                        self.save(); dirty = False
                time.sleep(0.003)
        finally:
            with self.lock:
                if dirty:
                    self.save()
                self._metadata_index["running"] = False

    def quality_settings(self) -> dict[str, Any]:
        with self.lock:
            return {"enabled": True, "min_pixels": 500000, **self.data.get("quality_settings", {})}

    def set_quality_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        threshold = body.get("min_pixels", 500000)
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 10000 <= threshold <= 100000000:
            raise ValueError("Threshold must be between 0.01 and 100 megapixels")
        if not isinstance(body.get("enabled", True), bool):
            raise ValueError("Enabled must be true or false")
        with self.lock:
            self.data["quality_settings"] = {"enabled": body.get("enabled", True), "min_pixels": threshold}
            self.save()
            return self.quality_settings()

    def _apply_resolution_flag(self, item: dict[str, Any]) -> bool:
        if item.get("media_type") != "image" or not item.get("width") or not item.get("height"):
            return False
        if item.get("replacement_override_sha") and item.get("replacement_override_sha") == item.get("sha256"):
            return False
        settings = self.quality_settings()
        low = settings["enabled"] and item["width"] * item["height"] < settings["min_pixels"]
        if low and not item.get("needs_replacement"):
            item["needs_replacement"] = True
            item["replacement_auto"] = True
            return True
        if not low and item.get("replacement_auto"):
            item["needs_replacement"] = False
            item["replacement_auto"] = False
            return True
        return False

    def character_stats(self, character_id: str) -> dict[str, Any]:
        with self.lock:
            character = self.character(character_id)
            if not character:
                raise KeyError("Character not found")
            media = [m for m in self.data["media"] if m.get("character_id") == character_id]
            sets = [g for g in self.data.get("sets", []) if g.get("character_id") == character_id and g.get("kind", "set") == "set"]
            in_sets = {id for group in sets for id in group.get("media_ids", [])}
            saved = [m for m in media if not m.get("in_review") and not m.get("in_purgatory")]
            def counts(items):
                return {"images": sum(m.get("media_type") == "image" for m in items),
                        "videos": sum(m.get("media_type") == "video" for m in items)}
            return {"name": character["name"], "saved": counts(saved),
                    "in_sets": counts([m for m in saved if m["id"] in in_sets]),
                    "outside_sets": counts([m for m in saved if m["id"] not in in_sets]),
                    "pending": counts([m for m in media if m.get("in_review") or m.get("in_purgatory")]),
                    "sets": len(sets), "needs_replacement": sum(bool(m.get("needs_replacement")) for m in saved),
                    "image_bytes": sum(m.get("file_bytes") or 0 for m in media if m.get("media_type") == "image"),
                    "video_bytes": sum(m.get("file_bytes") or 0 for m in media if m.get("media_type") == "video"),
                    "unknown_sizes": sum(m.get("file_bytes") is None for m in media)}


class StandaloneUI:
    """Download the verified standalone document on demand; keep an offline copy."""
    BASE = "https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/"

    def __init__(self, root: Path):
        self.directory = root / ".ui-cache"
        self.lock = threading.Lock()
        self.checked_at = 0.0
        self.cached: bytes | None = None

    def _download(self, url: str, limit: int, timeout: int = 20) -> bytes:
        if not url.startswith(self.BASE):
            raise ValueError("Untrusted standalone payload URL")
        request = urllib.request.Request(url, headers={"User-Agent": "NovelAI-Media-Library", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Standalone payload is too large")
        return data

    def document(self, force: bool = False) -> bytes:
        with self.lock:
            cached_path = self.directory / "standalone.json"
            if self.cached is None and cached_path.exists():
                try:
                    saved = json.loads(cached_path.read_text(encoding="utf-8"))
                    body = base64.b64decode(saved["body"], validate=True)
                    if hashlib.sha256(body).hexdigest() == saved["sha256"]:
                        self.cached = body
                except Exception:
                    pass
            if not force and self.cached is not None and time.monotonic() - self.checked_at < 60:
                return self.cached
            try:
                manifest = json.loads(self._download(self.BASE + "manifest.json?_=" + str(time.time_ns()), 256 * 1024, 8))
                url, digest = manifest.get("standalone_url", ""), manifest.get("standalone_sha256", "")
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("The standalone update is not available yet. Please retry shortly.")
                if self.cached is None or hashlib.sha256(self.cached).hexdigest() != digest:
                    body = self._download(url, 12 * 1024 * 1024)
                    if hashlib.sha256(body).hexdigest() != digest:
                        raise ValueError("Standalone download verification failed")
                    self.directory.mkdir(parents=True, exist_ok=True)
                    temp = cached_path.with_suffix(".tmp")
                    temp.write_text(json.dumps({"sha256": digest, "body": base64.b64encode(body).decode("ascii")}), encoding="utf-8")
                    os.replace(temp, cached_path)
                    self.cached = body
            except Exception:
                if force or self.cached is None:
                    raise
            self.checked_at = time.monotonic()
            return self.cached


class UIUpdates:
    """On-demand verified downloads; idle clients wait on a condition, not GitHub."""
    def __init__(self, standalone: StandaloneUI):
        self.standalone = standalone
        self.condition = threading.Condition()
        self.check_lock = threading.Lock()
        self.checked_at = 0.0
        self.version = ""
        self.code = ""
        self.digest = ""
        self.activation = ""
        self.cursor = uuid.uuid4().hex
        self.error = ""

    def status(self, after: str | None = None) -> dict[str, Any]:
        with self.condition:
            if after == self.cursor:
                self.condition.wait_for(lambda: after != self.cursor, timeout=25)
            return {"version": self.version, "activation": self.activation, "cursor": self.cursor, "error": self.error}

    def _notify(self) -> None:
        with self.condition:
            self.cursor = uuid.uuid4().hex
            self.condition.notify_all()

    def check(self, force: bool = False) -> dict[str, Any]:
        with self.check_lock:
            if not force and self.version and time.monotonic() - self.checked_at < 60:
                return self.status()
            ui = self.standalone
            try:
                manifest = json.loads(ui._download(ui.BASE + "manifest.json?_=" + str(time.time_ns()), 256 * 1024, 10))
                version = str(manifest.get("userscript_payload_version", ""))
                standalone_version = str(manifest.get("standalone_version", version))
                digest = str(manifest.get("userscript_sha256", ""))
                html_digest = str(manifest.get("standalone_sha256", ""))
                parts = manifest.get("userscript_parts", [])
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", version) or not re.fullmatch(r"[0-9a-f]{64}", digest) or not re.fullmatch(r"[0-9a-f]{64}", html_digest) or not isinstance(parts, list) or not 1 <= len(parts) <= 80:
                    raise ValueError("Invalid interface release manifest")
                if version == self.version and digest == self.digest and html_digest == getattr(self, 'html_digest', None):
                    self.checked_at = time.monotonic()
                    return self.status()
                cache = ui.directory / "coordinated-update.json"
                code_bytes = None
                if cache.exists():
                    try:
                        saved = json.loads(cache.read_text(encoding="utf-8"))
                        candidate = saved["code"].encode("utf-8")
                        if hashlib.sha256(candidate).hexdigest() == digest:
                            code_bytes = candidate
                    except Exception:
                        pass
                if code_bytes is None:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        code_bytes = b"".join(pool.map(lambda url: ui._download(url, 4 * 1024 * 1024), parts))
                if hashlib.sha256(code_bytes).hexdigest() != digest:
                    raise ValueError("Interface verification failed; current version kept")
                html = ui._download(manifest.get("standalone_url", ""), 12 * 1024 * 1024)
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", standalone_version) or hashlib.sha256(html).hexdigest() != html_digest or f'data-nai-media-payload-version="{standalone_version}"'.encode() not in html:
                    raise ValueError("Standalone verification failed; current version kept")
                code = code_bytes.decode("utf-8")
                ui.directory.mkdir(parents=True, exist_ok=True)
                temp = cache.with_suffix(".tmp")
                temp.write_text(json.dumps({"code": code}), encoding="utf-8")
                os.replace(temp, cache)
                with ui.lock:
                    path = ui.directory / "standalone.json"
                    temp = path.with_suffix(".tmp")
                    temp.write_text(json.dumps({"sha256": html_digest, "body": base64.b64encode(html).decode("ascii")}), encoding="utf-8")
                    os.replace(temp, path)
                    ui.cached = html
                    ui.checked_at = time.monotonic()
                with self.condition:
                    self.code, self.digest, self.version = code, digest, version
                    self.html_digest = html_digest
                    self.error = ""
                    # An activation always refers to the version prepared at the time.
                    self.activation = ""
                    self.checked_at = time.monotonic()
                    self._notify()
            except Exception as error:
                with self.condition:
                    self.error = str(error)
                    self._notify()
                raise
            return self.status()

    def activate(self, version: str) -> dict[str, Any]:
        with self.condition:
            if not self.code or version != self.version:
                raise ValueError("The requested update is not prepared. Check for updates again.")
            self.activation = uuid.uuid4().hex
            self._notify()
            return self.status()

    def payload(self) -> dict[str, str]:
        with self.condition:
            if not self.code:
                raise ValueError("No verified update is ready")
            return {"version": self.version, "code": self.code, "sha256": self.digest}


class MediaHandler(BaseHTTPRequestHandler):
    server_version = "NovelAIMedia/1.0"

    @property
    def store(self) -> LibraryStore:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep the GUI quiet; errors are returned to the caller.
        return

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed = urllib.parse.urlparse(origin)
        except Exception:
            return False
        return (parsed.scheme == "https" and parsed.hostname in {"novelai.net", "www.novelai.net"}) or origin in {
            f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"
        }

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin and self._origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")

    def _send_json(self, status: int, obj: Any) -> None:
        body = json_bytes(obj)
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 24 * 1024 * 1024:
            raise ValueError("JSON request is too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def _read_raw(self, max_bytes: int = 24 * 1024 * 1024) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > max_bytes:
            raise ValueError("Request body is empty or too large")
        return self.rfile.read(length)

    def _read_multipart(self) -> dict[str, list[tuple[str | None, bytes, str | None]]]:
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            raise ValueError("Expected multipart/form-data")
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 600 * 1024 * 1024:
            raise ValueError("Upload size is invalid or exceeds 600 MB")
        body = self.rfile.read(length)
        header = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        msg = BytesParser(policy=email_policy).parsebytes(header + body)
        result: dict[str, list[tuple[str | None, bytes, str | None]]] = {}
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            content_type = part.get_content_type()
            result.setdefault(name, []).append((filename, payload, content_type))
        return result

    def _field_text(self, fields: dict[str, list[tuple[str | None, bytes, str | None]]], name: str, default: str = "") -> str:
        values = fields.get(name)
        if not values:
            return default
        return values[0][1].decode("utf-8", errors="replace")

    def _send_file_with_range(self, file_path: Path, content_type: str, preview_name: str | None = None) -> None:
        size = file_path.stat().st_size
        range_header = self.headers.get("Range", "")
        start = 0
        end = size - 1
        partial = False

        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match:
                self.send_response(416)
                self._cors()
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            start_text, end_text = match.groups()
            if not start_text and not end_text:
                self.send_response(416)
                self._cors()
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if start_text:
                start = int(start_text)
                end = int(end_text) if end_text else size - 1
            else:
                suffix = int(end_text)
                if suffix <= 0:
                    self.send_response(416)
                    self._cors()
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                suffix = min(suffix, size)
                start = size - suffix
                end = size - 1

            if start >= size or start < 0 or end < start:
                self.send_response(416)
                self._cors()
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            end = min(end, size - 1)
            partial = True

        length = max(0, end - start + 1)
        self.send_response(206 if partial else 200)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store" if preview_name is not None else "private, max-age=86400")
        if preview_name is not None:
            self.send_header("X-NovelAI-Filename", urllib.parse.quote(preview_name, safe=""))
        self.end_headers()

        if self.command == "HEAD" or length <= 0:
            return

        with file_path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    def do_HEAD(self) -> None:
        try:
            path = urllib.parse.urlparse(self.path).path
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/(?:(thumb)|(original))", path)
            if not match:
                self.send_response(404)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            media_id = match.group(1)
            thumb = bool(match.group(2))
            file_path, content_type = self.store.media_path(media_id, thumb=thumb)
            self._send_file_with_range(file_path, content_type)
        except Exception:
            self.send_response(500)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_OPTIONS(self) -> None:
        if not self._origin_allowed():
            self.send_error(403)
            return
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        try:
            path = urllib.parse.urlparse(self.path).path
            if path in {"/", "/library", "/library/"}:
                # Bind the UI to loopback, including its browser Origin. Never serve
                # executable library pages to arbitrary Host names (DNS rebinding).
                if self.headers.get("Host") not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
                    self._send_json(403, {"error": "Host not allowed"})
                    return
                if self.headers.get("Host") == f"localhost:{self.server.server_port}":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/library/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                try:
                    body = self.server.standalone.document()
                    status = 200
                except Exception:
                    status = 503
                    body = b'''<!doctype html><meta charset="utf-8"><title>NovelAI Media Library</title>
                    <body style="background:#11142c;color:#eee;font:16px system-ui;padding:40px">
                    <h2>The standalone library could not load yet.</h2>
                    <p>Keep the companion running. The first launch needs internet access to download the interface.</p>
                    <p>If the update was just published, wait a moment and retry.</p><a href="/library/" style="color:#bcb5ff">Retry</a></body>'''
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/rapid-review":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self._send_json(200, self.store.rapid_queue(query.get('character_id', [''])[0]))
                return
            if path == "/api/sets/match-status":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self._send_json(200, self.store.outfit_matcher.status(query.get("id", [""])[0]))
                return
            if path == "/api/sets/matching-preferences":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self._send_json(200, self.store.matching_preferences(query.get('character_id', [''])[0]))
                return
            if path == "/api/ui-update/status":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self._send_json(200, self.server.ui_updates.status(query.get("after", [None])[0]))
                return
            if path == "/api/ui-update/payload":
                self._send_json(200, self.server.ui_updates.payload())
                return
            if path == "/api/quality/settings":
                self._send_json(200, self.store.quality_settings())
                return
            match = re.fullmatch(r"/api/characters/([0-9a-f]+)/stats", path)
            if match:
                self._send_json(200, self.store.character_stats(match.group(1)))
                return
            if path == "/api/library/revision":
                with self.store.lock:
                    self._send_json(200, {"revision": self.store.revision})
                return
            if path == "/api/health":
                self._send_json(200, {"ok": True, "version": API_VERSION, "duplicate_review": 1, "standalone_library": True, "coordinated_updates": True, "independent_updates": True, "set_categories": True, "set_removal": True, "set_preferences": True, "character_profiles": True, "image_set_battles": True, "outfit_matching": True, "outfit_library_scan": True, "photoshoot_matching": True, "persistent_rapid_review": True, "set_examples": True, "resolution_flags": True, "mixed_collections": True, "video_set_only": True, "chunked_uploads": True, "automatic_video_thumbnails": True, "undo_history": True, "replacement_flags": True, "featured_flags": True, "library_root": str(self.store.root)})
                return
            if path == "/api/duplicate-review/catalog":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self._send_json(200, self.store.duplicate_catalog(query.get("character_id", [""])[0]))
                return
            if path == "/api/duplicate-review/item":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self._send_json(200, self.store.duplicate_item(query.get("media_id", [""])[0], query.get("library_id", [""])[0]))
                return
            if path == "/api/duplicate-review/operation":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self._send_json(200, self.store.duplicate_operation(query.get("operation", [""])[0], query.get("library_id", [""])[0]))
                return
            if path == "/api/diagnostics/last-import":
                payload = dict(self.store.last_import_debug) if self.store.last_import_debug else {"state": "none"}
                self._send_json(200, payload)
                return
            if path == "/api/diagnostics/performance":
                self._send_json(200, self.store.performance_probe())
                return
            if path == "/api/undo":
                self._send_json(200, self.store.undo_history())
                return
            if path == "/api/library":
                self._send_json(200, self.store.public_library())
                return
            if path == "/api/media/metadata-index":
                self._send_json(200, self.store.metadata_index_status())
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/quality", path)
            if match:
                self._send_json(200, self.store.media_quality(match.group(1)))
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/(?:(thumb)|(original))", path)
            if match:
                media_id = match.group(1)
                thumb = bool(match.group(2))
                requested = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("size", ["0"])[0]
                size = int(requested) if str(requested).isdigit() else 0
                if thumb and size > 0 and not self.store.rapid_item(media_id):
                    file_path, content_type = self.store.grid_preview(media_id, size)
                else:
                    file_path, content_type = self.store.media_path(media_id, thumb=thumb)
                self._send_file_with_range(file_path, content_type)
                return
            self._send_json(404, {"error": "Not found"})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        if not self._origin_allowed():
            self._send_json(403, {"error": "Origin not allowed"})
            return
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/duplicate-review/replace":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                field = lambda key: query.get(key, [""])[0]
                self._send_json(200, self.store.duplicate_replace(self._read_raw(256 * 1024 * 1024), field("name"),
                    field("media_id"), field("expected_sha"), field("operation"), field("library_id")))
                return
            if path == "/api/duplicate-review/undo":
                body = self._read_json()
                self._send_json(200, self.store.duplicate_undo(str(body.get("operation", "")), str(body.get("library_id", ""))))
                return
            if path in {"/api/duplicate-review/cleanup", "/api/duplicate-review/cleanup-status", "/api/duplicate-review/cleanup-undo"}:
                body = self._read_json()
                args = (str(body.get("operation", "")), str(body.get("library_id", "")))
                if path.endswith("cleanup-status"):
                    result = self.store.duplicate_cleanup_status(*args)
                elif path.endswith("cleanup-undo"):
                    result = self.store.duplicate_cleanup_undo(*args)
                else:
                    result = self.store.duplicate_cleanup(*args, body.get("selection"))
                self._send_json(200, result)
                return
            if path == "/api/standalone/check":
                body = self.server.standalone.document(force=True)
                version = re.search(rb'data-nai-media-payload-version="([0-9.]+)"', body)
                if not version:
                    raise ValueError("Standalone version is missing")
                self._send_json(200, {"version": version.group(1).decode("ascii")})
                return
            if path == "/api/set-categories":
                body = self._read_json()
                self._send_json(200, self.store.add_set_category(str(body.get("character_id", "")), str(body.get("name", ""))))
                return
            match = re.fullmatch(r"/api/set-categories/([0-9a-f]+)", path)
            if match:
                body = self._read_json()
                self._send_json(200, self.store.edit_set_category(match.group(1), str(body.get("name", ""))))
                return
            if path == "/api/ui-update/check":
                body = self._read_json()
                self._send_json(200, self.server.ui_updates.check(body.get("force") is True))
                return
            if path == "/api/ui-update/activate":
                body = self._read_json()
                self._send_json(200, self.server.ui_updates.activate(str(body.get("version", ""))))
                return
            if path in {"/api/collection/state", "/api/collection/save", "/api/collection/frame", "/api/collection/review", "/api/collection/captain", "/api/collection/title", "/api/collection/title-correction"}:
                self._send_json(200, self.store.collection_request(path.rsplit("/", 1)[1], self._read_json()))
                return
            if path in {"/api/profile/state", "/api/profile/save"}:
                self._send_json(200, self.store.profile_request(path.rsplit("/", 1)[1], self._read_json()))
                return
            if path in {"/api/battles/state", "/api/battles/start", "/api/battles/vote", "/api/battles/undo", "/api/battles/place", "/api/battles/resume", "/api/battles/summary", "/api/battles/history", "/api/battles/cards", "/api/battles/seen", "/api/battles/challenge"}:
                self._send_json(200, self.store.battles.request(path.rsplit("/",1)[1], self._read_json()))
                return
            removal_match=re.fullmatch(r"/api/media/([0-9a-f]+)/removal-flag",path)
            if removal_match:
                self._send_json(200,self.store.set_removal_flag(removal_match.group(1),self._read_json().get('flagged')))
                return
            if path == "/api/quality/settings":
                self._send_json(200, self.store.set_quality_settings(self._read_json()))
                return
            if path == "/api/quality/scan":
                body = self._read_json()
                cid = str(body.get("character_id", ""))
                if not self.store.character(cid):
                    raise ValueError("Choose a character")
                self._send_json(200, self.store.start_metadata_index(cid, True))
                return
            if path == "/api/undo":
                body = self._read_json()
                self._send_json(200, self.store.undo_last(str(body.get("entry_id", ""))))
                return
            if path == "/api/undo/clear":
                body = self._read_json()
                self._send_json(200, self.store.clear_undo_history(str(body.get("entry_id", ""))))
                return
            if path == "/api/media/metadata-index":
                self._read_json()
                self._send_json(200, self.store.start_metadata_index())
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/needs-replacement", path)
            if match:
                body = self._read_json()
                self._send_json(200, self.store.set_needs_replacement(match.group(1), bool(body.get("needs_replacement"))))
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/featured", path)
            if match:
                body = self._read_json()
                self._send_json(200, self.store.set_featured(match.group(1), bool(body.get("featured"))))
                return
            if path == "/api/characters":
                body = self._read_json()
                self._send_json(200, self.store.add_character(str(body.get("name", ""))))
                return
            if path == "/api/rapid-review/state":
                self._send_json(200, self.store.rapid_state(self._read_json()))
                return
            if path == "/api/rapid-review/resolve":
                self._send_json(200, self.store.resolve_rapid(self._read_json()))
                return
            if path == "/api/categories/ghost":
                body = self._read_json()
                self._send_json(200, self.store.set_category_ghost(str(body.get('category_id', '')), body.get('ghost')))
                return
            if path == "/api/categories/order":
                body = self._read_json()
                self._send_json(200, self.store.reorder_categories(str(body.get('character_id', '')), body.get('media_type'), body.get('category_ids')))
                return
            if path == "/api/sets/order":
                body = self._read_json()
                self._send_json(200, self.store.reorder_set(str(body.get('set_id', '')), body.get('media_ids')))
                return
            if path == "/api/categories":
                body = self._read_json()
                self._send_json(200, self.store.add_category(str(body.get("character_id", "")), str(body.get("name", "")), str(body.get("media_type", "image"))))
                return
            match = re.fullmatch(r"/api/categories/([0-9a-f]+)", path)
            if match:
                body = self._read_json()
                self._send_json(200, self.store.rename_category(match.group(1), str(body.get("name", ""))))
                return
            if path == "/api/sets/scan":
                self._send_json(200, self.store.outfit_matcher.start(self._read_json(), scan=True))
                return
            if path == "/api/sets/matching-preferences":
                body = self._read_json()
                if 'mode' not in body or body['mode'] is None:
                    raise ValueError('Choose Outfit or Photoshoot matching.')
                self._send_json(200, self.store.matching_preferences(str(body.get('character_id', '')), body['mode']))
                return
            if path == "/api/sets/match-cancel":
                self._send_json(200, self.store.outfit_matcher.cancel(str(self._read_json().get('id', ''))))
                return
            if path == "/api/sets/scan-assign":
                self._send_json(200, self.store.outfit_matcher.assign_scan(self._read_json()))
                return
            if path == "/api/sets/matching-create":
                self._send_json(200, self.store.outfit_matcher.create_from_matches(self._read_json()))
                return
            if path == "/api/sets/find-matches":
                self._send_json(200, self.store.outfit_matcher.start(self._read_json()))
                return
            if path == "/api/sets/categories-bulk":
                body = self._read_json()
                self._send_json(200, self.store.bulk_set_categories(str(body.get("character_id", "")), body.get("set_ids"), body.get("categories"), str(body.get("action", ""))))
                return
            if path == "/api/sets":
                body = self._read_json()
                item = self.store.create_set(
                    str(body.get("character_id", "")),
                    str(body.get("name", "")),
                    list(body.get("media_ids", [])) if isinstance(body.get("media_ids", []), list) else [],
                    body.get("cover_media_id"),
                    str(body.get("kind", "set")),
                    bool(body.get("preserve_placement", False)),
                    body.get("cover_source"),
                    body.get("categories"),
                    body.get("aliases"), body.get("colors"), body.get("notes"),
                )
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/sets/([0-9a-f]+)", path)
            if match:
                body = self._read_json()
                item = self.store.update_set(
                    match.group(1),
                    body.get("name") if "name" in body else None,
                    body.get("media_ids") if "media_ids" in body else None,
                    body.get("cover_media_id") if "cover_media_id" in body else None,
                    bool(body.get("preserve_placement", False)),
                    body.get("add_media_ids"),
                    body.get("cover_source"),
                    body.get("favorite"),
                    body.get("categories"),
                    body.get("remove_media_ids"),
                    body.get("aliases"), body.get("colors"), body.get("notes"),
                )
                self._send_json(200, item)
                return
            if path == "/api/preview/url":
                body = self._read_json()
                temp, filename, content_type = self.store.download_url_preview(str(body.get("url", "")).strip())
                try:
                    self._send_file_with_range(temp, content_type, preview_name=filename)
                finally:
                    temp.unlink(missing_ok=True)
                return
            upload = re.fullmatch(r"/api/import/chunked/([A-Za-z0-9_-]{16,96})/(start|chunk|finish|cancel)", path)
            if upload:
                body = self._read_json()
                if not isinstance(body, dict):
                    raise ValueError("Expected upload object")
                self._send_json(200, self.store.chunk_upload(upload.group(1), upload.group(2), body))
                return
            if path == "/api/import/file":
                import_started = time.perf_counter()
                fields = self._read_multipart()
                multipart_done = time.perf_counter()
                character_id = self._field_text(fields, "character_id")
                categories = json.loads(self._field_text(fields, "categories", "[]"))
                files = fields.get("file", [])
                if len(files) != 1:
                    raise ValueError("Exactly one file must be uploaded per request")
                filename, payload, content_type = files[0]
                if not filename:
                    raise ValueError("Uploaded file has no filename")
                if not (content_type or "").startswith(("image/", "video/")):
                    guessed, _ = mimetypes.guess_type(filename)
                    content_type = guessed or content_type
                if not (content_type or "").startswith(("image/", "video/")):
                    raise ValueError("Only image and video files are supported")
                source_url = self._field_text(fields, "source_url").strip()
                if source_url and urllib.parse.urlparse(source_url).scheme not in ("http", "https"):
                    raise ValueError("Only http:// and https:// source URLs are supported")
                item, duplicate, backend_timing = self.store.import_bytes_profiled(
                    payload,
                    filename,
                    character_id,
                    list(categories) if isinstance(categories, list) else [],
                    {"kind": "url", "url": source_url} if source_url else {"kind": "local", "original_name": filename},
                    content_type,
                )
                finished = time.perf_counter()
                debug_timing = {
                    "multipart": round((multipart_done - import_started) * 1000, 1),
                    **backend_timing,
                    "server_total": round((finished - import_started) * 1000, 1),
                }
                self.store.last_import_debug = {
                    "state": "done",
                    "recorded_at_epoch_ms": int(time.time() * 1000),
                    "filename": filename,
                    "file_bytes": len(payload),
                    "duplicate": bool(duplicate),
                    "debug_timing_ms": debug_timing,
                    "library_root": str(self.store.root),
                }
                self._send_json(200, {
                    "item": item,
                    "duplicate": duplicate,
                    "debug_timing_ms": debug_timing,
                })
                return
            if path == "/api/import/url":
                body = self._read_json()
                item, duplicate = self.store.import_url(
                    str(body.get("url", "")).strip(),
                    str(body.get("character_id", "")),
                    list(body.get("categories", [])) if isinstance(body.get("categories", []), list) else [],
                )
                self._send_json(200, {"item": item, "duplicate": duplicate})
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/replace", path)
            if match:
                fields = self._read_multipart()
                files = fields.get("file", [])
                if len(files) != 1:
                    raise ValueError("Exactly one image must be selected")
                filename, payload, content_type = files[0]
                if not filename:
                    raise ValueError("Replacement image has no filename")
                if not (content_type or "").startswith("image/"):
                    guessed, _ = mimetypes.guess_type(filename)
                    content_type = guessed or content_type
                if not (content_type or "").startswith("image/"):
                    raise ValueError("Only image files are supported for source replacement")
                item = self.store.replace_media_bytes(payload, filename, match.group(1), content_type)
                self._send_json(200, item)
                return
            if path == "/api/backup":
                dst = self.store.manual_backup()
                self._send_json(200, {"ok": True, "path": str(dst)})
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/categories", path)
            if match:
                body = self._read_json()
                item = self.store.set_categories(match.group(1), list(body.get("categories", [])), body.get("in_all") if "in_all" in body else None, body.get("in_videos") if "in_videos" in body else None)
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/favorite", path)
            if match:
                body = self._read_json()
                item = self.store.set_favorite(match.group(1), bool(body.get("favorite")))
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/clear-holding", path)
            if match:
                self._read_json()
                self._send_json(200,self.store.clear_holding(match.group(1)))
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/review", path)
            if match:
                body = self._read_json()
                item = self.store.set_review(match.group(1), bool(body.get("in_review")))
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/purgatory", path)
            if match:
                body = self._read_json()
                item = self.store.set_purgatory(match.group(1), bool(body.get("in_purgatory")))
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/crop", path)
            if match:
                body = self._read_json()
                item = self.store.set_crop(match.group(1), body.get("top", 0.0), body.get("bottom", 0.0))
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/thumbnail", path)
            if match:
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                seconds_text = (query.get("seconds") or [None])[0]
                seconds = float(seconds_text) if seconds_text not in (None, "") else None
                content_type = (self.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
                payload = self._read_raw()
                automatic = (query.get("automatic") or ["0"])[0] == "1"
                item = self.store.set_video_thumbnail_bytes(match.group(1), payload, content_type, seconds, automatic)
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/video-meta", path)
            if match:
                body = self._read_json()
                item = self.store.set_video_meta(match.group(1), body.get("thumb_seconds"), body.get("markers"))
                self._send_json(200, item)
                return
            self._send_json(404, {"error": "Not found"})
        except (ValueError, KeyError, FileNotFoundError) as exc:
            self._send_json(400, {"error": str(exc).strip("'\"")})
        except Exception as exc:
            traceback.print_exc()
            self._send_json(500, {"error": str(exc)})

    def do_DELETE(self) -> None:
        if not self._origin_allowed():
            self._send_json(403, {"error": "Origin not allowed"})
            return
        try:
            path = urllib.parse.urlparse(self.path).path
            match = re.fullmatch(r"/api/characters/([0-9a-f]+)", path)
            if match:
                result = self.store.delete_character(match.group(1))
                self._send_json(200, result)
                return
            match = re.fullmatch(r"/api/categories/([0-9a-f]+)", path)
            if match:
                result = self.store.delete_category(match.group(1))
                self._send_json(200, result)
                return
            match = re.fullmatch(r"/api/set-categories/([0-9a-f]+)", path)
            if match:
                self._send_json(200, self.store.edit_set_category(match.group(1)))
                return
            match = re.fullmatch(r"/api/sets/([0-9a-f]+)", path)
            if match:
                result = self.store.delete_set(match.group(1))
                self._send_json(200, result)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)", path)
            if match:
                self.store.delete_media(match.group(1))
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"error": "Not found"})
        except (ValueError, KeyError, FileNotFoundError) as exc:
            self._send_json(400, {"error": str(exc).strip("'\"")})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})


class MediaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    # Older Python versions default to five pending connections. UI metadata, media,
    # and thumbnail bursts must not overflow that backlog and wait for TCP retries.
    request_queue_size = 128

    def __init__(self, address: tuple[str, int], store: LibraryStore):
        super().__init__(address, MediaHandler)
        self.store = store
        self.standalone = StandaloneUI(store.root)
        self.ui_updates = UIUpdates(self.standalone)
        store.cleanup_upload_orphans()


def open_folder(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')


def run_gui(server: MediaHTTPServer, store: LibraryStore) -> None:
    import tkinter as tk
    from tkinter import messagebox

    thread = threading.Thread(target=server.serve_forever, name="media-http", daemon=True)
    thread.start()

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("520x290")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=18, pady=18)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w")
    tk.Label(frame, text=f"Running locally on http://{HOST}:{PORT}", font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 2))
    tk.Label(frame, text="Keep this open while you use the NovelAI media viewer.", font=("Segoe UI", 10)).pack(anchor="w")
    tk.Label(frame, text=f"Library: {store.root}", font=("Segoe UI", 9), wraplength=480, justify="left").pack(anchor="w", pady=(8, 12))

    buttons = tk.Frame(frame)
    buttons.pack(fill="x")

    tk.Button(buttons, text="Open Library Folder", width=20, command=lambda: open_folder(store.root)).pack(side="left", padx=(0, 8))

    def backup() -> None:
        try:
            dst = store.manual_backup()
            messagebox.showinfo(APP_NAME, f"Metadata backup created:\n{dst}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    tk.Button(buttons, text="Backup Metadata Now", width=20, command=backup).pack(side="left")

    def close() -> None:
        try:
            server.shutdown()
            server.server_close()
        finally:
            root.destroy()

    tk.Button(frame, text="Open Library Tab", width=20, command=lambda: webbrowser.open_new_tab(f"http://{HOST}:{PORT}/library/")).pack(anchor="w", pady=(12, 0))

    tk.Button(frame, text="Stop & Exit", width=18, command=close).pack(anchor="e", pady=(22, 0))
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--headless", action="store_true", help="Run without the small control window")
    parser.add_argument("--root", type=Path, default=default_library_root(), help="Override the media library folder")
    args = parser.parse_args()

    store = LibraryStore(args.root.expanduser().resolve())
    try:
        server = MediaHTTPServer((HOST, PORT), store)
    except OSError as exc:
        message = f"Could not start {APP_NAME} on {HOST}:{PORT}.\n\n{exc}\n\nAnother copy may already be running."
        if args.headless:
            print(message, file=sys.stderr)
        else:
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk(); root.withdraw(); messagebox.showerror(APP_NAME, message); root.destroy()
            except Exception:
                pass
        raise SystemExit(1)

    if args.headless:
        print(f"{APP_NAME} running at http://{HOST}:{PORT}")
        print(f"Library: {store.root}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    else:
        run_gui(server, store)


if __name__ == "__main__":
    main()
