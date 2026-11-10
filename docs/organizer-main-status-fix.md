# Organizer Main placement indicator

The image card previously chose a single label: quarantine, set membership, or
library membership. It never reported Main placement. Cards now show Main
placement separately from set membership in the grid and suggested additions.

Placement comes from the selected character's current companion catalog,
matched by exact image hash and checked against the saved library identity.
Review and Purgatory records are not Main. Existing saved inventories work
without rescanning. Metadata is refreshed when organizer state loads and cached
briefly across image responses. Unavailable or mismatched libraries produce an
unknown status instead of a false negative. No source files, memberships,
rankings, or saved organizer inventories are changed by reading this status.

Validation: 34 Python organizer checks and 12 organizer DOM checks passed,
including new coverage for simultaneous Main/set badges, set-only images,
holding areas, changed placement, removed records, wrong character/library,
disconnection, and metadata request reuse. No live Windows interface check.

The 13 release-pipeline checks also passed.

Release target: Media Workbench 2.0.24. Publication is authorized; the final
release receipt must confirm published manifests and download verification.
