"""Drive the real suite pages in Edge with an isolated profile, library and career."""
import argparse
import ctypes
import json
import subprocess
import time
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


@contextmanager
def fixture_processes(host):
    # The companion launcher can leave a second Windows venv redirector between
    # itself and the runtime. Job membership follows every descendant.
    win = ctypes.WinDLL("kernel32", use_last_error=True)
    win.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    win.CreateJobObjectW.restype = wintypes.HANDLE
    win.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    win.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    win.CloseHandle.argtypes = [wintypes.HANDLE]
    job = win.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not win.AssignProcessToJobObject(job, int(host._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        yield
    finally:
        win.TerminateJobObject(job, 1)
        win.CloseHandle(job)


def until(frame, expression, arg=None):
    # Playwright's in-page wait_for_function uses eval, which the actual programs disallow.
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if frame.evaluate(expression, arg):
            return
        time.sleep(0.15)
    summary = frame.evaluate("() => (document.getElementById('nai-media-host')?.shadowRoot?.getElementById('app')?.innerText || document.body.innerText).slice(0,350)")
    raise AssertionError("Timed out checking " + expression[:120] + ". Fixture screen: " + summary)


def verify(page, address, root):
    page.set_default_timeout(120_000)
    page.goto(address)
    toggle = page.get_by_role("button", name="Mode", exact=True)
    picker = page.get_by_role("dialog", name="Choose a mode")

    def bottom_right():
        b = page.locator('#mode-toggle').bounding_box()
        size = page.viewport_size
        assert 0 <= size["height"] - b["y"] - b["height"] <= 24 and 0 <= size["width"] - b["x"] - b["width"] <= 24, b
        return b

    def full_viewport(frame_tag):
        size = page.viewport_size
        assert frame_tag.bounding_box() == {"x": 0, "y": 0, **size}, (frame_tag.bounding_box(), size)
        frame = frame_tag.element_handle().content_frame()
        assert frame.evaluate("[innerWidth, innerHeight]") == [size["width"], size["height"]]

    def section(name, label, keys=()):
        bottom_right()
        toggle.click()
        choice = picker.get_by_role("button", name=label, exact=True)
        if keys:
            for key in keys:
                page.keyboard.press(key)
            expect(choice).to_be_focused()
            page.keyboard.press("Enter")
        else:
            choice.click()
        expect(picker).to_be_hidden()
        frame_tag = page.locator(f'iframe[name="suite-{name}"]')
        try:
            frame_tag.wait_for(state="visible")
        except Exception:
            print("Connection status:", page.locator(f"#panel-{name} .feedback").inner_text()[:320], flush=True)
            raise
        full_viewport(frame_tag)
        assert frame_tag.evaluate("frame => [4, innerWidth / 2, innerWidth - 4].every(x => document.elementFromPoint(x, 4) === frame)"), 'The suite covers the top of the app.'
        print("Opened", label, "at full tab size", flush=True)
        return frame_tag.element_handle().content_frame()

    library = section("Library", "Media Library")
    select = library.locator("#characterSelect")
    select.locator("option").filter(has_text="Suite QA Patricia").wait_for(state="attached")
    owner = select.locator("option").filter(has_text="Suite QA Patricia").get_attribute("value")
    select.select_option(value=owner)
    library.get_by_text("Local library connected", exact=True).first.wait_for()
    expect(library.locator("#naiUpdateStatus")).to_be_hidden()
    until(library, "Array.from(document.getElementById('nai-media-host').shadowRoot.querySelectorAll('img')).some(img => img.naturalWidth > 0)")
    media_id = json.loads((root / "Media data/library.json").read_text(encoding="utf-8"))["media"][0]["id"]
    partial = page.request.get(library.url.split("/library/")[0] + f"/api/media/{media_id}/original", headers={"Range":"bytes=0-7"})
    assert partial.status == 206 and partial.headers["content-range"].startswith("bytes 0-7/")
    assert partial.body() == bytes.fromhex("89504e470d0a1a0a")

    library_frame = page.locator('iframe[name="suite-Library"]')
    desktop = page.viewport_size
    page.set_viewport_size({"width": 390, "height": 560})
    full_viewport(library_frame)
    corner = bottom_right()
    toggle.click()
    modes = picker.get_by_role("navigation", name="Suite modes").get_by_role("button")
    expect(modes).to_have_text(["Media Library", "Battles", "Workbench", "After Hours"])
    expect(picker.locator('[aria-current="page"]')).to_have_text("Media Library")
    expect(picker.get_by_role("button", name="Media Library")).to_be_focused()
    box = picker.bounding_box()
    assert box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= 390 and box["y"] + box["height"] <= 560
    assert box["y"] + box["height"] < corner["y"] and abs(box["x"] + box["width"] - corner["x"] - corner["width"]) <= 1
    full_viewport(library_frame)
    page.keyboard.press("Escape")
    expect(toggle).to_be_focused()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    toggle.click()
    page.mouse.click(6, 6)  # Over the underlying cross-origin app, outside the picker.
    expect(picker).to_be_hidden()
    page.set_viewport_size(desktop)
    full_viewport(library_frame)

    toggle.click()
    picker.get_by_role("button", name="Locations…").click()
    locations = page.get_by_role("dialog", name="Suite locations")
    locations.wait_for(state="visible")
    actual_library = Path(locations.locator("#libraryFolder").input_value())
    assert actual_library == root / "Media data", f"Unexpected library in Locations: {actual_library}"
    page.locator("#libraryFolder").fill(str(root / "missing folder"))
    page.get_by_role("button", name="Save locations").click()
    page.get_by_role("alert").filter(has_text="Could not find").wait_for()
    page.locator("#libraryFolder").fill(str(root / "Media data" / "library.json"))
    page.get_by_role("button", name="Save locations").click()
    page.get_by_role("dialog").wait_for(state="hidden")
    assert page.request.post(address + "api/locations", data={}).status == 403
    assert page.request.get(address + "api/session").status == 403
    assert page.request.get(address, headers={"Host": "example.org"}).status == 403

    bench = section("Workbench", "Workbench", keys=("Home", "ArrowDown", "ArrowDown"))
    expect(bench.locator("#programUpdate")).to_be_hidden()
    toggle.click()
    picker.get_by_role("button", name="Updates…").click()
    updates = page.get_by_role("dialog", name="Suite updates")
    expect(updates.locator("dt")).to_have_text(["Media Suite", "Media Library and Battles", "Workbench", "After Hours"])
    updates.get_by_text("Ready for next session · 2.0.1").wait_for()
    updates.get_by_role("button", name="Check for updates").click()
    updates.get_by_text("Ready for next session · 2.0.1").wait_for()
    updates.get_by_role("button", name="Close", exact=True).click()
    direct = page.context.new_page()
    try:
        ports = json.loads((root / "test-ports.json").read_text())
        direct.goto(f"http://127.0.0.1:{ports[0]}/library/")
        direct.get_by_role("button", name="Check updates", exact=True).wait_for()
        direct.goto((root / "Workbench data/state/running-url.txt").read_text().strip())
        direct.locator("#programUpdate").wait_for()
    finally:
        direct.close()
    post = bench.locator("#postList .post").filter(has_text="Post 2")
    until(bench, "!!document.getElementById('position')?.textContent && !document.getElementById('collectionPicker').disabled "
          "&& !!document.querySelector('#grid .card')")
    post.click()
    ident = (root / "import-id.txt").read_text().strip()
    until(bench, "id => document.getElementById('title').textContent.includes('Post 2') && "
          "Array.from(document.querySelectorAll('#grid .card')).some(c => c.dataset.id === id)", ident)
    bench.evaluate("window.suiteImportGate = new Promise(r => window.suiteResumeImport = r); window.suiteMark = 'same-document'")
    script = Path(__file__).with_name("workbench-import.js").read_text()
    bench.evaluate("id => { (" + script + ")(id).then(() => window.suiteFinished = true).catch(e => window.suiteFinished = e.message); }", ident)
    until(bench, "window.suiteImportStarted === true")

    battle = section("Battles", "Battles")
    battle.locator(".naiBattleWrap").wait_for()
    assert "Suite QA Patricia" in battle.locator(".naiBattleWrap h2").inner_text()
    game = section("AfterHours", "After Hours")
    try:
        until(game, """(() => {
            const app = document.getElementById('nai-media-host')?.shadowRoot?.getElementById('app');
            return app?.innerText.includes('Suite QA Patricia') || !!app?.querySelector('.error-panel');
        })()""")
        assert "Suite QA Patricia" in game.locator("#app").inner_text(), game.locator("#app").inner_text()[:350]
    except AssertionError:
        details = game.evaluate("""async () => {
            const paths = [...document.scripts].filter(s => s.src).map(s => new URL(s.src).pathname);
            const resources = await Promise.all([...paths, '/game/style.css', '/game/api/bootstrap', '/game/api/renderer'].map(async path => {
                const r = await fetch(path);
                return [path, r.status, r.headers.get('content-type')];
            }));
            const state = await fetch('/game/api/state');
            return {resources, renderer: typeof globalThis.AfterHoursCards, seed: state.ok ? (await state.json()).state?.seed : state.status};
        }""")
        print("Game fixture diagnostics:", details, flush=True)
        raise
    assert game.evaluate("async () => (await (await fetch('/game/api/state')).json()).state.seed") == 123456
    bench.evaluate("window.suiteResumeImport()")
    until(bench, "window.suiteFinished !== undefined")
    assert bench.evaluate("window.suiteFinished") is True
    returned = section("Workbench", "Workbench")
    assert returned.evaluate("window.suiteMark") == "same-document"
    assert "Post 2" in returned.locator("#title").inner_text()
    assert len(page.context.pages) == 1
    assert len({urlsplit(f.url).netloc for f in (page, library, bench, game)}) == 4
    assert page.evaluate("document.querySelector('iframe').contentDocument === null")
    forged = page.request.post(bench.url.replace("/organizer", "/api/organizer/related"),
                               headers={"Origin": "https://example.org"})
    assert forged.status == 403
    page.reload()
    page.locator('#panel-Workbench iframe').wait_for()
    toggle.click()
    expect(picker.locator('[aria-current="page"]')).to_have_text("Workbench")
    expect(picker.get_by_role("button", name="Workbench")).to_be_focused()
    page.keyboard.press("Escape")
    assert json.loads((root / "Suite profile/settings.json").read_text())["LastSection"] == "Workbench"
    print("Verified the full-size mode picker layout, keyboard and pointer switching, owner handoff, thumbnails, Locations, origin checks, an import during a switch, the original career and last mode.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("host_dll", type=Path)
    parser.add_argument("--dotnet", default="dotnet")
    args = parser.parse_args()
    fixture = args.fixture.resolve()
    with subprocess.Popen([args.dotnet, str(args.host_dll), str(fixture)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, text=True) as host, fixture_processes(host):
        try:
            address = host.stdout.readline().strip()
            assert address.startswith("http://127.0.0.1:"), address
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                try:
                    context = browser.new_context(viewport={"width": 1280, "height": 850})
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e).split("data:")[0][:200]))
                    page.on("response", lambda res: errors.append(f"{res.status} {urlsplit(res.url).path[:150]}")
                            if res.status >= 400 and res.url.startswith("http://127.0.0.1:") else None)
                    page.on("requestfailed", lambda req: errors.append(f"{req.failure} {urlsplit(req.url).path[:150]}")
                            if req.url.startswith("http://127.0.0.1:") else None)
                    try:
                        verify(page, address, fixture)
                        until(page, "presence.readyState === EventSource.OPEN")
                        def host_command(command):
                            host.stdin.write(command + "\n")
                            host.stdin.flush()
                            return host.stdout.readline().strip()
                        assert host_command("handoff") == "busy", "An open tab would have been restarted."
                        assert host_command("apply") == "waiting", "The suite restarted Workbench under an active tab."
                        another = browser.new_page()
                        another.goto(address)
                        until(another, "presence.readyState === EventSource.OPEN")
                        page.goto("about:blank")
                        assert host_command("handoff") == "busy", "A tab in a second profile would have been restarted."
                        another.close()
                        deadline = time.monotonic() + 30
                        while (result := host_command("apply")) != "applied":
                            assert time.monotonic() < deadline, f"A verified release did not resume after the last tab closed: {result}"
                            time.sleep(.2)
                        pointer = json.loads((fixture / "Workbench data/state/updates/active.json").read_text())
                        assert pointer["version"] == "2.0.1"
                        deadline = time.monotonic() + 15
                        while host_command("handoff") != "idle":
                            assert time.monotonic() < deadline, "Closed tabs prevented the update from applying."
                            time.sleep(.2)
                        print("Verified an open tab defers upgrades and closing it releases the host.")
                    except Exception:
                        print("Edge fixture errors:", errors[-12:], flush=True)
                        raise
                finally:
                    browser.close()
        finally:
            if host.poll() is None:
                host.communicate("\n", timeout=35)
        if host.returncode: raise SystemExit(host.returncode)
