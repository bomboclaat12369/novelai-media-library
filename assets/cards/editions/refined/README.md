# Approved larger-photo cards

Former #1, Valentine's and Cosplay reproduce the approved November 2026 card studio, including the narrowed Valentine's rank plaque. The common outer canvas is 1050 × 1500; the rectangular photo viewport is x=105, y=195, width=840, height=1120 (3:4). Ornaments overlap parts of the viewport.

`*-source.png` retains the full generated source artwork. The matching production `.png` is the transparent 1050 × 1500 output of `renderer.js` → `frame`, using `studio-layout.json`. This preserves the exact nine-region rendering accepted in the studio; the source PNG alone is not the normalized layout. Labels remain live, using the studio renderer embedded in the edition payload. Rank fits center the original visible emblem bounds.

Only these three edition assets and layouts changed. The other nine published editions, all seven rank tiers, owned traits and automatic Captain rules remain available.

Existing non-default saved framing uses its old viewport as a rendering reference. The editor carries this reference into an explicit save; Reset uses the current opening. No bulk rewriting of saved frames or user media occurs. Untouched Fit/Fill photos use the new opening directly.

Validation: approved studio composites inspected at full and 240px size; five edition/persistence tests; production framing function checked across three editions, portrait/landscape Fit/Fill, three card sizes, saved references, reset and display-only toggle; release and asset hashes checked. Browser automation was unavailable because the browser download was truncated; this is not a browser interaction pass.
