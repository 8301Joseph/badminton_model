# Hand-entering the lead-up matches

You're copying men's-singles results from the 8 pre-Olympics 2024 tournaments
into `matches_manual.csv`. The pipeline (`build_training_set.py`) now auto-detects
this winner/loser format — no flags to set.

## Columns
`tournament, tier, date, round, winner, loser, score`

- **tournament / tier / date** — copy from `tournaments_2024.csv` (already filled
  with the correct tier and start date for all 8). Use the **tournament start
  date for every match in that tournament** (see "Why one date" below).
- **round** — Final, SF, QF, R16, R32, R64 (be consistent; it's a feature).
- **winner / loser** — player names. **Spelling consistency is everything**
  (see below).
- **score** — optional, e.g. `21-15 21-18`. Not used by the model yet; nice to
  keep for later features.

Delete the two `DELETE_THIS_ROW` example rows before running.

## The one thing that will break your join: names
The winner/loser names must match the names in the SanderP99 ranking files well
enough to link. The pipeline normalizes aggressively (ignores case, accents, and
name order — "Viktor Axelsen", "AXELSEN Viktor", "viktor axelsen" all collapse to
the same key), so you do NOT need to match formatting. But you DO need the same
*spelling/transliteration*. Watch for:
- Transliteration variants (e.g. "Kunlavut Vitidsarn" vs "Vitidsarn Kunlavut" —
  fine, order-independent; but "Kidambi Srikanth" vs "Srikanth Kidambi" — also
  fine; a genuinely different romanization is the risk).
- When you run the build and see a high **"dropped (no ranking)"** count, those
  are names that didn't link. Add a fix to `NAME_OVERRIDES` in the script:
  `"normalized name from your file": "normalized name in the rankings"`.

## Why one date per tournament
Rankings update weekly. Using the tournament's start date for all its matches
makes every match in that event use the **same pre-tournament ranking** — the
"form going in" snapshot, which is what you want as a feature. Using per-day
dates risks a mid-week ranking update sneaking in and is needless extra typing.

## Which matches to include
More is better, but if you're rationing effort, prioritize later rounds (R16
onward) across all 8 events — that's where the Olympic-caliber players actually
meet each other, which is the signal your model needs. Early-round blowouts vs
qualifiers add less.

## Run it
```bash
python build_training_set.py \
    --matches matches_manual.csv \
    --rankings Badminton-Data/out/ \
    --out training_set.csv
```
`tier_ord` is assigned automatically (Super 1000 = 7, Super 750 = 6, Super 500 =
5, Continental = 6). The printed "higher-ranked win rate" is your baseline to beat.
