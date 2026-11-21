# After Hours — Club, Studio & Resort

A complete local main-game build for the Media Library companion. Choose two
founders, grow the club, collect cards, schedule Studio projects and manage
multi-night Resort stays on one calendar. The current local build is **1.4.1**.

## Play on this Windows computer

1. Open **After Hours** in Media Suite. In the local development workspace,
   double-click **`C:\Codex\After-Hours-Codex\PLAY-AFTER-HOURS.bat`**.
2. Leave the launcher window open. The browser opens
   **http://127.0.0.1:8877/game/**, accessible only on this computer.
3. Choose your own two founders when starting a new save. Later launches load
   your existing game; verification uses separate QA saves.
4. Close the launcher with Ctrl+C when finished. Reopen it to resume.
   An unfinished night keeps its speed and running or paused state. Time spent
   with the server shut down does not advance the night.

To apply local code updates, click **Restart game** at the top right. It makes
a backup, restarts the local server and reconnects the page automatically.
Keep the launcher window open. If the game was already running before this
button was added, close and reopen the launcher once to enable it. The button
loads code already updated on this computer; it does not download updates.

The ignored `game/local.json` is configured for the supplied library folder
and working Python runtime on this computer. The launcher checks that
configuration, Python on PATH, then the bundled Codex runtime. Python 3.10+
is required. The game needs only the standard library; Node, npm, Pillow,
an AI model and a story file are not required to play. Pillow is used only
by optional media-verification tools/tests.

`Start-Demo.bat` uses a separate synthetic catalog with placeholder portraits.
`Start-With-Library.bat` accepts the same options as the main launcher:

- `-Library "C:\path\to\Media Library"` selects another folder or library.json.
- `-Port 8878` selects another local port if 8877 is in use.
- `-NoBrowser` leaves browser opening to you.
- `-Check` checks Python and SQLite without opening a save.
- `-Save "C:\path\new.sqlite3"` selects a separate save file.

The launcher runs the restored companion's **game-only** entry before its
normal library store or updater initializes. It reads metadata, rankings,
thumbnails and originals, and writes separate game data. The source companion
also exposes `/game/` and an Open After Hours button. The installed production
companion was not replaced or updated.

## The operating loop

- **Prepare:** choose prices, assignments, rest/training and equipment. Save
  up to twelve named plans. Auto assign respects reservations and tired
  workers. Every employed person receives $30/night, including at rest.
- **Watch the night.** Three minutes pass at 1×. The next night opens at your
  saved speed, up to 8×. Each private room runs its own bookings with different
  durations. Select a room to see the ordered stages, the current action and
  earned photos or videos. Offers from every room still reach you.
- **Answer offers.** Two venue events and up to four client offers arrive at
  varied times. An offer pauses the clock. Choosing an option resumes your
  selected speed. Finish night uses the free defaults for unanswered offers.
  A client can buy an activity, a specific finish, extra time or a repeat round.
  A finish follows the last actual activity and the client’s paid permissions.
- **Group bookings.** A client can pay $95 to hire a second available worker.
  This spends 8 energy from the original worker and 10 from the partner. A
  resting worker or available lounge host can join through cleanup. Alternatively,
  another client can pay $75 to join for 10 worker energy. Each guest has a
  separate first round, wallet and paid extras. Both offers are rare. The join
  fits inside the existing booking. The timeline names the participants.
- **Collect and grow:** settle once, open earned/purchased packs, equip cards,
  use extra copies for mastery, optionally recruit and expand. A first pull
  waives that person's hiring fee; it never starts payroll automatically.
- **Studio:** available from night 4 after 18 club bookings. Opening costs
  $650 plus $14 upkeep per position. One-, two- and three-night projects have
  deposits, delivery risk and money rewards. Longer successful projects award
  Standard vouchers and sometimes an extra card marked as a Studio award.
- **Resort:** available after two Studio deliveries. Opening costs $1,250 plus
  $24 upkeep per suite. Two-, three- and four-night packages reserve a host,
  earn nightly revenue and track satisfaction for checkout bonuses.

During preparation, the Club shows what you still need to open the next
department. Before you pay an opening fee or reservation deposit, you can see
what you'll have left after the next night's wages and upkeep. Each contract
quote shows when you get paid. At checkout, the morning report includes the
guest's satisfaction and the bonus paid. A Studio delivery that earns a card
lets you open it from the receipt.

One person cannot occupy two departments on the same date. Projects, stays
and club work advance together with shared money, energy and career skills.
Reservations override a retained club plan. Cancellation frees the dates;
the deposit is not refunded. Equipment is locked for each shift. Starting
strengths and training focus are configurable game rules, not personal traits
inferred from photographs.

Club expansion supports six private rooms and three lounge positions, plus
reception and recovery improvements. Studio and Resort each support six
positions. The roster has no twenty-person cap; larger teams can rotate
through work, rest and training. Keep a payroll reserve when buying capacity
or paying deposits. If the next night is unaffordable, a recovery break
restores an operating reserve and energy, shifts reservations by two dates,
and retains your collection and facilities. There is no mandatory reset.

