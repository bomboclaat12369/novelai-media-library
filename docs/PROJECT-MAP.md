# Media Library / Media Workbench source map

Start with `AGENTS.md`, then the three release configs. They select the active
modules; older versioned payload parts remain immutable release history.
Read selected source files, not generated HTML or encoded runtime chunks.

| Area | Authoritative source | Notes |
| --- | --- | --- |
| Companion API, library metadata, imports and Undo | `runtime-src/companion-runtime.pyw` / `LibraryStore`, `MediaHandler` | `library.json`, managed originals and thumbnails |
| Battle model and history | Same file / `BattleRankings` | Separate `battles.json`; fixed history priors, joint fit, linked Undo |
| Organizer transfer | Same file / `organizer_preview`, `organizer_import`, `organizer_apply` | Preview token, source hashes, owner fingerprint, resumable imports, atomic membership commit |
| Library checkpoints | Same file / `create_checkpoint`, `checkpoint_preview`, `checkpoint_restore` | Verified ZIP; library + battles; optional originals; selected video frames always included when available |
| Viewer, imports and metadata controls | `.part01.txt` selected in each release config | Standalone supports management; NovelAI overlay is viewer focused |
| Persistent Rapid Review | `.review-core.txt` selected in standalone config | Chunked uploads into a durable pending queue; Close retains it; explicit actions promote/discard |
| Manual matching search | `ui-src/manual-search.js`, runtime `manual_search` / `manual_group` | Metadata filters, paged results, membership validation; no model dependency |
| Sets and matching | Selected `.sets.txt`, `.groups.txt`, `.outfit-matching.txt`, `.set-picker.txt` | One Set per item; categories and main-view placement are separate |
| Production cards | Selected `.collection.txt`, `.editions.txt`, `.base-layout.txt`, `.card-debug.txt` | Catalogs/layouts under `assets/cards`; no independent Studio renderer |
| Loop editor and video reference frame | `ui-src/video-workflow.js` | Source timestamps come from local FFmpeg; frame matching retains the video identity |
| Card Studio and library project tools | `ui-src/project-tools.js` | Original-resolution photo; calls `naiCards.lightCard`; preview controls do not save cards |
| Workbench server | `duplicate-review/app.py` | Loopback UI with per-launch token, serial operations |
| Scan/duplicate decisions | `duplicate-review/engine.py`, `matching.py`, `bulk_sets.py` | Existing duplicate engine unchanged by the video workflow |
| Organizer collections, drafts, Up next and Later | `duplicate-review/organizer.py`, `organizer.html`, `organizer-workflow.js`, `organizer-search.js` | SQLite state scoped to collection; star identity follows surviving copies |
| Coordinated restore | `duplicate-review/checkpoints.py` | Review, bulk and organizer DBs plus companion checkpoint and video frame sidecars |
| Missing originals | `MissingFileFinder` in the runtime, `duplicate-review/missing-files.js` | Cancellable inventory/search, paged reports, checksum-verified copies to expected paths |
| Publishing | `tools/PUBLISHING.md`, `publish-source-release.py`, `verify-published-release.py` | Source-only request; one authenticated Git push; verified receipt |

`module_sources` in release configs maps stable UI sources to new immutable
payload filenames. Run `python tools/sync-ui-sources.py` after editing them.
`--check` detects drift. Both builders also synchronize the selected modules.
Existing versioned modules without a stable mapping must be copied to a new
filename before changing their published bytes.

See `docs/WORKBENCH-BULK-IMPORT.md` for individual-image queues, import destinations,
shared Rapid Review, and the comparison with the library uploader.

## Workflow invariants

- Stars and Later are separate from membership, duplicate decisions and the
  currently selected draft. A star survives set assignment. Later posts remain
  searchable and keep their context, but sort after active posts.
- Organizer preview reports new/existing media, destination sets, conflicts and
  invalid sources. It uses exact file hashes, never filenames as identity.
  Imports copy originals and stay outside Main until assigned. Retry the preview
  after interruption: already imported hashes are reused.
- Apply rechecks owner/membership state. Move removes previous Set membership;
  Skip leaves that item's existing membership alone. It does not remove an item
  from a connection because that legacy feature has already been retired.
