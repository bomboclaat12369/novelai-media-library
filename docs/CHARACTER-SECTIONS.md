# Folder Organizer character sections (Workbench 2.0.22)

Opening the organizer reads the companion’s character list and retains an offline
copy. Every girl is selectable, including girls without a saved source inventory.
Names refresh from the library; identity uses the library journal namespace and
character UUID. No image scan, embedding/model load or duplicate review starts
merely by opening or switching sections.

Use **Folders…** to add paths or refresh that girl's inventory. Previous paths
remain attached. The full inventory reuses duplicate-check hashes and compatible
analysis; it hashes new or changed files only. This does not redo duplicate
review decisions or automatically analyze clothing. Original, quarantine and
keeper provenance remains recorded. Unsupported/unreadable images still appear
as inventory issues and are not claimed as successfully tracked.

Existing inventories with a known character UUID join that girl's section.
Unlabelled collections remain available by folder name. Select one and use
**Assign to girl…** to explicitly connect it, preserving its work. Display names
are never evidence of ownership. A different library with the same character ID
gets a separate section; legacy jobs are claimed only once.

The first adopted inventory retains its organizer scope and transfer namespace.
Additional inventories combine saved source metadata without clearing previous
files. Secondary scope records are copied once in a transaction, while original
rows remain recoverable. Sets, post statuses, rejections, parked files, stars and
video references are preserved. Primary unfinished selection and resume state
remain active; secondary unfinished states remain in the exported
`previous_collections` record. Conflicting saved set IDs retain a separate
recovered draft instead of overwriting one. Registry changes and adoption events
are recorded in the durable journal and included in database checkpoints.

A failed or interrupted folder refresh retains the previous section inventory.
Missing originals can be found using the existing Missing files tool. Refresh
requires the same companion library; section selection and saved work remain
available offline. Browser integration is covered by DOM tests; no live Windows
or browser-access troubleshooting was performed.