## Cards and source preservation

Packs contain five cards: Standard $100, Spotlight $200, Themed $200, Premium
$400 and Collector $600. Premium guarantees an Epic/Legendary when eligible;
Collector guarantees an unowned card while one remains. Impossible guarantees
are disabled. Earned vouchers open a Standard pack without spending cash.

Each Set marked ready in Media Library adds one evolution card to packs.
New evolutions take the highest After Hours rarity among their selected Main
photos. A selection composed entirely of Set-only photos enters as Rare.
Existing career rarities stay fixed.
Choose **Saves & catalog → Refresh catalog read-only** after preparing a Set.
The first pull reveals Form 1. Three-form cards unlock at mastery 0, 2 and 5.
Four-form cards unlock at 0, 1, 3 and 5. Equipped work earns XP and spending
an extra copy of that evolution card gives 30 XP. In **Collection → View**,
select any earned form to revisit its framed photo or open the original.
The album lists the cards collected in this career. An ordinary captain
or other eligible Main photo has its own ownership and mastery.

An acquired card keeps its original form order. New careers and cards that
have yet to drop use the latest ready order. Withdrawing a Set or removing
a chosen photo from the ready selection preserves the career record and
hides the withdrawn artwork on refresh. Set-only photos stay in their Set.

A Set can also have a **Duo** with two chosen photos. Refresh the catalog,
then pull the Duo from a pack to reveal its front. Choose **Flip to back**
in the pack opening or your collection to see the second photo immediately.
Flipping also chooses the side displayed in the album and while equipped.
Both sides share one card, specialty, copy count and mastery. Each new pack
copy opens front-first. The Duo inherits its highest eligible Main photo's
After Hours rarity in that career. A pair of Set-only photos enters as Common.

Ordinary slots choose a character uniformly, then weight their available
rarities 55/27/12/5/1. Missing tiers are removed and weights renormalized.
Spotlight/category and guarantee pools restrict eligibility first. Gallery
size alone does not dominate character odds. Multiple image cards of one
character share that character's energy and career.

The confidence-aware library ranking snapshot sets initial ordinary-card rarity. Unplaced
cards remain Common. Existing rarity and specialty are frozen as votes or
metadata change; newly eligible cards enter after refresh/restart. Main-library
images qualify for ordinary cards. Ready evolution Sets can also use selected
Set-only stills. Both pools exclude videos, review, purgatory and removal-flagged
media. Missing sources retain ownership and progress with an unavailable-art
message. Refresh never starts payroll or resets the business.

Cards use the existing production renderer, fonts, artwork and saved Fit/Fill
positioning. Approved artwork has a **7:10 outer frame and 3:4 photo aperture**;
it is preserved rather than stretched. Card and activity photos request
originals. Backend image routes enforce game ownership. The Media Library's
independent viewing and ownership rules remain separate.

## Video rewards, wardrobe and vouchers

Owning any collectible photo in the same Set unlocks that Set’s eligible
clips for the character. Both faces of an owned Duo and each earned Evolution
form qualify. Open **Collection → Earned videos** to play a clip or choose it
from **Booking media** in the room. Playback uses the same fixed portrait frame.
For clips without a collectible Set match, open **Saves & catalog → Edit video
pairings**, choose a clip and a photo of the same character, then save. Pairings
are stored beside the local career files and apply to careers using that Library.

Open Patricia’s **Wardrobe** from her room or her team card. All 19 outfits
show their names and goals while locked. Guaranteed career unlocks run from
level 20 through 56, every two levels. Five outfits have earlier routes using
a matching photo and career progress. The pastel floral bikini has front,
side and back artwork. Click her illustrated model to turn through its views.
Earned outfits stay in that career and can be switched for free.

Morning results list each pack voucher and its source. Use **Open pack shop**
to redeem one for five Standard cards. The shop and Night reports both retain
voucher history for the latest 40 nights.

Under **Saves & catalog**, import solo stage labels in **Stage labels**, and
event or group-stage variations in **Event and group wording**. The separate
offline writing handoff describes both formats.

## Saves, backups and recovery

Default new saves are in **`illustrated-game\game\data`**, with distinct hashed filenames
for demo and real libraries. `AFTER_HOURS_DATA` or `-Save` can override this.
Old `%LOCALAPPDATA%\NovelAIMediaGamePrototype` saves are not opened automatically.
QA files are isolated under ignored `game/test-data`. Back up the whole
`game/data` directory periodically.

Each action uses SQLite transactions, a request ID and a revision check.
Purchases, inventory and pending reveals commit together; reloading cannot
reroll a paid pack. Settlement applies once. Conflicting windows refresh
instead of charging twice. If another tab restores a different save, reload
older tabs before using them again.

**Saves & catalog → Start new career** begins again with two founders, $600
and night 1. Confirming backs up the current career, opens a separate save and
returns to founder selection. **Restore previous career** is available on that
screen. The **Previous career** backup also stays in Saves & catalog after
beginning the new club, alongside its twelve rotating backups.

