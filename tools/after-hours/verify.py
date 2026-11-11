"""Exercise the suite adapter with Windows PowerShell and a disposable real game."""

import argparse
from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zipfile


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(folder):
    return {p.name: sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()}


def api(port, path, body=None, token=None, raw=False):
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        headers = {"Content-Type": "application/json", "X-Game-Token": token or ""}
        connection.request("GET" if body is None else "POST", "/game/" + path,
                           None if body is None else json.dumps(body), headers)
        response = connection.getresponse()
        data = response.read()
        check(response.status < 300, f"{path} returned HTTP {response.status}: {data[:250]!r}")
        return data if raw else json.loads(data)
    finally:
        connection.close()


class Fixture:
    def use_release(self, output):
        self.feed = json.loads((output / "release-after-hours.json").read_bytes())
        self.version = self.feed["version"]
        self.package = output / f"After-Hours-{self.version}.zip"
        self.adapter = output / "Update-AfterHours.ps1"
        data = self.adapter.read_bytes()
        check(len(data) == self.feed["updater_bytes"] and sha(data) == self.feed["updater_sha256"], "Adapter vs feed")

    @property
    def version_dir(self):
        return self.state / "payload" / self.version

    def __init__(self, root, output):
        self.root = root
        self.use_release(output)
        self.shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        self.state = root / "suite cache"
        self.state.mkdir()
        self.suite_records = {}
        for name in ("active.json", "staged.json"):
            (self.state / name).write_text('{"owner":"suite"}', encoding="utf-8")
        self.suite_records = snapshot(self.state)
        self.install = root / "installed" / "game"
        with zipfile.ZipFile(self.package) as package:
            package.extractall(self.install.parent)
        self.library = root / "library [fixture]"
        self.library.mkdir()
        library = {"_tracking_store": "after-hours-release-fixture",
                   "characters": [{"id": key, "name": key.upper()} for key in "abc"],
                   "media": [{"id": key, "character_id": key, "stored_rel": "fixture.png",
                              "thumb_rel": "fixture.png", "in_all": True, "media_type": "image"} for key in "abc"]}
        (self.library / "library.json").write_text(json.dumps(library))
        (self.library / "battles.json").write_text('{"boards":{}}')
        (self.library / "fixture.png").write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c02"
            "0000000b4944415478da6364f80f00010501012718e3660000000049454e44ae426082"))
        self.library_before = snapshot(self.library)
        self.db_name = sha(library["_tracking_store"].encode())[:16] + ".sqlite3"
        self.selected_python = self.install / "Selected Python/Scripts/python.exe"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(self.install / "Selected Python")], check=True)
        self.config = {"python": str(self.selected_python.relative_to(self.install)), "library": "../unused library"}
        self.write_config()
        self.trace = root / "trace.jsonl"
        self.stop = root / "stop"
        self.browser = root / "browser-opened"
        probe = root / "probe"
        probe.mkdir()
        # The test process reports its real executable, cwd and script. Intercept
        # browser calls and give only fixture children a clean shutdown signal.
        (probe / "sitecustomize.py").write_text(
            "import json, os, sys, threading, time, webbrowser\n"
            "from pathlib import Path\n"
            "if sys.argv[0].endswith('.pyw'):\n"
            "    def opened(*args, **kwargs): Path(os.environ['AH_TEST_BROWSER']).touch()\n"
            "    webbrowser.open = webbrowser.open_new_tab = webbrowser.open_new = opened\n"
            "    with open(os.environ['AH_TEST_TRACE'], 'a') as f:\n"
            "        f.write(json.dumps([sys.executable, os.getcwd(), sys.argv]) + '\\n')\n"
            "    def watch():\n"
            "        while not Path(os.environ['AH_TEST_STOP']).is_file(): time.sleep(.1)\n"
            "        os._exit(0)\n"
            "    threading.Thread(target=watch, daemon=True).start()\n",
            encoding="utf-8")
        self.env = {**os.environ, "PYTHONPATH": str(probe), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
                    "AH_TEST_TRACE": str(self.trace), "AH_TEST_STOP": str(self.stop), "AH_TEST_BROWSER": str(self.browser)}
        self.env.pop("AFTER_HOURS_DATA", None)
        self.bad_download = False
        self.downloads = 0

    def write_config(self):
        self.config_bytes = json.dumps(self.config).encode()
        (self.install / "local.json").write_bytes(self.config_bytes)

    @contextmanager
    def downloads_from_fixture(self):
        fixture = self

        class Download(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path != "/" + fixture.package.name:
                    return self.send_error(404)
                fixture.downloads += 1
                self.send_response(200)
                self.send_header("Content-Length", str(fixture.package.stat().st_size))
                self.end_headers()
                with fixture.package.open("rb") as data:
                    if fixture.bad_download:
                        self.wfile.write(bytes([data.read(1)[0] ^ 1]))
                    shutil.copyfileobj(data, self.wfile)

        with ThreadingHTTPServer(("127.0.0.1", 0), Download) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            # Only the network fixture copy points at the loopback origin. All
            # other invocations run the exact feed-pinned production script.
            release_url = b"https://github.com/bomboclaat12369/novelai-media-library/releases/download/after-hours-v$ReleaseVersion"
            data = self.adapter.read_bytes()
            check(data.count(release_url) == 1, "Expected the fixed release asset origin")
            self.network_adapter = self.root / "fixture-updater.ps1"
            self.network_adapter.write_bytes(data.replace(release_url, f"http://127.0.0.1:{server.server_port}".encode()))
            try:
                yield
            finally:
                server.shutdown()
                thread.join()

    def command(self, phase, port, script=None):
        return [str(self.shell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(script or self.adapter), "-Phase", phase, "-GameFolder", str(self.install),
                "-StateFolder", str(self.state), "-Port", str(port), "-Library", str(self.library)]

    def run(self, phase, port, expected=0, network=False):
        proc = subprocess.run(self.command(phase, port, self.network_adapter if network else self.adapter),
                              cwd=self.install, env=self.env, capture_output=True, timeout=120,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        check(proc.returncode == expected, f"{phase} exited {proc.returncode}, expected {expected}: "
              f"{(proc.stdout + proc.stderr)[-1750:].decode(errors='replace')}")

    @contextmanager
    def playing(self, packaged, port=None, standalone=False):
        if port is None:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
        self.stop.unlink(missing_ok=True)
        log_path = self.root / "launch.log"
        with log_path.open("wb") as log:
            command = self.command("Launch", port)
            if standalone:
                command = command[:command.index("-File")+1] + [str(self.install / "Launch.ps1"),
                          "-NoBrowser", "-Port", str(port), "-Library", str(self.library)]
            proc = subprocess.Popen(command, cwd=self.install, env=self.env, stdout=log,
                                    stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline and proc.poll() is None:
                    try:
                        boot = api(port, "api/bootstrap")
                        break
                    except OSError:
                        time.sleep(.15)
                else:
                    raise AssertionError("Game did not start: " + log_path.read_text(errors="replace")[-1900:])
                executable, cwd, argv = json.loads(self.trace.read_text().splitlines()[-1])
                check(Path(executable) == self.selected_python and Path(cwd) == self.install, "Original Python and cwd")
                tree = self.version_dir / self.selection() if packaged else self.install.parent
                check(Path(argv[0]).resolve() == tree / "runtime-src/companion-runtime.pyw", "Wrong game code launched")
                check("--open-game" not in argv and not self.browser.exists(), "Unexpected browser launch")
                check(boot["restartable"] and set(boot["catalog"]["people"]) == set("abc"), "Library handoff")
                yield port, boot
            finally:
                self.stop.touch()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
                    proc.wait(timeout=10)
        check(proc.returncode == 0, "Game exited unexpectedly")
        check((self.install / "local.json").read_bytes() == self.config_bytes, "Game configuration changed")

    def selection(self):
        return (self.version_dir / "selected").read_text()

    def verify(self):
        with self.downloads_from_fixture(), self.playing(packaged=False) as (port, boot):
            old = api(port, "api/action", {"action": "new", "revision": 0, "id": "release-founders",
                      "body": {"selected": ["a", "b"], "seed": 4321}}, boot["token"])
            self.run("Stage", port, network=True)
            self.run("Apply", port, expected=75)
            check(not (self.version_dir / "selected").exists(), "Stage activated a running game")
            check(api(port, "api/state")["state"] == old["state"], "Running game changed during Stage")
        default_save = self.install / "data" / self.db_name
        check(default_save.is_file(), "Original default save path")
        cached = self.version_dir / "game.zip"
        with cached.open("r+b") as data:
            data.write(b"X")
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            self.run("Apply", port, expected=75)
        self.run("Apply", port, expected=1)
        with self.downloads_from_fixture():
            self.bad_download = True
            self.run("Stage", port, expected=1, network=True)
            self.bad_download = False
            self.run("Stage", port, network=True)
        self.run("Stage", port)
        self.run("Apply", port)
        first_selection = self.selection()
        self.run("Apply", port)
        check(first_selection == self.selection() and self.downloads == 3, "Retry or offline cache was not idempotent")
        with self.playing(packaged=True) as (port, boot):
            check(boot["state"] == old["state"] and boot["night_duration"] == 180, "Default saved club or game version")
            check(api(port, "api/backups")["save_name"] == self.db_name, "Default save filename")
            for name in ("ranks", "collection", "editions", "base"):
                check(len(api(port, f"renderer/{name}.js", raw=True)) > 100, f"Missing {name} renderer")
            renderer = api(port, "api/renderer")
            art = renderer["titles"]["team_captain"].removeprefix("/game/")
            check(bool(api(port, art, raw=True)) and bool(api(port, "app.js", raw=True)), "Packaged game assets")
            self.run("Stage", port)
            self.run("Apply", port, expected=75)
            self.run("Launch", port, expected=75)
            exported = api(port, "api/export")
            api(port, "api/restore", {"revision": boot["revision"], "export": exported}, boot["token"])
            restored_name = api(port, "api/backups")["save_name"]
        pointer = default_save.with_suffix(".active.json")
        check(json.loads(pointer.read_bytes())["file"] == restored_name, "Game restore pointer")
        save_dir = self.root / "installed" / "custom saves"
        save_dir.mkdir()
        custom = save_dir / "club.sqlite3"
        for source, dest in ((default_save, custom), (default_save.parent / restored_name, save_dir / restored_name)):
            with sqlite3.connect(source) as original, sqlite3.connect(dest) as copy:
                original.backup(copy)
            original.close()
            copy.close()
        custom_pointer = custom.with_suffix(".active.json")
        custom_pointer.write_bytes(pointer.read_bytes())
        pointer_before = custom_pointer.read_bytes()
        self.config["save"] = str(Path("..") / save_dir.name / custom.name)
        self.write_config()
        with self.playing(packaged=True) as (port, boot):
            check(api(port, "api/backups")["save_name"] == restored_name and boot["state"] == old["state"],
                  "Relative configured save or restored club")
        # A post-apply modification, including an extra importable module,
        # invalidates the cached tree. Launch must still open the installed game.
        (self.version_dir / first_selection / "game" / "unexpected.py").write_text("raise AssertionError()")
        with self.playing(packaged=False) as (port, _):
            check(api(port, "api/backups")["save_name"] == restored_name, "Original fallback lost the restored save")
        self.run("Apply", port)
        check(first_selection != self.selection(), "A damaged selected release could not be repaired")
        del self.config["save"]
        self.write_config()
        self.env["AFTER_HOURS_DATA"] = str(Path("..") / save_dir.name)
        (save_dir / self.db_name).with_suffix(".active.json").write_bytes(pointer_before)
        with self.playing(packaged=True) as (port, boot):
            check(api(port, "api/backups")["save_name"] == restored_name and boot["state"] == old["state"],
                  "Relative AFTER_HOURS_DATA or restored save was lost")
        check(custom_pointer.read_bytes() == pointer_before, "Original restore pointer changed")
        check(snapshot(self.library) == self.library_before and snapshot(self.state) == self.suite_records,
              "Library or suite-owned records changed")
        check(not self.browser.exists(), "A browser was opened")
        print("Windows PowerShell verified Stage, safe Apply, headless Launch, saved clubs, restore, and fallback.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, help="Existing parent for disposable data")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ah-", dir=args.scratch) as temp:
        Fixture(Path(temp).resolve(), args.output.resolve()).verify()
