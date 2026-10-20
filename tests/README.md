# Stability regression checks

## Standalone 2.8.94 / runtime 2.7.57 validation

`test_runtime_holding_assignments.py` passed four focused tests covering new
regular/ghost category assignments from both holding areas, category Undo, set
creation and assignment, and preservation of holding state on unrelated edits.
All seven existing `test_runtime_rapid_queue.py` checks passed, including durable
queue persistence, atomic failure, bulk assignment and duplicate protection.
The ghost-category expectation now reflects automatic exit from Purgatory while
remaining outside Main.

`test-rapid-controls.cjs` passed in Chromium with a 60-image temporary queue:
1700×1050 and 1366×768 layouts without control overflow, retained grid space,
scroll position and thumbnail size, the matching entry point with no selection,
creating/assigning sets, adding to Review, and assigning a ghost category from
Review without accidental Main promotion. Both layouts were visually inspected.
The matching service is stubbed in this UI test; the outfit model was not changed
or retested. NovelAI's UI config and payload hash remain unchanged at 2.8.93.

## UI 2.8.93 / runtime 2.7.56 validation

Three focused checks in `test_runtime_viewer_release.py` passed: leaving holding
areas without changing set membership or promoting to Main (including Undo),
category membership timestamps, and speculative forecasts that neither mutate
saved state nor fit history, while a real vote fits it exactly once.

`test-viewer-release.cjs` passed in Chromium for standalone and NovelAI. Coverage
includes the redesigned editor, retained favorites/featured, actual image crop
saving, profile editing and sorted/category-filtered photo selection, wide view,
image-only imports and page-wide drops, Review/Purgatory removal, viewer badges,
Recent movement returning to Leaderboard, and history without plotted circles.
The NovelAI fixture also plays a generated video, saves a timestamp and thumbnail,
and checks the absence of management controls. No page errors were reported.
The editor was visually inspected, and release syntax/hashes were checked.

Run the focused checks with:

```sh
python3 -m unittest discover -s tests -p test_runtime_viewer_release.py -v
NAI_CHROMIUM=/path/to/chromium node tests/test-viewer-release.cjs
```

These use synthetic temporary libraries, not the user's installed Windows app.
The broader historical suites were not rerun for this release. The legacy
review-DOM baseline below remains unchanged.

## UI 2.8.92 / runtime 2.7.55 validation

Focused runtime checks passed in `test_runtime_collection_ranking.py`,
`test_runtime_ranks.py` and `test_runtime_placement.py`: broad initial coverage,
placement completion, category scoping without splitting ratings, focus return,
removal-flag eligibility without changing ratings, direct/indirect/Undo graph
points, read-only history queries, progressive awards, and persistence/Undo.
`test-battle-grid-logic.cjs` also passed.

Real Chromium passed `test-battles-ui.cjs` for standalone and NovelAI: category
photo filtering, scoped placement battles, original-resolution images, voting,
Undo, history graphs, removal flags and the flagged library view, rank sorting
controls/badges, trophy cards, and no battle controls or requests on NovelAI.
`test-ranks-design.cjs` passed at wide and compact sizes; trophy layouts were
also visually inspected. Build/hash checks cover the versioned artifacts.
These checks use synthetic local images, not the user's installed Windows app.
The legacy review-DOM baseline failures documented below remain outside this release.

## UI 2.8.91 / runtime 2.7.54 validation

Historical-rating migration, fixed-prior/no-double-counting behavior, linked Undo,
all three outcomes, contradictory evidence, order independence and exact two-entry
marginal uncertainty are covered by `test_runtime_joint_history.py`. A synthetic
220-entry / 1,600-vote fit takes roughly one second in the validation environment.
The runtime suite passed (112 tests before adding the additional covariance check);
the joint-history module then passed all nine collected tests. The 18 UI stability
unit checks also passed.

Real Chromium checks passed in `test-battles-ui.cjs`, `test-battle-gallery-ui.cjs`
and `test-ranks-design.cjs`: original dimensions in both image and set battles,
preloading, voting/Undo, profiles, gallery controls, and absence of battle controls
and ranking requests in NovelAI. Independent-version handling is covered by
`test_runtime_efficiency.py`; use `NAI_CHROMIUM` for the browser executable.

Known baseline: `test-review-dom.cjs` has 23 failures in both this release and the
published 2.8.90 payload (checked with its exact release config). These older
fixtures target removed controls, obsolete queue paging and earlier import APIs.
They were not disabled or treated as passing; the legacy UI workflow will still
report them. Release artifacts and manifest hashes are built and verified locally
with `python3 tools/build-release.py` and published together.

Run from the repository root:

```sh
node --test tests/test-ui-stability.cjs
python -m unittest discover -s tests -p 'test_runtime_*.py' -v
```

The release workflows run the relevant checks before publishing a manifest.

The JavaScript tests exercise the real shared transport with a controllable fake
Tampermonkey transport. They check request limits, foreground capacity, concurrent
read sharing, invalidation after writes, cancellation, timeout handling, and cached
loader startup. A minimal mutation/animation-frame model runs the actual video
placement functions: the previous immutable part is a negative control that keeps
scheduling; the corrected part must settle for both image and video selections.
The complete payload selected by `release-userscript.json` is syntax checked.
Set `NAI_RELEASE_CONFIG` to a repository-relative candidate config to check it
before publishing.

The Python tests use temporary disposable libraries and the actual store and POST
dispatch code. They hold a thumbnail decoder open while importing a batch and
saving Review state, verify one daemon processes the queue, and check deletion,
decoder failures, no-op saves, video favorites, Sets, and metadata-only cropping.

These are deterministic regression checks, not end-to-end measurements of
Tampermonkey, NovelAI, or Windows networking. Slow foreground requests log their
queue time separately from dispatched-request time under `[NovelAI Media timing]`.
