import json
from pathlib import Path

path = Path('runtime-src/companion-runtime.pyw')
s = path.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    s = s.replace(old, new, 1)


replace_once('API_VERSION = 5', 'API_VERSION = 6', 'API version')

replace_once(
    '        self.media_dir = root / "media"\n        self.thumb_dir = root / "thumbnails"\n        self.backup_dir = root / "backups"\n',
    '        self.media_dir = root / "media"\n        self.thumb_dir = root / "thumbnails"\n        self.crop_dir = root / "cropped"\n        self.backup_dir = root / "backups"\n',
    'crop dir field',
)
replace_once(
    '        self.media_dir.mkdir(parents=True, exist_ok=True)\n        self.thumb_dir.mkdir(parents=True, exist_ok=True)\n        self.backup_dir.mkdir(parents=True, exist_ok=True)\n',
    '        self.media_dir.mkdir(parents=True, exist_ok=True)\n        self.thumb_dir.mkdir(parents=True, exist_ok=True)\n        self.crop_dir.mkdir(parents=True, exist_ok=True)\n        self.backup_dir.mkdir(parents=True, exist_ok=True)\n',
    'crop dir mkdir',
)

replace_once(
    '                if "crop_bottom" not in m:\n                    m["crop_bottom"] = 0.0\n                    changed = True\n',
    '                if "crop_bottom" not in m:\n                    m["crop_bottom"] = 0.0\n                    changed = True\n                if "cropped_rel" not in m:\n                    m["cropped_rel"] = None\n                    changed = True\n',
    'cropped_rel migration',
)

replace_once(
    '                "crop_top": 0.0,\n                "crop_bottom": 0.0,\n                "sha256": sha,\n',
    '                "crop_top": 0.0,\n                "crop_bottom": 0.0,\n                "cropped_rel": None,\n                "sha256": sha,\n',
    'new media cropped_rel',
)

old_crop = '''    def set_crop(self, media_id: str, top: Any = 0.0, bottom: Any = 0.0) -> dict[str, Any]:
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
'''

new_crop = '''    def _remove_cropped_derivative(self, m: dict[str, Any]) -> None:
        rel = m.get("cropped_rel")
        if rel:
            try:
                (self.root / str(rel)).unlink(missing_ok=True)
            except Exception:
                pass
        m["cropped_rel"] = None

    def _make_cropped_derivative(self, m: dict[str, Any]) -> Path:
        if Image is None:
            raise RuntimeError("Pillow is required to create persistent cropped images")
        if m.get("media_type") != "image":
            raise ValueError("Only images can be cropped")
        original = (self.root / str(m.get("stored_rel", ""))).resolve()
        root_resolved = self.root.resolve()
        if root_resolved not in original.parents and original != root_resolved:
            raise ValueError("Invalid media path")
        if not original.exists():
            raise FileNotFoundError("Original media file is missing")

        top = max(0.0, min(0.89, float(m.get("crop_top") or 0.0)))
        bottom = max(0.0, min(0.89, float(m.get("crop_bottom") or 0.0)))
        if top + bottom <= 0:
            self._remove_cropped_derivative(m)
            return original

        owner = self.character(str(m.get("character_id", "")))
        folder = self.crop_dir / safe_component(owner.get("name", "Character") if owner else "Character", "Character")
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f'{m["id"]}.png'
        temp = out.with_suffix('.png.tmp')

        with Image.open(original) as source:
            im = ImageOps.exif_transpose(source) if ImageOps is not None else source.copy()
            try:
                im.seek(0)
            except Exception:
                pass
            width, height = im.size
            y1 = max(0, min(height - 1, round(height * top)))
            y2 = max(y1 + 1, min(height, round(height * (1.0 - bottom))))
            cropped = im.crop((0, y1, width, y2))
            if cropped.mode == "CMYK":
                cropped = cropped.convert("RGB")
            elif cropped.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"):
                cropped = cropped.convert("RGBA" if "A" in cropped.mode else "RGB")
            cropped.save(temp, "PNG", optimize=True)
            try:
                cropped.close()
            except Exception:
                pass
            if im is not source:
                try:
                    im.close()
                except Exception:
                    pass
        os.replace(temp, out)
        m["cropped_rel"] = out.relative_to(self.root).as_posix()
        return out

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

            old_top = m.get("crop_top", 0.0)
            old_bottom = m.get("crop_bottom", 0.0)
            old_rel = m.get("cropped_rel")
            m["crop_top"] = round(top, 6)
            m["crop_bottom"] = round(bottom, 6)
            try:
                if m["crop_top"] or m["crop_bottom"]:
                    display_path = self._make_cropped_derivative(m)
                else:
                    self._remove_cropped_derivative(m)
                    display_path = (self.root / str(m.get("stored_rel", ""))).resolve()
                owner = self.character(str(m.get("character_id", "")))
                thumb_rel = self._make_thumbnail(display_path, media_id, owner.get("name", "Character") if owner else "Character")
                if thumb_rel:
                    m["thumb_rel"] = thumb_rel
                self.save()
                return m
            except Exception:
                m["crop_top"] = old_top
                m["crop_bottom"] = old_bottom
                m["cropped_rel"] = old_rel
                raise
'''
replace_once(old_crop, new_crop, 'set_crop implementation')

