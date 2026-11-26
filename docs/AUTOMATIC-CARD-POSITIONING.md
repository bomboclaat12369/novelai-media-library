# Automatic card positioning

In Media Library, open **Review card crops** in the Library toolbar or
the Battles image leaderboard. The companion prepares crops for the selected
character’s Main photos in the background while the review is open. Library
and Battles share the framing and decisions. Each side of a Duo has its own
photo and crop.

## Reviewing photos

**Needs a look** shows photos you flagged and automatic crops with a meaningful
composition choice. This includes a crop that trims beyond the visible hips
when the model could not locate the lower legs, and a fuller crop that could
lose part of a reclining pose. **All auto crops** also shows straightforward
fits and previously checked crops. Likely-good crops take effect automatically.

Each page shows up to twelve photos in their card frames. Tick **Mark to edit**
on the exceptions, then use **Approve others & edit**. With no exceptions, use
**Approve all**. Batch approval covers the ready previews on that page.

In the editor, click a crop preview or press its numbered shortcut to try it
on the current photo. Drag the photo, scroll to zoom, or use the same fit,
horizontal position, vertical position and zoom controls as **Position card**.
**Reset framing** returns the draft to a centered whole-photo fit.

**Peek original** shows the whole original inside its card. Hold **Space** to
peek temporarily. **Show photo beyond frame** shows the whole photo at its
original brightness and current position and zoom. The solid line marks the
photo opening. The dashed line marks the outside of the card. Drag the photo
in that view to bring a cut-off detail back into the opening.

**Save & next** applies the previewed framing. **Back to sheet** discards
the current preview. Choose **Later** to defer the photo and use the **Later**
filter to return to it. **Undo last** restores the previous state of the
affected photos.
You can also **Flag crop for review** on a Battles photo and continue voting.

## Local body analysis

On first use the companion downloads the local CPU pose software and verifies
the full pose model against its pinned SHA-256. It prepares reduced, oriented
copies for the model on this computer. It estimates the visible body and its
outline and compares the resulting crop with the full-photo fit. This allows
some empty space when filling the opening would sacrifice too much of the pose.
The queue keeps working as more photos finish. An unavailable analysis can be
retried. Saved manual frames and explicit choices take priority.

## Initial framing before body analysis

The shared photo opening is 840 × 1120. The companion measures the total gap
left by centered Fit at this reference size. A gap under one pixel needs no
adjustment. For example, the 1,537 × 2,049 source leaves 0.18 pixel of total
empty height and stays at Default.

For a wider photo, `centered-edge-fit-v2` preserves full height and crops at
most 4% from each side. A 4:5 photo uses 106.67% zoom. For a slightly taller
photo, the rule preserves full width and trims at most 2% from the top and
bottom. A 730 × 1,000 photo uses 102.74% zoom and loses 1.33% per vertical
edge. Previously automatic crops with imperceptible changes revert to Default
on load. Qualifying old crops keep their review token and checked state.

The initial edge-fit rule uses known dimensions to shortlist candidates, then verifies their
original file headers and EXIF orientation. It skips missing/unreadable files,
unknown dimensions, animated images, videos, removal flags, Review/Purgatory,
images outside Main, and images with saved library crops. It does not decode,
resize or rewrite image files and needs no model or remote image service.

The saved frame contains an explicit reference to the common opening. This
prevents legacy frame references from shifting an automatic crop when a special
edition is shown. Base and special editions retain the existing renderer and
artwork. Geometry guarantees edge alignment within the shared photo window;
composition and artwork overlapping the image still require visual judgment.

## Leaderboard tools and saved choices

Approval saves a page’s selected review decisions together. A source or crop
change invalidates the corresponding preview. Refresh if another window has
edited the same photo.

In the leaderboard, enable **Debug mode**, then use **Crop filter**:

- **Auto-positioned · Unchecked**: automatic crops awaiting optional review.
- **Auto-positioned · Checked**: automatic crops the user has checked.
- **All auto-positioned**, **Manual custom crops**, or **Default crops**.

An automatic crop offers **Mark checked** (or **Mark unchecked**), **Position /
crop**, and **Restore default**. Closing the positioning editor refreshes the
underlying view. Explicitly saving the automatic framing keeps
its automatic status. The Zoom control displays the precise percentage.
Restore immediately saves centered Fit at 1×. Editor adjustments save through
the existing Save framing control.
Both paths preserve an explicit manual frame, including a deliberate default,
so automation cannot reapply over it. Every previously saved frame, including
legacy defaults, takes priority. Profile positioning is independent.

`collection.frames` retains the existing renderer format. New `frame_meta`
records the derivation version, source identity and dimensions, applied frame,
horizontal and vertical crop amounts, timestamp, review token and checked state.
The atomic Library save records each changed photo’s previous and new framing
in the tracking journal, with the source and whether the decision was manual
or automatic. Checkpoints include this metadata and its history.

Review and restore validate the source and framing shown to the user. They
reject stale clicks and another character's media. A replacement source
invalidates the previous automatic analysis. Saved manual frames continue to
take priority.

## Validation

Runtime tests cover the crop geometry, EXIF/header checks, eligibility exclusions,
legacy/manual/default precedence, source changes, stale requests, persistence,
checkpoint/journal retention, owner isolation and atomic failure rollback.
DOM tests exercise debug labels, review/restore, stale-error recovery, the actual
leaderboard review filter and production photo placement with legacy references.
The normal product suite also checks ranking, Workbench and the 364 approved
special-edition card renders. The crop review release was exercised in a
disposable Windows Library in Edge, including batch approval, an original
comparison, a custom crop, Undo, Later and flagging a card during a battle.
