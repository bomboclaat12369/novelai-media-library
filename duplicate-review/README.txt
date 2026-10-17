LOCAL DUPLICATE REVIEW 1.7.1
============================
Local image comparison, reversible cleanup, and media-library replacement.

START / UPGRADE ON WINDOWS
1. Quit the old Duplicate Review app.
2. Extract the entire ZIP, then double-click "Start Duplicate Review.bat".
   Alternatively replace the old program files while closed; keep .venv.
3. Keep the launcher window open. Use Quit when finished.
Existing scans, cached fingerprints, review decisions and move history carry over.
The database is stored separately in %LOCALAPPDATA%\LocalDuplicateReview.

Requires 64-bit Python 3.11-3.14 (3.13 recommended), including tkinter and the
Python launcher. The first launch installs Pillow, NumPy and OpenCV in a private .venv.
Later launches, scans and image processing stay local; no cloud account or GPU.

NEW IN 1.7.1: FASTER CROP SEARCH AND MORE WORKERS
- Crop searches can now run concurrently against independent copies of the same
  search trees. This removes the single shared search lock. Up to eight copies
  are used, bounded per 256-image block to limit extra memory use.
- Adds 24 and 32 CPU-worker choices, capped to the CPU threads available on your
  computer. Existing choices are retained; the default remains 8. More workers
  are not always faster, particularly if other programs are busy.
- Completed task writes are checkpointed in short batches to avoid a disk flush
  for every worker result. Stop saves already collected results before returning.
  A forced shutdown can lose the last short uncommitted checkpoint, not prior work.
- Matching thresholds, candidate searches, image coverage, block ordering and
  cache keys are unchanged. Existing completed crop comparisons remain reusable,
  including when changing the worker count. Keep folders/files and matching mode
  unchanged when resuming. Keep/Different image decisions and Undo carry over.
- To upgrade during a scan: click Stop and wait, then Quit, replace/extract the
  program files, reopen, choose your worker count and click Scan again. Cached
  work is reused; the scan may first show its normal file-checking stages.
- No changes to automatic-quarantine verification or keeper selection.

NEW IN 1.7.0: AUTO-QUARANTINE VERIFIED COPIES
- Click Auto-quarantine verified copies after scanning. It checks your current
  review groups and then quarantines qualifying incoming copies in one batch.
  Existing completed scans can be used immediately; no rescan is required.
- Each discarded image is checked directly against its retained keeper. Review
  group membership, Broad-mode scores and indirect matches never authorize moves.
- The separate verifier aligns copies, requires full containment of the discarded
  image, and checks local structure and pixel differences across the image. Many
  resized, recompressed and cropped copies qualify. Different/uncertain poses,
  complementary crops, very small images and ambiguous edits stay for review.
- Highest megapixels wins; ties use the displayed left-to-right order. There is
  no separate sharpness/upscaling quality ranking. If a higher-MP crop lacks part
  of another image, the image with additional content is retained too.
- Library/reference images and manual Keep choices cannot be quarantined. An
  incoming copy above library resolution stays available for Replace library copy.
  Library-only cleanup remains manual to preserve your metadata assignments.
- Keep-both and Different image decisions are respected, as is the folder-scope
  selector. Verification uses up to 8 CPU workers, capped by your worker setting.
  Content-keyed verification results are cached; unchanged comparisons are reused.
- Stop during verification moves nothing. Stop during moving stops after the
  current copy. Undo restores this action's entire moved batch, including after
  restarting. Actual source and keeper files are verified again before each move.
- This is conservative visual verification, not mathematical proof of identity.
  Nothing is permanently deleted. Check Issues for skipped/unreadable/changed files.
- The older exact-selection buttons retain their existing byte/pixel-only behavior.
  They select first and still use newest-folder priority.

NEW IN 1.6.1: QUARANTINE A WHOLE INCOMING GROUP
- Click Quarantine all incoming to move every incoming image in the displayed
  group, including manual Keep choices. No keeper is required.
- Imported library images and reference folders stay protected. This action is
  only available in folder scans, not library-only cleanup.
- Undo last action restores the whole batch, including after restarting.
- Existing scans and matching caches carry over; no rescan is required.

NEW IN 1.6.0: DUPLICATES WITHIN YOUR LIBRARY
1. Restart the media companion to install runtime 2.7.40 or newer.
2. Choose "Duplicates within my library" under Scan type.
3. Click Connect to media library. Select All characters, or one character.
4. Click Scan library. No incoming folder is needed. Main, Sets, saved Review
   and Purgatory are included. Folder quarantine and retained deleted originals
   are excluded because only live library records are scanned.
5. Review matches and their character, category, favorite and Set labels.
   Mark every record to Keep and click Finish group, or select unwanted copies
   and click Remove selected library copies. At least one copy must remain.
6. Undo last action restores the removed records and their Set memberships.

