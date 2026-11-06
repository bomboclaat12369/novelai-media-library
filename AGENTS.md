# Working on Media Library and Media Workbench

- Follow the user's authorization for implementation and publication separately.
  Do not push a release merely because the user asked a feasibility question.
- For any publishing work, read `tools/PUBLISHING.md` first. Use the source
  release workflow or authenticated Git from disk. Never copy generated HTML,
  encoded artwork, ZIPs or Base64 release payloads into chat/tool arguments.
- Read source modules selected by the current release configs. Keep tool output
  bounded; report paths, sizes, hashes and short error summaries, not bundled
  documents or full source dumps. Base64 is not a workaround for a tool limit.
- Run the relevant product tests for the actual feature changes, then the
  release-pipeline checks. Packaging checks do not establish UI correctness.
- Preserve approved artwork and its quality. Do not shrink or regenerate card
  art to work around the upload transport. Do not disable failing checks to ship.
- Announce an update ready only after the published manifest and downloadable
  payload have been verified. Keep failed publication distinct from failed
  verification after a successful push, and preserve the release receipt.
- Preserve useful source, identity, relationship, decision, membership and analysis
  evidence when adding workflows. Use the durable tracking journal and existing
  transaction/outbox helpers; Undo and rebuildable caches are not history stores.
  Keep unknown facts unknown, version derivations, and carry evidence through
  export/transfer/restore. Do not add routine UI clutter or click telemetry.
