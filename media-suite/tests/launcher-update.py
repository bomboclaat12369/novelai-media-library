"""Apply a verified replacement EXE from inside two open disposable Edge profiles."""
import json
import os
from contextlib import ExitStack
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def verify(older, profile, version):
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    assert profile.resolve() == (Path(os.environ["LOCALAPPDATA"]) / "NovelAI Media Suite").resolve()
    pointer = profile / "updates/active.json"
    withheld = pointer.with_suffix(".test-pending")
    # The earlier shortcut test leaves the verified release and two ordinary
    # Edge windows installed. Isolate these two new tabs on their own origins.
    with ExitStack() as stack:
        ports = []
        for _ in range(4):
            listener = stack.enter_context(socket.socket())
            listener.bind(("127.0.0.1", 0))
            ports.append(listener.getsockname()[1])
        (profile / "chrome-ports.json").write_text(json.dumps(ports))
    address = f"http://127.0.0.1:{ports[0]}/"
    endpoint = Request(address + "api/session", headers={"X-Suite-Request": "session"})
    offline = {**os.environ, "HTTPS_PROXY": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1",
               "NO_PROXY": "127.0.0.1,localhost"}
    pointer.replace(withheld)
    try:
        old = subprocess.Popen([older, "--resume-tabs"], env=offline)
        deadline = time.monotonic() + 40
        while True:
            try:
                with urlopen(endpoint, timeout=2) as response:
                    original = json.load(response)
                break
            except URLError:
                assert old.poll() is None and time.monotonic() < deadline, "Older host failed to listen"
                time.sleep(.2)
        assert original["version"] == "1.0.99"
        with sync_playwright() as pw, ExitStack() as cleanup:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            cleanup.callback(browser.close)
            first, second = browser.new_page(), browser.new_page()
            for tab, mode in ((first, "Workbench"), (second, "AfterHours")):
                tab.set_default_timeout(90_000)
                tab.goto(address)
                tab.locator("#mode-toggle").click()
                tab.locator("#" + mode).click()
                # This packaged fixture intentionally has no connected application folders.
                tab.locator("#panel-" + mode + " .feedback button").wait_for()
                tab.evaluate("m => sessionStorage.setItem('fixture-place', m)", mode)
            withheld.replace(pointer)
            first.locator("#mode-toggle").click()
            first.locator("#updates").click()
            first.get_by_role("button", name="Update Media Suite").click()
            expect(first.locator("#update-message")).to_contain_text(version + " is running in this tab", timeout=120_000)
            for tab, mode in ((first, "Workbench"), (second, "AfterHours")):
                expect(tab.locator("#" + mode)).to_have_attribute("aria-current", "page", timeout=30_000)
                assert tab.url == address and len(tab.context.pages) == 1
                assert tab.evaluate("sessionStorage.getItem('fixture-place')") == mode
                assert tab.evaluate("async () => (await session()).version") == version
            assert old.wait(timeout=15) == 0
            with urlopen(endpoint, timeout=3) as response:
                assert json.load(response)["token"] != original["token"]
        print("Verified a packaged launcher replacement at the original address. Both Edge tabs resumed their own mode.")
    finally:
        if withheld.exists():
            withheld.replace(pointer)
        subprocess.run([older, "--stop"], check=True, timeout=15)


if __name__ == "__main__":
    verify(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
