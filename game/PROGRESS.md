# After Hours — completed local build

## Scope and preservation

Read START-HERE and every listed file, including the complete 457-line plan.
The unchanged plan hash is
`0be8aeb7b2a32e8d551bcb9fff4a55e27e79cd57a08c2c946c1e6bc63066c5d2`.
Restored exact prototype `5c8e396702f09ecb67aac875ed6fd5a1c52682ee` from the
included bundle against base `8f18c49324c49ea76f301a83b7fcfcbd2661c653`.
Local build branch: `game-build-20261109`. First implementation checkpoint:
`e0af556`. The final verification checkpoint follows this record.

No push, publication, deployment, updater, paid service, or installed companion
replacement. Original library/media/rankings and existing user saves were not
modified. The bundle and plan remain intact. All QA saves and per-file media
hashes are in ignored `game/test-data`. `game/data` does not yet exist: the
user's first launch creates a fresh campaign with founder selection.

## Local setup completed first

- Git 2.56.0 and Node 24.22.1 available. System Python Store aliases were
  unusable and `py` had no installed interpreter. Working bundled Python
  3.12.14 is configured in ignored `game/local.json` with the supplied library.
- No packages or system tools installed. Game runtime uses the Python standard
  library. Bundled Pillow and native canvas support were used for QA only.
- Initial sandbox network/temp failures were recorded; authorized loopback
  servers and workspace temporary files provided the testing route. No policy
  rejection was bypassed. Release fixture Git clones needed an authorized run
  and process-scoped `core.autocrlf=false` for byte-stable artifacts.
- Baseline 17 prototype tests passed. Windows in-app-browser preflight passed
  before expanded implementation. Actual Windows launchers and companion
  game-only entry were subsequently exercised.

## Implemented main game

- Chosen two founders, shared character energy/career, optional hiring after
  pulls, moderate card mastery/specialties, equal-character-first pack odds.
- Club rooms/lounge, rest/training, configurable strengths, retained plans,
  recovery/reception improvements and a clickable venue with owned-only photos.
- One five-minute clock with pause/speed controls and two economic choices.
  Browser pauses for new opportunities. Finish night resolves unanswered ones
  without extra rewards or rerolling the prepared simulation.
- Studio projects and multi-night Resort packages: deposits, capacity and
  calendar reservations, energy/quality, delivery risk, vouchers, occasional
  card awards, satisfaction and checkout rewards. Club → Studio → Resort
  unlocks work with the real four-person eligible roster; no large-roster gate.
- Ongoing milestones, repeat business, marketing, training and recovery from
  financial mistakes without a mandatory reset.
- Existing production card modules, fonts/art and saved positioning. Outer
  frame remains 7:10 with its uniform 3:4 photo aperture. Originals are served
  only for game-owned cards; unowned artwork is concealed at the backend too.
- Confidence-aware catalog snapshots, frozen existing rarity/specialty,
  read-only refresh, optional new recruits and retained missing-source cards.
- Schema-1 migration, durable journal, transaction/retry/revision protection,
  persisted clock across stores, rotating backups, JSON recovery into new
  sibling saves, active-save pointer and old-session rejection after restore.
- Companion `/game/` integration and local game-only launcher before source
  store/updater construction. Source GUI includes an Open After Hours button.
- Separate versioned narrative namespace. Story import, generation,
  relationships, videos, evolution and clothing-color detection stay deferred.

## Verification evidence — Windows, 9 November 2026

- **44 game tests:** integrated clock/calendar, cross-department and capacity
  conflicts, equipment lock, decisions, training, retained plans, vouchers,
  odds/guarantees, duplicate mastery, transaction rollback, retries, two stores,
  migration history, malformed exports, restore-to-copy, HTTP media ownership,
  Host/Origin checks, source-path rebinding and stale-session protection.
  Final run: 44 passed in 5.712 seconds.
- **12 runtime card tests:** passed in 6.054 seconds. Windows fixture cleanup
  now collects detached SQLite connections before temporary directory removal;
  no product assertion was removed or weakened.
- **13 release-pipeline tests:** final run passed in 34.867 seconds, including
  the final loyalty-floor fix. Local fixture repositories
  only; no real remote push or release.
- **Production renderer:** 364 native renders passed across 13 frames/seven
  ranks, alpha and bounds; saved Fit/Fill geometry regression passed. JS syntax
  checks passed for all three game scripts. No production renderer code changed.
- **Actual library:** 4 eligible characters, 270 cards, gallery counts
  2/19/33/216. All 270 originals fully decoded with Pillow; none missing.
  Before/after SHA-256 matches for library.json, battles.json and all 270
  originals. Hash detail is private and ignored, not included in tracked reports.
- **Source artwork audit:** 143 manifest entries checked. 77 byte-exact;
  66 text files match after Windows newline normalization; no other mismatch.
  Git shows no approved artwork/renderer edits.
- **Actual browser loop:** founders → pause/speed/decision → settle → paid pack
  → reload after revealing one card → complete reveal → equip → optional hire
  → upgrade → retained plan → Studio single/two-night delivery → Resort unlock
  → simultaneous Club/Studio/Resort → checkout → backup → restore new file.
  Relaunch through the top-level `.bat` selected the restored file correctly.
  A server restart during an active combined night resumed it paused.
