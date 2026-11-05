# Publishing without large chat payloads

The standalone page currently embeds more than 16 MB of code, artwork and fonts.
Keep that file on disk. Do not print it, Base64-encode it into tool arguments, or
upload it through a connector that accepts file contents as chat text.

`publish-source-release.py` builds in a temporary Git worktree, checks the
assembled files, creates payload and manifest commits locally, and transfers
them with **one ordinary Git push**. The source checkout stays unchanged.
GitHub Actions supplies Git authentication and handles the large transfer.
No new token or secret is required when the repository's Actions token has
`contents: write`. Workflows may need additional installation permission when
first added through an external GitHub connection.

## First installation

The checked-in `.github/release-request.json` has `publish: false`. Pushing this
pipeline and request runs its regression tests and a real standalone build,
without publishing an application update. The run appears under **Actions →
Build and publish from source**. Its `release-receipt` artifact contains the
result, byte counts, checksums and build log. The application release configs,
manifest, source modules and artwork do not change during this installation.

The legacy runtime/userscript workflows remain intact. Their existing product
test failures are not suppressed by this transport fix. This new workflow checks
release integrity and publication mechanics; it does not claim those product
suites or browser checks passed.

## An authorized application release

1. Recover the intended source changes and compare them with current `main`.
   Do not assume work from an interrupted chat is already in the repository.
2. Run the feature's relevant product checks. Address failures before requesting
   a live release. Keep browser/layout limitations explicit.
3. Bump the versions of changed components. Use new names for changed versioned
   payload modules; existing manifests can still reference old names. Never
   overwrite a published userscript part or reuse a version for different bytes.
4. Commit/push only the authorized source, assets, release configs, and the small
   `.github/release-request.json`. Do not include generated standalone HTML,
   runtime chunks or Workbench ZIPs. Unchanged artwork need not be uploaded.
5. Give the request a new `id`, list the intended components, and set `publish`
   to `true` only when publication is authorized. Available components are
   `standalone`, `userscript`, `runtime`, and `workbench`. Include
   `workbench_notes` when selecting Workbench. Its source version is in
   `duplicate-review/engine.py`; its bundle includes the companion source, so
   a changed bundle also needs a new Workbench version.
6. Watch the workflow. A successful build alone is not a completed update. The
   final receipt must say `published_verified` after both manifest routes and
   the downloadable bytes match. Network verification retries for cache delay.

Example request (dry run until explicitly changed):

```json
{
  "schema": 1,
  "id": "replace-with-a-unique-release-id",
  "components": ["standalone", "runtime", "workbench"],
  "publish": false,
  "workbench_notes": "Describe the approved Workbench changes here."
}
```

The workflow can also be run manually. Its Publish checkbox defaults to false.
Rerunning starts from the current branch, so an already published identical
release is a no-op. Publication is limited to `main`.

## Local use

Use a committed checkout and the pinned minifier:

```sh
npm ci --prefix tools --ignore-scripts --no-audit --no-fund
python -m unittest discover -s tests -p test_release_pipeline.py -v
python tools/publish-source-release.py --components standalone
```

This is a dry run and needs no push credentials. The report and expected
manifests are saved under `.release-output/`. Source edits must be committed
first; the isolated build intentionally excludes uncommitted changes.

In a checkout with authenticated Git, the same command with `--publish` can
publish an authorized release. Its source commit must be the current remote
`main`; it refuses stale source, version downgrades, same-version byte changes,
missing inputs, corrupt assemblies and documents exceeding the installed
updater's 32 MiB limit. Git checks the remote again before the single push and
never force-pushes. Unselected component manifest fields are preserved.

Media Library keeps its existing `main` payload URLs because installed clients
require that prefix. Workbench keeps immutable commit URLs. Payload objects and
their final manifests become reachable together; an interrupted transfer does
not advance `main` to an incomplete release.

## Recovery

- `failed`: validation or a pre-push check failed; inspect the report and log.
- `push_started` or `publication_unconfirmed`: inspect current `main` before
  retrying. A lost acknowledgement can occur after the server accepted a push.
  Expected manifests and commit IDs were saved before the push. Start the retry
  from current `main`, or verify the saved expected manifests if it succeeded.
- `pushed_verification_pending` or `published_verification_failed`: the push may
  already be complete. Retry verification using the saved expected manifests;
  do not bump versions or rebuild merely because a raw URL was still cached.
- `dry_run_passed`: packaging checks passed, with no remote release write.
- `published_verified`: both manifest routes and downloaded artifacts match.

For example, from the original source checkout with its saved receipt:

```sh
python tools/verify-published-release.py --components standalone \
  --expected-dir .release-output --report .release-output/report.json \
  --attempts 24 --interval 15
```

The regression tests use disposable local bare Git repositories. They exercise
documents over 16 MiB, failed/retried pushes, concurrent branch movement,
same-version replacement rejection, component isolation, complete Workbench
assembly, corrupt downloads, stale manifests and idempotent retries. They do
not access the user's collections or publish to GitHub.
