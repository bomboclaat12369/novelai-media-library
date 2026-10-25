LOCAL DUPLICATE REVIEW 1.9.3
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
Duplicate scans and image processing stay local; no cloud account or GPU is required.
The optional set-preparation pilot downloads matching models on first use.

NEW IN 1.9.3: TARGETED DUPLICATE-HISTORY REPAIR
1. Finish pending groups in regular Duplicate Review after updating. Single-keeper
   choices record the keeper relationship; keeping several images does not guess
   which kept photo a removed copy belongs to.
2. Build proposed sets once to refresh the full inventory after those decisions.
   Keep quarantine and both databases. No restoration or re-download is needed.
3. Open Repair duplicate history. Only unresolved quarantine is queued; exact,
   verified visual and recorded-keeper links are excluded automatically.
- Byte-identical unresolved copies share one review entry, with ALL their original
  locations displayed and retained. Counts distinguish photos from physical files.
- Progress and review labels survive restarts. Defer never resolves a connection.
  No surviving copy is an explicit, reversible label, not a deletion or proof.
  All unresolved includes both labels; exports retain them for auditing.
- Suggested counterparts use saved comparisons (including a two-edge search) and
  fingerprints. Weak/unsupported fillers are omitted. Search filename/path/post
  across ALL survivors or choose Browse all survivors, with paginated results.
  Empty suggestions do not prove that no surviving copy exists.
- Confirming validates every matching physical quarantine file and the survivor,
  preserves all origins, moves no files, and supports Undo connection.
- The screen reports remaining regular groups/images and file-processing issues.
  Missing/changed files stop confirmation rather than silently losing an origin.
- Original paths from the move journal are preferred when available, while the
  quarantine location is retained separately. Old path-wrapper recovery still works.
- Finish repair, then Build proposed sets to use the added origins in grouping.
  This release does not change set-grouping thresholds or restore quarantine.

NEW IN 1.9.2: ORIGINAL FOLDER CONNECTIONS AND RELATED-DRAFT REVIEW
- Single-keeper quarantine decisions now journal the kept image's hash and path
  before moving files. Completed links follow later keeper replacements; undone
  moves do not supply links. Keep-multiple actions do not guess which kept image
  a removed image belongs to. Quarantine-all does not imply a duplicate link.
- Build a fresh evaluation to recover recorded decisions, reuse existing visual
  recovery, and retain the complete readable folder inventory. Old saved pilots
  remain usable but cannot show outside-pilot files they never saved.
- Recover folder connections shows unresolved quarantine images and up to 12
  candidate survivors. Candidates are suggestions, not proof. Confirm only the
  same photograph. Skip if none fits (discarded images may have no counterpart).
  Connections persist across future scans; the latest confirmation can be undone.
  Build a fresh evaluation after recovery to regroup with those additional origins.
- Related drafts & folder images shows other images from the same original posts,
  including outside-pilot and unresolved quarantine files. Outside-pilot images
  are view-only. Full-collection evaluation makes all readable survivors editable.
- Inspect related drafts, transfer members or combine drafts. Affected accepted
  drafts require confirmation again. Undo review change restores the prior state.
  Accepting an image removes its pending membership elsewhere, avoiding overlaps.
- No automatic import, file restoration, new quarantine operations, or changed
  visual matching thresholds. Related posts are leads, never proof of one shoot.

NEW IN 1.9.1: SHOOT COMPLETENESS AND REVIEW RECOVERY
- Compare competing outfit-supported cores before merging; require stronger visual
  evidence before a coherent Instagram cluster joins another forum-post group.
- Discover tentative small shoots among shared-post leftovers before assigning
  single images. Reciprocal visual neighbors and repeated origins support these
  drafts. Shared sources alone cannot group visually unrelated images.
- Revisit fragments once at the end with frozen representatives. New suggestions
  do not increase the population prior or create repeated chains of guesses.
- Unassigned: Recheck unassigned creates a NEW saved evaluation, preserving existing
  drafts while retrying leftovers and skipped images. Explicit removals block the
  rejected membership; skips are not negative labels. Unchanged accepted drafts
  stay accepted; added members require confirmation. No automatic imports/moves.
- Show file details: filename, post origins, short ID and full path on hover.
  Preference persists. Exported IDs connect screenshots to recorded decisions.
- Re-evaluate same images remains a fresh algorithm evaluation without applying
  review corrections. Both modes reuse cached features and preserve the old job.
- 31 focused grouping/workflow checks and targeted browser validation passed.
  Models and duplicate verification are unchanged. Full-collection accuracy has
  not been established; suggestions remain reviewable drafts.

