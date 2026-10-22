# NovelAI Media Library

Local image/video library overlay for `novelai.net`, with a Tampermonkey front end and a local Python companion.

## Rank card designs and faster battles (standalone 2.8.99 / companion 2.7.60)

Cards now take their frame, shield and nameplate colors from their battle rank:
graphite placement, copper Bronze, brushed Silver, Gold, teal Platinum, ice-blue
Diamond, violet Master and black/gold/crimson Grandmaster. Upper tiers add distinct
crest details. Hiding MMR also hides rank styling. Profile finishes remain available;
battle finishes add texture while preserving the rank color.

The uncertainty calculation factors one shared matrix on medium, sufficiently
connected boards instead of solving it separately for every rated image. It uses
the same full history and covariance model, with the existing sparse solver retained
for small, sparse or large boards. A 220-entry / 1,600-comparison fixture measured
about 0.28 seconds versus 0.84 seconds for the previous calculation on the same
machine. MMR matched exactly and uncertainty matched to six decimal places in
comparison checks; this measures calculation time, not a guaranteed end-to-end vote
latency. Requests also avoid copying unrelated people's ranking histories.

Card frames use shared static vector assets instead of repeated inline artwork;
percentile OVR tables are cached per response, offscreen leaderboard rendering is
skipped, and Show more appends cards. Next-match images are decoded ahead of display
with a separate bounded cache (128 MiB estimated decoded pixels, at most 24 retained
images). Set layout changes are batched. Original-resolution battle images, vote
persistence and Undo are preserved.

Collection HQ now opens over the current battle/leaderboard and returns there on
Close or Escape. Starting an HQ battle task replaces the previous battle screen.
Enlarging a leaderboard image preserves its card frame, rank and saved positioning;
arrows browse cards and clicking the surrounding blank area closes the viewer.

Update standalone and **restart the companion** to apply the rating optimization.
NovelAI's interface remains 2.8.93. Focused checks cover solver parity, voting/Undo,
rank designs, HQ navigation, enlarged cards, backdrop closing and original image
layouts.

## Sculpted trading-card artwork (standalone 2.8.98)

Battle, leaderboard and profile cards now use layered metallic SVG frames with
beveled corners, etched inserts, foil accents and inset nameplates. Large OVR
shields and rank emblems sit in the upper corners. The illustration-inspired frame
replaces the previous thin outline; it scales cleanly without downloads or
continuous animation. Earned Emerald and Platinum finishes remain available.

Individual battle cards fit portrait proportions to the available height, with
roughly four-fifths of the card height retained for the image window. Set battles
keep their adaptive multi-image mosaics in wider matching frames. Battle controls
and MMR sit outside the artwork. Leaderboard cards keep their portrait shape;
**Details & actions** below each card contains history, comparison focus, filenames
and image positioning. Clicking an image still selects it in battles or opens it
from the leaderboard; arrow keys, fullscreen and saved positioning are preserved.

This is a standalone interface update only. Refresh and apply the update; companion
2.7.59 and NovelAI 2.8.93 are unchanged. Focused browser checks cover rendered photo
space, resizing, gallery actions, full-image browsing, card framing, click/keyboard
voting, set mosaics, hidden ratings and profile attributes.

## Collection HQ and cards (standalone 2.8.97 / companion 2.7.59)

**Collection HQ** opens a per-person progress map, collection statistics, roster and
permanent milestone cabinet. Image/set placement and confidence use the existing
battle eligibility and evidence rules; set tasks include small sets (minimum one
image). Profile curation and set organization are separate tracks. Unassigned
saved images can be explicitly marked checked/standalone, with Undo for the last
check, or investigated using Scan for Sets. Replacing their source invalidates that
check. No image is automatically assigned or removed.

Completion describes the current collection, not every photograph that exists.
Empty tracks are excluded; new imports can reopen work. First-time 25/50/75/100%
track milestones each earn 100 permanent XP, with levels every 400 XP. Emerald and
Platinum card finishes unlock at 800/1,600 XP. Milestones are retained when progress
falls or an action is undone; repeating the same milestone does not award more XP.

Standalone battles, leaderboards and profiles now have thin trading-card frames
that leave most space for the image. Set battles retain their adaptive mosaics and
original-resolution images. Image/set OVR is a presentation scale derived from the
placed MMR ordering within one person and battle type: 60 at the bottom, 78 around
the median, 91 around the 90th percentile and up to 99 at the top. Tied MMR receives
the same OVR. Fewer than five placed cards, an all-tied pool and provisional entries
show a dash; pools of 5–19 placed cards cap at 95. These are relative preference
ratings, not probabilities or a change to matchmaking. Ranks and MMR are unchanged.

Profile cards have exactly four personal attributes, initially Face, Breasts, Butt
and Style. Labels, ratings and weights are editable; values start blank. Overall
is the rounded weighted average only after all four are filled. These manual
ratings have no effect on battles. **Position card / Position image** saves pan
and zoom per image card or profile photo without editing the source, normal
library crop or fullscreen image. Different card shapes can reveal a wider area.

**+Media → Categories** restores image/video category creation, inline rename and
ghost controls, plus an Arrange toggle with drag insertion and accessible up/down
buttons. Ordering saves immediately. Edit Library uses the same category manager.
Dropping files anywhere while +Media is open returns to Upload images and keeps
the existing file queue; standalone also opens uploads on external file drops.

