"""Exercise a real headless companion update using disposable files and a private port."""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "media-suite/companion-session.py"


def wait_for(check):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, ValueError):
            pass
        time.sleep(.1)
    raise AssertionError("Disposable companion did not reach the expected state")


def verify(root):
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    program, state, library = (root / name for name in ("program", "state", "library"))
    runtime = program / ".runtime"
    runtime.mkdir(parents=True)
    state.mkdir()
    library.mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    code = (ROOT / "runtime-src/companion-runtime.pyw").read_text(encoding="utf-8").replace("PORT = 8765", f"PORT = {port}")
    code = code.replace("    def do_GET(self) -> None:\n", "    def do_GET(self) -> None:\n"
                        "        if self.path == '/_close-fixture':\n"
                        "            self._send_json(200, {})\n            self.server.shutdown()\n            return\n", 1)
    (runtime / "companion-runtime.pyw").write_text(code, encoding="utf-8")
    (runtime / "version.txt").write_text("1.0.0")
    body = (code + "\n# Next verified fixture release\n").encode()
    manifest = {"schema": 2, "runtime_version": "1.0.1", "runtime_sha256": hashlib.sha256(body).hexdigest(), "runtime_parts": ["fixture"]}
    feed = root / "feed.json"
    feed.write_text(json.dumps(manifest))
    part = root / "part.txt"
    part.write_bytes(base64.b64encode(body))
    launcher = (ROOT / "companion.pyw").read_text(encoding="utf-8")
    (program / "companion.pyw").write_text(launcher + f"\ndef fetch_text(url):\n    return Path({str(feed)!r} if url==MANIFEST_URL else {str(part)!r}).read_text()\n", encoding="utf-8")
    args = [str(program), str(state), str(library)]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    child = subprocess.Popen([sys.executable, str(HELPER), "serve", *args], creationflags=flags)
    base = f"http://127.0.0.1:{port}"

    def session():
        return json.loads((state / "session.json").read_text())

    def apply(token):
        request = urllib.request.Request(base + "/_media-suite/apply-runtime", data=b"", headers={"X-Suite-Companion": token})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    try:
        token = wait_for(session)["token"]
        stage = [sys.executable, str(HELPER), "stage", *args]
        assert subprocess.check_output(stage, creationflags=flags, text=True).strip() == "1.0.1"
        ready = (state / "ready.json").read_bytes()
        feed.write_text(json.dumps({**manifest, "runtime_version":"1.0.2", "runtime_sha256":"0"*64}))
        assert subprocess.run(stage, capture_output=True, creationflags=flags).returncode != 0
        assert (state / "ready.json").read_bytes() == ready
        assert session()["version"] == "1.0.0" and apply("unrelated") == 403
        with socket.create_connection(("127.0.0.1",port)) as held:
            held.sendall(b"GET /api/health HTTP/1.0\r\n")
            assert wait_for(lambda: apply(token) == 409), "A live request was interrupted"
            held.sendall(b"\r\n")
            assert held.recv(128).startswith(b"HTTP/")
        assert wait_for(lambda: apply(token) == 202)
        assert wait_for(lambda: session()["version"] == "1.0.1")
        with urllib.request.urlopen(base + "/api/health") as response:
            assert Path(json.load(response)["library_root"]) == library
        assert (runtime / "version.txt").read_text() == "1.0.0"
    finally:
        try:
            with urllib.request.urlopen(base + "/_close-fixture", timeout=4):
                pass
        except OSError:
            pass
        try:
            child.wait(timeout=12)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
        def closed():
            with socket.socket() as sock:
                return sock.connect_ex(("127.0.0.1",port)) != 0
        wait_for(closed)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as folder:
        verify(Path(folder))
    print("Verified companion staging, checksum failure, busy deferral, graceful activation and original library path.")
