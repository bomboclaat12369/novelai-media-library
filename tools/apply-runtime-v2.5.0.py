from pathlib import Path

path = Path('runtime-src/companion-runtime.pyw')
src = path.read_text(encoding='utf-8')

if 'API_VERSION = 5' in src and 'def create_set(' in src:
    print('Runtime sets patch already applied.')
    raise SystemExit(0)

src = src.replace('API_VERSION = 4', 'API_VERSION = 5', 1)

needle = '''            "characters": [],
            "media": [],
'''
insert = '''            "characters": [],
            "media": [],
            "sets": [],
'''
if needle not in src:
    raise SystemExit('empty-library insertion point not found')
src = src.replace(needle, insert, 1)

needle = '''            data.setdefault("characters", [])
            data.setdefault("media", [])
            changed = False
'''
insert = '''            data.setdefault("characters", [])
            data.setdefault("media", [])
            data.setdefault("sets", [])
            if not isinstance(data.get("sets"), list):
                data["sets"] = []
            changed = False
'''
if needle not in src:
    raise SystemExit('sets migration insertion point not found')
src = src.replace(needle, insert, 1)

needle = '''    def media_item(self, media_id: str) -> dict[str, Any] | None:
        return next((m for m in self.data["media"] if m["id"] == media_id), None)

'''
insert = needle + '''    def set_item(self, set_id: str) -> dict[str, Any] | None:
        return next((s for s in self.data.get("sets", []) if s.get("id") == set_id), None)

'''
if needle not in src:
    raise SystemExit('set_item insertion point not found')
src = src.replace(needle, insert, 1)

needle = '''    def set_categories(self, media_id: str, categories: list[str]) -> dict[str, Any]:
'''
methods = '''    def _validate_set_media(self, character_id: str, media_ids: list[Any]) -> list[str]:
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

'''
if needle not in src:
    raise SystemExit('set methods insertion point not found')
src = src.replace(needle, methods + needle, 1)

needle = '''            self.data["media"] = [x for x in self.data["media"] if x["id"] != media_id]
            self.save()
'''
insert = '''            self.data["media"] = [x for x in self.data["media"] if x["id"] != media_id]
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
'''
if needle not in src:
    raise SystemExit('delete-media set cleanup insertion point not found')
src = src.replace(needle, insert, 1)

needle = '''            if path == "/api/categories":
                body = self._read_json()
                self._send_json(200, self.store.add_category(str(body.get("character_id", "")), str(body.get("name", ""))))
                return
'''
insert = needle + '''            if path == "/api/sets":
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
'''
if needle not in src:
    raise SystemExit('POST set route insertion point not found')
src = src.replace(needle, insert, 1)

needle = '''            match = re.fullmatch(r"/api/categories/([0-9a-f]+)", path)
            if match:
                result = self.store.delete_category(match.group(1))
                self._send_json(200, result)
                return
'''
insert = needle + '''            match = re.fullmatch(r"/api/sets/([0-9a-f]+)", path)
            if match:
                result = self.store.delete_set(match.group(1))
                self._send_json(200, result)
                return
'''
if needle not in src:
    raise SystemExit('DELETE set route insertion point not found')
src = src.replace(needle, insert, 1)

path.write_text(src, encoding='utf-8')
print('Patched runtime source for API v5 image sets.')
