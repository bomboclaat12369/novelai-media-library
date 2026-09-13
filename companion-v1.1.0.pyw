from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

APP_NAME = "NovelAI Media Library"
LAUNCHER_VERSION = "1.1.0"
MANIFEST_URL = "https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/manifest.json"
CHECK_INTERVAL_SECONDS = 60
DOWNLOAD_TIMEOUT_SECONDS = 15
CROP_HOST = "127.0.0.1"
CROP_PORT = 8766
CROP_FILE_NAME = "crop-metadata.json"

_crop_lock = threading.RLock()
_crop_server = None


def fetch_text(url: str) -> str:
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        f"{url}{sep}_={int(time.time())}",
        headers={"User-Agent": "NovelAI-Media-Library-Launcher/1.1", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8")


def fetch_manifest() -> dict:
    data = json.loads(fetch_text(MANIFEST_URL))
    if not isinstance(data, dict) or int(data.get("schema", 0)) < 2:
        raise ValueError("Invalid update manifest")
    return data


def version_tuple(value: str) -> tuple[int, ...]:
    out = []
    for token in str(value or "").split("."):
        try:
            out.append(int(token))
        except ValueError:
            digits = "".join(ch for ch in token if ch.isdigit())
            out.append(int(digits or 0))
    return tuple(out or [0])


def maybe_update_launcher(manifest: dict) -> bool:
    """Replace this stable launcher if a newer launcher is published."""
    wanted = str(manifest.get("launcher_version") or "").strip()
    url = str(manifest.get("launcher_url") or "").strip()
    expected = str(manifest.get("launcher_sha256") or "").strip().lower()
    if not wanted or not url or not expected:
        return False
    if version_tuple(wanted) <= version_tuple(LAUNCHER_VERSION):
        return False
    payload = fetch_text(url).encode("utf-8")
    if hashlib.sha256(payload).hexdigest().lower() != expected:
        raise ValueError("Downloaded launcher failed SHA-256 verification")
    if b"NovelAI Media Library" not in payload or b"LAUNCHER_VERSION" not in payload:
        raise ValueError("Downloaded launcher did not look valid")
    target = Path(__file__).resolve()
    temp = target.with_suffix(target.suffix + ".new")
    temp.write_bytes(payload)
    os.replace(temp, target)
    return True


def restart_launcher() -> None:
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], close_fds=True)


def runtime_dir() -> Path:
    p = Path(__file__).resolve().parent / ".runtime"
    p.mkdir(parents=True, exist_ok=True)
    return p


