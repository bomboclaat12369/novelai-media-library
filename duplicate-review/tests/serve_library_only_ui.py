import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_library_only import LibraryOnlyTests
from app import make_server
fixture=LibraryOnlyTests();fixture.setUp();fixture.prepare_library()
# Start with the normal mode; exercise the mode selector and a real rescan in-browser.
fixture.scan()
server=make_server(fixture.engine)
print(json.dumps(dict(url=f'http://127.0.0.1:{server.server_port}/',character=fixture.owner['id'])),flush=True)
try:server.serve_forever()
finally:fixture.tearDown()
