# Workbench as a bulk image importer

Status: implemented and tested locally; not published. Candidate Workbench 2.0.23
and companion runtime 2.7.76. Media Library UI 2.9.25 already supplies the shared
Rapid Review tools and does not need a new UI payload for this change.

## User flow

Workbench opens Bulk Import & Folder Organizer. Choose a girl and her folders,
then browse posts or **All images**. Select thumbnails, a whole page/post, or a
range with Shift-click. The large viewer retains arrow navigation, Space to
select, fullscreen, Up next and source locations. **Original quality** loads the
source file only when requested; thumbnails stay lazy and inexpensive.

**Save individual images…** saves the current selection without requiring a set.
Choose Main, selected image categories, Review first, or Purgatory. Image
categories can be created here. Favorite, Featured and Needs replacement are
optional. These flags are additions: unchecked flags never clear metadata on
an existing library image. Category-only imports obey the library's regular vs
ghost category behavior; choosing Main explicitly adds the image to Main.

The **Import queue** survives restart, collection switching and refreshed
inventories. It follows verified duplicate-to-keeper connections through saved
hashes. Edit choices by selecting queued images and saving again; remove from
the queue or use local Undo without deleting originals. Missing/discarded
sources are retained as unavailable entries, not silently forgotten.

**Import to library** previews the operation. When individual images are queued,
the default applies those only; include saved set drafts explicitly if desired.
With no individual queue, existing set-only transfer behavior remains available.
Images may be added to Main and a set together. Review/Purgatory plus a set in
the same operation requires resolving the conflicting destination first.

Originals are copied byte for byte to the library; originals in source folders
stay in place. Stop waits for the current file and leaves the batch unapplied.
Reopening the preview reuses already copied hashes. Applying validates current
membership and commits destinations together with a checkpoint. Unavailable,
changed or cross-library inputs block the operation rather than guessing.

Review first places new images in the exact persistent Rapid Review queue used
by the library uploader. Open Media Library, select the girl, and choose
**Resume Rapid Review**. Cropping, individual decisions, categories, favorites,
Featured, replacement flags, set matching and bulk actions remain available.
Existing library images are not demoted to Review/Purgatory. An image already
in Rapid Review keeps its saved choices and is not duplicated or promoted by
an unrelated Workbench import.

## Import-path comparison

Audited the active release modules, not older payload versions:
`payload/userscript-2.9.12.part01.txt`, `userscript-2.8.96.review-core.txt`,
`userscript-2.9.12.sets.txt`, the current crop modules, and the companion's
register/rapid-review/organizer APIs. The Workbench side is `organizer.py`,
`organizer.html`, `organizer-workflow.js`, and `app.py`.

| Capability | Workbench behavior |
| --- | --- |
| Single or bulk images with no set | Saved individual queue; direct Main import |
| Normal and ghost image categories | Same companion validation and Main placement rules; create categories while queuing |
| Favorites, Featured, replacement flag | Per-selection choices; additive for existing images |
| Cropping and detailed import review | Same persistent library Rapid Review queue; not a second crop implementation |
| New/existing sets, names, colors and set categories | Existing organizer set workflow retained; optional in import preview |
| Exact duplicates | Reuse library identity; pending Rapid Review copies are recognized too |
| Visual duplicate comparison and source replacement | Side-by-side import preview, original-quality zoom, saved scan candidates or manual library search; Keep / Replace / Import separately |
| Original bytes and image dimensions | Shared library registration; original-quality inspection available before import |
| Ratings, card traits/framing, favorites, memberships | Existing media IDs retained; import route does not reset these fields |
| Visual similarity, source post links, stars, Later, saved progress | Existing organizer features retained |
| Pause/resume and recovery | Saved queue, resumable copies, stop-after-current-file, stale-preview validation, coordinated checkpoints |
| Provenance and future tracking | Original paths, origins, keeper/copy links, choices and apply results in the durable journal; export/checkpoint preserved |
| Raw URLs and drag/drop of loose files | Existing library uploader remains available; not newly implemented inside Workbench |
| Editing existing records | Workbench can rename sets, edit set colors/categories/favorites/Set Purgatory, and change image categories in the library or Rapid Review. Other image controls remain in the library. |

There is no claim that all library controls have been moved into Workbench.
The import path retains their availability and uses the shared review workflow.
Replacing an existing image is a distinct reviewed operation, not what the
Needs replacement flag does. Local Undo edits queued choices and set drafts;
restoring an applied transfer uses its checkpoint or normal library tools.

## Direct editing and import preview repair (Workbench 2.0.27)

Image cards and the large viewer have an **Edit** action. An existing library
image opens its current categories, including selected and ghost categories;
saving replaces its category choices through the same companion API as the
library. Native Main/holding-area rules still apply and are explained when
editing a held image. Rapid Review images stay in their queue; category edits
preserve their crop, other choices, queue cursor, selection and scroll position.
In the Workbench import queue, Edit reopens that image's saved destination,
categories and flags without importing it. Outside that queue, an unimported
image opens import choices; an already imported image can open either editor.

**Edit set** loads a library set's current name, colors, categories, favorite
and Set Purgatory status. **Save to library** applies changed metadata directly.
Set membership is not submitted or replaced. Cached metadata is refreshed,
while pending member additions/removals and unrelated unsent draft fields are
preserved. New local set drafts also have an editable name in Set details.
Edits validate the selected character/library and re-read the target before
saving, rejecting stale details rather than silently overwriting them. Ordinary
library edits use the companion's existing Undo and tracking services.