Restart/update the companion, then update standalone to activate these features.
NovelAI stays at 2.8.93, and main-library image grids/viewers keep their existing
presentation. Focused runtime and browser checks cover metadata persistence,
validation/conflicts, rollback, unchanged MMR, category ordering/drop handling,
card framing, full-resolution battles, keyboard voting and progress calculations.

## Faster incremental scans (Duplicate Review 1.7.5)

Download [Local Duplicate Review 1.7.5](downloads/Local-Duplicate-Review-1.7.5.zip).
Stop any running scan and wait, then Quit, extract the entire package, and launch
**Start Duplicate Review.bat**. Existing state stays in LocalAppData. Resume with
Scan; the media-library interfaces and companion do not need updating.

- Persistent comparison blocks preserve completed work when new folders are added
  or folder/reference priority changes. New images still search all existing blocks
  and one another. The last partial block may be rebuilt as it grows; changed or
  removed contents invalidate their affected work without shifting every later block.
- Compatible 1.7.4 checkpoints are migrated using the last scan's layout. Some older
  incompatible work may need recomparison once; preparation caches, Keep/Different
  decisions and Undo history are retained.
- Up to four preparation workers handle new/changed files. Full cache hits bypass
  preparation and unnecessary cache rewrites. Work is checkpointed for Stop/resume.
- Progress reports reused/prepared/failed images and reused comparison tasks. Cache
  hits are counted before estimating the remaining comparison time.
- Matching resolutions, candidate searches, crop/rotation/mirror thresholds and
  automatic-quarantine verification are unchanged. This speeds up work reuse and
  scheduling; it does not trade detection coverage for a faster/looser scan.

## Matching-screen review actions (standalone 2.8.96)

Click the reference image at the top of **Find matching Sets** to open its original-resolution fullscreen preview, just like the matching examples. Escape or clicking the fullscreen preview returns to the matching screen.

When matching unsaved Rapid Review uploads, **Discard image** removes only the currently displayed reference, regardless of the bulk selection. It closes both matching and the set-assignment dialog and returns to the next queue image; discarding the final image closes Rapid Review. Selecting another reference in the matching dropdown changes which image is discarded. Saved library images do not expose this upload-discard action. Original source files remain untouched, errors leave the dialog available to retry, and an in-progress matching job is cancelled when discarding.

Set rank badges now sit above the image/video count row, with count text kept on one line at smaller thumbnail sizes. Focused browser checks cover original previews, Escape, failed-discard retry, single-image scope, dropdown selection, next/final queue navigation, cancellation of a late-starting search, saved-library preservation and badge spacing. Companion remains 2.7.58 and NovelAI remains 2.8.93; this is a standalone interface update.

## Photoshoot matching (standalone 2.8.95 / companion 2.7.58)

**Match by: Outfit / Photoshoot** is saved separately for each person. Nikki and other existing people retain Outfit mode; a person named Mikayla defaults to Photoshoot unless a preference has been saved. The control is available in Find matching Sets (including import queues), Scan for Sets and Find missing Set images. The new mode prioritizes the setting and surrounding visual details while retaining outfit similarity as supporting evidence. Every readable image in every set remains eligible, as do ungrouped images in Main, Review, Purgatory and Unfiled. Results still require manual selection and never assign or import anything on their own.

Photoshoot mode adds a pinned, SHA-256-verified **DINOv2 Base** ONNX model (346,555,570 bytes, approximately 331 MiB). Its full-frame feature and pooled outer-region patch features are combined with the existing FashionSigLIP feature at weights 55% / 35% / 10%. The full frame is retained instead of center-cropped; the outer regions are contextual cues, not guaranteed background segmentation. The best coherent orientation (upright or either sideways rotation) is used. Each set is ranked by its strongest matching member, without a bonus for having more images. This is visual retrieval, not face identification or a classifier for clothing removal. Similar-looking settings can still be confused; close-ups with little visible context remain harder.

The first Photoshoot search downloads the additional model and indexes that person's images. Scene features and rotated query features persist in a separate, versioned cache alongside the existing outfit cache. New or replaced images are reindexed; repeat searches reuse the cache. No images are sent to a service. Failed downloads or image checks are reported instead of silently falling back to Outfit results. Photoshoot scans initially show **All remaining images**, since a weak lead is not proof that no matching set exists. Search scores are not calibrated probabilities.

Validation covers unchanged Outfit retrieval, mode persistence and isolation, cache reuse/invalidation, all-member and holding-area scope, explicit assignment, scan/reverse-scan UI, and a real-model smoke check on synthetic scenes with changed foreground clothing. This does not measure recall on the user's actual photoshoots. Restart the companion for the new engine, then update standalone. NovelAI remains at UI 2.8.93.

## Faster rapid-review controls (standalone 2.8.94 / companion 2.7.57)

Rapid Review now puts **Create set + assign**, **Find matching sets**, and **Add selected to Review** in a prominent, consistently ordered row with distinct colors and icons. **Add to existing set** sits beside Crop image. The selected count and selection controls stay above the actions; current-image flags and categories form a separate compact section. Whole category chips are clickable, with visible selected states, subtle category accents and a dashed treatment for ghost categories. Carry categories, category creation and the redundant Sets menu were removed from Rapid Review.

