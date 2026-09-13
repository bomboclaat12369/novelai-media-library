from pathlib import Path

path = Path('runtime-src/companion-runtime.pyw')
text = path.read_text(encoding='utf-8')
original = text


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    text = text.replace(old, new, 1)

replace_once('API_VERSION = 5', 'API_VERSION = 6', 'API version')

replace_once(
'''                if "favorite" not in m:\n                    m["favorite"] = False\n                    changed = True\n                if "categories" not in m or not isinstance(m.get("categories"), list):''',
'''                if "favorite" not in m:\n                    m["favorite"] = False\n                    changed = True\n                if "in_review" not in m:\n                    m["in_review"] = False\n                    changed = True\n                if "categories" not in m or not isinstance(m.get("categories"), list):''',
'load migration',
)

replace_once(
'''                "categories": categories,\n                "favorite": False,\n                "crop_top": 0.0,''',
'''                "categories": categories,\n                "favorite": False,\n                "in_review": False,\n                "crop_top": 0.0,''',
'new media default',
)

replace_once(
'''    def set_favorite(self, media_id: str, favorite: bool) -> dict[str, Any]:\n        with self.lock:\n            m = self.media_item(media_id)\n            if not m:\n                raise KeyError("Media not found")\n            m["favorite"] = bool(favorite)\n            self.save()\n            return m\n\n    def set_crop''',
'''    def set_favorite(self, media_id: str, favorite: bool) -> dict[str, Any]:\n        with self.lock:\n            m = self.media_item(media_id)\n            if not m:\n                raise KeyError("Media not found")\n            m["favorite"] = bool(favorite)\n            self.save()\n            return m\n\n    def set_review(self, media_id: str, in_review: bool) -> dict[str, Any]:\n        with self.lock:\n            m = self.media_item(media_id)\n            if not m:\n                raise KeyError("Media not found")\n            if m.get("media_type") != "image":\n                raise ValueError("Only images can be placed in Review")\n            m["in_review"] = bool(in_review)\n            self.save()\n            return m\n\n    def set_crop''',
'set_review method',
)

replace_once(
'''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/favorite", path)\n            if match:\n                body = self._read_json()\n                item = self.store.set_favorite(match.group(1), bool(body.get("favorite")))\n                self._send_json(200, item)\n                return\n            match = re.fullmatch(r"/api/media/([0-9a-f]+)/crop", path)''',
'''            match = re.fullmatch(r"/api/media/([0-9a-f]+)/favorite", path)\n            if match:\n                body = self._read_json()\n                item = self.store.set_favorite(match.group(1), bool(body.get("favorite")))\n                self._send_json(200, item)\n                return\n            match = re.fullmatch(r"/api/media/([0-9a-f]+)/review", path)\n            if match:\n                body = self._read_json()\n                item = self.store.set_review(match.group(1), bool(body.get("in_review")))\n                self._send_json(200, item)\n                return\n            match = re.fullmatch(r"/api/media/([0-9a-f]+)/crop", path)''',
'review route',
)

if text == original:
    print('Runtime already has the v2.7.0 Review changes.')
else:
    path.write_text(text, encoding='utf-8')
    print('Applied runtime v2.7.0 Review changes.')
