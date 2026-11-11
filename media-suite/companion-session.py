"""Stage verified companion releases and run the suite's headless Library service."""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import runpy
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time


def version(value):
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", value):
        raise ValueError("Invalid companion release version")
    return tuple(map(int, value.split(".")))


def save(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as f:
        json.dump(value, f)
    os.replace(f.name, path)


def verified(state):
    try:
        release = json.loads((state / "ready.json").read_text(encoding="utf-8"))
        version(release["version"])
        path = state / (release["version"] + ".pyw")
        if hashlib.sha256(path.read_bytes()).hexdigest() == release["sha256"]:
            return release["version"], path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def installed(program):
    folder = program / ".runtime"
    try:
        name = (folder / "version.txt").read_text().strip()
        version(name)
        if (folder / "companion-runtime.pyw").is_file():
            return name, folder / "companion-runtime.pyw"
    except (OSError, ValueError):
        pass
    return None


def stage(program, state):
    import msvcrt
    with (state / "stage.lock").open("a+b") as lock:
        if not lock.seek(0, os.SEEK_END):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        deadline = time.monotonic() + 150
        while True:
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.2)
        return stage_locked(program, state)


def stage_locked(program, state):
    # The installed launcher already verifies the published runtime parts. Give
    # it a private staging directory so a standalone launcher can update too.
    with tempfile.TemporaryDirectory(dir=state) as temp:
        launcher = Path(temp) / "companion.pyw"
        shutil.copyfile(program / "companion.pyw", launcher)
        native = runpy.run_path(str(launcher))
        manifest = native["fetch_manifest"]()
        wanted, digest = manifest["runtime_version"], manifest["runtime_sha256"]
        version(wanted)
        if not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Invalid companion checksum")
        ready = verified(state)
        if ready and version(ready[0]) >= version(wanted):
            if ready[0] == wanted and hashlib.sha256(ready[1].read_bytes()).hexdigest() != digest:
                raise ValueError("Conflicting companion release")
            return ready
        local = installed(program)
        if local and version(local[0]) > version(wanted):
            return local
        if local and hashlib.sha256(local[1].read_bytes()).hexdigest() == digest:
            candidate = Path(temp) / "runtime.pyw"
            shutil.copyfile(local[1], candidate)
        else:
            # Use the launcher's origin and checksum rules, fetching a few
            # independent parts at a time before its normal assembly step.
            parts = manifest.get("runtime_parts")
            prefix = "https://raw.githubusercontent.com/bomboclaat12369/novelai-media-library/main/payload/"
            if not isinstance(parts, list) or not 1 <= len(parts) <= 256 or any(
                    not isinstance(url, str) or not url.startswith(prefix) for url in parts):
                raise ValueError("Invalid runtime payload locations")
            with ThreadPoolExecutor(max_workers=5) as pool:
                downloaded = dict(zip(parts, pool.map(native["fetch_text"], parts)))
            native["download_runtime"].__globals__["fetch_text"] = downloaded.__getitem__
            candidate = native["download_runtime"](manifest)
        body = candidate.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("Companion failed verification")
        compile(body, str(candidate), "exec")
        target = state / (wanted + ".pyw")
        os.replace(candidate, target)
        save(state / "ready.json", {"version": wanted, "sha256": digest})
        return wanted, target


def busy(server):
    store = server.store
    thumbnails = getattr(store, "_thumbnail_worker", None)
    allowed = {threading.main_thread(), threading.current_thread(), thumbnails}
    if any(thread not in allowed for thread in threading.enumerate()):
        return True
    if thumbnails and store._thumbnail_queue.unfinished_tasks:
        return True
    return any(job["state"] == "receiving" and time.monotonic() - job["touched"] < 3600
               for job in getattr(store, "_uploads", {}).values())


def serve(program, state, library):
    choices = [item for item in (verified(state), installed(program)) if item]
    current, path = max(choices, key=lambda item: version(item[0])) if choices else stage(program, state)
    runtime = runpy.run_path(str(path))
    token = secrets.token_urlsafe(32)
    retired = False
    # Keep the normal runtime entry point, server setup, UI cache and shutdown.
    # Only suite-launched instances expose this authenticated graceful restart.
    class Handler(runtime["MediaHandler"]):
        def do_POST(self):
            if self.path != "/_media-suite/apply-runtime":
                return super().do_POST()
            if not secrets.compare_digest(self.headers.get("X-Suite-Companion", ""), token):
                return self._send_json(403, {"error": "Unknown suite session"})
            with self.server.admission:
                ready = verified(state)
                if not ready or version(ready[0]) <= version(current):
                    return self._send_json(200, {"current": current})
                if busy(self.server):
                    return self._send_json(409, {"busy": True})
                self.server.retiring = True
            try:
                self._send_json(202, {"version": ready[0]})
            finally:
                self.server.shutdown()

    class Server(runtime["MediaHTTPServer"]):
        def __init__(self, *args):
            super().__init__(*args)
            self.admission = threading.Lock()
            self.retiring = False
            self.RequestHandlerClass = Handler
            save(state / "session.json", {"version": current, "token": token, "port": self.server_port})

        def process_request(self, request, address):
            with self.admission:
                if self.retiring:
                    return self.shutdown_request(request)
                return super().process_request(request, address)

        def server_close(self):
            nonlocal retired
            super().server_close()
            retired = self.retiring

    entry = runtime["main"]
    entry.__globals__["MediaHTTPServer"] = Server
    sys.argv = [str(path), "--headless", "--root", str(library)]
    entry()
    return 75 if retired else 0


if __name__ == "__main__":
    mode, program, state, library = sys.argv[1:]
    program, state, library = map(Path, (program, state, library))
    state.mkdir(parents=True, exist_ok=True)
    if mode == "stage":
        print(stage(program, state)[0], flush=True)
    elif mode == "serve":
        command = [sys.executable, str(Path(__file__).resolve()), "session", str(program), str(state), str(library)]
        # Popen quotes all Windows paths, including custom Python installations.
        while True:
            result = subprocess.call(command)
            if result != 75:
                raise SystemExit(result)
    elif mode == "session":
        raise SystemExit(serve(program, state, library))