The controls remain above the independently scrolling thumbnail grid. Compact spacing at smaller window heights preserves thumbnail room, while the existing thumbnail-size preference, scroll position and resumable queue remain intact. Matching starts with the current image even when no queue thumbnails are selected; assignment and Review actions use the selected images.

Adding a new category or assigning a set now clears **both Review and Purgatory**. Ghost categories and set-only membership do not independently promote an image to All; ordinary categories and explicit Main placement still do. Saving unchanged categories, removing a category, renaming a set or reordering its existing members does not release unrelated held images. Rapid Review clears its Review checkbox on category assignment so saving cannot accidentally restore the old holding status. NovelAI stays at UI 2.8.93 for this standalone interface update.

## Viewing and library management (UI 2.8.93 / companion 2.7.56)

NovelAI is now a lighter viewer. Browsing, sets, sorting, profiles and profile editing remain, along with favorites, featured, image cropping, video thumbnail selection and timestamps. Imports, organization, deletion, rapid review, set detection and battles belong in standalone. Heavy management modules are omitted from the NovelAI release; shared viewing code stays shared. Versioned modules and Git history preserve the removed functionality if it is needed again.

Standalone **Edit Library** separates selected-media actions from library setup. Compact controls provide placement, set membership, Review/Purgatory, removal flags and Needs replacement. File actions are collapsed. The viewer toolbar no longer repeats these controls, and **Add to Set** only appears for images without a set. Profile photos are managed from the profile page; Focus comparisons and rating history are confined to Battles.

**+Media** opens image uploads directly. Dropping files anywhere while the import dialog is open adds them to the current selection; dropping files elsewhere opens it. Video and URL imports remain in Edit Library. **Remove from holding area** leaves Review/Purgatory without deleting the file, promoting it to Main or changing set membership. Unassigned files remain accessible in **Unfiled**. **Wide** provides a remembered, single viewer spanning the dual-view width.

The addition-date sort is labeled for the current category and uses recorded category membership dates. Older memberships without such a date fall back to the import date. Profile photo selection now offers sorting alongside category and filename filtering. Viewer badges emphasize the rank emblem with smaller MMR text, and removal thumbnails show only a red flag.

Battle preloading uses lightweight rating estimates instead of repeatedly fitting the complete comparison history. Actual votes still run the full history fit, preserving rating behavior. Library redraws are deferred while Battles is open. **Leaderboard** reliably returns from Recent movement, and rating history uses a sampled timeline without a dot for every recalculation. This reduces avoidable work; actual transition speed still depends on library size and storage.

## Collection ranking and review (UI 2.8.92 / companion 2.7.55)

Normal matchmaking spreads initial comparisons across unfinished entries before refining placements. **Finish placements** prioritizes unfinished entries and stops when the eligible scope is placed. Established entries can still serve as useful opponents; equal appearance counts are not the objective. Repeats remain possible when needed, with recent-pair avoidance and opponent diversity. There are no rating bonuses, resets or inactivity decay. The joint-history rating model is unchanged.

**Battle category** optionally restricts both opponents to one image or set category. It uses the same person/type MMR and global placed-entry tier denominator; it does not create category-specific ratings. Focus comparisons temporarily broadens the scope and returns to the prior category afterward.

**Flag for removal** is available on image battle cards, full-size browsing and the regular viewer. Flags exclude images from future matchmaking without changing their Main membership, votes or MMR, and the currently displayed matchup remains usable. The **Flagged for removal** library section includes flagged images even if subsequently moved to Review or Purgatory. Clear the flag, inspect the image or use the existing deletion/Undo controls there.

Standalone library thumbnails can show rank badges. Images and sets have **Highest MMR**, **Lowest MMR** and **Fewest comparisons** sorting; ordinary MMR sorts put completed placements before provisional entries and unrated/ineligible items. Viewer ratings and leaderboard **Rating history** open an MMR graph showing direct results, indirect history recalculations and Undo. Earlier detailed direct results are shown where available; missing older indirect changes cannot be reconstructed. Graph samples are bounded, while the underlying comparison log is preserved.

The trophy cabinet now has five progressive cards per person/type: placements, collection coverage, established entries, first Grandmaster and comparisons. Milestones upgrade a card instead of creating per-image rank spam. Earlier awards remain in a collapsed archive. Profile **Choose photos** now filters by image category alongside filename search, including set-only, Review and Purgatory images. This shared profile improvement is the reason NovelAI also advances to 2.8.92; all battle features remain standalone-only.

## Historical ratings and standalone-only battles (UI 2.8.91 / companion 2.7.54)

MMR jointly fits all recorded wins, losses and ties. Later evidence about an opponent can move an earlier participant's rating without another direct comparison. Each active vote enters the model once; a tie contributes one half-result, not two bonus wins. Fixed starting priors anchor the scale. Confidence incorporates linked opponent uncertainty, and sparse evidence remains provisional. Undo removes a vote's influence throughout the comparison history, not only its two participants. The last-vote message reports when other ratings were refined.

Migration automatically recalculates logged history and saves `backups/battles-before-joint-history.json`. Detailed event logging started in UI 2.8.89 / companion 2.7.52: earlier unlogged evidence is retained as a fixed baseline using the first logged before-values. Missing old matchups cannot be reconstructed. Existing counts, trophies, sessions and Undo remain intact. Model: regularized Bradley–Terry with fractional ties, Newton/PCG fitting, and marginal Laplace uncertainty; no inactivity penalty or repeated replay bonuses. Ratings describe your comparisons, not an objective or guaranteed ordering.

