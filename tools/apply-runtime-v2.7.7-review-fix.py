from pathlib import Path

path = Path('runtime-src/companion-runtime.pyw')
text = path.read_text(encoding='utf-8')

# Restore the Review state that was accidentally dropped when the optimized runtime
# was rebuilt from the older API v5 baseline.
text = text.replace('API_VERSION = 5', 'API_VERSION = 6', 1)

old = '''                if "favorite" not in m:\n                    m["favorite"] = False\n                    changed = True\n                if "categories" not in m or not isinstance(m.get("categories"), list):\n'''
new = '''                if "favorite" not in m:\n                    m["favorite"] = False\n                    changed = True\n                if "in_review" not in m:\n                    m["in_review"] = False\n                    changed = True\n                if "categories" not in m or not isinstance(m.get("categories"), list):\n'''
if old not in text:
    raise SystemExit('load migration anchor not found')
text = text.replace(old, new, 1)

old = '''                "categories": categories,\n                "favorite": False,\n                "crop_top": 0.0,\n'''
new = '''                "categories": categories,\n                "favorite": False,\n                "in_review": False,\n                "crop_top": 0.0,\n'''
if old not in text:
    raise SystemExit('new media anchor not found')
text = text.replace(old, new, 1)

old = '''    def set_favorite(self, media_id: str, favorite: bool) -> dict[str, Any]:\n        with self.lock:\n            m = self.media_item(media_id)\n            if not m:\n                raise KeyError("Media not found")\n            m["favorite"] = bool(favorite)\n            self.save()\n            return m\n\n'''
new = old + '''    def set_review(self, media_id: str, in_review: bool) -> dict[str, Any]:\n        with self.lock:\n            m = self.media_item(media_id)\n            if not m:\n                raise KeyError("Media not found")\n            if m.get("media_type") != "image":\n                raise ValueError("Only images can be placed in Review")\n            m["in_review"] = bool(in_review)\n            self.save()\n            return m\n\n'''
if old not in text:
    raise SystemExit('set_favorite anchor not found')
text = text.replace(old, new, 1)

old = '''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/favorite", path)\n            if match:\n                body = self._read_json()\n                item = self.store.set_favorite(match.group(1), bool(body.get("favorite")))\n                self._send_json(200, item)\n                return\n'''
new = old + '''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/review", path)\n            if match:\n                body = self._read_json()\n                item = self.store.set_review(match.group(1), bool(body.get("in_review")))\n                self._send_json(200, item)\n                return\n'''
if old not in text:
    raise SystemExit('favorite route anchor not found')
text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
print('Restored Review state + /review API on optimized runtime')
