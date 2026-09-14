# Stability regression checks

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
