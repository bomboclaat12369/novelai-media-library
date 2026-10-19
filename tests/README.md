# Stability regression checks

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