Library cleanup goes through the companion. It retains original files for Undo,
updates Set covers/membership, and does NOT merge metadata into keepers. Automatic
selection is disabled in library-only mode because identical images may have
important different assignments. Visual matching includes the existing crop,
rotation and mirror checks. No scan can guarantee finding every edited duplicate.

Unfinished actions are journaled before being sent. Resume library cleanup retries
the same request safely after a connection interruption; Undo can cancel an
unapplied request or restore an applied batch. A new scan is blocked until a
pending cleanup is resolved. Undo refuses to overwrite later conflicting Set
edits, changed originals, or missing categories/characters. Cleanup records and
originals remain retained across restarts; this does not reclaim their disk space.

The normal Incoming folders + library mode still protects all library references.
Existing matching caches carry over. Run a new library-only scan to build its
review groups. Prior dismissed matches remain excluded unless you reset them.

NEW IN 1.5.1: FASTER COMPARISONS
- Defaults to 8 concurrent CPU workers, adjustable from 1 to 16 (hardware capped).
- Keeps a larger decoded analysis cache in RAM (about 1.4 GB at its 2,048-image cap,
  plus compressed fingerprints, search index and normal app overhead).
- Counts actual completed comparison tasks, with elapsed time and estimated time
  remaining. Estimates vary with image complexity and cached tasks.
- Saves completed comparison tasks. Unchanged block/image/mode combinations are
  reused across scans and after restarting; content or matching changes invalidate
  them. Keep/Different image decisions are reapplied, never bypassed by this cache.
- Version 1.5 fingerprints carry over. Version 1.5 did not save completed comparison
  tasks, so an interrupted 1.5 crop pass must restart once in 1.5.1.
- Crop retrieval and acceptance thresholds are unchanged. Visual matches still
  require manual review; automatic selection requires identical bytes or pixels.
- No companion update is required when upgrading from checker 1.5.0.

CROP-AWARE MATCHING AND SCAN COVERAGE
- A second visual pass aligns local details and compares overlapping image content.
  It handles many crops, rotations, mirrors, borders and mild exposure changes.
  It is independent of the old whole-image hash and 3% aspect-ratio restriction.
- These scan matches are manual-review suggestions. The separate 1.7 verifier
  rechecks candidates before auto-quarantine; Broad suggestions alone never qualify.
- Run a fresh scan after upgrading. The first scan builds new cached fingerprints
  and takes longer. Scan time increases with collection size; Stop stays available.
- Read the scan summary: included/discovered totals, library totals and any Issues.
  Failed images or library changes during scanning are reported as incomplete.
- Saved Keep and Different image decisions are respected. Use Reset keep decisions
  and rescan if you want to reconsider those previously dismissed matches.
- No visual algorithm guarantees zero misses. Extreme edits, tiny crops, collages,
  very low detail and unreadable or unsupported files may not be recognized.

COMPARE AGAINST YOUR IMPORTED LIBRARY
- Keep the NovelAI media companion running. This requires companion runtime
  2.7.38 or later. The permanent companion launcher downloads published updates;
  restart it if Connect reports that the companion needs updating.
- Click Connect to media library, select All characters (or Nikki for a narrower scan), add your
  incoming download folders, and Scan folders.
- Main, Set-only, saved Review and Purgatory images are included, with area labels.
  Unsaved browser import queues must be saved before the companion can include them.
  Only live image records are compared: deleted/retained originals are excluded.
- Imported images are protected. Cleanup never moves or deletes those originals.
- Choose Folder comparison only to use the tool without the companion.
  Optional reference folders remain available for other protected collections.
- Use incoming folders outside the managed media-library folder.

KEEP SEVERAL IMAGES IN A GROUP
- Click Keep on each incoming image you want to retain. Imported/reference images
  are already kept. Keep choices are saved immediately, without popups.
- Finish group keeps every marked image and quarantines the OTHER incoming copies.
  The button shows the keep/move counts before you click it.
- Keep all / dismiss group leaves every file in place and dismisses the group.
- Keep only this remains available on cards and in Compare originals. It directly
  quarantines all OTHER incoming copies in that group; all references still stay.
- You can also tick unwanted copies and use Move selected copies across groups.
  Unmark Keep before selecting that image to move. Automatic selection respects
  manual Keep choices.

DIFFERENT IMAGE, INCLUDING ITS OWN COPIES
- On a false match, click Different image.
- Select that different pose AND every copy of it. Verified identical copies are
  checked together. Add any resized/recompressed/watermarked copies yourself.
- Split into separate group preserves both families for independent review.
  A single unique image simply stays in its incoming folder.
- Splits survive reopening and rescanning. New byte-identical copies of a known
  image join its existing family. A newly re-encoded or changed image can require
  review again. Reset keep decisions also clears saved splits.
- Splitting does not move files. Multiple false poses can be split one at a time.