Battle images and every visible set-grid tile now load the **stored original file**, scaled to fit without cropping. The leaderboard still uses efficient thumbnails. Likely upcoming original files are prefetched as encoded blobs rather than keeping all possible sets decoded. Background requests are bounded and lower-priority; the actual next pair is still chosen after the vote. Voting waits for the displayed images to load, and failures remain visible.

Battles, focus controls, battle statistics, top-ranked profile images and trophies are **standalone only**. NovelAI retains normal library viewing and profile photos/measurements. Battle history is not deleted. `release-standalone.json` and `manifest.standalone_version` are independent of `release-userscript.json`; future battle-only releases must leave the NovelAI config, parts and hash unchanged. Build all artifacts with `python3 tools/build-release.py` and publish them atomically with the manifest. The shared companion must be restarted for this runtime update.

## Continuous battles and a visual ranked gallery (UI 2.8.90 / companion 2.7.53)

New battle sessions default to **Continuous**; optional 10/25/50-vote sessions remain. Existing active sessions retain their settings. Every vote saves immediately, and the most recent twenty undoable votes remain available across session changes. **Focus comparisons** is available on battle cards, beneath the library viewer, inside sets, and on leaderboard cards. It runs ten comparisons featuring that entry and then returns to the previous mode. **End focus** returns early. Focus uses ordinary MMR calculations without bonuses or rating resets.

The leaderboard is now a gallery with large whole-image previews and set collages. Image size is adjustable and remembered, with name, rank and confidence filters. Click a card to view full-size images; image leaderboards browse in their filtered ranking order, while set leaderboards provide both image and set navigation. **Recent movement** shows MMR changes since the current session began. Close-contender labels identify neighbors whose rating gap is within their combined model uncertainty; they do not claim certainty about the correct order. **Refine top 10/25** concentrates comparisons on the current highest-MMR played entries that meet the battle filters.

Seven ranks have distinct custom vector emblems: Bronze, Silver, Gold, Platinum, Diamond, Master and Grandmaster. Among entries that have completed placement, the cumulative cutoffs are Grandmaster 1%, Master 5%, Diamond 10%, Platinum 25%, Gold 50%, Silver 80%, and Bronze the rest. Cutoffs round up to whole entries; exact MMR ties share tiers, and small collections may not populate every tier. The crown identifies the sole highest-rated placed entry. Tiers remain separate per person and battle type. Existing MMR, votes and historical trophies are preserved, including older Champion awards; Champion is no longer a current tier.

Upcoming previews are prepared for possible vote outcomes without recording a vote or changing saved ratings. The actual matchup is still chosen after voting. Preview sizes scale with the number of displayed images, decoded previews use a bounded cache, and speculative loading uses three workers only while battles are open. The current matchup stays visible while the next is prepared. Preview loading uses the companion transport in both NovelAI and standalone; fullscreen continues to load originals.

## Faster placement and adaptive set battles (UI 2.8.89 / companion 2.7.52)

Battle MMR now uses uncertainty-aware Glicko updates: new images and sets move quickly, while established ratings change more cautiously. Matchmaking keeps a persistent batch of up to eight unfinished placements, mixes in calibration comparisons, and favors informative, varied opponents. **Place this image** beneath the viewer and **Place this set** inside a set start a focused ten-comparison round; both are also available from the leaderboard. Choosing placement never grants rating points by itself.

Ratings show Unrated, Provisional, Developing or Established confidence. Placement requires at least six comparisons against four distinct opponents and sufficiently low uncertainty; Established requires twelve comparisons, eight opponents and tighter uncertainty. Tiers require completed placement and at least five placed eligible entries. Ratings do not decay with inactivity. These are estimates of your preferences, not guarantees of an exact ordering. Only wins, losses and ties affect MMR; there is no “Both are great” bonus.

Existing MMR and vote totals are preserved. Older ratings begin with estimated uncertainty and need new varied comparisons to establish confidence. A one-time pre-migration battle backup is retained. Each new comparison records the before/after ratings and uncertainty; Undo restores the previous state and records the reversal. Older comparisons are not reconstructed.

Set battles fill each side with an adaptive grid of whole, uncropped images, up to twelve per set. Larger sets show the cover and evenly spaced samples with a visible count. Click the grid to choose that set, or use Left/Right arrows to vote. **Browse full set** opens every image individually; arrows browse instead of voting while this view is open. Compact controls leave more room for images.

## Profile design, rank tiers and trophies (UI 2.8.88 / companion 2.7.51)

Profiles now show and edit height in feet and inches; stored inch values convert automatically. Overview uses a larger photo gallery, measurement cards, battle statistics and top-ranked image cards. Trophy Cabinet is available from profiles and battles, with filters for image or set achievements. The three screens share a dark gallery design with compact controls and colored rank badges.

Tiers are separate per person and battle type. Entries need five comparisons; at least five eligible entries must finish placement, with differing MMR, before tiers unlock. The sole MMR leader is Champion, followed by Diamond (top 10%), Gold (top 25%), Silver (top 50%), and Bronze. Tied scores share a tier; tied leaders receive Diamond. Tiers reflect current eligible entries, while trophies preserve achievements.

