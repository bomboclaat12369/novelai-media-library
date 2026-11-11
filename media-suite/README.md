# Media Suite for Windows

Open Media Library, Battles, Workbench and After Hours in one regular Microsoft Edge tab. Each mode fills the tab. Click **Mode** in the bottom-right corner to open the menu above it. A checkmark shows the current mode. Each page keeps your place when you switch, and the suite remembers the last mode for your next launch. Battles uses the character selected in Media Library when opening a matchup.

## Install

For first-time setup, run **Install-Media-Suite.cmd** from the [Windows suite release](https://github.com/bomboclaat12369/novelai-media-library/releases/tag/media-suite-v1.3.0). Your Desktop and Start shortcuts use the frontmost Edge browser window and its profile. If that window already has a suite tab, the shortcut selects it. When all Edge windows are closed, the shortcut starts Edge normally. To install from the ZIP, extract it and double-click **Install Media Suite.cmd**.

Version 1.2.0 and later check the Windows suite update feed automatically. A new session checks before opening. While the suite is running, it can stage a release in the background. The next shortcut launch after all suite tabs close applies the verified version. An active tab or request keeps its current host. An offline or interrupted check uses the installed version and retries later. The updater checks the ZIP size and SHA-256 and verifies the files before selecting the new version.

For an existing pre-1.2 installation, running the verified package's `Install.ps1 -OnNextLaunch` queues the one-time migration behind the usual Desktop and Start shortcuts. Finish the current session and use either shortcut when ready.

Starting with 1.3.0, opening the suite checks the connected apps even when the Windows launcher is current. **Mode → Updates…** shows each result and offers one **Check for updates** button. Media Library and Battles share the companion and its verified interface cache. New pages use the updated interface. Workbench verifies its own package and restarts after all suite tabs close and its active jobs finish. The individual update controls are hidden in suite views and available in standalone views. Checks run again while the host is open and on a new session.

After Hours publishes releases from its game project. The suite reads `release-after-hours.json` on `game-build-20261109`, checks the size and SHA-256 of `Update-AfterHours.ps1` on the matching `after-hours-vX.Y.Z` release, and gives it a separate cache per connected installation. The adapter stages and applies a verified game package and launches it using the original game folder and library settings. Exit 75 defers a busy activation. Until a release is applied, the suite uses the existing game launcher. The game chat owns the release assets and save compatibility.

The suite also checks the companion program that powers Library and Battles. Its headless session uses the installed Python environment and original media folder. The suite stages verified runtime files in its own cache. A busy import, request, thumbnail queue, or running scan defers activation. A companion already open outside the suite continues its session, and the verified runtime is available on the next suite-owned start.

The first installation also prepares a main Git checkout next to the existing After Hours checkout, usually at C:\Codex\Media-Suite, and opens a new local Codex chat with a starter message. Press Send in that chat. Use the existing After Hours chat for game development. **Media Suite - Main Codex** in Start can reopen the first-time setup if it was interrupted. Future day-to-day work belongs in the same chat.

## Connect existing applications

Running services are recognized on their normal loopback addresses. For a cold start, the suite looks in common installation locations. Choose **Mode → Locations…** if a folder is missing or several copies exist.

| Location | Choose |
| --- | --- |
| Media folder | Your existing folder containing library.json. |
| Media Library program | Your installed folder containing companion.pyw, run.bat and its .venv. |
| Workbench program | Your installed duplicate-review folder with app.py and its .venv. Its parent is also accepted. |
| After Hours program | The game folder containing Launch.ps1. Its project or After-Hours-Codex parent is also accepted. |

The companion starts in the background for Library, Battles and Workbench. Workbench launches with its installed updater and normal review database. After Hours launches through its own Launch.ps1 and reads its configured library and save. Closing the Edge tab leaves the local services available for ongoing jobs and the next launch. Quit in Workbench and Restart game retain their usual behavior.

The launcher reads your existing suite locations from %LOCALAPPDATA%\NovelAI Media Suite. Edge stores browser-only preferences in the selected profile, so a new profile can require selecting a character again. The original programs manage media, queue data, rankings and game saves. Each program has its own loopback browser origin. The launcher streams media and uploads to the selected local services.

## Development

Use .NET SDK 8, Python with Pillow and Microsoft Edge. Run `python media-suite/make-icon.py`, then `dotnet publish media-suite/MediaSuite.csproj -c Release -r win-x64 --self-contained true` and `python media-suite/package.py`. The service tests run with `dotnet run --project media-suite/tests/core/CoreChecks.csproj -c Release`.

The hosted Windows workflow tests the packaged shortcut in two Edge profiles, checks automatic updates, drives all four real pages with disposable data and verifies a Workbench import through a mode switch. A suite release verifies the public ZIP and downloader, then promotes the manifest to `release-media-suite.json` on main. The release receipt records verification of the downloads and feed. Increment the suite project version for a changed public binary. See [main thread handoff](MAIN-CODEX.md).
