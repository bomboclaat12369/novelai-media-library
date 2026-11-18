# Illustrated venue — preview and release

18 November 2026. Based on After Hours 1.2.4 at `001f7de`, with the approved
Character Game lounge as the visual reference. Walker authorized publication
of the illustrated layout, profile toggle, fixed photo frame and floating
events as 1.3.0. It is published and verified: both public feed routes and
downloaded assets match the tested build. Evidence is in `PROGRESS.md`.

Open `C:\Codex\After-Hours-Codex\OPEN-ILLUSTRATED-PREVIEW.bat`.
It reads the existing Media Library and keeps a separate review career under
`game/test-data/illustrated-preview/`. The first launch selects Patricia and
Alice, buys the second private room using the usual $350 upgrade, and assigns
both to private rooms. The lounge remains available; the review starts with
$250. Later launches retain only that review career. The installed game and
its saves are not selected or changed. Reopening the launcher reuses its own
running preview when available.

The preview now uses `http://127.0.0.1:62412/game/` on new starts so its link
remains stable. If the page says it cannot be reached, open the preview
launcher above to start its local server, then refresh the page.

The Club view has approved full-body illustrations, simultaneous cutaway
rooms in a left rail, a portrait-proportioned earned-photo viewer, an enlarge
control, and full-width horizontal booking history with the current stage
highlighted. The fixed 4:5 photo area contains each original without stretching
or cropping; changing image shapes does not change the layout. Events float
over the room column on desktop and above the page on narrow screens, without
pushing the venue down. Choices retain the existing automatic continuation.
The large figure
has an open background. Clicking Patricia or Alice switches between the
approved front and side views; click again to return. Keyboard Enter/Space
also works. Each character's view is retained while switching rooms and
through clock repaints in that tab; reloading starts with front views.
Planning, saved
plans and the venue log expand below. Club navigation moves across the top
to preserve room for the artwork and media. Other sections retain their
existing layout and card renderer. Booking timing, events, equipment,
ownership and save rules are unchanged. Events are venue-wide regardless of
the room being viewed. Clock repaints retain the decoded photo and the
tracker's reading position.

Only Patricia and Alice currently have approved figure art. Other identities
keep their owned photo viewer and show a clearly labeled illustration
placeholder. Mapping uses exact Library IDs, never display-name guesses.
Appearance metadata is independent of career state, leaving room for later
approved outfits. No wardrobe, walking animation or new character art is
claimed.

Future feature requested by Walker on 17 November 2026: character outfits
should be unlockable through gameplay. Retain this as deferred work. The
outfits, unlock requirements, costs, selection interface and any gameplay
effects remain undecided; no wardrobe implementation is requested yet.

Videos remain deferred. The main media area is reserved for photo/video
presentation, but this change does not add playback, unlock rules, rewards,
or video cards. The existing original-photo endpoints continue enforcing
owned cards and earned Evolution forms / Duo sides.

Walker explicitly excluded the three suggested extras from this update:
remembering the view across restarts, clicking the whole photo to enlarge,
and a Jump to current history control. Existing Enlarge and tab-local profile
choices remain. Unlockable outfits stay deferred.

## Artwork provenance

Native PNG copies match the approved reference bytes:

- Patricia front: `50c0b49d449e30f1fa2e7be04d4c2122a6c2508aefe4d44a0e94e419c3f3eaab`
- Patricia side: `fbe655474056afd848a6f42b8e76c4c7461260f5188a669011ffd907799467a8`
- Alice front: `bfe2134dddd3387f0dd09c6af7ce6073e7a2fb9533ed0b94956e09a36fdf67df`
- Alice side: `ac192c10d12046640e21bf22c3dbcf9f8135e7db77dfb611d56a128a8e35f558`

Authoritative approval inventory:
`C:/Codex/Media-Suite/assets/cards/concepts/approved-character-finals-2026-11-16/presentation-record.json`.
Room scenery is code-drawn presentation adapted from the reviewed lounge.
Full images fit without cropping or distortion. Approximate working heights
remain presentation hints, not anatomical measurements.

## Focused verification

`tests/test_game_illustrated_venue.cjs` exercises the actual browser against
`tests/serve_illustrated_fixture.py` with disposable data. It checks real room
capacity, two concurrent assignments, stable identity mapping, current/past
stage display, selection without career mutation, original-photo enlargement,
card inspection, decoded-image retention, ownership denial, missing art,
empty rooms, desktop/narrow layout and a real clock-driven event resolving
while another room is selected. Screenshots use labeled neutral photo fixtures.

The existing browser-control checks and HTTP/ownership/save integration
checks also run. No unrelated economy simulation or release build is needed.
Results and screenshots are retained under `.release-output/illustrated-venue/`.
The initial integration passed 23 focused browser assertions, five existing
browser-control cases and seven existing HTTP/save integration tests.
The portrait-layout/profile follow-up passed 36 focused browser assertions,
covering both approved side views, keyboard/focus retention, independent view
choices, no career mutations, natural portrait/landscape proportions and
horizontal history. Layout checks cover 1600-, 1280-, 760- and 390-pixel widths.
At smaller heights, scroll down for the history; narrow screens retain the
two portraits together and put rooms in a horizontally scrollable row.
Only the focused illustrated-venue suite and syntax/diff checks were rerun
for this presentation change; no balance simulations or release build.

The 18 November fixed-frame and floating-event update passed 41 focused
browser assertions. Portrait/landscape swaps keep the frame, character, rooms
and tracker in the same positions; showing an event adds no layout space;
desktop events stay over the rooms, phone choices fit the viewport, and the
overlay clears when a choice resumes operations. Release packaging and
Windows adapter checks are recorded separately from the earlier local review.

The actual read-only Library check found four eligible identities and 374
cards. Both review founders' original photographs decoded (682 × 800 and
2560 × 1920); an unowned photo still returned 403. The Library and Battles JSON
hashes were identical before and after that check. The preview launcher
successfully reused its own server without starting another career.

The ordinary restricted test environment denied localhost connections; the
same scoped checks run with approved local access. No reference art or
requested feature was substituted because of that environment restriction.
