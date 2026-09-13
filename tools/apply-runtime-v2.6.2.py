from pathlib import Path

p = Path('runtime-src/companion-runtime.pyw')
s = p.read_text(encoding='utf-8')

if 'API_VERSION = 6' not in s:
    raise SystemExit('expected API_VERSION 6 not found')
s = s.replace('API_VERSION = 6', 'API_VERSION = 7', 1)

start = s.find('    def media_path(self, media_id: str, thumb: bool = False, source: bool = False) -> tuple[Path, str]:\n')
end = s.find('\n\n\nclass MediaHandler', start)
if start < 0 or end < 0:
    raise SystemExit('media_path block not found')

replacement = '''    def media_path(self, media_id: str, thumb: bool = False, source: bool = False) -> tuple[Path, str]:
        with self.lock:
            m = self.media_item(media_id)
            if not m:
                raise KeyError("Media not found")

            if thumb:
                rel = m.get("thumb_rel") or m.get("stored_rel")
                path = (self.root / str(rel or "")).resolve()
                if self.root.resolve() not in path.parents and path != self.root.resolve():
                    raise ValueError("Invalid media path")
                if not path.exists():
                    raise FileNotFoundError("Media file is missing")
                if m.get("thumb_rel"):
                    return path, mimetypes.guess_type(path.name)[0] or "image/webp"
                return path, m.get("content_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"

            # /source is always the exact untouched imported file. Videos also always
            # use their original file. Normal image display, however, must prefer the
            # persistent cropped derivative whenever crop metadata is present.
            if source or m.get("media_type") != "image":
                rel = m.get("stored_rel")
                using_crop = False
            else:
                try:
                    top = float(m.get("crop_top") or 0.0)
                except Exception:
                    top = 0.0
                try:
                    bottom = float(m.get("crop_bottom") or 0.0)
                except Exception:
                    bottom = 0.0
                has_crop = top > 0.0 or bottom > 0.0
                using_crop = False
                if has_crop:
                    rel = m.get("cropped_rel")
                    candidate = (self.root / str(rel or "")).resolve() if rel else None
                    if not rel or candidate is None or not candidate.exists():
                        self._make_cropped_derivative(m)
                        self.save()
                        rel = m.get("cropped_rel")
                    if not rel:
                        raise FileNotFoundError("Cropped media file is missing")
                    using_crop = True
                else:
                    rel = m.get("stored_rel")

            path = (self.root / str(rel or "")).resolve()
            if self.root.resolve() not in path.parents and path != self.root.resolve():
                raise ValueError("Invalid media path")
            if not path.exists():
                raise FileNotFoundError("Media file is missing")
            if using_crop:
                return path, "image/png"
            return path, m.get("content_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
'''

s = s[:start] + replacement + s[end:]

# Keep the library schema/version marker current for existing libraries too.
s = s.replace('            data.setdefault("version", API_VERSION)\n', '            if data.get("version") != API_VERSION:\n                data["version"] = API_VERSION\n                changed = True\n', 1)
# The replacement above references changed before its old declaration, so move the declaration earlier.
s = s.replace('            if not isinstance(data, dict):\n                raise ValueError("library.json is not a JSON object")\n            if data.get("version") != API_VERSION:\n', '            if not isinstance(data, dict):\n                raise ValueError("library.json is not a JSON object")\n            changed = False\n            if data.get("version") != API_VERSION:\n', 1)
s = s.replace('            if not isinstance(data.get("sets"), list):\n                data["sets"] = []\n            changed = False\n', '            if not isinstance(data.get("sets"), list):\n                data["sets"] = []\n                changed = True\n', 1)

p.write_text(s, encoding='utf-8')
print('patched runtime to API v7 / release 2.6.2')
