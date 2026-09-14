from pathlib import Path

path = Path('runtime-src/companion-runtime.pyw')
text = path.read_text(encoding='utf-8')

if 'API_VERSION = 8' in text:
    raise SystemExit('runtime v2.7.2 already applied')
if 'API_VERSION = 7' not in text:
    raise SystemExit('expected API_VERSION = 7')
text = text.replace('API_VERSION = 7', 'API_VERSION = 8', 1)

server_old = '''    def __init__(self, address: tuple[str, int], store: LibraryStore):
        super().__init__(address, MediaHandler)
        self.store = store
'''
server_new = '''    def __init__(self, address: tuple[str, int], store: LibraryStore):
        super().__init__(address, MediaHandler)
        self.store = store
        self.import_jobs: dict[str, dict[str, Any]] = {}
        self.import_jobs_lock = threading.RLock()
'''
if server_old not in text:
    raise SystemExit('server init marker not found')
text = text.replace(server_old, server_new, 1)

library_old = '''            if path == "/api/library":
                self._send_json(200, self.store.public_library())
                return
'''
status_block = '''            if path == "/api/library":
                self._send_json(200, self.store.public_library())
                return
            match = re.fullmatch(r"/api/import/status/([A-Za-z0-9_-]{8,128})", path)
            if match:
                token = match.group(1)
                now = time.time()
                with self.server.import_jobs_lock:  # type: ignore[attr-defined]
                    jobs = self.server.import_jobs  # type: ignore[attr-defined]
                    stale = [key for key, value in jobs.items() if now - float(value.get("updated_at", now)) > 1800]
                    for key in stale:
                        jobs.pop(key, None)
                    job = jobs.get(token)
                    payload = dict(job) if job else {"state": "unknown"}
                payload.pop("updated_at", None)
                self._send_json(200, payload)
                return
'''
if library_old not in text:
    raise SystemExit('library GET marker not found')
text = text.replace(library_old, status_block, 1)

start_marker = '            if path == "/api/import/raw":\n'
end_marker = '            if path == "/api/import/url":\n'
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('raw import route markers not found')

raw_block = '''            if path == "/api/import/raw":
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                character_id = str((query.get("character_id") or [""])[0])
                filename = str((query.get("filename") or [""])[0])
                token = str((query.get("token") or [""])[0]).strip()
                if token and not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", token):
                    raise ValueError("Invalid import token")
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

                if token:
                    with self.server.import_jobs_lock:  # type: ignore[attr-defined]
                        self.server.import_jobs[token] = {  # type: ignore[attr-defined]
                            "state": "uploading",
                            "updated_at": time.time(),
                        }

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
                except Exception as exc:
                    try:
                        temp.unlink(missing_ok=True)
                    except Exception:
                        pass
                    if token:
                        with self.server.import_jobs_lock:  # type: ignore[attr-defined]
                            self.server.import_jobs[token] = {  # type: ignore[attr-defined]
                                "state": "error",
                                "error": str(exc),
                                "updated_at": time.time(),
                            }
                    raise

                if token:
                    server = self.server
                    store = self.store
                    categories_copy = list(categories)
                    source_copy = {"kind": "local", "original_name": filename}

                    def finish_import_job() -> None:
                        try:
                            item, duplicate = store._register_file(
                                temp,
                                filename,
                                character_id,
                                categories_copy,
                                source_copy,
                                content_type,
                            )
                            result = {
                                "state": "done",
                                "item": item,
                                "duplicate": duplicate,
                                "updated_at": time.time(),
                            }
                        except Exception as exc:
                            try:
                                temp.unlink(missing_ok=True)
                            except Exception:
                                pass
                            result = {
                                "state": "error",
                                "error": str(exc),
                                "updated_at": time.time(),
                            }
                        with server.import_jobs_lock:  # type: ignore[attr-defined]
                            server.import_jobs[token] = result  # type: ignore[attr-defined]

                    with self.server.import_jobs_lock:  # type: ignore[attr-defined]
                        self.server.import_jobs[token] = {  # type: ignore[attr-defined]
                            "state": "processing",
                            "updated_at": time.time(),
                        }
                    threading.Thread(target=finish_import_job, name=f"nai-import-{token[:12]}", daemon=True).start()

                    body = json_bytes({"accepted": True, "token": token})
                    self.send_response(202)
                    self._cors()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)
                    self.wfile.flush()
                    self.close_connection = True
                    return

                try:
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
text = text[:start] + raw_block + text[end:]

path.write_text(text, encoding='utf-8')
print('patched runtime source for v2.7.2 import jobs')
