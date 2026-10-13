import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_library_workflow import LibraryWorkflowTests
from app import make_server
from test_engine import artwork
fixture=LibraryWorkflowTests();fixture.setUp()
# Two copies of a near-identical but different pose, initially in the same visual group.
im=artwork();im.putpixel((310,100),(255,255,255));im.save(fixture.source/'different.png');im.save(fixture.source/'different-copy.png')
fixture.scan();server=make_server(fixture.engine)
print(json.dumps(dict(url=f'http://127.0.0.1:{server.server_port}/',incoming=str(fixture.source),character=fixture.owner['id'],base=str(fixture.base))),flush=True)
try:server.serve_forever()
finally:fixture.tearDown()
