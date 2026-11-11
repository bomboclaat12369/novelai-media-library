# Media Suite for Windows

Open Media Library, Battles, Workbench and After Hours in one window. Each tab keeps its live page while you switch. The Battles tab uses the character selected in the Library when opening a matchup. The suite remembers the last tab for your next launch.

## Install

Download **Install-Media-Suite.cmd** from the [Windows suite release](https://github.com/bomboclaat12369/novelai-media-library/releases/tag/media-suite-v1.0.0) and run it. It checks the package hash, installs the 64-bit Windows app for your account, adds Desktop and Start shortcuts, and opens Media Suite. To install from the ZIP, extract it and double-click **Install Media Suite.cmd**. You can pin the installed shortcut to your taskbar.

The first installation also prepares a main Git checkout next to the existing After Hours checkout, usually at C:\Codex\Media-Suite, and opens a new local Codex chat with a starter message. Press Send in that chat. Use the existing After Hours chat for game development. **Media Suite - Main Codex** in Start can reopen the first-time setup if it was interrupted. Future day-to-day work belongs in the same chat.

## Connect existing applications

Running services are recognized on their normal loopback addresses. For a cold start, the suite looks in common installation locations. Open **Locations…** once if a folder is missing or several copies exist.

| Location | Choose |
| --- | --- |
| Media folder | Your existing folder containing library.json. |
| Media Library program | Your installed folder containing companion.pyw, run.bat and its .venv. |
| Workbench program | Your installed duplicate-review folder with app.py and its .venv. Its parent is also accepted. |
| After Hours program | The game folder containing Launch.ps1. Its project or After-Hours-Codex parent is also accepted. |

The companion starts in the background for Library, Battles and Workbench. Workbench launches with its installed updater and normal review database. After Hours launches through its own Launch.ps1 and reads its configured library and save. Closing the suite window leaves background services available for ongoing jobs and the next launch. Quit in Workbench and Restart game retain their usual behavior.

The suite uses a dedicated WebView2 profile under %LOCALAPPDATA%\NovelAI Media Suite. Browser-only preferences such as the last selected girl can need setting once. Media, queue data, rankings and game saves are read by their original applications. Windows needs the x64 Microsoft Edge WebView2 Runtime. The three existing programs still use their own prerequisites.

## Development

Use .NET SDK 8, Python with Pillow, and the Windows WebView2 Runtime. Run `python media-suite/make-icon.py`, then `dotnet build media-suite/MediaSuite.csproj -c Release` and `python media-suite/package.py`. The service tests run with `dotnet run --project media-suite/tests/core/CoreChecks.csproj -c Release`.

The Windows workflow builds a disposable collection and game save, drives all four actual WebView2 pages, applies a Workbench import during a tab switch and checks the persisted result. A suite release publishes the verified Windows ZIP, a hash-checking downloader and its manifest. Increment the suite project version for a changed public binary. Existing application release manifests are managed by their respective publishers. See [main thread handoff](MAIN-CODEX.md).
