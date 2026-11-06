# Approved seam repairs — 2.9.25

Signature, Hall of Fame, #1, Valentine’s, Christmas and Whore now use the six
approved November 4 repairs recovered intact from the handoff. Original PNGs
and their checksums are retained under `../repairs/2026-11-04/` and in
`tools/import-approved-card-repairs.cjs`. Integration adds one transparent row
and column to the native 1049×1499 art; it does not crop or resample it.
Production WebP is a lossless encoding of the normalized PNG. The importer and
encoder can reproduce these six frames without touching the other seven.

The approved 840×1120 photo viewport, runtime overlay guides, saved photo
positions and Pregnant card are unchanged. Native render checks cover all
13 editions, seven ranks and both placement/legacy-rating modes. Visual review
uses the real renderer with neutral photo placeholders; it is not a live
Windows/browser layout test.

Rebuild only these repairs:

```
node tools/import-approved-card-repairs.cjs
python tools/encode-card-frames.py signature hall-of-fame number-one valentines christmas whore-stage
```

---

# Current production checkpoint: 2.9.21

`../catalog.json` and its referenced `.webp` assets are authoritative for current
production frames and measured guides. The older `baseline.json`, PNG/source
artwork, and `layout-guides.json` below are historical checkpoints and must not
be re-imported over this release without reconciliation.

Eleven frame assets have locally regenerated upper rating/rank housings. Their
central motifs, rails and footers are preserved outside the local patches. The
#1 and Hall of Fame patches are the exact approved viewer composites. The
Pregnant artwork and full catalog entry are unchanged. Ass's artwork is also
unchanged. All output frames remain 1050×1500 lossless WebP with transparency.

The catalog `rankColoredOverall` flag enables emblem-colored overall numerals
and neutral smaller OVR text. Updated overall labels use the same bundled
numeral font under the EditionRankNumeralsV1 alias, loaded from bytes to avoid
blocked data-URL font requests in the local app. Pregnant does not opt in.
Names and placements retain their existing font path. Shared guide rendering
continues centering the complete visible text and fitting it inside the plaque
polygon. Rank geometry remains based on each emblem's visible alpha bounds.
Photo opening and saved framing references, plus all name/placement guides,
are preserved. Ass's corrected placement anchor remains [525.5,1426.5].

Browser and native-renderer verification cover all cards, seven ranks, overall
values 0–99, 7/92 placements, long names, and the packaged update document.

---

## Historical checkpoint notes

# Approved larger-photo cards — all 13 editions

The authoritative production checkpoint is now `baseline.json` and
`layout-guides.json`, using `frame-renderer.js` and `guide-renderer.js`. The older
trio-only `studio-layout.json` and `renderer.js` below remain historical files.

Every `*-source.png` is byte-identical to the approved source artwork. Normalized
`.png` frames are transparent 1050 × 1500 lossless renders. Production `.webp`
frames are lossless, pixel-identical encodings of these PNGs. Run
`python3 tools/encode-card-frames.py` after importing a checkpoint. The viewport is exactly
x105 / y195 / width840 / height1120 (3:4), with the accepted frame overlaps.
Ass's original upper WebP is composited unchanged above y1200; its refined footer
is below that line. No private preview photographs are included in the release.

The 52 saved guides specify actual plaque outlines, fitting limits and centers.
The complete visible name/number is centered and fits its polygon. Side-by-side
OVR is one centered group; existing number-only preferences remain supported.
Ass's user-corrected placement anchor is [525.5,1426.5].

All seven emblem assets remain unchanged from the approved checkpoint. Visible
bounds use alpha >8 consistently, so nearly transparent fringe does not skew
centering. Rank fits preserve proportions and center on the saved slot anchor,
including the accepted 15% enlargement on #1, Birthday and Hidden Gem. They are
not clipped to their plaques. Existing saved photo references are preserved.

Validation uses native canvas and a lightweight DOM harness for the production
decorator, actual rank alpha bounds, 7/92 and long-name alignment, both OVR modes,
all 13 native frames and asset hashes. Focused runtime tests cover Ass eligibility,
owned traits, automatic editions, save/reload and unchanged media/battle state.
Framing checks cover all 12 previously published editions, saved compositions,
Fit/Fill, reset and hidden frames at three display sizes. A real browser was not
available; these are not browser CSS/layout tests. The actual larger-than-12-MiB release also
passes both verified document-download paths with the new 32 MiB allowance.

## Previous trio release

Former #1, Valentine's and Cosplay reproduce the approved November 2026 card studio, including the narrowed Valentine's rank plaque. The common outer canvas is 1050 × 1500; the rectangular photo viewport is x=105, y=195, width=840, height=1120 (3:4). Ornaments overlap parts of the viewport.

`*-source.png` retains the full generated source artwork. The matching production `.png` is the transparent 1050 × 1500 output of `renderer.js` → `frame`, using `studio-layout.json`. This preserves the exact nine-region rendering accepted in the studio; the source PNG alone is not the normalized layout. Labels remain live, using the studio renderer embedded in the edition payload. Rank fits center the original visible emblem bounds.

Only these three edition assets and layouts changed. The other nine published editions, all seven rank tiers, owned traits and automatic Captain rules remain available.

Existing non-default saved framing uses its old viewport as a rendering reference. The editor carries this reference into an explicit save; Reset uses the current opening. No bulk rewriting of saved frames or user media occurs. Untouched Fit/Fill photos use the new opening directly.

Validation: approved studio composites inspected at full and 240px size; five edition/persistence tests; production framing function checked across three editions, portrait/landscape Fit/Fill, three card sizes, saved references, reset and display-only toggle; release and asset hashes checked. Browser automation was unavailable because the browser download was truncated; this is not a browser interaction pass.