replace_once(
    '            for key in ("stored_rel", "thumb_rel"):\n',
    '            for key in ("stored_rel", "thumb_rel", "cropped_rel"):\n',
    'delete cropped derivative',
)

old_media_path = '''    def media_path(self, media_id: str, thumb: bool = False) -> tuple[Path, str]:
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
'''
new_media_path = '''    def media_path(self, media_id: str, thumb: bool = False, source: bool = False) -> tuple[Path, str]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")

            using_crop = False
            if thumb:
                rel = m.get("thumb_rel") or m.get("stored_rel")
            elif source or m.get("media_type") != "image":
                rel = m.get("stored_rel")
            else:
                cropped = bool(float(m.get("crop_top") or 0.0) or float(m.get("crop_bottom") or 0.0))
                rel = m.get("cropped_rel") if cropped else m.get("stored_rel")
                candidate = (self.root / str(rel or "")).resolve() if rel else None
                if cropped and (not rel or candidate is None or not candidate.exists()):
                    candidate = self._make_cropped_derivative(m)
                    self.save()
                    rel = m.get("cropped_rel")
                using_crop = bool(cropped and rel == m.get("cropped_rel"))

            path = (self.root / str(rel or "")).resolve()
            if self.root.resolve() not in path.parents and path != self.root.resolve():
                raise ValueError("Invalid media path")
            if not path.exists():
                raise FileNotFoundError("Media file is missing")
            if thumb and m.get("thumb_rel"):
                return path, mimetypes.guess_type(path.name)[0] or "image/webp"
            if using_crop:
                return path, "image/png"
            return path, m.get("content_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
'''
replace_once(old_media_path, new_media_path, 'media_path implementation')

old_head = '''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/(?:(thumb)|(original))", path)
            if not match:
                self.send_response(404)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            media_id = match.group(1)
            thumb = bool(match.group(2))
            file_path, content_type = self.store.media_path(media_id, thumb=thumb)
'''
new_head = '''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/(thumb|original|source)", path)
            if not match:
                self.send_response(404)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            media_id = match.group(1)
            kind = match.group(2)
            file_path, content_type = self.store.media_path(media_id, thumb=(kind == "thumb"), source=(kind == "source"))
'''
replace_once(old_head, new_head, 'HEAD media route')

old_get = '''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/(?:(thumb)|(original))", path)
            if match:
                media_id = match.group(1)
                thumb = bool(match.group(2))
                file_path, content_type = self.store.media_path(media_id, thumb=thumb)
                self._send_file_with_range(file_path, content_type)
                return
'''
new_get = '''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/(thumb|original|source)", path)
            if match:
                media_id = match.group(1)
                kind = match.group(2)
                file_path, content_type = self.store.media_path(media_id, thumb=(kind == "thumb"), source=(kind == "source"))
                self._send_file_with_range(file_path, content_type)
                return
'''
replace_once(old_get, new_get, 'GET media route')

replace_once(
    '        self.send_header("Cache-Control", "private, max-age=86400")\n',
    '        self.send_header("Cache-Control", "private, max-age=3600" if content_type.startswith("video/") else "no-store")\n',
    'media cache control',
)

path.write_text(s, encoding='utf-8')
release = json.loads(Path('release-runtime.json').read_text(encoding='utf-8'))
release['version'] = '2.6.0'
release['source'] = 'runtime-src/companion-runtime.pyw'
Path('release-runtime.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
