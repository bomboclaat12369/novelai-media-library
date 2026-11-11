import json
from pathlib import Path
import sqlite3
import sys

root = Path(sys.argv[1])
library = json.loads((root / "Media data/library.json").read_text(encoding="utf-8"))
digest = (root / "import-id.txt").read_text()
matches = [item for item in library["media"] if item["sha256"] == digest and item["in_all"]]
assert len(matches) == 1 and matches[0]["favorite"] and len(library["media"]) == 9
with sqlite3.connect(root / "Original game save.sqlite3") as db:
    revision, state = db.execute("SELECT revision,body FROM save WHERE id=1").fetchone()
    assert revision == 1 and json.loads(state)["seed"] == 123456
print("Verified exactly one imported favorite in Main and the original game save.")