Trophies recognize vote milestones, Gold/Diamond/Champion achievements, and consecutive win streaks of 5, 10 and 25 appearances. Ties end streaks; skips do not count. Existing totals and current qualifying tiers are recognized as existing records, without inventing past streaks or achievement dates. New votes save awards atomically with MMR; Undo reverses the undone vote's awards and streak changes. Existing MMR, votes, profile photos and measurements are preserved.

## Profiles and battle MMR (UI 2.8.87 / companion 2.7.50)

Use **Profile** beside the person selector for five curated photos (first is the main photo), optional height/bust/waist/hips in inches, bra size, per-measurement Estimated or Confirmed labels, and notes. Use **Add to profile photos** beneath the viewer or choose photos inside Edit profile; Save profile commits changes. Profiles also display the top five played Main images by battle MMR, independently of curated photos.

Image and set battles retain their existing Elo ratings and votes, now labeled MMR. Ratings start at 1200, remain provisional for the first five comparisons, and update with opponent strength. Show MMR can be toggled; the last vote shows rating changes. Battle images fill the available screen height with compact controls.

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

## Easier Set organization and Main-entry sorting (UI 2.8.76 / companion 2.7.42)

- The Sets screen keeps its thumbnail grid. Each card shows its name, categories,
  media counts, and an **Edit** button for quick name/category changes.
- **Manage categories** opens a separate category editor. **Select Sets → Categories**
  adds or removes categories across selected Sets while preserving other assignments.
- Open Sets have **Rename**, **Categories**, and **Edit contents** actions. The content
  picker shows existing members and unassigned media by default. Enable **Show media
  in other Sets** to include those files. Existing assignment behavior still moves
  newly added media out of its previous Set; metadata-only edits preserve memberships.
- Assigning a main category to an image or video in Purgatory now automatically
  removes it from Purgatory. This transition and its Main-entry date are undoable.
- **Date added to Main** sorting defaults to newest first. Main-entry dates are
  recorded separately from import dates, including Review promotion and Set release.
  Older records without a recorded Main-entry date fall back to their import date.
- Library text/search fields suppress browser saved-form suggestions without changing
  browser-wide settings. App-owned live Set search results remain available.

Restart the companion and refresh both interfaces. Focused backend and Chromium
browser checks cover the changed organization and placement flows in standalone and
NovelAI; Edge's native Saved info popup still needs confirmation on the user's PC.

## Classic Set thumbnails and stable navigation (UI 2.8.77)

- Restored the earlier full-thumbnail Set cards: the extra category strip and Edit
  button are removed. Rename, Categories, and Edit contents remain inside open Sets.
- The toolbar **Sets** button opens a searchable management menu with those same
  actions, New Set, and category management. The **Sets** category still browses
  thumbnails. Bulk category assignment remains under Select Sets in that browser.
- Editing preserves the thumbnail scroll position, including within large Sets.
  Back from an open Set restores the previous Set-list position. Grid refreshes no
  longer briefly switch to ordinary media or lose scroll while replacing tiles.
- The main search defaults to Set names; typing searches Sets directly. Choose
  **Files** beside it for filename searches. Category navigation defaults back to
  Sets search without carrying a filename filter into the next view.
- Add to Set and Set-management dialogs focus their search/name field on opening.

Focused browser checks passed in NovelAI and standalone, including long grids and
edit/return scroll preservation. Refresh the interfaces; companion 2.7.42 is unchanged.

## Quarantine every incoming image in a group (Duplicate Review 1.6.1)

**Quarantine all incoming** discards every incoming copy in the displayed review
group, including manual Keep choices, without requiring a keeper. Imported library
images and reference folders stay protected. Undo restores the batch, even after
restarting. Existing scans and caches carry over; no rescan is required.

Download `downloads/Local-Duplicate-Review-1.6.1.zip`, close the older checker,
extract the ZIP and run its batch file. This checker update is separate from the
media-library UI; no companion update is needed.

## Individual outfit matching and Scan for Sets (UI 2.8.80 / companion 2.7.45)

- **Find matching Sets** also shows this character's ungrouped images, including
  Main, Review and Purgatory. The saved query itself is excluded from individual
  results. Video files and other characters are excluded.
- Select matching individual images and name a Set to create it explicitly. For
  a saved query, the new Set includes that query. If the query already belongs to
  a Set, selected individuals can be added to that Set instead. For an unsaved
  upload, only selected library images are grouped; the upload stays in its queue
  until **Assign selected files**. Existing placement rules still apply.
- Open **Sets → Scan for Sets**, or use **Scan for Sets** in the Sets category.
  Start the scan to compare all current non-set images against existing Sets.
  Review the source beside Set examples, then explicitly click **Add to [Set]**.
  Three alternatives are visible initially, with up to five available. There is
  no automatic assignment or remembered rejection.
- The default **Stronger leads** filter requires best cosine similarity >= 0.86
  and a >= 0.025 gap over the next Set (when a second Set exists). These are
  conservative review heuristics, not calibrated probabilities. **Other
  possibilities** and **All remaining images** expose the remaining suggestions.
  No strong lead does not establish that a matching Set is absent.