REPLACE AN IMPORTED IMAGE DIRECTLY
- On the preferred incoming image, click Replace library copy.
- Select the imported target. When several imported images are shown, you must
  explicitly choose which one to replace. Check the previews and Set labels.
- The companion preserves the target's ID, categories, favorites, crop settings,
  main/Set placement and Set memberships. Only its source image changes.
- The old original is retained. The new source is hashed and verified before the
  incoming downloaded source is moved to quarantine, avoiding a second import.
- Other incoming copies remain for review; replacement does not discard them.
- Return to the main library window to refresh its changed record.
- Undo last action restores the old library source and the incoming download.
  Later metadata edits are preserved. Undo refuses to overwrite occupied paths
  or a library source that has since been replaced again.
- If interrupted, Resume unfinished replacement safely retries the recorded
  operation. Undo can cancel an uncommitted replacement or reverse a committed
  one. Keep the companion running for replacement recovery and undo.
- Old sources are retained under the library's replacement-originals directory.
  Leave that directory intact for Undo. They are not counted as active images.
  Download quarantine paths must also remain intact for automatic restore.
- Replacements support still images up to 256 MB. More megapixels alone do not
  prove better quality; the replacement choice is always yours.

COMPARISON AND AUTOMATIC SELECTION
- Results are groups of connected match suggestions. Different poses may appear
  together. Counts mean possible duplicates, not a guarantee of identical images.
- Sort by most duplicates, fewest duplicates or newest folder. Choose 2-5 per row.
- A blue outline highlights the highest megapixel count when dimensions differ.
  Ties at the highest count are highlighted; equal pixel counts get no highlight.
- Click a preview or Compare large. Previews are up to 2,000 pixels, with linked
  zoom/scrolling. Open original opens the full-resolution file externally.
- Click the dark space around comparison images, Escape, or Close to return.
- Show in folder reveals the file in Explorer (or the platform's file manager).
- Select obvious duplicates requires identical full-resolution decoded pixels OR
  identical SHA-256 bytes. Names, lossless encoding and nonvisual metadata can
  differ; color profiles/display interpretation must agree.
- JPEG recompression normally changes pixels. The separate Auto-quarantine
  verifier can handle many of these copies; uncertain cases need manual review.
  Same dimensions, a visual similarity score, or group membership is not proof.
- Select exact bytes only limits automatic selection to SHA-256 equality.
- Both buttons select first. Nothing moves until you click Move selected copies.
- Automatic choices keep all protected references and manually marked Keep files.
  Otherwise they keep the newest valid YYYY-MM-DD or YYYY_MM_DD folder date in
  the ancestry (nearest dated folder), then descending natural folder name, then
  alphabetical filename for ties. Folder input order does not change this rule.
- Within each folder only limits automatic cleanup to each immediate directory.
- Actual source and keeper hashes are checked again before each move. Changed or
  missing files are skipped with a message. Run Scan again after changing files.

QUARANTINE / UNDO
Moves go under each incoming root's _Duplicate_Review_Quarantine folder, retaining
relative paths inside a unique move directory. No permanent deletion occurs.
Undo last action restores the last move batch or library replacement, including
after restarting. Existing files are never overwritten. Stop ends a move batch
after the current file. Move history shows recorded source/destination paths.

Exclude quarantine from later imports; this tool excludes it from scans, but a
media import of a whole folder tree could otherwise import it again. Import only
your cleaned subfolders or move quarantine outside the import tree after review.

CACHE AND LIMITS
- Scans decode one image at a time; unchanged files reuse cached fingerprints.
  Closing during a scan does not move anything. Rescan to complete an interrupted
  scan. No automatic background scan runs.
- Completed results, Keep choices, splits and undo journals persist. Temporary
  Select to move checkboxes do not persist across restarts or result changes.
- Supported still formats: JPEG, PNG, WebP, BMP, TIFF, AVIF and GIF. No videos or
  HEIC. Animated/multi-page, corrupt or unusually large images are skipped.
- Linked files, linked folders and Windows junction subfolders are omitted.
- Large crops, borders, watermarks, mirrored images and heavy edits may not match.
  Near-identical burst photos may be suggested too. Manual review remains useful.
- Scan one person's collection at a time, after downloads have finished.
- The Windows launcher/Explorer integration has not been run on Windows here.
  Engine, real companion HTTP integration and browser workflows were tested on
  Linux, including interrupted replacements, quarantine failure and safe undo.

KEYBOARD / SOURCE
Left/right: browse groups. K: keep all/dismiss. Ctrl+Z: undo last file action.
app.py serves only on 127.0.0.1 with per-run tokens and Host/Origin checks.
library_bridge.py communicates only with the local companion at 127.0.0.1:8765.
Manual start: python -m pip install -r requirements.txt
              python app.py
Tests: python -m unittest discover -s tests -v
Companion integration tests skip when the companion source is unavailable.
