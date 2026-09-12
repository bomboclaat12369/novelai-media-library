from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP_NAME = "NovelAI Media Library"
MANIFEST_URL = "https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/manifest.json"
CHECK_INTERVAL_SECONDS = 60
DOWNLOAD_TIMEOUT_SECONDS = 15


def fetch_text(url: str) -> str:
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        f"{url}{sep}_={int(time.time())}",
        headers={"User-Agent": "NovelAI-Media-Library-Launcher/1.0", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8")


def fetch_manifest() -> dict:
    data = json.loads(fetch_text(MANIFEST_URL))
    if not isinstance(data, dict) or int(data.get("schema", 0)) < 2:
        raise ValueError("Invalid update manifest")
    return data


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
            runtime, current_version = ensure_runtime(manifest)
        except Exception as online_error:
            runtime = runtime_dir() / "companion-runtime.pyw"
            if not runtime.exists():
                raise RuntimeError(f"Could not download the NovelAI Media Library runtime.\n\n{online_error}")
            current_version = installed_version()

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
