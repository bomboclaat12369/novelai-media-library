# Main Media Suite Codex thread

This local checkout is for Media Suite, Media Library, Battles, card artwork and framing, and Media Workbench including the folder organizer, import and duplicate review. Walker uses a separate Codex thread and checkout for After Hours gameplay, balancing, writing packs and saves. Both checkouts use the same GitHub repository. The suite connects to the installed game launcher.

Read the root AGENTS.md, docs/PROJECT-MAP.md and the relevant component sources before editing. For releases, read tools/PUBLISHING.md and the suite README. Begin with git status and git fetch origin. Work from current main for suite and library releases, preserving local work. Run and publish requested updates under the repository's standing authorization.

The Windows installer records the main checkout path in %LOCALAPPDATA%\NovelAI Media Suite\main-workspace.txt. The suite's Locations dialog connects the existing companion, original library folder, Workbench installation and game folder. Workbench maintains its normal per-user state. The game launcher reads its own local.json and save. Use disposable libraries and game saves for automated tests.

For first-run verification, open Media Suite from its installed shortcut in Chrome. Confirm the active library and existing roster, switch from an organizer post to Battles and After Hours, and return to the same post. A second shortcut launch should select the existing Chrome tab and bring its window forward. Prefer the existing checks for read-only smoke tests on Walker's PC.
