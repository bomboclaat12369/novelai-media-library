"""Build throwaway copies of the three installations and a real existing QA save."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from PIL import Image

REPO = Path(__file__).resolve().parents[2]

def prepare(root, source):
    root.mkdir(parents=True, exist_ok=False)
    media = root / "Media data"
    runtime = runpy.run_path(str(REPO / "runtime-src/companion-runtime.pyw"))
    store = runtime["LibraryStore"](media)
    store._queue_image_thumbnail = lambda *a: None
    owners = [store.add_character(name)["id"] for name in ("Suite QA Patricia", "Suite QA Nikki")]
    for owner_index, owner in enumerate(owners):
        for index in range(4):
            data = io.BytesIO()
            Image.new("RGB", (120, 160), (50 * index, 65 * owner_index, 120)).save(data, "PNG")
            item, _ = store.import_bytes(data.getvalue(), f"{owner_index}-{index}.png", owner, [], {}, "image/png")
            item["in_all"] = True
    store.save()
    config = json.loads((REPO / "release-standalone.json").read_text())
    body = (REPO / "payload" / f"standalone-{config['version']}.html").read_bytes()
    cache = media / ".ui-cache"
    cache.mkdir(exist_ok=True)
    (cache / "standalone.json").write_text(json.dumps({"sha256": hashlib.sha256(body).hexdigest(),
                                                      "body": base64.b64encode(body).decode("ascii")}))
    companion = root / "Companion program"
    (companion / ".runtime").mkdir(parents=True)
    shutil.copy(REPO / "companion.pyw", companion)
    shutil.copy(REPO / "runtime-src/companion-runtime.pyw", companion / ".runtime")
    manifest = json.loads((REPO / "manifest.json").read_text())
    (companion / ".runtime/version.txt").write_text(manifest["runtime_version"])

    shutil.copytree(REPO / "runtime-src", root / "runtime-src")
    bench = root / "Workbench program"
    shutil.copytree(REPO / "duplicate-review", bench, ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests"))
    sys.path.insert(0, str(REPO / "duplicate-review/tests"))
    from test_organizer import fixture
    _, bulk, _, identifiers = fixture(root / "Workbench data")
    bulk.current["config"]["character_id"] = owners[0]
    bulk.persist()
    (root / "import-id.txt").write_text(identifiers[3])

    project = root / "Game project"
    game = project / "game"
    game.mkdir(parents=True)
    for pattern in ("*.py", "Launch.ps1"):
        for path in (source / "game").glob(pattern):
            shutil.copy(path, game)
    shutil.copytree(source / "game/web", game / "web")
    shutil.copytree(source / "runtime-src", project / "runtime-src")
    shutil.copytree(source / "assets", project / "assets")
    shutil.copy(source / "release-standalone.json", project)
    game_config = json.loads((source / "release-standalone.json").read_text())
    for relative in game_config["parts"]:
        if any(relative.endswith("." + name + ".txt") for name in ("ranks","collection","editions","base-layout")):
            (project / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source / relative, project / relative)
    sys.path.insert(0, str(project))
    from game.catalog import read_library
    from game.store import GameStore
    save = root / "Original game save.sqlite3"
    game_store = GameStore(save, read_library(media))
    game_store.apply("new", {"selected": owners, "seed": 123456}, "suite-original-save", 0)
    (game / "local.json").write_text(json.dumps({"python": sys.executable, "library": str(media), "save": str(save)}))
    if sys.platform == "win32":
        for program in (companion, bench):
            subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(program / ".venv")], check=True)
    (root / "suite-qa.json").write_text(json.dumps({"LibraryFolder": str(media), "CompanionFolder": str(companion),
        "WorkbenchFolder": str(bench), "GameFolder": str(game), "LastSection": "Library"}))

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("new_directory", type=Path)
    p.add_argument("game_checkout", type=Path)
    a = p.parse_args()
    prepare(a.new_directory.resolve(), a.game_checkout.resolve())
