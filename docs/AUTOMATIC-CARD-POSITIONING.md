# Automatic card positioning

Media Library 2.9.28 and companion 2.7.78 (also bundled with Workbench 2.0.30)
automatically position eligible images when collection settings load. Opening or
refreshing Battles loads these settings for both existing and newly imported
images. Normal card browsing has no additional badges or controls.

## Conservative first policy

The shared card photo window is 840 × 1120, a 3:4 opening. Policy
`center-height-v1` covers that opening with a centered image only when its
displayed ratio is slightly wider and the necessary side crop is at most 4%
per edge. It never crops vertically to qualify a taller image. A 4:5 image uses
16/15 of its original Fit scale and hides 3.125% from each side. Already matching
3:4 photos need no adjustment and stay at default.

The runtime uses known dimensions to shortlist candidates, then verifies their
original file headers and EXIF orientation. It skips missing/unreadable files,
unknown dimensions, animated images, videos, removal flags, Review/Purgatory,
images outside Main, and images with saved library crops. It does not decode,
resize or rewrite image files and needs no model or remote image service.

The saved frame contains an explicit reference to the common opening. This
prevents legacy frame references from shifting an automatic crop when a special
edition is shown. Base and special editions retain the existing renderer and
artwork. Geometry guarantees edge alignment within the shared photo window;
composition and artwork overlapping the image still require visual judgment.

## Review and overrides

In the leaderboard, enable **Debug mode**, then use **Crop filter**:

- **Auto-positioned · Unchecked**: automatic crops awaiting optional review.
- **Auto-positioned · Checked**: automatic crops the user has checked.
- **All auto-positioned**, **Manual custom crops**, or **Default crops**.

An automatic crop offers **Mark checked** (or **Mark unchecked**), **Position /
crop**, and **Restore default**. Restore immediately saves centered Fit at 1×;
normal editor adjustments save through the existing Save framing control.
Both paths preserve an explicit manual frame, including a deliberate default,
so automation cannot reapply over it. Every previously saved frame, including
legacy defaults, takes priority. Profile positioning is independent.

`collection.frames` retains the existing renderer format. New `frame_meta`
records the derivation version, source identity and dimensions, applied frame,
side crop, timestamp, review token and checked state. The existing atomic
library save and durable character tracking journal retain before/after
evidence. Checkpoints include this metadata and its history.

Review and restore validate the collection revision and the exact automatic
frame token shown to the user. They reject stale clicks and another character's
media. A replacement source invalidates the previous automatic frame/review;
eligible replacements get a fresh unchecked crop, otherwise the automatic
frame is removed. Saved manual frames continue to take priority.

## Validation

Runtime tests cover the crop geometry, EXIF/header checks, eligibility exclusions,
legacy/manual/default precedence, source changes, stale requests, persistence,
checkpoint/journal retention, owner isolation and atomic failure rollback.
DOM tests exercise debug labels, review/restore, stale-error recovery, the actual
leaderboard review filter and production photo placement with legacy references.
The normal product suite also checks ranking, Workbench and the 364 approved
special-edition card renders. No live Windows desktop verification is claimed.