- Indexing and orientation results reuse the existing local cache. The first scan
  includes additional ungrouped images and their orientation checks, so it can
  take substantially longer than a single-image search. Progress shows indexing
  and comparison separately. Stop preserves cached work. Closing the dialog lets
  the scan continue; reopening it in the same page retrieves the results. Scan
  sessions expire after companion restart or enough newer searches; no user
  decisions train or modify the model.
- Scan approval checks the source and comparison files against the search
  snapshot, validates character ownership and refuses to move an image that has
  meanwhile joined another Set. Missing files or incomplete coverage are reported.
- Focused checks cover placement/owner scope, cache reuse, cancellation, explicit
  creation/assignment, stale results and both standalone/NovelAI browser flows.
- Restart the companion, then refresh and apply the UI update.

## Outfit search and Set manager fixes (UI 2.8.79 / companion 2.7.44)

- Matching result thumbnails now load after their cards are attached. Clicking a
  preview loads the original for closer inspection.
- Manage Sets uses a wider, responsive row layout. Long lists keep their row
  height and scroll inside the dialog; rename, categories and contents stay visible.
- Query matching checks the original image plus 90°/270° orientations, with cached
  results. On the supplied 44-image/12-Set leave-one-out sample, first-place matches
  improved from 37 to 39; top-five remained 43. Exact pixel copies were excluded,
  but similar poses remain, so this is not a whole-library accuracy guarantee.
- **Focus on outfit** lets you draw a temporary search crop. **Use full image**
  resets it. Neither action edits or imports the original.
- Cached Set descriptions are reused in memory and on disk. New descriptions are
  saved in batches rather than flushing every image; file changes still invalidate
  cached descriptions. Progress shows cached/new image counts and elapsed time.
- In a local 44-image check, initial indexing/model load took 9.84s, a different
  saved query took 0.32s, and an unsaved query took 0.56s. These are backend times,
  excluding the UI polling interval, and will vary by PC/library/storage. Initial
  installation, model loading after restart, and newly added images take longer.
- Restart the companion and refresh/apply the UI update. Existing model and image
  caches are retained. Matching remains on demand and assignment remains manual.

## Find matching Sets by outfit (UI 2.8.78 / companion 2.7.43)

- **Find matching Sets** runs only when clicked. Available below the image viewer,
  in Add to Set, in Rapid Review (including unsaved images), in its Set assignment
  panel, and in the Set editor for selected new additions. Both interfaces use
  the same feature. For multiple images, choose the image used for the search;
  existing assignment controls still determine which files are added.
- Compares against the current character's Set images, ranks Sets by their best
  matching member, and shows five suggestions with up to three actual matching
  thumbnails each. **Show more matches** reveals the next five. Choosing a result
  selects a Set; the existing Add/Assign/Save action applies the membership change.
- First use downloads a verified 355 MiB model and optional matching dependencies,
  then indexes the character's Set images. Images remain local. Subsequent searches
  reuse a disk cache; changed sources are re-encoded. No matching runs while idle.
  The model remains loaded in RAM after use. Four CPU threads are used at most;
  no CUDA, GPU drivers, accounts, API keys, or cloud inference are required.
- Requires 64-bit Python 3.11–3.14 for the optional ONNX Runtime engine. Restart the
  companion after updating; use the existing UI Update button in each interface.
- Missing/unreadable images and Sets without searchable images are reported.
  Search does not import unsaved files or change metadata. A change to Set images during
  indexing asks for a retry, using the already-cached images.
- Suggestions are not proof of outfit identity or absence. Similar clothing,
  hidden details, changed poses and group photos can confuse matching. Video-only
  Sets have no searchable image members in this release.