NEW IN 1.9.0: PHOTOSHOOT GROUPING AND FOLDER COMPLETION
- Replaced the fragment reconciliation/attachment strategy with shoot hypotheses
  built from established visual cores and all recovered post origins. Outfit and
  setting evidence is combined across representative views; changed framing no
  longer has to pass a fixed fraction of every possible cross-image comparison.
- Source influence depends on the shoots already found in the evaluated post.
  A dominant shoot supports plausible remaining members; a post with several
  shoots compares the remaining images against those alternatives. Compilations
  with many unrelated groups receive less completion support. Instagram post
  identity receives a stronger initial prior, but can still contain multiple sets.
- Source counts are frozen before missing-member placement. Newly assigned images
  cannot strengthen their own prior or recruit further images in the same run.
  Counts describe the evaluated cohort, not unexamined files outside the sample.
- Strong matches to one representative can now support membership when source
  context agrees. Competing near-ties and clear visual conflicts can still remain
  unassigned. Source evidence alone does not force unrelated images into a shoot.
- Check addition / Check grouping badges identify source-assisted suggestions.
  Uncheck an incorrect member before accepting; it remains available in Unassigned.
  Details explain the suggestion. Acceptance is not treated as proof a set is
  complete; previous review decisions remain preserved and do not train a model.
- The export includes observed source mixtures, merge decisions, and unresolved
  placements with visual and source contributions. These are heuristics, not
  confidence percentages. Routine polling excludes these diagnostic details.
- Validation: 24 focused grouping/workflow checks and a browser check of tentative
  badges, explanations and persisted member removal. On 27 supplied screenshot
  crops, the actual models reproduced 10 old fragments; the new strategy produced
  the four user-identified shoots with no unassigned or mixed members. It also
  kept those four shoots when all 27 were assigned one synthetic mixed forum post.
  This is a limited screenshot check, not a full 400-image accuracy measurement.
- Quit the old app, extract the COMPLETE repository ZIP, then launch the batch
  file. Select your completed evaluation and click Re-evaluate same images.
  Compatible cached features are reused; no new model inference is required when
  all are cached. Old evaluations and accepted/skipped decisions remain intact.
- Draft-only: no file moves/imports, duplicate-rule changes, or main-library update.

NEW IN 1.8.2: COMPLETE SETS AND UNASSIGNED RECOVERY
- Uncertain clothing cues no longer disable outfit evidence when corroborated
  by the setting. Shared recognized posts allow combined appearance/context
  evidence without first requiring the whole post to be visually consistent.
  Clearly limited clothing still needs setting evidence; a post alone is not proof.
- Remaining images can form a new set from three mutually supported images with
  a common post, even when no single comparison established a strong initial pair.
- Fragment reconciliation accepts multiple source-backed visual links across
  both groups rather than demanding three strong cross-links in every case.
  Reconciliation runs up to eight rounds, stopping as soon as no merges occur.
  Unassigned attachment accepts corroborating source/scene evidence from two
  members. Coverage and competing-group checks remain in place.
- New exports include up to five candidate matches per unassigned image (including
  rejected pairs), attachment rejection reasons, and up to 200 rejected fragment
  comparisons. These are diagnostic scores, not confidence percentages. Details
  stay out of routine UI polling, and triangle candidate storage is bounded.
- Update, then choose the completed pilot and click Re-evaluate same images.
  Compatible cached features are reused. Original decisions stay in the old run;
  the new run is pending review. Acceptance does not imply a set was complete,
  and skipping does not train the matcher to reject those image relationships.
- This iteration prioritizes recovering complete shoots. It can introduce more
  incorrect memberships; final review is still required. Focused synthetic and
  workflow checks pass, but originals from the 400-image evaluation were not
  available for an end-to-end accuracy measurement. Compare both completeness
  and incorrect members, not only proposal count or acceptance count.
- Draft-only: no imports or file moves; duplicate-checking/quarantine rules and
  the main library set finder remain unchanged. No new neural-model pass is needed.

NEW IN 1.8.1: RE-EVALUATE THE SAME IMAGES, BETTER SHOOT GROUPING
- Click Re-evaluate same images while viewing your completed pilot. This creates
  a NEW evaluation from exactly the saved image cohort, including Unassigned.
  The old evaluation and every accepted/skipped decision stay in the dropdown.
  New proposals start pending; old acceptance is not assumed to prove new groups.
- No new folder inventory or random sample is needed. Existing compatible outfit
  and scene features are reused without loading the neural models when all are
  cached. An unchanged 400-image rerun should therefore be much quicker than the
  initial scan. Missing/changed images stop the rerun explicitly; no substitutions.
  If interrupted, select the original completed evaluation and re-evaluate again.
