from pathlib import Path

path = Path('runtime-src/companion-runtime.pyw')
src = path.read_text(encoding='utf-8')

src = src.replace('API_VERSION = 3', 'API_VERSION = 4', 1)

needle = '''                if "categories" not in m or not isinstance(m.get("categories"), list):
                    m["categories"] = []
                    changed = True
'''
insert = needle + '''                if "crop_top" not in m:
                    m["crop_top"] = 0.0
                    changed = True
                if "crop_bottom" not in m:
                    m["crop_bottom"] = 0.0
                    changed = True
'''
if needle not in src:
    raise SystemExit('migration insertion point not found')
src = src.replace(needle, insert, 1)

needle = '''                "favorite": False,
                "sha256": sha,
'''
insert = '''                "favorite": False,
                "crop_top": 0.0,
                "crop_bottom": 0.0,
                "sha256": sha,
'''
if needle not in src:
    raise SystemExit('new media insertion point not found')
src = src.replace(needle, insert, 1)

needle = '''    def set_video_meta(self, media_id: str, thumb_seconds: float | None = None, markers: list[Any] | None = None) -> dict[str, Any]:
'''
method = '''    def set_crop(self, media_id: str, top: Any = 0.0, bottom: Any = 0.0) -> dict[str, Any]:
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
if needle not in src:
    raise SystemExit('method insertion point not found')
src = src.replace(needle, method + needle, 1)

needle = '''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/favorite", path)
            if match:
                body = self._read_json()
                item = self.store.set_favorite(match.group(1), bool(body.get("favorite")))
                self._send_json(200, item)
                return
'''
insert = needle + '''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/crop", path)
            if match:
                body = self._read_json()
                item = self.store.set_crop(match.group(1), body.get("top", 0.0), body.get("bottom", 0.0))
                self._send_json(200, item)
                return
'''
if needle not in src:
    raise SystemExit('route insertion point not found')
src = src.replace(needle, insert, 1)

path.write_text(src, encoding='utf-8')
print('Patched runtime source for API v4 crop persistence.')
