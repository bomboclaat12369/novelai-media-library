# Durable background tracking — schema 1

Companion 2.7.75 and Workbench 2.0.21 add local metadata history without new
normal-screen controls or extra review steps. Automatic clothing-color detection
and browser-access troubleshooting remain paused. No media bytes, vector BLOBs,
page navigation or thumbnail-view telemetry are copied into the journal.

## Evidence and meaning

| Area | Records retained | Interpretation |
| --- | --- | --- |
| Sources | Known original names, paths, source URLs, accounts/posts, origin/copy records, import observations and inventory batches | A second exact import retains its source even when only one media item survives. Unknown browser paths are not fabricated. |
| Identities | Existing media/set UUIDs, a persistent library UUID, collection UUIDs, folder UUIDs and path aliases | Legacy organizer scope keys and duplicate catalog guards stay compatible. A path change alone does not prove two folders are the same; a future explicit relocation can register another alias for the existing identity. |
| Relationships | Exact/hash evidence, same-photo recipe/results, explicit keeper/origin links, proposal evidence, source/post membership, set membership and replacements | Similarity, shared post, shared set, exact bytes and verified same-photo are distinct kinds. A replacement alone does not prove same-photo or higher resolution. Crop edits remain explicit metadata changes. |
| Decisions | Positive and negative duplicate decisions, keeper hashes/paths, score/kind when present, algorithm versions, revocation and timestamps | Scan-cache resets do not erase decisions. An unknown historical actor/confidence is not relabeled manual or certain. |
| Sets | Creation, name/details, added/removed members and positions, reorder, transfer mappings and deletion tombstones | Independent of the 20-item Undo list. Membership deltas allow later move/split/merge interpretation without inventing an explicit merge action today. |
| Negatives | Rejected candidates, separated/ignored pairs, discarded items, deferred posts/images and pins | Unassigned, unevaluated, deferred and explicitly rejected remain different states. |
| Replacements/deletion | Old/new hashes and metadata, origins, retained operation evidence, deleted media/set snapshots | Metadata persists beyond Undo expiration. This does not promise permanent storage of deleted original bytes. |
| Provenance | Mutation entry point, known actor, operation ID, implementation marker, source facts, field derivation rules | Manual action provenance does not assert every resulting field was typed. Color tags retain existing literal-name/manual rules; automatic image color detection is not enabled. |
| Analysis | File hashes/stamps, model/recipe/version, config, completed/cache-reused/failed states, selected cohorts and omissions | Rebuildable vectors remain in caches. Durable coverage supports later selective reanalysis. Missing coverage is unknown, never an implicit negative. |

Migration observes existing library records, surviving Undo/replacement/cleanup
records, saved Workbench jobs, inventories, decisions and analysis metadata once.
The observation date is recorded separately; unknown original action dates stay
unknown. Information already discarded by older versions cannot be reconstructed
from metadata alone. No automatic rescan or new model download is started.

## Persistence and recovery

The companion owns `tracking.sqlite3` beside `library.json`. The JSON save embeds
a private outbox and batch ID in the same fsynced atomic replacement as the user
change. Replay is idempotent. A ledger failure after JSON commit leaves that
outbox pending, reports it through existing diagnostics, and does not falsely
claim the application mutation rolled back. The next write must replay it first.
Public library responses exclude all outbox fields. The latest outbox is bounded
by the last operation, rather than growing with the full history.

Workbench journals live inside its three existing SQLite databases. Triggers
commit relevant column changes with the mutation, omit BLOBs and transient scan
deletions, and handle INSERT OR REPLACE using current projection rows. All writer
connections register the shared journal functions. Schema installation does not
implicitly commit callers' transactions. Application IDs are never transient
SQLite file row numbers: pair decision records capture hashes/paths at decision
time. A small in-memory inventory comparison cache advances only after commit.

Manual and daily library JSON backups have a sibling `.tracking.jsonl` file;
copy both when moving one of these backups. Checkpoint ZIPs include verified
`tracking.jsonl`. Complete project checkpoints also include all three Workbench
databases. Restore merges history while restoring application state, preserving
later evidence and recording the restore. Legacy checkpoints remain readable.
Workbench's existing JSON exports include journal records. Organizer transfers
send bounded, resumable history pages before applying drafts; stable event IDs
make retries safe, and destination-instance cursors avoid retransmitting old
history. Large single records use checksum-verified fragments. No growing journal
is sent in normal screen/status responses.

History schemas: `tracking_events` (immutable ID/store/time/kind/entity/payload),
`tracking_heads` (deduplication/current projection), `tracking_identities` (typed
alias → stable identity), and `tracking_meta` (schema/migration/transfer cursors).
Query history by kind/entity/store; preserve these namespaces in future tools.
Never interpret a `legacy_observation` as a new decision. `at` is an observation
or commit time; source metadata may carry a separate original timestamp.

## Validation

Failure/restart tests cover atomic JSON failure, post-commit ledger failure,
blocked replay, repeated imports, pruning Undo, set deletion, source retention,
manual provenance, analysis deduplication, fragmented transfers, transaction
rollback, cache resets, collection switching and checkpoint-history union.

Synthetic Linux measurements (not Windows guarantees): at 30,000 images and 750
sets, favorite edits measured 59.61 ms before and 66.73 ms after (20-edit median).
The new journal was 55,586,816 bytes; those 20 later edits grew it by 12,288 bytes.
Initial recording of the synthetic 30,000-item batch took 3.83 seconds, versus
0.67 seconds for a metadata-only save before tracking. This is initial history
creation, not repeated work on every edit. Restart preserved all metadata.
At 30,000 Workbench inventory records, first persistence took 3.18 seconds and
unchanged saves took 184 ms median; five repeat saves added zero history events.
These fixtures perform no image decoding, downloads, or real-user file changes.
Reproduce the companion comparison with `python tools/benchmark-tracking.py`.

DOM/native rendering checks cover the existing interface and approved artwork.
Live browser access and Windows installer behavior remain untested in this run.
