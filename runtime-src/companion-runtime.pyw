from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
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
API_VERSION = 6


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


class LibraryStore:
    def __init__(self, root: Path):
        self.root = root
        self.media_dir = root / "media"
        self.thumb_dir = root / "thumbnails"
        self.backup_dir = root / "backups"
        self.db_path = root / "library.json"
        self.lock = threading.RLock()
        self.last_import_debug: dict[str, Any] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

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
            changed = False
            for m in data.get("media", []):
                if "favorite" not in m:
                    m["favorite"] = False
                    changed = True
                if "in_review" not in m:
                    m["in_review"] = False
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
                if m.get("media_type") == "video":
                    if m.get("categories"):
                        m["categories"] = []
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

    def save(self) -> None:
        with self.lock:
            self.data["updated_at"] = now_iso()
            self._write_atomic(self.data)

    def manual_backup(self) -> Path:
        with self.lock:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dst = self.backup_dir / f"library-manual-{stamp}.json"
            shutil.copy2(self.db_path, dst)
            return dst

    def public_library(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.data))

    def character(self, character_id: str) -> dict[str, Any] | None:
        return next((c for c in self.data["characters"] if c["id"] == character_id), None)

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

    def add_category(self, character_id: str, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        if name.casefold() == "all":
            raise ValueError("All is automatic and cannot be created as a category")
        with self.lock:
            c = self.character(character_id)
            if not c:
                raise KeyError("Character not found")
            for cat in c["categories"]:
                if cat["name"].casefold() == name.casefold():
                    return cat
            cat = {"id": uuid.uuid4().hex, "name": name, "created_at": now_iso()}
            c["categories"].append(cat)
            self.save()
            return cat

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
            for m in self.data["media"]:
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

    def _validate_categories(self, character_id: str, categories: list[str]) -> list[str]:
        c = self.character(character_id)
        if not c:
            raise KeyError("Character not found")
        valid = {cat["id"] for cat in c["categories"]}
        return [x for x in dict.fromkeys(categories) if x in valid]

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _make_thumbnail(self, original: Path, media_id: str, character_name: str) -> str | None:
        if Image is None:
            return None
        folder = self.thumb_dir / safe_component(character_name, "Character")
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"{media_id}.webp"
        try:
            with Image.open(original) as im:
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
            return out.relative_to(self.root).as_posix()
        except Exception:
            try:
                if out.exists():
                    out.unlink()
            except Exception:
                pass
            return None

    def _queue_image_thumbnail(self, original: Path, media_id: str, character_name: str) -> None:
        # Thumbnail generation is deliberately off the import critical path. Large JPEG/PNG
        # decode + resize can take seconds on some machines; the original media is already
        # safely stored by this point, so Rapid Review should not wait for a 420px thumbnail.
        def worker() -> None:
            # Give the request thread a chance to serialize/flush the successful import first.
            time.sleep(0.10)
            thumb_rel = self._make_thumbnail(original, media_id, character_name)
            if not thumb_rel:
                return
            with self.lock:
                item = self.media_item(media_id)
                if not item:
                    try:
                        (self.root / thumb_rel).unlink(missing_ok=True)
                    except Exception:
                        pass
                    return
                # Do not resurrect/attach a thumbnail to a replaced media record.
                try:
                    expected = original.resolve()
                    current = (self.root / str(item.get("stored_rel") or "")).resolve()
                    if current != expected:
                        return
                except Exception:
                    return
                item["thumb_rel"] = thumb_rel
                self.save()

        threading.Thread(
            target=worker,
            name=f"nai-thumb-{media_id[:8]}",
            daemon=True,
        ).start()

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
    ) -> tuple[dict[str, Any], bool]:
        with self.lock:
            c = self.character(character_id)
            if not c:
                raise KeyError("Character not found")
            categories = self._validate_categories(character_id, categories)
            sha = self._hash_file(temp_path)
            for existing in self.data["media"]:
                if existing.get("character_id") == character_id and existing.get("sha256") == sha:
                    changed = False
                    if existing.get("media_type") == "video":
                        if existing.get("categories"):
                            existing["categories"] = []
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

            media_type = "video" if (content_type or "").startswith("video/") else "image"
            if not content_type:
                guessed_type, _ = mimetypes.guess_type(original_name)
                content_type = guessed_type or "application/octet-stream"
                media_type = "video" if content_type.startswith("video/") else "image"
            if media_type == "video":
                categories = []

            char_folder = self.media_dir / safe_component(c["name"], "Character")
            char_folder.mkdir(parents=True, exist_ok=True)
            stored_name = f"{media_id}_{original_name}"
            destination = char_folder / stored_name
            shutil.move(str(temp_path), destination)

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
                "favorite": False,
                "in_review": False,
                "crop_top": 0.0,
                "crop_bottom": 0.0,
                "sha256": sha,
                "source": source,
                "video_markers": video_markers,
                "video_thumb_seconds": video_thumb_seconds,
                "created_at": now_iso(),
            }
            self.data["media"].append(item)
            self.save()
            if media_type == "image":
                self._queue_image_thumbnail(destination, media_id, c["name"])
            return item, False

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

    def import_url(self, url: str, character_id: str, categories: list[str]) -> tuple[dict[str, Any], bool]:
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
            return self._register_file(
                temp,
                filename,
                character_id,
                categories,
                {"kind": "url", "url": url},
                content_type,
            )
        except Exception:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            raise

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
                raise ValueError("All set images must belong to the selected character")
            if m.get("media_type") != "image":
                raise ValueError("Sets currently support images only")
            seen.add(media_id)
            result.append(media_id)
        if not result:
            raise ValueError("A set must contain at least one image")
        return result

    def _detach_set_members(self, character_id: str, media_ids: list[str], except_set_id: str | None = None) -> None:
        member_ids = set(media_ids)
        kept_sets = []
        for item in self.data.get("sets", []):
            if item.get("character_id") != character_id or item.get("id") == except_set_id:
                kept_sets.append(item)
                continue
            old_members = list(item.get("media_ids", []))
            new_members = [mid for mid in old_members if mid not in member_ids]
            if not new_members:
                continue
            if new_members != old_members:
                item["media_ids"] = new_members
                if item.get("cover_media_id") not in new_members:
                    item["cover_media_id"] = new_members[0]
                item["updated_at"] = now_iso()
            kept_sets.append(item)
        self.data["sets"] = kept_sets

    def create_set(self, character_id: str, name: str, media_ids: list[Any], cover_media_id: Any = None) -> dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            raise ValueError("Set name cannot be empty")
        with self.lock:
            if not self.character(character_id):
                raise KeyError("Character not found")
            for existing in self.data.get("sets", []):
                if existing.get("character_id") == character_id and str(existing.get("name", "")).casefold() == name.casefold():
                    raise ValueError("A set with that name already exists for this character")
            members = self._validate_set_media(character_id, list(media_ids or []))
            self._detach_set_members(character_id, members)
            cover = str(cover_media_id or "")
            if cover not in members:
                cover = members[0]
            stamp = now_iso()
            item = {
                "id": uuid.uuid4().hex,
                "character_id": character_id,
                "name": name,
                "media_ids": members,
                "cover_media_id": cover,
                "created_at": stamp,
                "updated_at": stamp,
            }
            self.data.setdefault("sets", []).append(item)
            self.save()
            return item

    def update_set(self, set_id: str, name: Any = None, media_ids: Any = None, cover_media_id: Any = None) -> dict[str, Any]:
        with self.lock:
            item = self.set_item(set_id)
            if not item:
                raise KeyError("Set not found")
            character_id = str(item.get("character_id", ""))
            next_name = str(item.get("name", "")) if name is None else str(name or "").strip()
            if not next_name:
                raise ValueError("Set name cannot be empty")
            for other in self.data.get("sets", []):
                if other.get("id") == set_id:
                    continue
                if other.get("character_id") == character_id and str(other.get("name", "")).casefold() == next_name.casefold():
                    raise ValueError("A set with that name already exists for this character")
            members = list(item.get("media_ids", [])) if media_ids is None else self._validate_set_media(character_id, list(media_ids or []))
            if media_ids is None:
                members = self._validate_set_media(character_id, members)
            self._detach_set_members(character_id, members, except_set_id=set_id)
            cover = str(item.get("cover_media_id", "")) if cover_media_id is None else str(cover_media_id or "")
            if cover not in members:
                cover = members[0]
            item["name"] = next_name
            item["media_ids"] = members
            item["cover_media_id"] = cover
            item["updated_at"] = now_iso()
            self.save()
            return item

    def delete_set(self, set_id: str) -> dict[str, Any]:
        with self.lock:
            item = self.set_item(set_id)
            if not item:
                raise KeyError("Set not found")
            self.data["sets"] = [s for s in self.data.get("sets", []) if s.get("id") != set_id]
            self.save()
            return {"ok": True, "set_id": set_id}

    def set_categories(self, media_id: str, categories: list[str]) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            m["categories"] = self._validate_categories(m["character_id"], categories)
            self.save()
            return m

    def set_favorite(self, media_id: str, favorite: bool) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            m["favorite"] = bool(favorite)
            self.save()
            return m

    def set_review(self, media_id: str, in_review: bool) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            if m.get("media_type") != "image":
                raise ValueError("Only images can be placed in Review")
            m["in_review"] = bool(in_review)
            self.save()
            return m

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

    def set_video_thumbnail_bytes(self, media_id: str, payload: bytes, content_type: str, seconds: float | None = None) -> dict[str, Any]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            if m.get("media_type") != "video":
                raise ValueError("Selected media is not a video")
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
            if seconds is not None:
                m["video_thumb_seconds"] = max(0.0, float(seconds))
            self.save()
            return m

    def delete_media(self, media_id: str) -> None:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")
            for key in ("stored_rel", "thumb_rel"):
                rel = m.get(key)
                if rel:
                    try:
                        (self.root / rel).unlink(missing_ok=True)
                    except Exception:
                        pass
            self.data["media"] = [x for x in self.data["media"] if x["id"] != media_id]
            kept_sets = []
            for item in self.data.get("sets", []):
                members = [mid for mid in item.get("media_ids", []) if mid != media_id]
                if not members:
                    continue
                item["media_ids"] = members
                if item.get("cover_media_id") not in members:
                    item["cover_media_id"] = members[0]
                item["updated_at"] = now_iso()
                kept_sets.append(item)
            self.data["sets"] = kept_sets
            self.save()

    def media_path(self, media_id: str, thumb: bool = False) -> tuple[Path, str]:
        with self.lock:
            m = self.media_item(media_id)
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
        return parsed.scheme == "https" and parsed.hostname in {"novelai.net", "www.novelai.net"}

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
        if length > 10 * 1024 * 1024:
            raise ValueError("JSON request is too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def _read_raw(self, max_bytes: int = 12 * 1024 * 1024) -> bytes:
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

    def _send_file_with_range(self, file_path: Path, content_type: str) -> None:
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
        self.send_header("Cache-Control", "private, max-age=86400")
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
            if path == "/api/health":
                self._send_json(200, {"ok": True, "version": API_VERSION, "library_root": str(self.store.root)})
                return
            if path == "/api/diagnostics/last-import":
                payload = dict(self.store.last_import_debug) if self.store.last_import_debug else {"state": "none"}
                self._send_json(200, payload)
                return
            if path == "/api/diagnostics/performance":
                self._send_json(200, self.store.performance_probe())
                return
            if path == "/api/library":
                self._send_json(200, self.store.public_library())
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/(?:(thumb)|(original))", path)
            if match:
                media_id = match.group(1)
                thumb = bool(match.group(2))
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
            if path == "/api/characters":
                body = self._read_json()
                self._send_json(200, self.store.add_character(str(body.get("name", ""))))
                return
            if path == "/api/categories":
                body = self._read_json()
                self._send_json(200, self.store.add_category(str(body.get("character_id", "")), str(body.get("name", ""))))
                return
            if path == "/api/sets":
                body = self._read_json()
                item = self.store.create_set(
                    str(body.get("character_id", "")),
                    str(body.get("name", "")),
                    list(body.get("media_ids", [])) if isinstance(body.get("media_ids", []), list) else [],
                    body.get("cover_media_id"),
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
                )
                self._send_json(200, item)
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
                item, duplicate, backend_timing = self.store.import_bytes_profiled(
                    payload,
                    filename,
                    character_id,
                    list(categories) if isinstance(categories, list) else [],
                    {"kind": "local", "original_name": filename},
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
            if path == "/api/backup":
                dst = self.store.manual_backup()
                self._send_json(200, {"ok": True, "path": str(dst)})
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/categories", path)
            if match:
                body = self._read_json()
                item = self.store.set_categories(match.group(1), list(body.get("categories", [])))
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/favorite", path)
            if match:
                body = self._read_json()
                item = self.store.set_favorite(match.group(1), bool(body.get("favorite")))
                self._send_json(200, item)
                return
            match = re.fullmatch(r"/api/media/([0-9a-f]+)/review", path)
            if match:
                body = self._read_json()
                item = self.store.set_review(match.group(1), bool(body.get("in_review")))
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
                item = self.store.set_video_thumbnail_bytes(match.group(1), payload, content_type, seconds)
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
            match = re.fullmatch(r"/api/categories/([0-9a-f]+)", path)
            if match:
                result = self.store.delete_category(match.group(1))
                self._send_json(200, result)
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

    def __init__(self, address: tuple[str, int], store: LibraryStore):
        super().__init__(address, MediaHandler)
        self.store = store


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
    root.geometry("520x250")
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