Matching model: [Marqo-FashionSigLIP](https://huggingface.co/Marqo/marqo-fashionSigLIP),
Apache 2.0, revision `c56244cc94f92419e8369fa71efdaf403b124ce8`.
Model weights are downloaded from the publisher on first use, not included here.
A 44-image, 12-Set leave-one-out pilot ranked the correct Set first for 37 queries,
in the first three for 41, and in the first five for 43. Exact pixel copies were
excluded; near-identical poses were not. These pilot results do not establish
accuracy across a larger library or outfits with no existing Set.


## Recent Set items and Main covers (UI 2.8.81 / companion 2.7.46)

- **Recent Set items** is available beside Sets and in the Sets management menu.
  It shows individual current Set members for the selected character, newest Set
  additions first, with Images / Videos / both and **Only outside Main** filters.
  Search Set names or filenames, open images in the existing viewer, or click a
  tile's Set-name caption to open its Set. Saved Review members are included.
- Set-entry dates are recorded on real additions, moves and re-additions. Renaming,
  changing categories or covers, and saving existing membership do not bump them.
  Earlier additions without a recorded date appear last; no dates are invented.
- Clicking empty space below an open Set's contents follows its Back action.
  Tile gaps, dragging, scrollbars and ordinary media categories do not navigate.
- Automatic Set covers prefer an image also in Main and retain the **Auto** badge.
  Manual covers and older covers with unknown provenance remain untouched. A
  current eligible Main cover stays selected when more Main images are added.
- Focused validation: membership-date persistence and cover precedence checks,
  plus real-companion browser checks of both standalone and NovelAI interfaces.


## Persistent Rapid Review and Set tools (UI 2.8.82 / companion 2.7.47)

- Imports sent to Rapid Review are staged in a durable per-character queue. Close,
  refresh, or restart the companion and use **Resume Rapid Review** to continue.
  Pending items stay outside Main until explicitly saved. **Discard remaining
  queue** requires confirmation and deletes only the remaining pending copies.
- A resizable preview sits beside a large, adjustable thumbnail grid. Expand the
  grid, Shift-select a range, or use Select all / Unselect all. Items start selected;
  selection controls apply to bulk **Add to Review**, **Add to existing Set**, and
  **Create Set + assign**. New imports append to an unfinished queue.
- New Set creation and assignment happen together, with a Color(s) field. Set
  **Edit details** also offers aliases and notes; aliases and notes participate in
  Set text searches. Colors are stored separately for future color filtering.
- **Arrange** toggles intentional Set image movement on/off. Drag images or use
  the earlier/later buttons; each move saves immediately. Category order is
  adjustable in Edit Media for images and videos.
- Opening a Set in dual mode displays its cover in Viewer 2, retaining Viewer 1.
- **Find missing images** inside a Set searches ungrouped library images against
  that Set's searchable members. Multi-image outfit searches can use up to four
  extra examples. Assignment remains manual; there is no decision-based learning.
  Incomplete matching shows a simple warning.
- Existing-library exact duplicates encountered while resolving a pending import
  are skipped, preserving their current placement and Set membership.
- Verified with focused queue/restart, rollback, Set metadata/order and matching
  checks, plus real-companion browser workflows in standalone and NovelAI.
- Apply the companion update and refresh/apply the UI update before importing
  into the new queue. Previously discarded unsaved sessions cannot be recovered.


## Rapid Review placement, ghost categories, and Default sorting (UI 2.8.83 / companion 2.7.48)

- Rapid Review has **Add to All + Next** and **Send to Purgatory** for the current
  image. The **Add to All** checkbox also preserves Main placement when assigning
  the image to a Set, without requiring any category.
- In **Edit Media → Category actions**, toggle **Ghost** beside an image or video
  category. Ghost categories remain browsable and assignable but do not by
  themselves add media to All or remove it from Purgatory. A regular category or
  explicit Add to All can still do so. Switching an existing category to Ghost
  removes its automatic Main placement where no other regular category or recorded
  explicit Main choice applies; files and memberships are retained.
- **Default** is the initial sort and groups visible Set members together at the
  earliest import date among that Set's members. Date Imported remains available
  for strictly individual ordering. Existing Date Imported preferences migrate to
  Default once; subsequent choices are remembered. Legacy overlapping Sets are
  kept together as a combined group.
- Removed Rapid Review's Expand Grid button. Thumbnail size is remembered through
  closing and refreshing. A prominent green check marks edited queue items; the
  smaller checkbox controls bulk selection. Edited status persists for pending
  queue items.
- Empty space beside or between Set images now follows Back, as does the space
  below them. Image and control clicks, scrollbars, and Arrange mode are excluded.
- Focused validation covers ghost/regular/explicit Main placement, Purgatory,
  persistence, sorting, and the affected standalone and NovelAI UI workflows.


## Rapid Review layout (UI 2.8.84)

- The preview uses nearly the full panel height. Current-image flags and categories
  sit in compact rows above the thumbnail grid, with All styled like Review,
  Favorite, Featured, and Needs replacement. Crop, Sets, Find matching Sets,
  Create Category, and Carry categories remain visible beside these controls.
- Selected-image controls retain Select all, Unselect all, thumbnail size,
  Create Set + assign, Add to existing Set, and Add selected to Review.
- Click the main image to view it fullscreen. Escape, another click, or the close
  control returns without changing the current image, selections, or grid scroll.
  Fullscreen uses the same preview element, including any displayed crop.
- Edited thumbnails use a pencil badge. Removed Add to All + Next; use the All
  checkbox with Save + Next or Set assignment. Existing queue persistence and
  remembered thumbnail size are retained.
- Focused browser checks cover both interfaces at 2048×1026 and 1280×720,
  fullscreen return, visible controls, and queue state. Companion stays at 2.7.48.


## Compact Rapid Review controls and reliable arrangement (UI 2.8.85)

- Current-image controls use compact, content-width buttons in wrapping rows for
  flags, categories, and actions. Selected-image bulk tools remain separate.
- Rapid Review keeps its thumbnail scroll position when selecting images, including
  with larger saved thumbnail sizes.
- Set Arrange accepts drops before or after images and in grid gaps, displays an
  insertion marker, and immediately shows the new order while saving. Arrange Off
  continues to prevent accidental moves.
- Focused browser checks cover repeated review selections and native mouse dragging
  forward, backward, and into gaps in standalone and NovelAI. Companion remains 2.7.48.


## Automatic same-photo quarantine (Duplicate Review 1.7.0)

- **Auto-quarantine verified copies** performs a stricter verification pass over
  current review groups, then moves qualifying incoming copies in one undoable batch.
  It handles many resized, recompressed and contained cropped copies, independently
  of the Broad/Balanced/Strict review-suggestion setting.
- Highest megapixels wins; ties follow the current left-to-right order. Every
  discarded copy is compared directly with its retained keeper. Local detail and
  full containment are checked; group membership and indirect matches are insufficient.
- Uncertain matches and complementary crops remain for manual review. Library
  references, manual Keep choices and Different image decisions stay protected.
  Incoming upgrades above library resolution remain available for replacement.
- Verification is cached and runs with up to eight CPU workers. Stop before the
  move phase leaves all files untouched. Source and keeper hashes are rechecked
  before each journaled move, and Undo restores the entire moved batch.
- Focused checks cover resizing/cropping versus localized changes, mixed-group
  keeper selection, library validation, scope/decisions, changed files, caching,
  cancellation and batch Undo across restart, plus the real browser/HTTP action.
- Download [Local Duplicate Review 1.7.0](downloads/Local-Duplicate-Review-1.7.0.zip).
  Quit the old checker, extract the whole package and run its launcher. Existing
  scans, decisions and Undo history carry over. No media-library UI or companion
  update is needed. Visual verification is conservative, not a zero-error guarantee.


## Parallel crop searches (Duplicate Review 1.7.1)

- Crop comparison uses bounded independent copies of the same saved search trees,
  allowing simultaneous searches instead of serializing them behind one lock.
  Native index objects are never searched concurrently by multiple threads.
- Adds 24/32-worker options (hardware capped) and batches frequent database flushes
  into short checkpoints. Stop commits the completed results already collected.
- Existing cache keys, matching thresholds, candidate parameters and image
  coverage are unchanged. Previously completed comparisons can be reused after
  upgrading or changing workers with unchanged files, folders and matching mode.
- Focused checks cover identical search results, matching results, reuse of the
  previous version's database, multiple blocks, review decisions, and Stop/resume.
- Download [Local Duplicate Review 1.7.1](downloads/Local-Duplicate-Review-1.7.1.zip).
  Stop the scan and wait, Quit, extract the full package, reopen and Scan again.
  No media-library UI or companion update is required.

## Consistent comparison order (Duplicate Review 1.7.2)

- Compare Large preserves thumbnail order. Clicking an image shows it beside
  its next neighbor; the last image appears on the right beside its predecessor.
- The toolbar button opens the first two images. Numbered dropdowns match the
  grid and preserve distinct choices in left-to-right order.
- Scanning, matching rules, caches and saved decisions are unchanged. No rescan
  is needed for this fix.
- Download [Local Duplicate Review 1.7.2](downloads/Local-Duplicate-Review-1.7.2.zip).
  Quit the old checker, extract the full package and run the launcher.

## Preview automatic quarantine (Duplicate Review 1.7.3)

- Preview auto-quarantine runs the existing verifier without moving files, then
  shows each proposed removal beside its actual keeper with zoom and original access.
- Exclude individual suggestions or all, then explicitly apply the approved subset.
  A final confirmation shows the count. Closing the preview moves nothing.
- Prepared plans are tied to the current review; changed files are rechecked before
  moving. Undo restores the batch. Exclusions last for this preview on the current page,
  not future automatic runs or browser refreshes. Restarting the checker clears plans.
- Matching rules, scan caches and the separate automatic action are unchanged.
- Download [Local Duplicate Review 1.7.3](downloads/Local-Duplicate-Review-1.7.3.zip).
  Quit the old checker, extract the full package and launch it. No rescan required.

## Separate exact and visual duplicates (Duplicate Review 1.7.4)

- **Select exact duplicates** selects identical bytes or decoded pixels. Use
  **Move selected copies** to quarantine that selection.
- **Preview visual copies** and **Quarantine verified visual copies** handle only
  non-exact matches that pass same-photo verification. Exact-match families remain
  untouched by both visual actions, including lower-resolution exact families.
- Run exact cleanup first, then visual cleanup. Exact-family images may serve as
  keepers; after exact cleanup their remaining representatives can be considered
  for visual cleanup. Preview approval and Undo remain available.
- Matching thresholds and scan caches are unchanged. No rescan is required.
- Download [Local Duplicate Review 1.7.4](downloads/Local-Duplicate-Review-1.7.4.zip).
  Quit the old checker, extract the entire package and launch it.

## Image and Set Battles (UI 2.8.86 / companion 2.7.49)

Click **Battles** next to Random after selecting a character. Both interfaces offer
Rank my library and Winner stays, with 10-, 25-, or 50-vote rounds, Tie, Skip and
Undo last vote. Close any time and reopen to resume; starting a new round retains
ratings and starts a fresh round/undo history.

- Image battles include only that character's Main images. Images also in sets are
  eligible if they are in Main; set-only, Review, Purgatory and videos are excluded.
- Set battles compare your favorite sets, with a default minimum of five images
  and an optional within-2x size filter. Both opponents show equal sample counts,
  begin at their covers when eligible, and allow browsing all saved images in each
  set. Review/Purgatory images and videos do not count toward the minimum.
- Separate per-character image and set leaderboards use personal pairwise Elo
  ratings. Fewer than five comparisons is marked Provisional; unplayed entries
  remain unranked. Matchups favor underplayed entries and similarly rated opponents.
- Votes, current matchups and undo history are written atomically to battles.json
  beside library.json, with a previous-file backup. Voting does not change media
  placement, Favorites, set membership, or thumbnails. Deleted/ineligible entries
  disappear from eligible rankings while their historical ratings stay stored.
- Keyboard: left/right chooses a side, T ties, S skips. Set photos open full-size
  browsing; individual battle photos can be clicked to vote.

Update/restart the companion for 2.7.49, then refresh and apply the library UI update
for 2.8.86. The standalone and NovelAI interfaces share the same saved rankings.