An oversized preview was reproduced over real HTTP: a healthy companion rejects
a request beyond its 24 MiB JSON limit before reading the body, and the former
client reported the closed socket as "Cannot reach the media companion". The
preview no longer serializes the organizer backup (including undo snapshots,
dispositions and post history). It sends only the selected drafts/imports,
their source records and relevant duplicate choices. Full exported history and
provenance remain intact and still transfer on Apply. A regression with over
25 MiB of undo history now produces a small, successful preview.

Oversized JSON is caught before transmission; refusal, disconnection and timeout
have separate messages. All organizer transfer stages allow the existing long
operation timeout. Failed previews remain visible with **Retry preview**, and
never automatically retry a write. This reproduces a cause of the reported
error; it does not establish the exact request size on the user's Windows PC.

Preparation checks passed: 215 companion tests, 187 Workbench tests, 77 DOM
tests, 364 native production-card renders, and 13 release-pipeline tests. The
native renderer was also run explicitly with the pinned canvas dependency to
verify its completion report. The new edit and import regressions use real
local HTTP servers and disposable libraries. No live Windows UI check.
Workbench 2.0.27 was published and verified; see
`releases/2026-11-10-workbench-import-editing.json`.

## Stay in place when queueing (Workbench 2.0.28)

**Save to import queue** updates the count and image badges without opening a
different screen or reloading the image grid. The current post/set, page, image
order, scroll position, viewer and Back history stay in place. The saved session
also keeps that location for reopening the Workbench. Use **Import queue** to
open the queue explicitly. Editing choices within the queue keeps its page too.

When an individual image opens a destination-girl chooser, that exact image
remains the import target even if other images are selected in the background.
Regression checks cover later pages, original/similar ordering, set and queue
views, reopening the session, Back navigation and suggested-image imports.
These are DOM checks; no live Windows desktop check was performed.

## Storage and compatibility

`individual_imports(scope, sha, data)` stores destination, character identity,
known library instance, options, source hashes, timestamps and apply result.
Typed journal events are `organizer.individual_import`. An older checkpoint
restores an empty individual queue and installs its journal triggers. Unknown
legacy library namespaces remain unknown. Legacy exports and set-only callers
remain accepted; individual transfers require companion support and fail before
copying if an older companion ignores the new contract.

Automatic clothing-color detection and browser-access troubleshooting remain
paused. No new image model runs or duplicate comparisons start from selecting,
queuing or importing images.

## Further improvements worth considering

- A shared review workspace opened directly from Workbench, already focused on
  the girl and queued selection, to remove the remaining handoff clicks.
- A compact destination preset per girl, with one-key save-and-next while
  browsing, without silently applying the previous girl's settings.
- Native loose-file selection and direct URL input in Workbench, routed through
  the same import services and provenance tracking as the library uploader.

These are suggestions, not claims of implemented features. Batch-only image
history views from the earlier discussion were not added.

## Manual search, Set Purgatory and import comparison (2.9.26 / 2.0.23)

- **Search manually** in the library matching window works without a model,
  index or ranked result. Search Sets or individual images by name, aliases,
  colors, notes and category names. Filter categories and location, including
  unassigned images and both holding areas. An image result already in a Set
  offers that Set; ungrouped selections can create a Set. The server checks
  membership and ownership again before creating it.
- **Search Sets / images** in Workbench searches the current library or saved
  folder inventory. Selecting a live library reference attaches its verified
  source and membership to the inventory without a folder or duplicate rescan.
  Original paths and known library identity are retained. Local image filtering
  uses its Sets' categories; library image filtering uses image categories.
- **Set Purgatory** is separate from individual-image Purgatory. Normal Sets,
  Favorite Sets, Recent Set items and set battles exclude held Sets. Manage
  Sets and the dedicated holding view can restore them. IDs, members, covers,
  categories, notes and historical battle data remain intact. Images retain
  their own placement. Workbench Set details saves the same status with its
  draft; only an explicit status edit changes an existing library Set's status.
- **Compare duplicates before importing** opens a side-by-side review from the
  transfer preview. It can show saved duplicate-engine pairs or search the
  library manually. No new scan is implied and absence of candidates proves
  nothing. Originals can be inspected at full quality. Keep maps the source to
  the chosen existing image; Replace calls the existing verified replacement
  service; Import separately cancels the saved duplicate decision. Exact hashes
  are always reused. A source cannot silently create a second copy of itself.
- Choices are stored by source hash in `state.duplicate_choices`, journaled in
  `organizer.evidence`, carried through scope merges/checkpoints/export, and
  emitted as `decision.import_duplicate` on application. Source/target hashes,
  library namespace, operation ID, action and time are kept. Replacements retain
  the original and create a checkpoint before applying; source files stay in
  place. Interrupted replacement retries retain identity and do not copy again.
  Stale targets, wrong libraries, conflicting aliases to one target and changed
  sources stop the transfer. Reopen the import preview after changing a choice.

Library search pages 60 results at a time. Workbench lazily loads cached 600px
library thumbnails; original resolution is fetched only when requested. Search
never invokes clothing-color detection, model downloads or automatic source
replacement. Full Windows desktop/browser smoke testing remains outstanding;
DOM, HTTP integration, native card rendering and product regression tests are
run for this release.
