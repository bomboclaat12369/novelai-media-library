# NovelAI Media Library

A local image/video library overlay for `novelai.net`, consisting of a Tampermonkey userscript and a small local Python companion.

## Automatic updates

As of **v2.2.0**, both runtime pieces are designed to update without copying/pasting future releases:

- **Tampermonkey userscript:** `novelai-media.user.js` contains `@updateURL` and `@downloadURL` metadata pointing at this repository. Tampermonkey's normal userscript updater installs newer versions when the `@version` increases.
- **Local companion:** `companion.pyw` checks `manifest.json` on startup. The userscript also asks a v2.2+ running companion to check for updates. If a newer verified companion is published, it replaces itself and restarts automatically.
- **Integrity:** companion updates are verified against the SHA-256 stored in `manifest.json` before replacement.

The user's actual library (`library.json`, media, thumbnails and backups) remains local and is **not** stored in this repository.

## One-time bootstrap from v2.1 or earlier

Older companions cannot retroactively self-update, so there is one final bootstrap step. You can either update the two runtime files manually once, or download/run `bootstrap-auto-update.bat` and select your existing NovelAI Media Library program folder.

The bootstrap updates only the program file `companion.pyw`; it does not touch the media library or `library.json`. It also opens the stable `.user.js` URL so Tampermonkey can install the self-updating script once.

## Fresh install

1. Put `companion.pyw`, `requirements.txt`, `setup.bat`, and `run.bat` together in one folder.
2. Run `setup.bat` once.
3. Run `run.bat` whenever using the NovelAI media viewer.
4. Install `novelai-media.user.js` in Tampermonkey.

## Publishing future changes

For a userscript change, increment its `@version` before publishing. For a companion change, increment `APP_VERSION`, publish `companion.pyw`, then update `manifest.json` **last** with the new version and SHA-256. Publishing the manifest last prevents clients from seeing a manifest that points at a not-yet-published companion.