- **Actual card presentation:** production frames visibly inspected with real
  originals. DOM geometry is 7:10, image dimensions match originals, and an
  owned card's saved zoom 1.07 appears unchanged in the rendered transform.
- **Additional UI checks:** 1440×960 desktop and 390×844 narrow layouts,
  department forms, voucher reveal, no horizontal document overflow, room
  selection, missing-original placeholders and catalog addition with optional
  recruitment. Missing/addition scenarios used disposable fixtures. Real
  walkthrough and demo console checks had no script errors; the missing-file
  fixture intentionally exercised an HTTP 404 and its visible fallback.
- **Balance:** `full-balance-report.json` contains 10,884 modeled nights, with
  six seeds and 120-night integrated campaigns for 4/5/12/20-character policies,
  continued collecting and the actual catalog. Every campaign reached Resort.
  Two-founder opening mean $94.08, median $116, Standard pack $100. Actual
  catalog collecting: Resort days 15–23, about 194 packs, final $645–$1,277.
- **Growing saves:** Windows server benchmark covers 10k/50k catalogs and a
  10,001-owned-card save with 20,001 history events. Restore ~510 ms; reload
  ~171 ms; ownership preserved. Full timing scope is in `performance-report.json`.

## Completion criteria

- [x] Full shared Club / Studio / Resort loop and small-roster progression
- [x] Business choices, career/training, plans, milestones and recovery
- [x] Approved renderer, original quality and real saved positioning
- [x] Clickable venue and game-owned-only activity imagery
- [x] Catalog additions, missing-source behavior and retained ownership
- [x] Migrations, restore UI, backups and concurrent-window safeguards
- [x] Actual Windows launcher and companion route
- [x] Relevant automated, balance, performance and visual verification
- [x] Fresh real-library whole-loop walkthrough and source preservation
- [x] Updated launch/save instructions and private-data-free demo screenshot

## Delivery and limits

Follow-up, 9 November 2026: successful event choices now resume the night in
the same transaction, retaining its selected speed. The persisted clock resets
at the choice so time spent deciding cannot jump the simulation forward.
Invalid choices remain paused and retries cannot duplicate rewards. Added 24
casual, non-graphic event variants and 56 activity/round descriptions, chosen
without consuming gameplay random draws. Event wording stays fixed through
the night and reload; quiet/tired rounds replace stale activity text.

Follow-up checks: 47 game tests passed in 4.727 s; 13 release-pipeline checks
passed in 29.392 s; JavaScript syntax and diff checks passed. Windows browser
verification accepted the first event at 1:42, then reached the next event at
3:22 without Resume. Declining that event also continued automatically; the
timer reached 4:36 at 4×. Console checks showed no script errors. A new demo
QA save was used, and `screenshots/event-continues-demo.jpg` records the result.

Language follow-up, 9 November 2026: private-room activities and all eight
booking-event variants now refer directly to paid sex, hookups or getting
laid, without describing sexual acts. The eight successful room-activity
variants use the same tone, and the activity label is now `Paid sex`.
Economics, energy costs, deterministic variation and automatic continuation
are unchanged. The user approved this non-graphic wording and a source push
to the existing isolated build branch; the Media Library release workflow
does not currently package the game.

Language checks: 47 game tests passed in 4.730 s and 13 release-pipeline tests
passed in 30.189 s. Browser verification showed the new booking text and
activity caption, accepted the booking, and returned to an active night with
a Pause control without pressing Resume. No console warnings or errors were
reported. `screenshots/non-graphic-language-demo.jpg` uses synthetic demo
portraits and a separate QA save. No existing play save or library was edited.

Casual-language follow-up, 9 November 2026: booking and room descriptions now
include the requested words `pussy` and `ass`, plus casual references to sex
using `fuck`. Other activity and break descriptions use matching informal
wording. Each category retains eight distinct variants, and the writing
preference is recorded in `game/AGENTS.md` for future edits. Costs, outcomes,
saved event wording and automatic continuation are unchanged.

Casual-language checks: 47 game tests passed in 5.169 s; 13 release-pipeline
tests passed in 31.610 s; diff checks passed. All event and activity categories
were checked for eight unique variants. No layout or renderer changed, and
this wording-only follow-up did not open a desktop computer-control session
or repeat visual QA. Existing game saves and library media were not edited.

Planning decision, 9 November 2026: Walker prefers generating large message
pools offline and importing the results, with the model shut down during
play. Implementation is deferred until near the final game revisions, when
the scenario inventory is clearer. Walker will write and edit generation
instructions directly; tone and wording remain under his control. The future
integration handles scenario facts, output structure, validation and message
selection. This decision is recorded in `game/AGENTS.md` for ongoing work.
No model was installed or selected, and no generator or importer was built.

Launch `C:\Codex\After-Hours-Codex\PLAY-AFTER-HOURS.bat` or
`project\game\Start-After-Hours.bat`. See `README.md` for play, data locations,
restore and developer commands. `screenshots/after-hours-demo.jpg` contains
only synthetic demo placeholders. QA servers are stopped at final teardown.

Balance simulations are policy comparisons, not human playtesting. Players
who stop spending can accumulate money; continued collecting competes with
expansion. Very large catalogs still load all metadata, although only 24 cards
render per collection page. Benchmark timings do not measure browser FPS.
Other operating systems and the installed production GUI were not visually
tested. No main-game completion criterion remains blocked.
