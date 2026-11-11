"""Build the Windows suite's After Hours release from tracked Git blobs."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[2]
TOOLS = "tools/after-hours"
FILE_LIST = "after-hours-files.json"
GAME_MODULES = (
    "__init__ booking_state bookings catalog companion engine flavor library_snapshot "
    "management meeting_rules meetings migrations server stage_labels store"
).split()
WEB_FILES = "index.html app.js management-ui.js renderer.js style.css favicon.svg".split()
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def as_json(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode()


def card_paths(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from card_paths(key)
            yield from card_paths(child)
    elif isinstance(value, list):
        for child in value:
            yield from card_paths(child)
    elif isinstance(value, str) and value.startswith("assets/cards/"):
        if not re.fullmatch(r"assets/cards/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_.-]+", value):
            raise ValueError(f"Invalid card asset path {value!r}")
        yield value


def contents(rev):
    config_path = "release-standalone.json"
    config = json.loads(git("show", f"{rev}:{config_path}"))
    names = {"runtime-src/companion-runtime.pyw", "game/Launch.ps1", config_path,
             "game/stage-data/catalog.json", "game/stage-data/stage-labels.json"}
    names.update(f"game/{name}.py" for name in GAME_MODULES)
    names.update(f"game/web/{name}" for name in WEB_FILES)
    for suffix in ("ranks", "collection", "editions", "base-layout"):
        part, = (p for p in config["parts"] if p.endswith(f".{suffix}.txt"))
        if not re.fullmatch(r"payload/userscript-[0-9.]+\.[a-z-]+\.txt", part):
            raise ValueError(f"Invalid renderer part {part!r}")
        names.add(part)
    names.update(card_paths(config["title_artwork"]))
    for key in ("edition_catalog", "base_catalog"):
        path, = card_paths(config[key])
        names.add(path)
        names.update(card_paths(json.loads(git("show", f"{rev}:{path}"))))

    # Reading committed blobs keeps local line endings, personal data and build
    # output out of the archive. Reject missing paths and symlinks.
    blobs = {}
    for item in git("ls-tree", "-r", "-z", rev, "--", *sorted(names)).split(b"\0"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        if mode not in (b"100644", b"100755") or kind != b"blob":
            raise ValueError(f"Not a regular file: {path!r}")
        blobs[path.decode()] = oid
    if blobs.keys() != names:
        raise ValueError(f"Package entries differ from the allowlist: {sorted(names ^ blobs.keys())}")
    batch = subprocess.run(["git", "-C", str(ROOT), "cat-file", "--batch"], check=True,
                           input=b"\n".join(blobs.values()) + b"\n", stdout=subprocess.PIPE)
    stream = io.BytesIO(batch.stdout)
    files = {}
    for path, oid in blobs.items():
        actual, kind, length = stream.readline().split()
        if actual != oid or kind != b"blob":
            raise ValueError(f"Unexpected Git object for {path}")
        files[path] = stream.read(int(length))
        if stream.read(1) != b"\n":
            raise ValueError(f"Incomplete Git blob for {path}")
    return files


def build(output, revision="HEAD"):
    rev = git("rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()
    version = git("show", f"{rev}:game/release-version.txt").decode().strip()
    if not VERSION.fullmatch(version) or any(int(n) > 2147483647 for n in version.split(".")):
        raise ValueError("Expected a three-part numeric release version")
    files = contents(rev)
    entries = [{"path": name, "bytes": len(data), "sha256": digest(data)} for name, data in sorted(files.items())]
    files[FILE_LIST] = as_json({"schema": 1, "version": version, "files": entries})
    output.mkdir(parents=True, exist_ok=True)
    package = output / f"After-Hours-{version}.zip"
    with zipfile.ZipFile(package, "w") as bundle:
        for name, data in sorted(files.items()):
            # Fixed headers and stored entries reproduce the same checksum on
            # Windows and Linux regardless of checkout time or zlib version.
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, data)
    payload = package.read_bytes()
    adapter = git("show", f"{rev}:{TOOLS}/Update-AfterHours.ps1.in").decode("ascii").replace("\r\n", "\n")
    for token, value in {"@VERSION@": version, "@PACKAGE_BYTES@": str(len(payload)),
                         "@PACKAGE_SHA256@": digest(payload), "@FILES_SHA256@": digest(files[FILE_LIST])}.items():
        if adapter.count(token) != 1:
            raise ValueError(f"Expected one {token} in updater")
        adapter = adapter.replace(token, value)
    data = adapter.replace("\n", "\r\n").encode("ascii")
    (output / "Update-AfterHours.ps1").write_bytes(data)
    feed = {"schema": 1, "version": version, "updater_bytes": len(data), "updater_sha256": digest(data)}
    (output / "release-after-hours.json").write_bytes(as_json(feed))
    print(f"After Hours {version}: {len(entries)} files, {len(payload)} bytes, SHA-256 {digest(payload)}")
    return feed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    args = parser.parse_args()
    build(args.output.resolve(), args.revision)
