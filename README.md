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

## Sets (UI 2.8.70 / companion 2.7.35)

Duplicate names are numbered per character: `White Bikini`, `White Bikini 1`, `White Bikini 2`. Creating or renaming a set uses the next available number after the highest existing suffix; other characters have independent names.

Use the star on a set card or inside an open set to add it to **Favorite Sets**. This section is separate from image/video favorites, and favoriting a set does not change its members' flags.

An **Auto** badge marks an automatically chosen set thumbnail. Use the pin inside the set or Manage Sets to choose or confirm a cover. Older covers without provenance display **?** (Unconfirmed) until selected; their existing image is preserved. If a cover is removed, its automatic replacement receives the Auto badge.

**Update** now reloads only the interface where it is clicked, using the update already downloaded during a check. Refreshing checks for updates; the available version is shown beside Update. There is no shared activation or cross-tab reload. Close an open editor before updating and save NovelAI text when prompted.

## Local Duplicate Review integration (companion 2.7.36)

Local Duplicate Review 1.4 can compare incoming folders against a character's live
main and Set image records. Deleted originals retained for undo are excluded.
The local catalog reports imported IDs and Set names; the checker protects those
files from ordinary duplicate cleanup.

Its explicit replacement endpoint verifies the expected library/source, retains
the old original under `replacement-originals`, and changes only source fields on
the stable media record. Categories, favorites, crops and Set references remain.
A persistent operation ID makes retries idempotent after a lost response. The
checker verifies the committed library bytes before quarantining the download.
Undo restores source fields while preserving later metadata edits and rejects
conflicting source changes. Retained originals are not automatically purged.

This is a runtime-only release; the NovelAI and standalone UI remains 2.8.71.

## Set workflow improvements (UI 2.8.72 / companion 2.7.37)

Standalone image viewers have a bottom-right fullscreen icon. NovelAI's existing
image-click fullscreen behavior is unchanged. Set assignment uses visible live
search results and up to eight cached preview thumbnails of the selected Set.
Rapid Review assignment starts with no checked files and offers Select all and
Unselect all. Set searches are remembered per character for the browser session;
Recently updated sorts by the latest Set edit, cover/favorite change or membership
change. Assigning from Purgatory clears that status; uncategorized files remain
Set-only and categorized files also return to main Images/Videos.

## Duplicate Review coverage (companion 2.7.38 / checker 1.5.0)

The catalog exposes saved Review and Purgatory status alongside Main and Sets,
and supports All characters. Deleted originals retained for Undo stay excluded.
Duplicate Review 1.5 adds cached crop/rotation/mirror alignment for manual review,
scan coverage counts and explicit incomplete-scan notices. Unsaved browser
import queues must be saved before the companion can compare them.
The NovelAI and standalone interface remains 2.8.72.

## Simple updates and Set categories (UI 2.8.73 / companion 2.7.39)

Restart the companion once to load the new runtime, then refresh each interface.
If NovelAI initially starts the older cached UI, let its background download finish
and refresh once more to apply 2.8.73 without using the old Update button.

- Interface updates are independent. Update uses the cached release immediately;
  it no longer repeats preparation or waits for the other interface.
- Sets have their own categories per character. In Manage Sets, create/rename/delete
  categories, check the categories for a Set, and click Save set.
- Filter Sets, Favorite Sets, Manage Sets, and assignment pickers by category or
  Uncategorized Sets. Image/video categories and individual media are unchanged.
- Deleting a Set category removes its assignments and keeps the Sets and files.

Focused verification: category API validation/persistence, independent update
checks and reloads, and browser checks of the changed flows in both interfaces.

## Library duplicate scan and explicit Set removal (UI 2.8.74 / companion 2.7.40)

Local Duplicate Review 1.6.0 adds a library-only scan using live image records
from every saved area. Choose All characters or a single character, review the
matching copies, and keep/remove explicitly. Cleanup is atomic, hash-checked and
retryable through the companion. Originals and metadata remain available for Undo;
later conflicting changes block restoration instead of being overwritten.

Set thumbnails now have Remove controls, and the selected media's membership
row has Remove from Set. Both preserve the file and its metadata. Set-only media
removed from its final Set returns to main Images/Videos, while Review/Purgatory
placement stays intact. The Set editor's existing deselect-and-save path now
explains removal and has the same placement behavior.

Checker source: `duplicate-review/`. Packaged Windows app:
`downloads/Local-Duplicate-Review-1.6.0.zip`. Quit the older checker, extract the
new ZIP and launch its batch file. The checker retains its existing state in
LocalAppData; its package is updated separately from the media-library UI.

## Confirmed Set removal and replacement Undo (UI 2.8.75 / companion 2.7.41)

- Thumbnail Remove controls are gone. Use **Remove from Set** below the viewer,
  then confirm. Images in multiple Sets require choosing which Set to remove.
  Other memberships and the media file stay intact.
- Set searches are remembered inside Sets only. Leaving Sets for an image/video
  category or another character clears the search in the normal media browser.
- **Undo** now includes normal image source replacements. The previous original
  stays available within the 20-action history, including across restarts.
  Repeated replacements and subsequent deletions can be undone in order.
  Relationships, placement, favorites, and crops remain attached to the image.
- This cannot retroactively restore originals discarded by earlier versions.

Restart the companion and refresh NovelAI/the standalone tab. Focused checks cover
both interfaces, multi-Set removal, search scope, replacement/deletion ordering,
persistence, source verification, and failed-save protection.
