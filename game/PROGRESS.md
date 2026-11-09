# After Hours build checkpoint

## Scope and preservation
Read all 457 lines of the unchanged version-12 plan and every START-HERE file.
Plan SHA-256 matches `0be8aeb7b2a32e8d551bcb9fff4a55e27e79cd57a08c2c946c1e6bc63066c5d2`.
Restored prototype `5c8e396702f09ecb67aac875ed6fd5a1c52682ee` from the verified
incremental bundle against base `8f18c49324c49ea76f301a83b7fcfcbd2661c653`.
Work is on local `game-build-20261109`. No push, release, deploy, or updater.
Original library/media/rankings and existing saves are read-only. QA data lives
under ignored `game/test-data`; new play saves will use `game/data`.

## Local setup, 9 November 2026
- Git 2.56.0, Node 24.22.1, bundled Python 3.12.14 available.
- System Python aliases are unusable; `py` exists without an installed Python.
  Launchers need a tested runtime fallback. npm is absent from PATH; build-tool
  dependencies will be resolved only if actually needed.
- User supplied the companion library location; library.json and battles.json
  read successfully. No personal data copied into tracked files.
- Baseline: all 17 game tests passed in 1.094 seconds on Windows.
- Initial sandbox temp/SQLite and network failures were real. Authorized tests
  with workspace temp data and an elevated loopback-only server succeeded.
- Browser preflight: current prototype founder screen loaded at localhost:8878
  in the in-app browser. This verifies the testing route, not expanded gameplay.
- Existing launch scripts inspected; actual launcher verification pending fixes.

## Current implementation checkpoint
- Shared Studio project and Resort stay reservations now advance within the club
  clock. Deposits, energy/quality, vouchers, occasional extra cards and checkout
  satisfaction are implemented; overlap and capacity are checked for every date.
- Two timed business opportunities, adjustable game strengths, department skills,
  saved plans, milestones and repeat-customer progress are implemented.
- Approved production renderer modules/assets are served unchanged. Saved source
  framing is copied into a read-only cache. Production geometry is 7:10 outside
  with the approved uniform 3:4 photo aperture (not a stretched outer frame).
- Backend artwork access now requires game ownership. Founder/recruit/missing
  catalog artwork is concealed until acquired.
- Schema-1 migration, rotating backups, JSON restore to new sibling saves,
  read-only catalog refresh and persisted multi-process clock are implemented.
- Companion has a /game route and a --game-only entry that avoids LibraryStore
  construction, source migration and the updater. Windows launcher check passes
  through the actual .bat after fixing Windows PowerShell argument quoting.
- Real snapshot: four eligible characters, 270 eligible cards, all original
  paths present; confidence-aware rarity uses the companion's pure methods.
- Fresh Windows browser: founder selection and desktop venue layout checked.
- 19 new integrated rules/recovery checks pass (0.767 s). Original 17 tests pass
  (1.319 s). Native production renderer: 364 renders pass; saved Fit/Fill and
  geometry regression checks pass. Full browser and real-source checks pending.

## Completion checklist
- [ ] Shared Club / Studio / Resort rules, availability, rewards, recovery
- [ ] Business decisions, configurable strengths, retained plans, milestones
- [ ] Approved renderer, original quality and saved positioning
- [ ] Clickable venue and owned-only selected-room imagery
- [ ] Confidence-aware catalog, refresh and retained ownership/rarity
- [ ] Versioned migrations, restore UI, backups, concurrent-window protection
- [ ] Companion route and usable Windows launchers
- [ ] Expanded rule/integration tests, simulations and performance checks
- [ ] Fresh Windows visual whole-loop verification and actual-library checks
- [ ] Updated launch/save instructions and final limitations

Story import/generation and narrative relationships remain deferred. A separate
versioned narrative namespace will preserve future compatibility.
