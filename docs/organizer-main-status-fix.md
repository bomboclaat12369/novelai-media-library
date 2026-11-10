# Organizer Main placement indicator

The image card previously chose a single label: quarantine, set membership, or
library membership. It never reported Main placement. Cards now show Main
placement separately from set membership in the grid and suggested additions.

Placement comes from the selected character's current companion catalog,
matched by exact image hash and checked against the saved library identity.
The saved `library_instance` is checked against `/api/tracking/status.instance`.
It is a separate identity from the catalog's `stable_library_id` (tracking store).
Review and Purgatory records are not Main. Existing saved inventories work
without rescanning. Metadata is refreshed when organizer state loads and cached
briefly across image responses. Unavailable or mismatched libraries produce an
unknown status instead of a false negative. No source files, memberships,
rankings, or saved organizer inventories are changed by reading this status.

Workbench 2.0.24 incorrectly compared these different identities and therefore
showed "Main status unavailable" for valid saved character sections. Its mocked
catalog tests used matching IDs and missed the error. Workbench 2.0.25 corrects
the identity comparison without changing library or organizer data.

Validation: a new integration test starts the actual companion HTTP server with
a disposable library, imports fixture images, and creates a saved character
section through the real section-sync path. It confirms the IDs are different,
reproduces all-unknown placement before the fix, and verifies Main, set-only,
Review, Purgatory, absent images, simultaneous Main/set membership, and unchanged
saved data after the fix. Older catalogs without a store ID, disconnected
companions, mismatched or missing instance IDs, and request reuse are covered.

All 36 Python organizer checks and 12 organizer DOM checks passed. No live
Windows interface check.

The 13 release-pipeline checks also passed.

Release target: Media Workbench 2.0.25. Publication is authorized; the final
release receipt must confirm published manifests and download verification.
