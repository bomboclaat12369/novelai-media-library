from pathlib import Path

p = Path('runtime-src/companion-runtime.pyw')
text = p.read_text(encoding='utf-8')

text = text.replace('API_VERSION = 8', 'API_VERSION = 9', 1)

needle = '''    def _make_video_thumbnail(self, original: Path, media_id: str, character_name: str, seconds: float = 0.0) -> str | None:\n'''
insert = '''    def _queue_image_thumbnail(self, original: Path, media_id: str, character_name: str) -> None:\n        # Thumbnail generation is deliberately off the import critical path. Large JPEG/PNG\n        # decode + resize can take seconds on some machines; the original media is already\n        # safely stored by this point, so Rapid Review should not wait for a 420px thumbnail.\n        def worker() -> None:\n            # Give the request thread a chance to serialize/flush the successful import first.\n            time.sleep(0.10)\n            thumb_rel = self._make_thumbnail(original, media_id, character_name)\n            if not thumb_rel:\n                return\n            with self.lock:\n                item = self.media_item(media_id)\n                if not item:\n                    try:\n                        (self.root / thumb_rel).unlink(missing_ok=True)\n                    except Exception:\n                        pass\n                    return\n                # Do not resurrect/attach a thumbnail to a replaced media record.\n                try:\n                    expected = original.resolve()\n                    current = (self.root / str(item.get("stored_rel") or "")).resolve()\n                    if current != expected:\n                        return\n                except Exception:\n                    return\n                item["thumb_rel"] = thumb_rel\n                self.save()\n\n        threading.Thread(\n            target=worker,\n            name=f"nai-thumb-{media_id[:8]}",\n            daemon=True,\n        ).start()\n\n    def _make_video_thumbnail(self, original: Path, media_id: str, character_name: str, seconds: float = 0.0) -> str | None:\n'''
if needle not in text:
    raise SystemExit('thumbnail insertion point not found')
text = text.replace(needle, insert, 1)

old = '''            thumb_rel = None\n            video_markers = [None, None, None]\n            video_thumb_seconds = None\n            if media_type == "image":\n                thumb_rel = self._make_thumbnail(destination, media_id, c["name"])\n            else:\n                # Video thumbnails are captured from the exact frame chosen in the browser.\n                # Avoid decoding the entire video during import so large videos import faster.\n                video_thumb_seconds = 0.0\n                thumb_rel = None\n'''
new = '''            # Import completion must not wait for image decoding/resizing. The media endpoint\n            # already falls back to the original while thumb_rel is empty, and a background\n            # worker fills in the thumbnail shortly after the successful import response.\n            thumb_rel = None\n            video_markers = [None, None, None]\n            video_thumb_seconds = None\n            if media_type == "video":\n                # Video thumbnails are captured from the exact frame chosen in the browser.\n                video_thumb_seconds = 0.0\n'''
if old not in text:
    raise SystemExit('synchronous thumbnail block not found')
text = text.replace(old, new, 1)

old = '''                "favorite": False,\n                "crop_top": 0.0,\n'''
new = '''                "favorite": False,\n                "in_review": False,\n                "crop_top": 0.0,\n'''
if old not in text:
    raise SystemExit('item favorite block not found')
text = text.replace(old, new, 1)

old = '''            self.data["media"].append(item)\n            self.save()\n            return item, False\n'''
new = '''            self.data["media"].append(item)\n            self.save()\n            if media_type == "image":\n                self._queue_image_thumbnail(destination, media_id, c["name"])\n            return item, False\n'''
if old not in text:
    raise SystemExit('register return block not found')
text = text.replace(old, new, 1)

# Add phase timings to the legacy multipart route. Existing userscripts ignore the extra\n# JSON field, but it gives us exact backend timings in DevTools if another machine-specific\n# bottleneck remains after thumbnail generation is moved off-path.
old = '''            if path == "/api/import/file":\n                fields = self._read_multipart()\n                character_id = self._field_text(fields, "character_id")\n'''
new = '''            if path == "/api/import/file":\n                import_started = time.perf_counter()\n                fields = self._read_multipart()\n                multipart_done = time.perf_counter()\n                character_id = self._field_text(fields, "character_id")\n'''
if old not in text:
    raise SystemExit('import route start not found')
text = text.replace(old, new, 1)

old = '''                item, duplicate = self.store.import_bytes(\n                    payload,\n                    filename,\n                    character_id,\n                    list(categories) if isinstance(categories, list) else [],\n                    {"kind": "local", "original_name": filename},\n                    content_type,\n                )\n                self._send_json(200, {"item": item, "duplicate": duplicate})\n                return\n'''
new = '''                register_started = time.perf_counter()\n                item, duplicate = self.store.import_bytes(\n                    payload,\n                    filename,\n                    character_id,\n                    list(categories) if isinstance(categories, list) else [],\n                    {"kind": "local", "original_name": filename},\n                    content_type,\n                )\n                register_done = time.perf_counter()\n                self._send_json(200, {\n                    "item": item,\n                    "duplicate": duplicate,\n                    "debug_timing_ms": {\n                        "multipart": round((multipart_done - import_started) * 1000, 1),\n                        "register": round((register_done - register_started) * 1000, 1),\n                        "total": round((register_done - import_started) * 1000, 1),\n                    },\n                })\n                return\n'''
if old not in text:
    raise SystemExit('import route completion not found')
text = text.replace(old, new, 1)

p.write_text(text, encoding='utf-8')
print('patched', p)