**Saves & catalog** provides JSON export/import, an explicit backup button,
the twelve latest rotating backups and read-only catalog refresh. A latest
`.sqlite3.backup` is also maintained. **Restore creates a new sibling save**
and retains the previous file. An `.active.json` pointer selects that restored
file on the next launch. Keep the pointer and database together. Larger exports
download as compressed `.json.gz` files and can be restored directly. Restore
requires the same source identity and rebinds source paths to the selected
library. Imported paths are never served directly.

Schema-1 prototype saves migrate to schema 2 without discarding cards, money,
career progress or pending reveals. Opening an old SQLite save creates a
`.before-schema-2` snapshot; use a *copy* with `-Save` when migrating an existing
campaign. Prototype JSON exports can be restored in the UI. Unsupported
future or malformed saves are rejected. Full business history is exported;
reports show the latest 40 nights. Deposits and capital purchases are recorded
separately from nightly recurring profit.

## Verification — Windows, 9 November 2026

- Latest dropdown/event update: nine focused Python checks and four browser
  control cases passed. The in-app browser held the native speed menu open
  for over 17 seconds while the server clock advanced, then selected 8×.
  Full renderer, balance and release suites were not rerun for this update.
- Previous full run: 54 game rule, persistence, companion HTTP, restart and recovery checks;
  two JavaScript background-tab regression cases; 12 existing runtime card
  checks; 13 release-pipeline checks. Pipeline tests use temporary local
  repositories only. No release was published.
- Latest controls check: three restarts through the actual demo launcher in
  the in-app browser preserved running, manually paused and event-paused
  nights at 8×. Both choices stopped at their exact scheduled times and
  continued automatically after selection through settlement. The regular
  companion launcher also passed restart/reconnect against a synthetic
  library, with unchanged source hashes. `screenshots/speed-restart-demo.jpg`
  shows the controls using demo placeholders.
- Native production renderer: 364 renders covering 13 frames, seven ranks,
  transparency and bounds; saved Fit/Fill geometry checks pass.
- Actual library: four eligible characters and 270 cards, with galleries of
  2/19/33/216 images. All originals fully decoded. Before/after hashes of both
  metadata files and all eligible originals match.
- Actual Windows `.bat` launch and browser walkthrough: founders, timed choice,
  settlement, interrupted reveal/reload, equip, optional hire, expansion,
  retained plan, Studio projects, shared Club/Studio/Resort operation, checkout,
  mid-night restart, backup restore and relaunch into the restored file.
- Real cards loaded originals; an actual saved 1.07 zoom matched its source
  framing. Desktop and 390-pixel layouts, mobile voucher reveal, missing-source
  placeholders and optional catalog arrivals were checked in the Windows
  in-app browser. Missing/addition cases used disposable fixtures.
- Approved assets/modules: 143 source-manifest entries checked. 77 match exact
  bytes; 66 text files differ only by Windows checkout newlines. No approved
  artwork or renderer source was edited.

`full-balance-report.json` records **10,884 modeled nights**: six seeds across
four/five/twelve/twenty-character policies, continued-collecting policies and
the actual eligible catalog. The two-founder opening averages $94 net
(median $116), against a $100 Standard pack. All campaigns reached Resort.
Real-catalog collecting runs reached it on days 15–23, opened about 194 packs
over 120 nights and retained $645–$1,277. Buying packs competes with expansion;
players who stop spending can accumulate substantial cash. These are explicit
automated strategies, not guaranteed payouts or human playtesting.

`performance-report.json` records Windows server timings: about 242 ms for a
pack transaction with 50,000 catalog cards. A save with 10,001 owned cards and
20,001 history events restored in about 510 ms and reloaded in 171 ms with
ownership intact. These are server measurements, not browser frame rates.
Large metadata catalogs load in full; collection pages show 24 at a time.
Other operating systems and the installed production GUI were not visually
tested in that November 9 pass. See `PROGRESS.md` for the current Windows
walkthrough and video checks. Story generation, narrative relationships
and automatic clothing detection remain deferred.

## Developer commands

Run from `project` with a working Python 3.10+ executable:

```text
python -m unittest discover -s tests -p "test_game*.py"
python -m unittest discover -s tests -p "test_runtime_card*.py"
python -m unittest discover -s tests -p "test_release_pipeline.py"
node --check game/web/app.js
node --check game/web/management-ui.js
node --check game/web/renderer.js
node tests/test_game_browser_controls.cjs
python -m game.simulate_full --seeds 6 --nights 120
python -m game.benchmark
python -m game.server --open
```

On this host, use the Python path in ignored `game/local.json`. Set TEMP/TMP
to a writable test folder. Release fixtures need byte-stable Git checkouts
(`core.autocrlf=false` scoped to that test process). Optional
`game.verify_library` requires Pillow and accepts `--library`, `--output` and
`--compare`; keep its per-file hash reports private and untracked.

Source lives on local `game-complete-local-20261120`. The handoff bundle and plan remain
intact. Narrative state has a separate versioned namespace for a future
optional interface; no writing service or story upload is part of this build.
