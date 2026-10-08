# NovelAI Media Library

Local image/video library overlay for `novelai.net`, with a Tampermonkey front end and a local Python companion.

## Automatic updates

Starting with the v2.2 bootstrap, normal future updates require no copying or pasting.

- `novelai-media.user.js` is a small permanent Tampermonkey loader. It checks `manifest.json`, downloads the current UI payload from this repository, caches it locally, and runs it on NovelAI.
- `companion.pyw` is a small permanent launcher. It downloads the current verified Python runtime into a local `.runtime` folder, starts it, checks GitHub about once per minute, and automatically restarts the runtime when a new version is published.
- The launcher can also update **itself** from `manifest.json`, so future launcher changes do not require another manual replacement.
- Python runtime updates are SHA-256 verified before being installed.
- If GitHub is temporarily unavailable, both sides keep using their previously cached working version.

Your actual media library is not stored here. `library.json`, media files, thumbnails, and backups remain under your local `Documents\NovelAI Media Library` folder.

## One-time bootstrap for an existing installation

If you are coming from v2.1 or earlier, run `bootstrap-auto-update.bat` once:

1. Download and run `bootstrap-auto-update.bat`.
2. Select the existing NovelAI Media Library **program folder** — the folder that contains `companion.pyw` and `run.bat`.
3. The bootstrap replaces only the old program launcher, starts it, and opens the permanent Tampermonkey loader.
4. Approve Tampermonkey's Install/Update page once.

After that one transition, future UI, runtime, and launcher releases are pulled automatically from this repository.

The bootstrap does **not** modify or delete your media, categories, favorites, timestamps, thumbnails, or `library.json`.

## Fresh install

1. Download `companion.pyw`, `requirements.txt`, `setup.bat`, and `run.bat` into one folder.
2. Run `setup.bat` once.
3. Run `run.bat` whenever you use the NovelAI media viewer.
4. Install `novelai-media.user.js` in Tampermonkey once.

## Release layout

- `novelai-media.user.js` — stable Tampermonkey loader
- `companion.pyw` — stable/self-updating local launcher
- `manifest.json` — currently published versions and payload locations
- `payload/` — versioned UI/runtime payloads
- `setup.bat`, `run.bat`, `requirements.txt` — local Python setup/launch files

## Publishing updates

Payload files are published first and `manifest.json` is updated **last**. This prevents installed clients from seeing a release before all of its files are available. Runtime and launcher hashes in the manifest must match the exact published files.

## Standalone browser tab

With the companion running, open `http://127.0.0.1:8765/library/`, use **Open standalone** in the NovelAI overlay, or **Open Library Tab** in the companion window. You can bookmark the local page. NovelAI does not need to be open.

The standalone page shares the same files and metadata as the overlay, with independent browsing state. It starts in Dual mode: two viewers and the thumbnail panel each occupy one third of the window. Click a viewer (or its Viewer 1/2 button) to target subsequent thumbnail selections. The existing controls apply to that active viewer. Single mode keeps the first viewer at one third and expands thumbnails to the other two thirds; thumbnails default to five columns, with a remembered **4–8 per row** selector. Enlarged image thumbnails are generated on demand at an appropriate resolution and cached, rather than loading every original. Image and video selection share a compact, fixed-height footer. Selecting an inactive video viewer leaves playback unchanged; subsequent clicks play/pause normally.

The companion verifies and caches the standalone interface on first use. Internet access is needed for that first download; afterward the cached page remains available offline. Opening/reloading the page checks for interface updates, with a short cache interval. Returning to either tab checks for saved library changes; there is no continuous synchronization polling. Edits are not automatically refreshed while an import or editor is open.
