# Faster initial rankings

Runtime 2.7.77, bundled with Workbench 2.0.29, makes the first usable ranked
cards arrive sooner for new and partially ranked collections. It works through
the existing battle modes and requires no import or reset. The normal standalone
interface stays at 2.9.27.

## Match selection

Previously, initial comparisons spread across the entire collection before
finishing many placements. The new scheduler keeps a connected starter group
of up to 12 entries, normally four favorites and eight other images. Already
completed and partially completed placements take priority over fresh entries.
It stays in starter calibration until eight eligible entries are placed, or
the eligible collection is smaller.

After calibration, it finishes batches of four unfinished entries using placed
opponents. Opponent selection still favors useful rating proximity, confidence
and distinct opponents. Difficult entries rotate out after six additional
comparisons so they cannot hold up untouched entries. Skip moves past the
current candidates; focused comparisons, category filters, removal flags,
set-size restrictions, refine modes and winner-stays behavior retain their
existing rules.

There is no fixed promise of placement after three battles. Placement still
requires at least three real comparisons, three distinct opponents and rating
deviation at most 220. Established status retains its higher requirements.
Normal tiers still need five placed entries and a meaningful rating spread.

## Favorite starting evidence

On the first battle action observing an image, an eligible favorite starts at
1360 instead of 1200, with the same uncertainty of 350. This is a weak starting
preference, not a win, a confidence boost or a guaranteed rank. Non-favorites
stay at 1200. Actual results can overturn the preference; ties and wins against
favorites naturally affect other images through the joint history fit.

Existing images can receive the hint only while unrated/provisional, with at
most four comparisons and an original neutral 1200/350 prior. Developed rankings
and nonneutral legacy priors are protected. Every observed image's initial
favorite choice is frozen, including non-favorites; later toggles cannot stack
or repeatedly reapply the hint. Newly imported images are observed on a later
battle action. Favorite images do not seed set rankings.

`battles.json` stores a versioned per-image observation and typed
`starting_preferences` history event containing before/after priors. These are
included in the existing battle checkpoints. Real vote history remains intact;
Undo reverses actual votes and refits from the same starting evidence. History
priors can be reconstructed from recorded preference events. Forecasts remain
read-only. Scheduler version 2 replaces only derived scheduling state.

## Validation and benchmark limits

`tests/test_runtime_fast_placement.py` covers one-time seeding, ties, incorrect
favorites, legacy protection, existing-history upgrades, Undo/reload, read-only
forecasts, starter selection, actual placement requirements, starvation
prevention, filters and image/set isolation.

The repeatable benchmark uses both the actual scheduler and full history fit
on every comparison, with synthetic preferences and seeded noisy answers. It
does not access user media. Results are in
[`benchmarks/2026-11-10-fast-ranking-start.json`](benchmarks/2026-11-10-fast-ranking-start.json).

| Synthetic scenario | Previous scheduler | New scheduler |
| --- | ---: | ---: |
| 120 images, helpful favorites: comparisons to five placed | 138 | 17 |
| Same collection: placed after 150 comparisons | 6 | 47 |
| Same collection: comparisons until all 120 placed | 375 | 374 |
| 500 images, helpful favorites: placed after 150 comparisons | 3 | 47 |
| 120 images, no favorites: placed after 150 comparisons | 6 | 48 |
| 120 images, intentionally incorrect favorites: placed after 150 comparisons | 6 | 48 |

These fixtures measure earlier usable ranks, not a universal reduction in total
comparisons or a guarantee about Patricia's collection. At 550 comparisons in
the first fixture, ordering agreement was 98.10% before and 98.19% after. That
metric covers placed pairs with a synthetic true-rating gap above 50; close
neighbors are excluded, and early snapshots contain different subsets.
Reported execution time excludes UI, image loading and disk persistence.

Reproduce the first fixture from a checkout with test dependencies installed:

```sh
OPENBLAS_NUM_THREADS=1 python tools/benchmark-ranking-start.py \
  --baseline-ref 08d45f2a3d9248426afbed018090432d4b4cd5bd \
  --entries 120 --votes 550 --seed 7 --favorites helpful
```

The benchmark report records the exact runtime source SHA-256, seed, favorite
assignment, noise and comparison counts for each run. Windows desktop operation
and the user's real ranking quality require observation on their installation.