- Metadata save failure restores the last committed in-memory snapshot. A later
  successful save cannot accidentally persist the failed edit.
- Complete Workbench checkpoints include local databases, provenance, queue
  state, saved drafts and the library/battle snapshot. Originals are optional;
  missing source paths are listed before restore. Restore creates a rollback
  checkpoint and journals the coordinated operation. Restart completes rollback
  after interruption. Changed originals are never silently overwritten.
- Video frame references are search inputs only. Workbench videos do not enter
  the duplicate-removal engine. Library matching attaches a JPEG + source video
  hash + source timestamp to the video; it does not create an unrelated image.
- Loop boundaries are stored independently of playback. Play locks editing;
  Off keeps saved boundaries. FFmpeg runs locally and decodes actual timestamps
  rather than estimating frame positions using a nominal frame rate.
- Missing-original scans never remove records or infer identity from filenames.
  Search is restricted to explicitly selected folders and skips linked paths.
  Recovery revalidates collection identity, verifies the copied bytes, and uses
  atomic no-clobber publication. Workbench records approved recoveries before
  publication; previews and duplicate actions recheck their hashes when inode or
  timestamps change. Existing sets, stars, saved inventory and history stay linked.
- Small field edits reuse serialized unchanged media and copy only changed
  records into the rollback snapshot. `library.json` is still complete after
  every successful edit, fsynced and atomically replaced; backups stay readable.
  General edits invalidate serialization and lookup caches. There is no journal
  migration, background pending save, or new database dependency.
- Battle ratings/priors are unchanged. Dense covariance calculation uses NumPy
  for medium boards; larger boards use bounded sparse batches with the same
  residual tolerance. The prior solver remains available without NumPy. Vote calculation
  releases the library lock and rejects a stale fit before saving.

## Tests and diagnostics

Install pinned Python dependencies with `requirements.txt` and
`duplicate-review/requirements.txt`, and build dependencies with
`npm ci --prefix tools --ignore-scripts`. DOM tests use `jsdom@26.1.0`; native
renderer tests use `@napi-rs/canvas@0.1.80` (set `NODE_PATH` if installed outside
the repository). FFmpeg is required to exercise the real video decoder tests.

Run `python tools/check-product.py`, then
`python -m unittest discover -s tests -p test_release_pipeline.py`.
Product checks assemble current sources locally, run runtime/Workbench suites,
exercise the complete interface in a DOM, and render the approved card artwork
with native canvas. They restore the original manifest after local builds.
Generated payloads are never part of the source publication commit.

The older DOM assertions were updated to current behavior: retired Connections
are absent, Sets move membership, Rapid Review persists locally on Close,
Create Set assigns selected files, the queue uses a lazy grid, and replacement
has a separate confirmation dialog. The suite is still required before release.
Both legacy workflow entry points now validate only; the source workflow is the
only publisher and runs the same product tests before writing release refs.

Use Project tools / Download diagnostics or Workbench / Diagnostics for session
operation timings and recent metadata-write failures. The main library report
contains counts and timings, not media contents. It may contain file paths in
error messages; review the downloaded report before sharing it.

`python tools/benchmark-workflows.py --entries 1000 --votes 8000 --repeat 3
--compare-reference` creates a disposable seeded fixture. In the development
Linux environment, median joint-fit time was 0.403 s versus 22.165 s for the
reference iterative covariance solver. Maximum rating difference was zero;
maximum uncertainty difference was 2.42e-13. These are synthetic measurements,
not a guarantee for the user's Windows machine or actual collection.

DOM and native rendering tests do not establish browser layout, video playback
precision in a particular browser, or Windows installer behavior. Browser-access
troubleshooting and automatic clothing-color detection remain paused.

Background history is implemented by `TrackingJournal` in the companion runtime
and the shared `duplicate-review/tracking.py` adapter. The runtime source ships
inside Workbench, so there is one journal implementation. See
`docs/BACKGROUND-TRACKING.md` for typed evidence, persistence/backup contracts,
legacy migration, performance measurements and limitations.
