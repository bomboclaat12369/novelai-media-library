"""Verify two successive idle game updates on the same Windows port and save."""

import argparse
from contextlib import closing
from http.client import HTTPConnection
import json
from pathlib import Path
import socket
import tempfile
import time
import zipfile

from build import FILE_LIST, write_release
from verify import Fixture, api, check, snapshot


def successors(fixture):
    template = Path(__file__).with_name("Update-AfterHours.ps1.in").read_text(encoding="ascii")
    with zipfile.ZipFile(fixture.package) as bundle:
        files = {name: bundle.read(name) for name in bundle.namelist() if name != FILE_LIST}
    major, minor, patch = map(int, fixture.version.split("."))
    for increment in (1, 2):
        version = f"{major}.{minor}.{patch+increment}"
        folder = fixture.root / ("fixture-release-" + version)
        marker = f"\n# Disposable handoff check for {version}\n".encode()
        write_release(folder, version, {**files, "game/__init__.py": files["game/__init__.py"] + marker}, template)
        yield folder


def stage(fixture, port):
    with fixture.downloads_from_fixture():
        fixture.run("Stage", port, network=True)


def protected_during_play(fixture, port, boot):
    # This socket uses the same EventSource endpoint as a top-level game tab.
    # Leave it open beyond the ordinary quiet period without sending any ticks.
    with closing(HTTPConnection("127.0.0.1", port, timeout=8)) as client:
        client.request("GET", "/game/api/player-presence?key=" + boot["player_presence"])
        with client.getresponse() as response:
            check(response.status == 200 and response.readline().startswith(b":"), "Player presence did not open")
            time.sleep(3.2)
            fixture.run("Apply", port, expected=75)
            check(not (fixture.version_dir / "selected").exists(), "An open standalone tab was interrupted")

    # Send only the first byte of an authenticated request. The game must
    # reject a handoff even before the rest of the action body has arrived.
    with closing(HTTPConnection("127.0.0.1", port, timeout=12)) as client:
        client.putrequest("POST", "/game/api/backup")
        client.putheader("X-Game-Token", boot["token"])
        client.putheader("Content-Type", "application/json")
        client.putheader("Content-Length", "2")
        client.endheaders()
        client.send(b"{")
        time.sleep(3.2)
        fixture.run("Apply", port, expected=75)
        client.send(b"}")
        with client.getresponse() as response:
            check(response.status == 200 and "backups" in json.loads(response.read()), "In-flight request was lost")


def verify(root, release, previous=None):
    f = Fixture(root, release)
    next_releases = list(successors(f))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    stage(f, port)
    with f.playing(packaged=False, port=port, standalone=True) as (_, boot):
        check(not boot.get("player_presence"), "Independent launcher acquired suite ownership")
        f.run("Apply", port, expected=75)
        check(api(port, "api/bootstrap")["token"] == boot["token"], "Independent game was interrupted")
    if previous:
        f.use_release(previous)
        stage(f, port)
        f.run("Apply", port)
        with f.playing(packaged=True, port=port) as (_, boot):
            check(not boot.get("player_presence"), "Expected a legacy, unowned session")
            f.use_release(release)
            f.run("Apply", port, expected=75)
            check(api(port, "api/bootstrap")["token"] == boot["token"], "Legacy session was interrupted")
    f.run("Apply", port)
    state = None
    restored = None
    for index, target in enumerate(next_releases):
        with f.playing(packaged=True, port=port) as (_, boot):
            check(boot.get("player_presence"), "Selected game did not register a managed session")
            if index == 0:
                state = api(port, "api/action", {"action": "new", "revision": 0, "id": "idle-handoff-founders",
                            "body": {"selected": ["a", "b"], "seed": 882}}, boot["token"])["state"]
                exported = api(port, "api/export")
                revision = api(port, "api/state")["revision"]
                api(port, "api/restore", {"revision": revision, "export": exported}, boot["token"])
                boot = api(port, "api/bootstrap")
                restored = api(port, "api/backups")["save_name"]
            check(boot["state"] == state and api(port, "api/backups")["save_name"] == restored,
                  "Update lost the club or restore pointer")
            with closing(HTTPConnection("127.0.0.1", port, timeout=3)) as client:
                client.request("POST", "/game/api/suite-handoff", headers={"X-After-Hours-Owner": boot["token"]})
                with client.getresponse() as response:
                    check(response.status == 403, "A browser game token could retire the server")
                    response.read()
            f.use_release(target)
            stage(f, port)
            if index == 0:
                protected_during_play(f, port, boot)
            time.sleep(3.2)
            f.run("Apply", port)
            check(not f.stop.exists(), "The test stopped the server instead of the updater")
            with socket.socket() as connection:
                connection.settimeout(2)
                check(connection.connect_ex(("127.0.0.1", port)) != 0, "Old service retained its port")
            check(not (f.state / "payload/owner.json").exists(), "Old launcher retained session ownership")
    with f.playing(packaged=True, port=port) as (_, boot):
        check(boot["state"] == state and api(port, "api/backups")["save_name"] == restored, "Second update lost the club")
    check(snapshot(f.library) == f.library_before and not f.browser.exists(), "Library or browser changed")
    print("Two consecutive idle handoffs passed on one port and restored save. Active players, requests and independent games deferred.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--previous", type=Path, help="Optional previously released adapter without handoff support")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="handoff-", dir=args.scratch) as temp:
        verify(Path(temp).resolve(), args.output.resolve(), args.previous.resolve() if args.previous else None)