- An outfit-model score alone is no longer sufficient when clothing evidence is
  limited or uncertain. A small bundled set of text features gates that route
  using the existing image vectors. Clear clothing matches keep the original
  outfit threshold; other images require setting/source corroboration. The gate
  is fallible, and its scores are NOT confidence percentages or a nudity detector.
  No additional large model download or per-image neural pass is introduced.
- Posts can contain multiple coherent visual subsets. Consistent scene evidence
  within each subset supports changed poses/viewpoints without treating an entire
  mixed forum post as one shoot. Unknown folders still supply no post boost.
- A second pass reconciles fragments with support across several members on both
  sides. A third pass checks unassigned images against established cores, requiring
  two supporting members and a margin over competing groups. A lone bridge cannot
  join unrelated sets; newly attached images do not seed a chain of attachments.
- The new export records source consistency, clothing cues, appearance/full-scene/
  outer-scene scores, merge/attachment counts and before/after cohort counts.
  An unchanged membership group displays its earlier review status for reference.
  A lower Unassigned count by itself is not evidence of improved accuracy.
- Fixed compressed/clipped unassigned thumbnails: rows retain their image height,
  the grid scrolls, and pagination spans the row. Unassigned no longer presents
  unusable set-selection/edit controls. Image fullscreen and source details remain.
- Validation includes focused grouping/replay tests, crowded-grid browser checks,
  and a limited check on supplied screenshot crops. The screenshot examples now
  assemble the four window images and separate the mixed group into the confirmed
  pair plus three unassigned images. This does NOT validate the full collection or
  guarantee identical results from originals in the complete 400-image context.
- This is still a draft-only evaluation tool: no library import, source movement,
  automatic cleanup, or changes to the main library's set finder are introduced.

NEW IN 1.8.0: BULK SET PREPARATION — LOCAL EVALUATION PILOT
- Open "Bulk set preparation · Pilot" from the duplicate-review screen. This is
  the first evaluation stage of the combined duplicate/source/set workflow.
  It creates persistent review drafts. It does NOT import images, create library
  sets, move files, or delete originals/quarantined files. The existing duplicate
  reviewer remains available, with unchanged matching and quarantine rules.
- Extract the COMPLETE repository ZIP, including its runtime-src directory. Run
  duplicate-review/Start Duplicate Review.bat. The pilot reuses the companion's
  outfit and scene encoders; extracting duplicate-review alone is insufficient.
- Start the media companion if you want existing library images as references.
  Pick the person in the reference dropdown. All image placements supplied by the
  companion catalog are included: Main, Sets, Review and Purgatory. Video grouping
  is not part of this pilot. Without the companion, choose Folders only.
- Select the top-level cleaned collection folder, including its quarantine folder.
  For example: C:\Users\Empathy\Desktop\SMG\Mikayla. Start with about 400 incoming
  images. All source files are inventoried; only the pilot sample and library
  references receive visual grouping. "Outside pilot" is NOT a processed count.
  The sample tries to retain whole source posts. A later full run can reuse caches.
- Keep forum identity set to smg for SMG downloads. Same forum + post number is
  one source regardless of date, download batch, or quarantine move ID. Instagram
  username + case-sensitive post shortcode is another source identity. Different
  forums require separate evaluations with different forum labels.
- Reconstructs all available origins from exact copies and directly verified
  visual-copy relationships. Unresolved quarantine files are counted separately;
  manual quarantine membership alone is not proof of a surviving duplicate.
  Original review.sqlite3 is read locally; there is no need to upload it.
- Outfit similarity is evaluated without blending it down with background scores.
  Scene/context evidence provides additional connections, supported by post origin
  where available. A shared post alone never forms a set. Mixed posts can split
  into several proposals; known different library sets are not merged together.
  Scores/thresholds are hypotheses for evaluation, NOT accuracy percentages.
- Inspect the large grid, click an image to enlarge, then Accept draft & next.
  Edit name/colors/categories before accepting. Categories come from the selected
  person's library. Select part of a proposal and Split selected if necessary;
  deselected members return to Unassigned. Details shows recovered sources and
  competing candidate images. Enter in the name/colors field accepts the draft.
- Review decisions and completed identity/visual caches persist in the separate
  bulk-preparation.sqlite3 beside review.sqlite3. Closing the browser does not stop
  the local server. Use Stop before quitting; a stopped/interrupted scan must be
  started again, but completed cached work is reused. Saved drafts can be reopened
  through the evaluation dropdown. Avoid simultaneous matching/model downloads
  in the companion while the pilot is preparing its shared model cache.