def installed_version() -> str:
    try:
        return (runtime_dir() / "version.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def download_runtime(manifest: dict) -> Path:
    version = str(manifest.get("runtime_version") or "").strip()
    parts = manifest.get("runtime_parts") or []
    expected_sha = str(manifest.get("runtime_sha256") or "").strip().lower()
    if not version or not isinstance(parts, list) or not parts or not expected_sha:
        raise ValueError("Manifest is missing runtime update fields")
    encoded = "".join(fetch_text(str(url)).strip() for url in parts)
    payload = base64.b64decode(encoded, validate=True)
    actual_sha = hashlib.sha256(payload).hexdigest().lower()
    if actual_sha != expected_sha:
        raise ValueError("Downloaded runtime failed SHA-256 verification")
    root = runtime_dir()
    target = root / "companion-runtime.pyw"
    temp = root / "companion-runtime.pyw.new"
    temp.write_bytes(payload)
    os.replace(temp, target)
    (root / "version.txt").write_text(version, encoding="utf-8")
    return target


def ensure_runtime(manifest: dict | None = None) -> tuple[Path, str]:
    root = runtime_dir()
    target = root / "companion-runtime.pyw"
    if manifest is None:
        manifest = fetch_manifest()
    wanted = str(manifest.get("runtime_version") or "").strip()
    current = installed_version()
    if not target.exists() or current != wanted:
        target = download_runtime(manifest)
        current = wanted
    return target, current


def library_root() -> Path:
    # Keep crop metadata beside the user's existing on-disk media library, not in browser storage.
    root = Path.home() / "Documents" / "NovelAI Media Library"
    root.mkdir(parents=True, exist_ok=True)
    return root


def crop_file() -> Path:
    return library_root() / CROP_FILE_NAME


def _normalize_crop(value) -> dict:
    if not isinstance(value, dict):
        return {"top": 0.0, "bottom": 0.0}
    try:
        top = max(0.0, min(0.89, float(value.get("top", 0.0) or 0.0)))
        bottom = max(0.0, min(0.89, float(value.get("bottom", 0.0) or 0.0)))
    except (TypeError, ValueError):
        top = bottom = 0.0
    if top + bottom > 0.90:
        scale = 0.90 / max(top + bottom, 0.000001)
        top *= scale
        bottom *= scale
    return {"top": round(top, 6), "bottom": round(bottom, 6)}


def load_crops() -> dict:
    with _crop_lock:
        path = crop_file()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("crops", data) if isinstance(data, dict) else {}
            if not isinstance(raw, dict):
                return {}
            out = {}
            for media_id, crop in raw.items():
                if not isinstance(media_id, str) or not media_id:
                    continue
                normalized = _normalize_crop(crop)
                if normalized["top"] > 0 or normalized["bottom"] > 0:
                    out[media_id] = normalized
            return out
        except Exception:
            return {}


def save_crops(crops: dict) -> None:
    with _crop_lock:
        root = library_root()
        path = crop_file()
        payload = {
            "schema": 1,
            "updated_at": int(time.time()),
            "crops": crops,
        }
        temp = root / (CROP_FILE_NAME + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)


def set_crop(media_id: str, crop: dict) -> dict:
    media_id = str(media_id or "").strip()
    if not media_id or len(media_id) > 256:
        raise ValueError("Invalid media id")
    normalized = _normalize_crop(crop)
    with _crop_lock:
        crops = load_crops()
        if normalized["top"] <= 0 and normalized["bottom"] <= 0:
            crops.pop(media_id, None)
        else:
            crops[media_id] = normalized
        save_crops(crops)
    return normalized


class CropHandler(BaseHTTPRequestHandler):
    server_version = "NovelAIMediaCrop/1.0"

    def log_message(self, format, *args):
        return

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Origin")
        self.send_header("Cache-Control", "no-store")

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "version": 1, "launcher": LAUNCHER_VERSION})
            return
        if path == "/api/crops":
            self._json(200, {"ok": True, "crops": load_crops()})
            return
        if path.startswith("/api/crop/"):
            media_id = unquote(path[len("/api/crop/"):])
            crop = load_crops().get(media_id, {"top": 0.0, "bottom": 0.0})
            self._json(200, {"ok": True, "media_id": media_id, "crop": crop})
            return
        self._json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/crop/"):
            self._json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length < 0 or length > 65536:
                raise ValueError("Invalid request size")
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            media_id = unquote(path[len("/api/crop/"):])
            crop = set_crop(media_id, data)
            self._json(200, {"ok": True, "media_id": media_id, "crop": crop})
        except Exception as exc:
            self._json(400, {"error": str(exc)})


def start_crop_server() -> None:
    global _crop_server
    try:
        server = ThreadingHTTPServer((CROP_HOST, CROP_PORT), CropHandler)
        server.daemon_threads = True
        _crop_server = server
        thread = threading.Thread(target=server.serve_forever, name="NovelAI Crop Metadata", daemon=True)
        thread.start()
    except OSError:
        # If an older/newer launcher already owns the sidecar port, keep the main runtime available.
        _crop_server = None


def show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(APP_NAME, message)
        root.destroy()
    except Exception:
        pass


def spawn_runtime(path: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(path), *sys.argv[1:]], close_fds=True)


def main() -> None:
    try:
        try:
            manifest = fetch_manifest()
            if maybe_update_launcher(manifest):
                restart_launcher()
                return
            runtime, current_version = ensure_runtime(manifest)
        except Exception as online_error:
            runtime = runtime_dir() / "companion-runtime.pyw"
            if not runtime.exists():
                raise RuntimeError(f"Could not download the NovelAI Media Library runtime.\n\n{online_error}")
            current_version = installed_version()

        start_crop_server()
        child = spawn_runtime(runtime)
        next_check = time.time() + CHECK_INTERVAL_SECONDS
        while True:
            code = child.poll()
            if code is not None:
                return
            now = time.time()
            if now >= next_check:
                next_check = now + CHECK_INTERVAL_SECONDS
                try:
                    manifest = fetch_manifest()
                    if maybe_update_launcher(manifest):
                        child.terminate()
                        try:
                            child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            child.kill(); child.wait(timeout=3)
                        restart_launcher()
                        return
                    wanted = str(manifest.get("runtime_version") or "").strip()
                    if wanted and wanted != current_version:
                        runtime = download_runtime(manifest)
                        current_version = wanted
                        child.terminate()
                        try:
                            child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            child.kill(); child.wait(timeout=3)
                        child = spawn_runtime(runtime)
                except Exception:
                    pass
            time.sleep(0.5)
    except Exception as exc:
        show_error(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
