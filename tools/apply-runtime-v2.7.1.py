from pathlib import Path

path = Path('runtime-src/companion-runtime.pyw')
text = path.read_text(encoding='utf-8')

if 'if path == "/api/import/raw":' in text:
    raise SystemExit('raw import route already present')

text = text.replace('API_VERSION = 6', 'API_VERSION = 7', 1)
needle = '            if path == "/api/import/url":\n'
if needle not in text:
    raise SystemExit('import/url route marker not found')

block = '''            if path == "/api/import/raw":
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                character_id = str((query.get("character_id") or [""])[0])
                filename = str((query.get("filename") or [""])[0])
                categories_text = str((query.get("categories") or ["[]"])[0])
                try:
                    categories = json.loads(categories_text)
                except Exception:
                    categories = []
                if not isinstance(categories, list):
                    categories = []
                if not filename:
                    raise ValueError("Uploaded file has no filename")
                content_type = (self.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
                if not (content_type.startswith("image/") or content_type.startswith("video/")):
                    guessed, _ = mimetypes.guess_type(filename)
                    content_type = guessed or content_type
                if not (content_type or "").startswith(("image/", "video/")):
                    raise ValueError("Only image and video files are supported")

                length = int(self.headers.get("Content-Length", "0") or "0")
                max_bytes = 2 * 1024 * 1024 * 1024
                if length <= 0 or length > max_bytes:
                    raise ValueError("Uploaded file is empty or larger than 2 GB")

                temp_dir = self.store.root / ".incoming"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp = temp_dir / f"{uuid.uuid4().hex}.part"
                try:
                    remaining = length
                    with temp.open("wb") as out:
                        while remaining > 0:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("Upload ended before the complete file was received")
                            out.write(chunk)
                            remaining -= len(chunk)
                    item, duplicate = self.store._register_file(
                        temp,
                        filename,
                        character_id,
                        list(categories),
                        {"kind": "local", "original_name": filename},
                        content_type,
                    )
                except Exception:
                    try:
                        temp.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise
                self._send_json(200, {"item": item, "duplicate": duplicate})
                return
'''

text = text.replace(needle, block + needle, 1)
path.write_text(text, encoding='utf-8')
print('patched runtime source for v2.7.1')