- First use may download approximately 686 MiB of models and install ONNX Runtime
  if not already available. Later visual work is content-cached. Source inventory
  and unchanged-file checks still run; initial quarantine recovery can take time.
- Export evaluation writes a JSON report with paths, source relationships, draft
  metadata and correction counts; it contains no image bytes or feature vectors.
  The report cannot establish visual correctness by itself. Inspect representative
  proposals and report false members/missing members before relying on bulk import.
- Candidate search is bounded: visual nearest neighbors, exhaustive post candidates
  only up to 200 images per source, and at most 120 members per proposal. Larger
  sources still receive visual search and are flagged. "Unassigned" does not prove
  that no matching set exists, especially outside a limited pilot sample.
- Direct approved-set imports and the separate Batch Imports library section are
  the next stage, after real-collection evaluation. No standalone, companion or
  NovelAI version change is required for this pilot.

NEW IN 1.7.5: REUSE WORK WHEN ADDING FOLDERS
- Comparison blocks now retain persistent content slots. Adding/reordering folders
  or changing protected-reference priority no longer reshuffles established blocks.
  New images are still compared against all existing blocks and one another.
  Adding files can rebuild the last partial block; changed/removed contents rebuild
  affected blocks, while unaffected completed tasks remain reusable.
- Upgrading seeds this layout from the last scan where possible, retaining
  compatible 1.7.4 checkpoints. Older incompatible tasks may need one recomparison;
  this does not discard cached image preparation, review decisions or move history.
- Image preparation uses up to four workers, bounded separately from crop workers
  because full-resolution decoding uses more memory. Unchanged fingerprints and
  features are reused without rewriting them to the database. Completed preparation
  is checkpointed and survives Stop. File changes and analysis failures stay visible.
- Reading progress distinguishes reused/prepared/failed images. A saved-comparison
  check counts reusable tasks before estimating the remaining crop-comparison time.
  The completed scan summary retains the cache counts.
- No matching thresholds, fingerprint resolutions, candidate limits, crop/rotation/
  mirror checks, or automatic-quarantine verification rules have been weakened.
  New/changed images still require analysis; a first-ever scan is still substantial.
- To upgrade during a scan: Stop and wait, then Quit. Extract the entire new ZIP,
  launch its batch file, and Scan again with the same folders and matching mode.
  Keep the existing LocalAppData state. No media-library/companion update is needed.

NEW IN 1.7.4: SEPARATE EXACT AND VISUAL CLEANUP
- Select exact duplicates (formerly Select obvious duplicates) selects identical
  file bytes or identical decoded pixels. Then use Move selected copies.
- Preview visual copies and Quarantine verified visual copies handle only non-exact
  matches accepted by the existing same-photo verifier. Both exclude exact families.
- Exact-family members can be retained keepers for visual copies but are never moved
  by the visual action. This includes lower-resolution exact families that could
  also visually match a larger image. Clean up exact duplicates first, then run
  visual cleanup to consider the remaining representative from each family.
- Preview and automatic visual cleanup use the same proposal generator. Preview
  still moves nothing until you explicitly approve a subset. Undo is unchanged.
- Matching thresholds and scan-cache keys are unchanged. No rescan required.

NEW IN 1.7.3: PREVIEW AUTO-QUARANTINE
- Preview auto-quarantine runs the same checks as the automatic action, but moves
  nothing. It opens a large KEEP / QUARANTINE comparison for each proposed removal.
- Use Previous / Next or the pair selector, Fit / 100%, and Open original to inspect.
  The reason distinguishes identical bytes, identical decoded pixels and visual checks.
- Uncheck Include this removal to keep both images, or use Exclude all / Include all.
  Apply approved moves shows a final count and confirmation before moving the subset.
- Close preview moves nothing; Review prepared preview reopens it. Exclusions are
  retained while this page stays open, but reset on browser refresh. Prepared plans
  expire when review data changes or the checker quits; verification results stay cached.
- Exclusions only affect this preview, not future automatic runs. Existing automatic
  quarantine is still available separately and still moves files after verification.
- Approval is tied to server-owned pairs and the current review. Changed files are
  checked again before moving. Undo last action restores the approved batch.
- No matching thresholds or scan-cache keys changed. Visual verification is still
  fallible; the preview lets you inspect actual decisions rather than assume accuracy.

NEW IN 1.7.2: CONSISTENT COMPARE LARGE ORDER
- Clicking a thumbnail compares it with the next image in grid order. The last
  thumbnail is compared with the preceding image, retaining left-to-right order.
- Compare large starts with the first two images. Numbered dropdown choices
  match the grid; changing choices keeps the pair distinct and in grid order.
- No scanning, matching, quarantine or cache changes. No rescan is required.

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
