# After Hours — playable prototype 0.1.0

A local prototype of the club, staffing and collectible-card loop for NovelAI Media Library. This is an isolated prototype, not a published Media Library update. The working title, presentation and balance are provisional.

## Try it on Windows

1. Extract the whole ZIP; keep the folder named `game` intact.
2. Open `game` and double-click **Start-Demo.bat**. It needs an installed Python 3.10 or newer; Python 3.12 was tested here. No third-party Python packages are needed.
3. Choose two founders and open the club. Use Pause, 1×/2×/4× or Finish night. A normal night lasts five simulated minutes.
4. Spend earnings in the Pack shop. Tap cards individually or reveal all five. Recruitment and Expansion give new hires working positions.
5. Leave the launcher window open while playing. Close it to stop. Reopen the same launcher to resume; an unfinished night resumes paused.

To try existing images, **Start-With-Library.bat** asks for the companion's `library.json`. It reads that file, `battles.json`, existing thumbnails and originals. It does not edit them. This is optional and has been tested with synthetic library fixtures, not Walker's actual collection. The launcher uses Python's standard Tk file picker; the Windows launcher itself has not been run on Windows in this workspace.

The default address is `http://127.0.0.1:8877/`. It listens only on this computer. If that port is already occupied, run `python game/server.py --port 8878 --open` from the extracted parent folder. For a selected library, add `--library "C:\path\to\library-folder"`.

## What works

- Two founders, shared character energy/career progress, one equipped card per person, and $600 starting cash.
- Planning, prices, room/lounge assignments, rest, training, automatic assignment and six service rounds per night.
- Hiring directly with a starter card; pulling a girl's first card waives her hiring fee. Accepting recruitment starts her nightly wages.
- Private rooms and lounge growth up to nine simultaneous positions, recovery facilities and reception. The roster can grow beyond those positions to support rest and training.
- Standard ($100), Girl spotlight ($200), Themed ($200), Premium ($400) and Collector ($600) packs, each containing five cards.
- Premium guarantees an Epic or Legendary; Collector guarantees an unowned card while one remains. Offers are disabled when their guarantee cannot be met.
- Cards revealed individually or together; owned/missing, girl and rarity filters; text search includes categories and specialties; equipment and duplicate mastery.
- Nightly reports, disk saves, automatic SQLite backups, full save/history export, and recovery from interrupted reveals.
- A read-only library adapter with separate game ownership. Eligible main-library images remain in the catalog even when unranked. Review, purgatory, videos, set-only images and removal-flagged images are excluded.

The demo contains 20 names and 576 abstract placeholder cards: 120 each for Nikki, Mikayla, Alice and Genesis, and six each for 16 guest placeholders. These are sample game records, not copied media, and game specialties are assigned by deterministic game rules rather than inferred from a person or photograph.

## Images, rarity and pack odds

Every card points to one image and one character. Owning several images of a character does not create multiple staff members. Energy and career progress stay with the character; copies, usage and mastery stay with the card.

Mixed standard slots choose uniformly among girls in the eligible pool, then use relative rarity weights 55 / 27 / 12 / 5 / 1 among that girl's existing tiers. Missing tiers are removed and weights renormalized. Consequently those weights are not universal displayed drop percentages. Themed and spotlight pools restrict eligibility; guaranteed slots choose from their qualifying pool. A girl with six images is not overwhelmed by a girl with 120.

Initial library rarity uses per-girl ranked-image percentiles, with a minimum of five voted images and distinct ratings before allocating higher tiers. Unranked images begin as Common. The snapshot remains stable when later votes change; newly eligible images are added on server restart. Removed images retain owned-card records and progress, with unavailable artwork. This first adapter uses raw ratings with `played > 0`, not the library's complete placement-confidence policy. Rarity reassessment and migration rules still need final design.

Existing thumbnails are used where available, otherwise originals are loaded on demand. View active card / View opens the original. Existing special-edition frames and saved positioning have not yet been connected: the prototype uses temporary 3:4 layouts with fit rather than changing approved artwork.

## Saves and recovery

Game saves are independent of Media Library data:

- Windows: `%LOCALAPPDATA%\NovelAIMediaGamePrototype\`.
- Other systems: `$XDG_DATA_HOME/NovelAIMediaGamePrototype/`, or `~/.local/share/NovelAIMediaGamePrototype/`.
- Each source catalog has its own hashed `.sqlite3` filename. Demo progress and library-backed progress are separate. The catalog's stable library identity keeps the save associated with it when available.

Purchases commit money, cards and reveal results in one SQLite transaction before any reveal. Request IDs and revision checks protect retries and concurrent windows. Restarting pauses an unfinished night. Meaningful game events are retained; the reports screen shows the latest 40 nights.

A `.sqlite3.backup` is refreshed after major purchases and night settlement. To recover it, close the launcher, preserve the entire save directory, and copy the backup to a **new** filename ending `.sqlite3`; launch with `--save "full-path-to-the-new-file.sqlite3"` and the same library selection if applicable. This avoids overwriting a live database or reusing its WAL files. Export produces JSON with inventory, catalog metadata and history; a JSON import interface is not implemented yet.

This is a prototype save schema. Future schema migrations and restore UI must be tested before production integration. No compulsory restart or prestige system is planned.

## Verification on 2026-11-09

- 17 automated game checks pass: clock consistency across speeds, paused time, energy sharing, capacity, recruitment, guarantees, unequal image counts, duplicate handling, recovery, transaction rollback, retries, concurrent windows, restart, catalog changes, source-file integrity and HTTP boundaries.
- 13 existing release-pipeline checks pass. No release request or production files were changed.
- Browser walkthrough passed: choose founders → start/speed/pause/finish night → open a pack → reveal one card → reload during reveal → finish opening → filter collection → equip → recruit with fee waived → upgrade → auto-assign → inspect active card → report and export.
- Browser checking used demo placeholders at the available desktop viewport. Windows, mobile layout, real-library image decoding and production card rendering remain unverified.
- JavaScript syntax validation passed.

Seeded simulations used the same rules as the playable prototype: 40 seeds × 120 nights × five staffing scenarios, plus 40 growing campaigns (28,800 modeled nights total). Mean net nightly income after the first 14 nights:

| Scenario | Working positions | Mean net per night |
| --- | ---: | ---: |
| Opening two-person club | 2 | $107.98 |
| Established four-person club | 4 | $290.00 |
| Expanded eight-person roster | 9 | $488.18 |
| Expanded twelve-person roster | 9 | $687.80 |
| Only two people in the expanded club | 9 | $63.48 |

These are synthetic scenario results with specific facilities and an automatic staffing policy, not guaranteed payouts. Rest rotations matter; additional payroll is useful when staffing matches capacity. The sample growth policy bought a pack every other night, expanded first on days 4–9, and reached 12 staff in every 120-night run without using recovery grants. It accumulated excess late-game money because it kept buying only inexpensive packs: long-term sinks and further departments are still needed.

Across 40,000 standard card draws, each of 20 girls received 4.73%–5.34% of draws despite the 120-versus-six image imbalance. Full outputs are in `balance-report.json`.

Synthetic server benchmarks with a small owned inventory:

| Catalog size | Initial catalog/save open | Catalog JSON encoding | Mean pack transaction |
| --- | ---: | ---: | ---: |
| 10,000 cards | 28 ms | 23 ms | 12 ms |
| 50,000 cards | 154 ms | 154 ms | 50 ms |

These are Linux workspace timings, not a Windows or browser frame-rate measurement. The 50,000-card metadata response is approximately 11.7 MB; it loads once and the collection renders 24 cards at a time. Very large owned inventories and long histories still need endurance profiling. See `performance-report.json`.

## Next development milestone

Try several nights and pack openings, then use that feedback to tune pacing. Next implementation work should connect the approved card renderer/positioning and companion launch route, validate real-library data and Windows saves, and add meaningful night events plus long-term club goals. The integrated resort and studio remain planned later departments sharing this roster, money and calendar. Night events, persistent customer relationships, distinct staff personalities and the long-term goals are not implemented in this first loop. Booking quality and repeat-business specialties currently share a small acceptance bonus; their distinct systems need development. Evolution and set-linked evolution remain deferred. Automatic clothing-color detection and browser-access troubleshooting remain paused.

## Developer commands

Run from the repository or extracted parent directory:

```sh
python3 -m unittest discover -s tests -p test_game_prototype.py -v
node --check game/web/app.js
python3 -m game.simulate --seeds 40 --nights 120
python3 -m game.benchmark
python3 -m game.server --open
```

The simulation is pure rules code, shared by the server. Generated reports contain no source photographs. `--preview` is for isolated managed demo QA only and cannot be combined with a real library.
