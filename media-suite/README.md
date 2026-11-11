# Media Suite for Windows

Open Media Library, Battles, Workbench and After Hours in one regular Google Chrome tab. The four buttons across the top keep each section open while you switch. Battles uses the character selected in Media Library when opening a matchup. The suite remembers the last section for your next launch.

## Install

With Google Chrome installed on Windows, download **Install-Media-Suite.cmd** from the [Windows suite release](https://github.com/bomboclaat12369/novelai-media-library/releases/tag/media-suite-v1.1.0) and run it. It checks the package hash and installs the local launcher for your account. Your Desktop and Start shortcuts open the suite in Chrome. Opening the shortcut again selects the existing suite tab. To install from the ZIP, extract it and double-click **Install Media Suite.cmd**.

The first installation also prepares a main Git checkout next to the existing After Hours checkout, usually at C:\Codex\Media-Suite, and opens a new local Codex chat with a starter message. Press Send in that chat. Use the existing After Hours chat for game development. **Media Suite - Main Codex** in Start can reopen the first-time setup if it was interrupted. Future day-to-day work belongs in the same chat.

## Connect existing applications

Running services are recognized on their normal loopback addresses. For a cold start, the suite looks in common installation locations. Open **Locations…** once if a folder is missing or several copies exist.

| Location | Choose |
| --- | --- |
| Media folder | Your existing folder containing library.json. |
| Media Library program | Your installed folder containing companion.pyw, run.bat and its .venv. |
| Workbench program | Your installed duplicate-review folder with app.py and its .venv. Its parent is also accepted. |
| After Hours program | The game folder containing Launch.ps1. Its project or After-Hours-Codex parent is also accepted. |

The companion starts in the background for Library, Battles and Workbench. Workbench launches with its installed updater and normal review database. After Hours launches through its own Launch.ps1 and reads its configured library and save. Closing the Chrome tab leaves the local services available for ongoing jobs and the next launch. Quit in Workbench and Restart game retain their usual behavior.

The launcher reads your existing suite locations from %LOCALAPPDATA%\NovelAI Media Suite. Chrome stores browser-only preferences in your Chrome profile, so the first Chrome launch can require selecting a character again. The original programs manage media, queue data, rankings and game saves. Each program has its own loopback browser origin. The launcher streams media and uploads to the selected local services.

## Development

Use .NET SDK 8, Python with Pillow and Google Chrome. Run `python media-suite/make-icon.py`, then `dotnet publish media-suite/MediaSuite.csproj -c Release -r win-x64 --self-contained true` and `python media-suite/package.py`. The service tests run with `dotnet run --project media-suite/tests/core/CoreChecks.csproj -c Release`.

The Windows workflow tests the packaged shortcut in Chrome, builds a disposable collection and career, drives all four real pages and checks a Workbench import through a tab switch. The fixture supports `--isolated-ports` on a PC with running services. A suite release publishes the Windows ZIP, a hash-checking downloader and its manifest. The release receipt records verification of both downloads. Increment the suite project version for a changed public binary. Existing application release manifests are managed by their respective publishers. See [main thread handoff](MAIN-CODEX.md).
